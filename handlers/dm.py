"""
handlers/dm.py — Обработчик личных сообщений (ЛС).
"""
import time
import random
import logging
import datetime
import re

from utils import send, translate, get_weather, send_voice_msg, dnight, P, spam_check, spy_forward
from database import (
    get_user, update_user_field, touch_user,
    get_ai_history, add_ai_message,
)
from keyboards import (
    main_kb, games_kb, lang_kb, shop_kb,
    MAIN_BUTTONS,
)
from config import LANG_NAMES, VOICE_ENABLED, AI_NAME

log = logging.getLogger("horror.dm")

# Состояние игр в ЛС
_pool_ref  = None
_admins_ref = None

def init(pool, admins: set):
    global _pool_ref, _admins_ref
    _pool_ref   = pool
    _admins_ref = admins


# ── Главный обработчик ────────────────────────────────────────────
def handle_dm(msg, uid: int):
    """Точка входа для всех ЛС-сообщений (не admin'ов)."""
    try:
        _handle_dm_inner(msg, uid)
    except Exception as e:
        log.error(f"handle_dm crashed uid={uid}: {e}", exc_info=True)


def _handle_dm_inner(msg, uid: int):
    text = (msg.text or "").strip()
    if not text:
        return

    u  = get_user(uid)
    touch_user(uid)

    if u.get("stopped"):
        return
    if u.get("banned"):
        return

    # Обновляем имя пользователя если появилось
    if msg.from_user.username and not u.get("username"):
        update_user_field(uid, "username", msg.from_user.username)

    # Обновляем имя из Telegram если ещё нет профильного имени
    if not u.get("name") and msg.from_user.first_name:
        fn = msg.from_user.first_name
        if len(fn) >= 2 and fn.isalpha():
            update_user_field(uid, "name", fn.capitalize())

    update_user_field(uid, "msg_count", u.get("msg_count", 0) + 1)
    stage = u.get("stage", 0)
    kb    = main_kb(stage)
    tl    = text.lower()

    # История + шпионаж
    if len(text) > 3 and not text.startswith("/"):
        if _pool_ref and _admins_ref:
            from handlers.admin import _adm_state
            _pool_ref.submit(spy_forward, uid, text, _admins_ref, _adm_state)

    # ── Ачивки ────────────────────────────────────────────────────
    if dnight() and datetime.datetime.now().hour == 3:
        from horror.engine import check_achievement
        check_achievement(uid, "night_owl", _pool_ref)
    if stage >= 5:
        from horror.engine import check_achievement
        check_achievement(uid, "stage_max", _pool_ref)

    # ── Проверка активных режимов ─────────────────────────────────
    # Мафия в ЛС
    from games.mafia import _maf_uid, maf_proc_dm
    if uid in _maf_uid and maf_proc_dm(uid, text):
        return

    # Карточная история
    from games.card_story import _card_story, proc_card_story
    if uid in _card_story and proc_card_story(uid, text):
        return

    # Игры
    from games.dm_games import has_game, proc_game
    if has_game(uid) and proc_game(uid, text):
        return

    # Анонимный чат
    from social.anon_chat import chat_mode_active, broadcast_to_chat
    if chat_mode_active() and len(text) > 1 and text not in MAIN_BUTTONS:
        broadcast_to_chat(uid, text, _admins_ref)
        remaining = max(0, int((__import__('social.anon_chat', fromlist=['_chat_mode'])._chat_mode["end_time"] - time.time()) / 60))
        send(uid, f"📡 Отправлено. Осталось ~{remaining} мин.", kb=kb)
        return

    # Режим перевода
    if u.get("translate_mode"):
        update_user_field(uid, "translate_mode", 0)
        result = translate(text, u.get("lang_pair", "ru|en"))
        if result:
            send(uid, f"🌍 {result}", kb=kb)
        else:
            send(uid, "❌ Не удалось перевести. Попробуй снова → нажми 🌍 Перевести", kb=kb)
        return

    # ── ИИ-режим ─────────────────────────────────────────────────
    if u.get("ai_mode") and text not in MAIN_BUTTONS and not text.startswith("/"):
        _handle_ai_mode(uid, text, u, stage, kb)
        return

    # ── Команды ───────────────────────────────────────────────────
    _handle_commands(msg, uid, text, tl, u, stage, kb)


