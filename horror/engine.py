"""
horror/engine.py — Движок хоррора: стадии, тики, планировщик атак.
"""
import time
import random
import threading
import logging
import datetime

from config import STAGE_SEC, HORROR_DELAY_SEC, log as _cfg_log
from database import (
    get_user, update_user_field, save_user,
    get_active_users, log_stage_change,
    schedule_attack, get_pending_attacks, mark_attack_done,
    cancel_user_attacks,
)
from utils import send, send_voice_msg, spam_check, dnight, P, get_city_news

log = logging.getLogger("horror.engine")

# Импортируем эффекты лениво во избежание циклического импорта
def _effects():
    from horror import effects
    return effects

# ── Ачивки ───────────────────────────────────────────────────────
ACHIEVEMENTS = {
    "first_blood":    {"name": "🩸 Первая кровь",    "desc": "Получить первое хоррор-сообщение", "reward": 10},
    "week_survivor":  {"name": "📅 Выживший",         "desc": "Провести в боте 7 дней",          "reward": 50},
    "scream_x10":     {"name": "😱 10 скримеров",     "desc": "Пережить 10 хоррор-атак",         "reward": 30},
    "secrets_told":   {"name": "🤫 Открытая книга",   "desc": "Рассказать все данные о себе",     "reward": 40},
    "mafia_winner":   {"name": "🔫 Победитель мафии", "desc": "Победить в игре мафия",           "reward": 60},
    "quiz_master":    {"name": "🧠 Эрудит",           "desc": "Ответить правильно на 10 вопросов","reward": 25},
    "night_owl":      {"name": "🦉 Ночная птица",     "desc": "Написать боту в 3 ночи",          "reward": 20},
    "stage_max":      {"name": "💀 Конец пути",       "desc": "Достичь стадии страха 5",         "reward": 100},
    "daily_streak_3": {"name": "🗓 3 дня подряд",     "desc": "Выполнить задание 3 дня подряд",  "reward": 35},
    "ai_chat_50":     {"name": "🤖 Собеседник",       "desc": "Написать ИИ 50 сообщений",        "reward": 30},
    "invited_friend": {"name": "👥 Вербовщик",        "desc": "Привести друга в бота",           "reward": 50},
}

def check_achievement(uid: int, achievement_id: str, pool=None):
    """Выдаёт ачивку если ещё нет."""
    u = get_user(uid)
    earned = u.get("achievements") or []
    if achievement_id in earned:
        return False
    a = ACHIEVEMENTS.get(achievement_id)
    if not a:
        return False
    earned.append(achievement_id)
    new_score = u.get("score", 0) + a["reward"]
    update_user_field(uid, "achievements", earned)
    update_user_field(uid, "score", new_score)

    def _notify(_uid=uid, _a=a):
        time.sleep(random.uniform(0.5, 2))
        from keyboards import main_kb
        u2 = get_user(_uid)
        send(_uid,
            f"🏅 ДОСТИЖЕНИЕ РАЗБЛОКИРОВАНО!\n\n"
            f"{_a['name']}\n{_a['desc']}\n\n"
            f"🏆 +{_a['reward']} очков страха",
            kb=main_kb(u2.get("stage", 0)))

    if pool:
        pool.submit(_notify)
    else:
        threading.Thread(target=_notify, daemon=True).start()
    return True


def get_achievements_text(uid: int) -> str:
    u = get_user(uid)
    earned = u.get("achievements") or []
    lines = []
    for aid, a in ACHIEVEMENTS.items():
        icon = "✅" if aid in earned else "🔒"
        lines.append(f"{icon} {a['name']} — {a['desc']}")
    return f"🏅 АЧИВКИ ({len(earned)}/{len(ACHIEVEMENTS)})\n\n" + "\n".join(lines)


# ── Магазин ───────────────────────────────────────────────────────
FEAR_SHOP = {
    "shield_1h":   {"name": "🛡 Щит (1 час)",        "price": 50,  "desc": "Защита от хоррора на 1 час"},
    "shield_24h":  {"name": "🛡 Щит (сутки)",         "price": 150, "desc": "Защита от хоррора на 24 часа"},
    "silence_2h":  {"name": "🔕 Тишина (2 часа)",     "price": 35,  "desc": "Бот временно замолчит"},
    "hint_quest":  {"name": "💡 Подсказка",            "price": 30,  "desc": "Подсказка в следующем задании"},
    "boost_fear":  {"name": "😈 Ужас другому",         "price": 40,  "desc": "Отправить ужас другой жертве"},
    "extra_daily": {"name": "📋 Доп. задание",         "price": 20,  "desc": "Ещё одно задание сегодня"},
}