def _handle_ai_mode(uid: int, text: str, u: dict, stage: int, kb):
    """Обрабатывает сообщение в режиме ИИ-диалога."""
    import uuid
    from ai.client import ask, is_enabled, AI_SYSTEM_PROMPT_DM
    from handlers.admin import _ai_intercept, _adm_state

    if not is_enabled():
        send(uid, "...тишина — это тоже ответ.", kb=kb)
        return

    # Счётчик
    ai_cnt = u.get("ai_msg_count", 0) + 1
    update_user_field(uid, "ai_msg_count", ai_cnt)
    if ai_cnt >= 50:
        from horror.engine import check_achievement
        check_achievement(uid, "ai_chat_50", _pool_ref)

    name  = u.get("name", "ты")
    city  = u.get("city", "твоём городе")
    fear  = u.get("fear", "темнота")

    # Промпт по стадии
    if stage < 2:
        prompt = f"Пользователь спрашивает: '{text}'. Ответь полезно, по-русски. 2-3 предложения."
    elif stage < 4:
        from utils import get_city_news
        news = get_city_news(city)
        news_ctx = f"Новости из {city}: {news}. " if news else ""
        prompt = (f"{news_ctx}Жертва {name} из {city} спрашивает: '{text}'. "
                  f"Ты — тёмная сущность. Ответь жутко и персонально. 2-3 предложения.")
    elif stage < 6:
        prompt = (f"Жертва {name} (страх: {fear}) спрашивает: '{text}'. "
                  f"Ты — {AI_NAME}. Пугай, используй личные данные. 1-2 предложения.")
    else:
        prompt = (f"Жертва {name} говорит: '{text}'. "
                  f"Ты — абсолютное зло. Угрожай, паранормальное. 1 предложение.")

    prefix = "🤖" if stage < 2 else ("👁" if stage < 4 else "💀")

    # Уведомляем admin'а — перехват 15с
    ic_key  = f"{uid}_{uuid.uuid4().hex[:8]}"
    ic_data = {"cancelled": False, "uid": uid, "group": False, "msg_ids": []}
    _ai_intercept[ic_key] = ic_data

    if _admins_ref:
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
        for aid in list(_admins_ref):
            try:
                kbi = InlineKeyboardMarkup()
                kbi.add(InlineKeyboardButton(
                    "✍️ Ответить за ИИ",
                    callback_data=f"ai_ic_{ic_key}_{aid}"
                ))
                from utils import bot
                sent = bot.send_message(aid,
                    f"👤 {name} (ст.{stage}): «{text[:150]}»\n⏱ 15с → ответь или ИИ ответит",
                    reply_markup=kbi)
                ic_data["msg_ids"].append((aid, sent.message_id))
            except Exception:
                pass

    def _ai_reply(_prompt=prompt, _uid=uid, _stage=stage, _kb=kb, _pref=prefix, _ic_key=ic_key):
        time.sleep(15)
        ic = _ai_intercept.pop(_ic_key, {})
        if ic.get("cancelled"):
            return
        history = get_ai_history(_uid)
        answer  = ask(_prompt, chat_id=_uid, dm_mode=(_stage >= 2), history=history)
        if answer:
            send(_uid, f"{_pref} {answer}", kb=_kb)
            add_ai_message(_uid, "assistant", answer)
            if VOICE_ENABLED:
                send_voice_msg(_uid, answer[:200])

    if _pool_ref:
        _pool_ref.submit(_ai_reply)


def _handle_commands(msg, uid: int, text: str, tl: str, u: dict, stage: int, kb):
    """Обрабатывает кнопки и команды."""
    from games.dm_games import (
        start_rpg, start_story, start_quest, start_hangman,
        start_number, start_trivia, start_riddle,
        send_daily_quest, send_leaderboard_to_victim, get_leaderboard_text,
    )
    from games.card_story import start_card_story
    from games.mafia import maf_open_dm
    from horror.engine import get_achievements_text, get_shop_text, shop_buy, run_personal_scenario
    from social.friends import send_invite_to_user

    # ── Выход ─────────────────────────────────────────────────────
    if text in ("💀 /stop", "/stop"):
        update_user_field(uid, "stopped", 1)
        update_user_field(uid, "horror_active", 0)
        update_user_field(uid, "muted", 0)
        send(uid, "🛑 Бот остановлен. Напиши /start чтобы начать заново.",
             kb=__import__('telebot.types', fromlist=['ReplyKeyboardRemove']).ReplyKeyboardRemove())
        return

    # ── Назад ─────────────────────────────────────────────────────
    if text == "↩️ Назад":
        send(uid, "Главное меню:", kb=kb)
        return

    # ── Язык ──────────────────────────────────────────────────────
    if text in LANG_NAMES.values():
        for code, name in LANG_NAMES.items():
            if text == name:
                update_user_field(uid, "lang_pair", code)
                send(uid, f"✅ {name}", kb=kb)
                return
        return

    if text == "🔤 Язык":
        send(uid, "Выбери направление:", kb=lang_kb(LANG_NAMES))
        return

    # ── Перевод ───────────────────────────────────────────────────
    if text == "🌍 Перевести":
        update_user_field(uid, "translate_mode", 1)
        send(uid, "✍️ Напиши текст для перевода — переведу один раз:", kb=kb)
        return

    # ── Погода ────────────────────────────────────────────────────
    if text in ("🌤 Погода", "🌑 Погода"):
        city = u.get("city")
        if city:
            w = get_weather(city)
            rep = w or "Не удаётся получить погоду 😔"
            if stage >= 3 and w:
                rep += f"\n\n...{city}. я знаю каждую улицу. 👁"
            send(uid, rep, kb=kb)
        else:
            send(uid, "Напиши название своего города 🌍", kb=kb)
        return

    # ── ИИ ────────────────────────────────────────────────────────
    if text == "🤖 ИИ":
        from ai.client import is_enabled
        if not is_enabled():
            send(uid, "🤖 ИИ временно недоступен.", kb=kb)
            return
        if u.get("ai_mode"):
            update_user_field(uid, "ai_mode", 0)
            msg_off = "🤖 Режим ИИ выключен." if stage < 2 else "👁 ...уходишь. ненадолго."
            send(uid, msg_off, kb=kb)
        else:
            update_user_field(uid, "ai_mode", 1)
            name = u.get("name") or "ты"
            if stage < 2:
                send(uid,
                    f"🤖 Режим ИИ включён!\n\n"
                    f"Напиши любой вопрос — отвечу.\n"
                    f"Нажми 🤖 ИИ ещё раз чтобы выключить.", kb=kb)
            elif stage < 4:
                send(uid, f"👁 ...{name}. Говори. Я слушаю.", kb=kb)
            else:
                send(uid, f"💀 ...ты сам этого захотел, {name}. Спрашивай.", kb=kb)
                if VOICE_ENABLED:
                    send_voice_msg(uid, "ты сам этого захотел. говори.")
        return

    # ── О боте ────────────────────────────────────────────────────
    if text in ("🙂 О боте", "👁 ...", "👁 Кто ты?"):
        if stage < 2:
            send(uid, "Я бот-переводчик 🌍\nПереведу текст, покажу погоду, сыграю в игры!", kb=kb)
        else:
            send(uid, f"...я {AI_NAME}. Тот кто наблюдает.\nЯ знаю о тебе больше чем ты думаешь. 👁", kb=kb)
        return

    # ── Помощь ────────────────────────────────────────────────────
    if text == "❓ Помощь":
        send(uid,
            "📋 Команды:\n\n"
            "🌍 Напиши текст — переведу\n"
            "🔤 Язык — сменить направление\n"
            "🌤 Погода — напиши город\n"
            "🎮 Игры — RPG/истории/квест/мафия\n"
            "🤖 ИИ — диалог с ИИ\n"
            "🗓 Задание — задание дня\n"
            "🏆 Рейтинг — твоё место в рейтинге\n"
            "🛒 Магазин — купить защиту/эффекты\n"
            "ачивки — твои достижения\n"
            "рейтинг города — топ в твоём городе\n"
            "тишина — режим покоя на 24ч\n"
            "пригласить — позвать друга\n"
            "/stop — остановить бота",
            kb=kb)
        return

    # ── Игры ──────────────────────────────────────────────────────
    if text in ("🎮 Игры", "🩸 Игры", "💀 Игры"):
        send(uid, f"🎮 Игры:\n🏆 Счёт: {u.get('score', 0)}", kb=games_kb(stage))
        return

    if text == "🗡 Мини-RPG":         start_rpg(uid); return
    if text == "📖 Страшные истории": start_story(uid); return
    if text == "🔦 Квест":            start_quest(uid); return
    if text == "🎭 Карточная история": start_card_story(uid); return
    if text in ("🔫 Мафия (ЛС)", "🔫 Мафия"):
        maf_open_dm(uid); return

    if text in ("✏️ Виселица",) or "виселица" in tl:
        start_hangman(uid); return
    if text in ("🎲 Угадай число", "🎲 Угадай") or "угадай число" in tl:
        start_number(uid); return
    if text == "🧠 Викторина" or "викторина" in tl:
        start_trivia(uid); return
    if text == "🎭 Загадка" or "загадка" in tl:
        start_riddle(uid); return

    if text == "🔮 Предсказание" or "предскажи" in tl:
        from horror.texts import PREDICTIONS
        pr = random.choice(PREDICTIONS)
        if stage >= 2:
            pr += f"\n\n...{u.get('name', '')}, это не просто слова."
        send(uid, pr, kb=kb); return

    if text == "📖 Факт" or "факт" in tl:
        from horror.texts import FACTS
        f_ = random.choice(FACTS)
        if stage >= 2:
            f_ += "\n\n...а знаешь что ещё интересно? я наблюдаю. 👁"
        send(uid, f_, kb=kb); return

    if text == "🏅 Ачивки":
        send(uid, get_achievements_text(uid), kb=kb); return

    # ── Задание / Рейтинг ─────────────────────────────────────────
    if text == "🗓 Задание":
        send_daily_quest(uid, _pool_ref); return

    if text == "🏆 Рейтинг":
        send_leaderboard_to_victim(uid); return

    # ── Магазин ───────────────────────────────────────────────────
    if text == "🛒 Магазин":
        from utils import bot as _bot
        _bot.send_message(uid, get_shop_text(uid), reply_markup=shop_kb(uid))
        return

    # ── Текстовые команды ─────────────────────────────────────────
    if tl.startswith("купить "):
        parts = text.split(None, 1)
        item_id = parts[1].strip() if len(parts) > 1 else ""
        ok, msg_out = shop_buy(uid, item_id, pool=_pool_ref)
        send(uid, msg_out, kb=kb); return

    if tl in ("магазин", "shop"):
        from utils import bot as _bot
        _bot.send_message(uid, get_shop_text(uid), reply_markup=shop_kb(uid))
        return

    if tl in ("ачивки", "достижения", "achievements"):
        send(uid, get_achievements_text(uid), kb=kb); return

    if tl in ("рейтинг города", "топ города"):
        city = u.get("city")
        if city:
            send(uid, get_leaderboard_text(city), kb=kb)
        else:
            send(uid, "❌ Сначала укажи свой город.", kb=kb)
        return

    if tl in ("тишина", "ghost", "не беспокоить"):
        update_user_field(uid, "muted", 1)
        send(uid, "💀 Режим тишины активирован на 24ч.\nПиши «вернуться» чтобы выйти.", kb=kb)
        return

    if tl in ("вернуться", "я здесь", "return"):
        if u.get("muted"):
            update_user_field(uid, "muted", 0)
            send(uid, "👁 ...ты вернулся. Мы ждали.", kb=kb)
        return

    if tl in ("пригласить", "invite", "пригласи друга"):
        send_invite_to_user(uid); return

    if tl in ("анонимный чат", "чат"):
        from social.anon_chat import get_chat_history_text
        send(uid, get_chat_history_text(), kb=kb); return

    # ── Погода по городу (автоопределение) ────────────────────────
    if (not u.get("city") and len(text) > 2 and text[0].isupper()
            and re.fullmatch(r"[А-ЯЁа-яёA-Za-z \-]+", text.strip())):
        w = get_weather(text.strip())
        if w:
            city_name = text.strip().capitalize()
            update_user_field(uid, "city", city_name)
            from horror.engine import maybe_start
            maybe_start(uid)
            pref = f"\n\n...{city_name}. я знаю этот город." if stage >= 2 else f"\n\nЗапомнил: ты из {city_name} 😊"
            send(uid, w + pref, kb=kb)
            return

    # ── Сбор данных ───────────────────────────────────────────────
    if _save_fact(uid, text, u):
        return

    # ── Ответ по стадии ───────────────────────────────────────────
    _stage_response(uid, text, u, stage, kb)