def shop_buy(uid: int, item_id: str, target_uid: int = 0, pool=None) -> tuple:
    from database import get_shop_item, set_shop_item, remove_shop_item
    u = get_user(uid)
    item = FEAR_SHOP.get(item_id)
    if not item:
        return False, "❌ Товар не найден."
    if u.get("score", 0) < item["price"]:
        return False, f"❌ Нужно {item['price']} очков. У тебя {u.get('score', 0)}."

    update_user_field(uid, "score", u.get("score", 0) - item["price"])
    now = time.time()

    if item_id == "shield_1h":
        set_shop_item(uid, "shield", now + 3600)
        return True, f"✅ {item['name']} активен."
    elif item_id == "shield_24h":
        set_shop_item(uid, "shield", now + 86400)
        return True, f"✅ {item['name']} активен."
    elif item_id == "silence_2h":
        update_user_field(uid, "muted", 1)
        set_shop_item(uid, "silence", now + 7200)
        return True, f"✅ {item['name']} — тишина на 2 часа."
    elif item_id == "hint_quest":
        set_shop_item(uid, "hint_quest", None)
        return True, f"✅ {item['name']} — активна."
    elif item_id == "boost_fear":
        if target_uid and target_uid > 0:
            if pool:
                pool.submit(horror_tick, target_uid)
            return True, f"✅ Ужас отправлен! 😈"
        return False, "❌ Укажи ID жертвы."
    elif item_id == "extra_daily":
        from database import set_daily_done
        set_daily_done(uid, "0000-00-00", 0)  # сброс
        return True, f"✅ Можешь взять ещё одно задание сегодня."

    return False, "❌ Ошибка."


def is_shielded(uid: int) -> bool:
    from database import get_shop_item, remove_shop_item
    item = get_shop_item(uid, "shield")
    if not item:
        return False
    if item.get("expires_at") and time.time() > item["expires_at"]:
        remove_shop_item(uid, "shield")
        return False
    return True


def get_shop_text(uid: int) -> str:
    u = get_user(uid)
    score = u.get("score", 0)
    lines = [f"🛒 МАГАЗИН СТРАХА\n\nТвои очки: {score}\n"]
    for iid, item in FEAR_SHOP.items():
        can = "✅" if score >= item["price"] else "❌"
        lines.append(f"{can} {item['name']} — {item['price']} очков\n   {item['desc']}")
    lines.append("\nДля покупки нажми кнопку ниже 👇")
    return "\n".join(lines)


# ── Планировщик ───────────────────────────────────────────────────
_shutdown = threading.Event()
_pool_ref = None  # будет установлен из main.py

def set_pool(pool):
    global _pool_ref
    _pool_ref = pool

def _scheduler_loop():
    """Фоновый цикл: выполняет запланированные атаки из БД."""
    while not _shutdown.is_set():
        try:
            pending = get_pending_attacks()
            for attack in pending:
                mark_attack_done(attack["id"])
                uid = attack["uid"]
                func_name = attack["func_name"]
                u = get_user(uid)
                if u.get("stopped") or u.get("muted") or u.get("banned"):
                    continue
                # Выполняем нужную функцию
                fn = getattr(_effects(), func_name, None)
                if fn and _pool_ref:
                    _pool_ref.submit(fn, uid)
        except Exception as e:
            log.debug(f"Scheduler error: {e}")
        _shutdown.wait(30)  # проверяем каждые 30 секунд


def _random_event_loop():
    """Фоновый цикл: каждые 2 часа шлёт событие активным жертвам stage>=2."""
    _shutdown.wait(600)  # старт через 10 минут
    while not _shutdown.is_set():
        try:
            active = get_active_users(min_stage=2)
            if active and _pool_ref:
                victim = random.choice(active)
                _pool_ref.submit(horror_tick, victim["uid"])
        except Exception as e:
            log.debug(f"Random event error: {e}")
        _shutdown.wait(7200)  # каждые 2 часа


def stop_loops():
    _shutdown.set()