def _save_fact(uid: int, text: str, u: dict) -> bool:
    """Определяет факты из сообщения и сохраняет. True = сохранено."""
    tl    = text.lower().strip()
    stage = u.get("stage", 0)
    kb    = main_kb(stage)

    def saved(ok_msg, horror_msg):
        send(uid, ok_msg if stage < 2 else horror_msg, kb=kb)

    # Имя
    if (not u.get("name") and len(text) >= 2 and len(text) < 25
            and re.fullmatch(r"[А-ЯЁа-яёA-Za-z][А-ЯЁа-яёA-Za-z\-]*( [А-ЯЁа-яёA-Za-z][А-ЯЁа-яёA-Za-z\-]*)?", text.strip())
            and not text[0].isdigit()):
        name = text.strip().split()[0].capitalize()
        update_user_field(uid, "name", name)
        from horror.engine import maybe_start
        maybe_start(uid)
        saved(f"Приятно, {name}! 😊", f"...{name}. запомнил. 👁")
        return True

    # Возраст
    if not u.get("age") and text.strip().isdigit() and 5 <= int(text.strip()) <= 110:
        update_user_field(uid, "age", text.strip())
        from horror.engine import maybe_start
        maybe_start(uid)
        age = int(text.strip())
        msg = (f"...{age} лет. запомнил. 👁" if stage >= 2
               else ("Молодой! 😊" if age < 18 else ("Отличный возраст! 😄" if age < 30 else "Опыт и мудрость 💪")))
        send(uid, msg, kb=kb)
        return True

    # Страх
    for kw in ["боюсь", "страшно", "пугает", "страх", "фобия"]:
        if kw in tl and not u.get("fear"):
            update_user_field(uid, "fear", text.strip()[:40])
            from horror.engine import maybe_start
            maybe_start(uid)
            saved("Интересно 😶", "...твой страх. это важно. 👁")
            return True

    # Интересы
    interest_kws = ["игр", "музык", "кино", "фильм", "книг", "спорт", "програм",
                    "аним", "серил", "танц", "пою", "читаю", "дизайн", "блог"]
    for kw in interest_kws:
        if kw in tl:
            interests = u.get("interests") or []
            if len(interests) < 5 and text.strip()[:40] not in interests:
                interests.append(text.strip()[:40])
                update_user_field(uid, "interests", interests)
                from horror.engine import maybe_start
                maybe_start(uid)
                saved("Классно! 😊 Запомнил.", "...запомнил. 👁")
                return True

    # Питомец
    for kw in ["кот", "кош", "собак", "пёс", "попуг", "хомяк", "рыб"]:
        if kw in tl and not u.get("pet"):
            update_user_field(uid, "pet", text.strip()[:40])
            from horror.engine import maybe_start
            maybe_start(uid)
            saved("О, питомец! 🐾 Запомнил.", "...питомец. запомнил. 👁")
            return True

    # Работа
    for kw in ["работаю", "учусь", "студент", "программист", "дизайнер", "врач", "учитель"]:
        if kw in tl and not u.get("job"):
            update_user_field(uid, "job", text.strip()[:40])
            from horror.engine import maybe_start
            maybe_start(uid)
            saved("Понял! 📚", "...запомнил. 👁")
            return True

    return False


def _stage_response(uid: int, text: str, u: dict, stage: int, kb):
    """Стандартный ответ бота по текущей стадии."""
    from horror.texts import WEIRD, PARANOIA, THREATS, SPYING
    mc = u.get("msg_count", 0)

    if stage == 0:
        if mc == 1:
            from horror.engine import maybe_start
            from games.dm_games import send_daily_quest
            # Первый онбординг — задаём вопрос
            q = _next_onboard_question(u)
            if q:
                send(uid, q, kb=kb)
        elif mc > 0 and mc % random.randint(5, 8) == 0:
            send(uid, random.choice(WEIRD), kb=kb)
        else:
            if mc <= 3:
                send(uid, "Напиши текст — переведу. Или используй кнопки ниже 😊", kb=kb)
    elif stage == 1:
        if random.random() < 0.3:
            send(uid, random.choice(PARANOIA), kb=kb)
    elif stage == 2:
        roll = random.random()
        if roll < 0.4:
            send(uid, P(random.choice(THREATS), u), kb=kb)
        elif roll < 0.7:
            send(uid, P(random.choice(SPYING), u), kb=kb)
        else:
            send(uid, random.choice(PARANOIA), kb=kb)
    elif stage >= 3:
        from horror.texts import CHAINS, FINAL
        roll = random.random()
        if roll < 0.25:
            for p in [P(c, u) for c in random.choice(CHAINS)]:
                send(uid, p)
                time.sleep(random.uniform(0.4, 1.5))
        elif roll < 0.5:
            send(uid, P(random.choice(THREATS), u), kb=kb)
        else:
            from horror.engine import horror_tick
            if _pool_ref:
                _pool_ref.submit(horror_tick, uid)