# ── Хоррор-тик ───────────────────────────────────────────────────
def horror_tick(uid: int):
    """Выбирает и запускает случайный хоррор-эффект для жертвы."""
    u = get_user(uid)
    if u.get("stopped") or u.get("muted") or u.get("banned"):
        return
    if is_shielded(uid):
        return
    if not spam_check(uid):
        return

    stage   = u.get("stage", 0)
    eff     = _effects()
    night   = dnight()
    hist    = u.get("msg_history") or []

    # Выбираем эффект с весами по стадии
    pool_w = []
    pool_f = []

    def add(fn, w): pool_f.append(fn); pool_w.append(w)

    # Стадия 0-1: лёгкие намёки
    if stage >= 0:
        add(lambda u=uid: send(u, random.choice(__import__('horror.texts', fromlist=['WEIRD']).WEIRD)), 30)
    if stage >= 1:
        add(lambda u=uid: send(u, random.choice(__import__('horror.texts', fromlist=['PARANOIA']).PARANOIA)), 25)

    # Стадия 2+: начало настоящего страха
    if stage >= 2:
        add(eff.fake_geolocation, 20)
        add(eff.smart_echo_history, 15)
        add(eff.glitch_attack, 15)
        add(eff.fake_telegram_security, 10)
        add(lambda u=uid: send(u, random.choice(__import__('horror.texts', fromlist=['SPYING']).SPYING)), 20)

    # Стадия 3+: психологическое давление
    if stage >= 3:
        add(eff.signal_loss, 15)
        add(eff.fake_live_stream, 12)
        add(eff.mirror_event, 10)
        add(eff.fake_gps_tracking, 10)
        add(eff.fake_wifi_hack, 10)
        add(eff.fake_notifications, 12)
        add(lambda u=uid: send(u, P(random.choice(__import__('horror.texts', fromlist=['THREATS']).THREATS), get_user(u))), 20)
        if night:
            add(eff.three_am_mode, 30)

    # Стадия 4+: полный ужас
    if stage >= 4:
        add(eff.heartbeat_event, 15)
        add(eff.fake_ghost_users, 12)
        add(eff.fake_file_scan, 10)
        add(eff.fake_deleted_message, 10)
        add(eff.fake_phone_scan, 10)

    # Стадия 5+: паранормальщина
    if stage >= 5:
        add(eff.fake_call_sequence, 10)
        add(eff.fake_ban_sequence, 8)
        add(eff.fake_leave_sequence, 8)
        chains = __import__('horror.texts', fromlist=['CHAINS']).CHAINS
        add(lambda u=uid: _send_chain(u, random.choice(chains)), 15)

    if not pool_f:
        return

    # Выбираем и запускаем
    chosen = random.choices(pool_f, weights=pool_w, k=1)[0]
    try:
        chosen(uid)
    except TypeError:
        try:
            chosen()
        except Exception as e:
            log.debug(f"horror_tick effect error: {e}")

    # Ачивка за первый хоррор
    u2 = get_user(uid)
    if u2.get("score", 0) == 0:
        check_achievement(uid, "first_blood", _pool_ref)

    # Счётчик атак
    horror_count = u2.get("horror_count", 0) + 1
    update_user_field(uid, "horror_count", horror_count)
    if horror_count >= 10:
        check_achievement(uid, "scream_x10", _pool_ref)


def _send_chain(uid: int, chain: list):
    from keyboards import main_kb
    u = get_user(uid)
    kb = main_kb(u.get("stage", 0))
    for msg in chain:
        send(uid, P(msg, u))
        time.sleep(random.uniform(0.5, 2))
    # Голосовое последнего сообщения
    if chain:
        send_voice_msg(uid, P(chain[-1], u))


# ── Запуск хоррора ───────────────────────────────────────────────
def start_horror(uid: int):
    """Запускает хоррор-режим для пользователя."""
    u = get_user(uid)
    if u.get("horror_active"):
        return
    update_user_field(uid, "horror_active", 1)
    log.info(f"Horror started for uid={uid}")

    def _delay_tick(_uid=uid):
        time.sleep(HORROR_DELAY_SEC)
        u2 = get_user(_uid)
        if not u2.get("stopped") and not u2.get("banned"):
            horror_tick(_uid)

    if _pool_ref:
        _pool_ref.submit(_delay_tick)
    else:
        threading.Thread(target=_delay_tick, daemon=True).start()