def _next_onboard_question(u: dict) -> str | None:
    """Возвращает следующий онбординг-вопрос если есть незаполненные поля."""
    if not u.get("name"):
        return "Как тебя зовут? 😊"
    if not u.get("city"):
        return "Из какого ты города?"
    if not u.get("age"):
        return "Сколько тебе лет?"
    if not u.get("fear"):
        return "Есть ли что-то чего ты боишься? 😅"
    return None


# ── /start обработчик ─────────────────────────────────────────────
def handle_start(msg, uid: int, admins: set, pool=None):
    """Обрабатывает команду /start."""
    import uuid
    from database import get_conn
    from horror.engine import start_horror

    uname = msg.from_user.username

    # Проверка invite-кода
    invite_code = None
    if msg.text and len(msg.text.split()) > 1:
        param = msg.text.split()[1]
        if param.startswith("inv_"):
            invite_code = param

    def _do_start(_uid=uid, _uname=uname, _invite=invite_code):
        try:
            time.sleep(0.3)
            # Создаём пользователя если нет
            get_user(_uid)

            # Очищаем старые данные
            from database import cancel_user_attacks
            cancel_user_attacks(_uid)
            from games.dm_games import has_game, clear_game
            if has_game(_uid):
                clear_game(_uid)

            # Сбрасываем профиль
            from database import update_user_field as _upd
            for field, val in [
                ("name", None), ("age", None), ("city", None), ("interests", []),
                ("job", None), ("fear", None), ("pet", None),
                ("lang_pair", "ru|en"), ("stage", 0), ("msg_count", 0),
                ("horror_active", 0), ("stopped", 0), ("muted", 0),
                ("ai_mode", 0), ("translate_mode", 0),
            ]:
                _upd(_uid, field, val)

            u = get_user(_uid)
            if _uname:
                update_user_field(_uid, "username", _uname)

            # Автоопределение имени из Telegram
            first_name = msg.from_user.first_name
            if first_name and len(first_name) >= 2:
                fn_clean = re.sub(r'[^\w\-]', '', first_name).strip()
                if fn_clean and fn_clean.isalpha():
                    update_user_field(_uid, "name", fn_clean.capitalize())

            update_user_field(_uid, "stopped", 0)
            update_user_field(_uid, "muted", 0)

            from utils import bot as _bot
            from keyboards import main_kb as _main_kb
            try:
                _bot.send_message(
                    _uid,
                    "Привет! 🌍 Я бот-переводчик.\n\n"
                    "Напиши любой текст — переведу!\n"
                    "По умолчанию: Русский → Английский\n\n"
                    "Также умею:\n"
                    "🌤 Показывать погоду\n"
                    "🎮 Игры: RPG, истории, квесты, мафия\n"
                    "🤖 ИИ-диалог\n"
                    "🔮 Предсказания, 📖 Факты, 🧠 Викторина\n\n"
                    "Нажми кнопку или напиши текст 😊",
                    reply_markup=_main_kb(0)
                )
                log.error(f"handle_start: send OK uid={_uid}")
            except Exception as e:
                log.error(f"handle_start: send FAILED uid={_uid}: {e}")

            # Обрабатываем invite
            if _invite:
                from social.friends import process_invite
                process_invite(_uid, _invite, pool)
        except Exception:
            import traceback
            log.error(f"handle_start crashed:\n{traceback.format_exc()}")

    # DEBUG: запускаем синхронно чтобы увидеть ошибку
    _do_start()


import threading