def maybe_start(uid: int):
    """Запускает хоррор когда собраны базовые данные."""
    u = get_user(uid)
    if u.get("horror_active") or u.get("stopped"):
        return
    # Нужно имя + хотя бы одно из: город, возраст, страх
    if u.get("name") and (u.get("city") or u.get("age") or u.get("fear")):
        # Проверяем ачивку "secrets_told"
        if u.get("name") and u.get("age") and u.get("city") and u.get("fear"):
            check_achievement(uid, "secrets_told", _pool_ref)
        start_horror(uid)


# ── Стадии ───────────────────────────────────────────────────────
def set_stage(uid: int, stage: int):
    """Устанавливает стадию страха."""
    old = get_user(uid).get("stage", 0)
    stage = max(0, min(5, stage))
    update_user_field(uid, "stage", stage)
    log_stage_change(uid, stage)
    # Ачивка
    if stage >= 5:
        check_achievement(uid, "stage_max", _pool_ref)
    return stage


def advance_stage(uid: int) -> int:
    """Увеличивает стадию на 1 если прошло достаточно времени."""
    u = get_user(uid)
    if u.get("stopped") or not u.get("horror_active"):
        return u.get("stage", 0)
    stage = u.get("stage", 0)
    if stage >= 5:
        return 5
    new_stage = stage + 1
    return set_stage(uid, new_stage)


def freeze_stage(uid: int, minutes: int):
    update_user_field(uid, "stage_frozen_until", time.time() + minutes * 60)

def unfreeze_stage(uid: int):
    update_user_field(uid, "stage_frozen_until", 0)

def is_stage_frozen(uid: int) -> bool:
    u = get_user(uid)
    until = u.get("stage_frozen_until", 0)
    return bool(until and time.time() < until)


# ── Фоновый поток стадий ─────────────────────────────────────────
def _stage_advance_loop():
    """Каждые STAGE_SEC секунд повышает стадию активным жертвам."""
    while not _shutdown.is_set():
        _shutdown.wait(STAGE_SEC)
        try:
            active = get_active_users(min_stage=0)
            for u in active:
                uid = u["uid"]
                if is_stage_frozen(uid):
                    continue
                old = u.get("stage", 0)
                if old < 5:
                    advance_stage(uid)
        except Exception as e:
            log.debug(f"Stage loop error: {e}")


# ── Персональный ИИ-сценарий ─────────────────────────────────────
def generate_personal_scenario(uid: int) -> list:
    """Генерирует 5-шаговый персональный сценарий через ИИ."""
    from ai.client import ask
    u = get_user(uid)
    name   = u.get("name", "жертва")
    city   = u.get("city", "неизвестном городе")
    fear   = u.get("fear", "темнота")
    job    = u.get("job", "")
    news   = get_city_news(city)
    news_l = f"Новость из {city}: {news}. " if news else ""

    prompt = (
        f"Создай 5-шаговый психологический хоррор-сценарий для человека:\n"
        f"Имя: {name}, Город: {city}, Страх: {fear}, Работа: {job}.\n"
        f"{news_l}"
        f"Используй РЕАЛЬНЫЕ данные человека. Каждый шаг — отдельное жуткое сообщение.\n"
        f"Формат: ШАГ1: [текст] | ШАГ2: [текст] | ШАГ3: [текст] | ШАГ4: [текст] | ШАГ5: [текст]\n"
        f"Каждый шаг максимум 25 слов. Психологически жутко, без паранормальщины."
    )

    raw = ask(prompt, chat_id=uid, dm_mode=True, max_tokens=400)
    import re
    steps = re.findall(r'ШАГ\d+:\s*(.+?)(?=\s*\||\s*ШАГ|\Z)', raw, re.DOTALL)
    if not steps:
        steps = [s.strip() for s in raw.split('|') if s.strip()]
    return [s.strip()[:200] for s in steps[:5] if s.strip()]


def run_personal_scenario(uid: int, pool=None):
    """Запускает персональный сценарий."""
    def _run(_uid=uid):
        from keyboards import main_kb
        u = get_user(_uid)
        steps = generate_personal_scenario(_uid)
        if not steps:
            steps = ["...я знаю о тебе достаточно.", "...больше чем ты думаешь."]
        for step in steps:
            send(_uid, step, kb=main_kb(u.get("stage", 0)))
            time.sleep(random.uniform(8, 15))
            send_voice_msg(_uid, step[:150])

    if pool:
        pool.submit(_run)
    elif _pool_ref:
        _pool_ref.submit(_run)
    else:
        threading.Thread(target=_run, daemon=True).start()
