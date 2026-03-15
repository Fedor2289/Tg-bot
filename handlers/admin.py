"""
handlers/admin.py — Вся логика admin-панели.
"""
import time
import random
import threading
import logging

from utils import send, send_group, send_voice_msg, send_gif, get_random_gif, P, bot
from database import (
    get_user, save_user, update_user_field, get_all_users, get_active_users,
    add_admin, remove_admin, get_leaderboard, log_stage_change,
    cancel_user_attacks,
)
from keyboards import admin_main_kb, admin_victim_kb
from horror.engine import (
    horror_tick, start_horror, set_stage, freeze_stage, unfreeze_stage,
    check_achievement, get_achievements_text, get_shop_text, run_personal_scenario,
    ACHIEVEMENTS,
)
from horror.texts import CHAINS, THREATS, PREDICTIONS
from ai.client import ask as ask_ai, get_status as ai_status, is_enabled as ai_is_enabled
from config import log as _cfg_log

log = logging.getLogger("horror.admin")

# ── Состояние admin'ов ────────────────────────────────────────────
_adm_state: dict = {}  # admin_uid → {step, target_uid, ...}
_pool_ref = None

def set_pool(pool):
    global _pool_ref
    _pool_ref = pool

def adm_ctx_reset(uid: int):
    _adm_state[uid] = {"step": None, "target_uid": None}

def get_adm(uid: int) -> dict:
    if uid not in _adm_state:
        _adm_state[uid] = {"step": None, "target_uid": None}
    ctx = _adm_state[uid]
    ctx.setdefault("step", None)
    ctx.setdefault("target_uid", None)
    return ctx


# ── Вспомогательные команды ───────────────────────────────────────
def adm_info(tid: int) -> str:
    u = get_user(tid)
    interests = ", ".join(u.get("interests") or []) or "—"
    achievements = u.get("achievements") or []
    return (
        f"👤 ПРОФИЛЬ ЖЕРТВЫ\n\n"
        f"ID: {tid}\n"
        f"Username: @{u.get('username') or '—'}\n"
        f"Имя: {u.get('name') or '—'}\n"
        f"Возраст: {u.get('age') or '—'}\n"
        f"Город: {u.get('city') or '—'}\n"
        f"Работа: {u.get('job') or '—'}\n"
        f"Страх: {u.get('fear') or '—'}\n"
        f"Питомец: {u.get('pet') or '—'}\n"
        f"Интересы: {interests}\n"
        f"Телефон: {u.get('phone_model') or '—'}\n\n"
        f"Стадия: {u.get('stage', 0)}\n"
        f"Очки: {u.get('score', 0)}\n"
        f"Сообщений: {u.get('msg_count', 0)}\n"
        f"Хоррор: {'✅' if u.get('horror_active') else '❌'}\n"
        f"Заглушён: {'✅' if u.get('muted') else '❌'}\n"
        f"Остановлен: {'✅' if u.get('stopped') else '❌'}\n"
        f"Забанен: {'✅' if u.get('banned') else '❌'}\n\n"
        f"Ачивки ({len(achievements)}/{len(ACHIEVEMENTS)}): "
        f"{', '.join(achievements[:3]) or '—'}{'...' if len(achievements) > 3 else ''}"
    )


def adm_screamer(tid: int):
    u = get_user(tid)
    from horror.texts import CHAINS, THREATS
    def _r(_tid=tid, _u=u):
        for p in [P(c, _u) for c in random.choice(CHAINS)]:
            send(_tid, p)
            time.sleep(random.uniform(0.3, 1.2))
        time.sleep(1.5)
        send(_tid, P(random.choice(THREATS), _u))
        send_voice_msg(_tid, P(random.choice(THREATS), _u)[:150])
    if _pool_ref:
        _pool_ref.submit(_r)


def adm_max(tid: int):
    """Максимальный хоррор — 8-12 тиков подряд, стадия 5."""
    update_user_field(tid, "stage", 5)
    update_user_field(tid, "horror_active", 1)
    update_user_field(tid, "stopped", 0)
    update_user_field(tid, "muted", 0)
    def _b(_tid=tid):
        from utils import spam_mark
        for _ in range(random.randint(8, 12)):
            spam_mark(_tid)  # сбрасываем антиспам
            horror_tick(_tid)
            time.sleep(random.uniform(1.5, 3.0))
    if _pool_ref:
        _pool_ref.submit(_b)


def adm_ritual(tid: int):
    u = get_user(tid)
    RITUAL = [
        ("...начинается.", 2), ("...ты слышишь?", 2),
        ("...это я. твой {name}.", 3), ("...я всегда здесь.", 2),
        ("...твой {city}. твой дом. твой страх.", 3),
        ("...{fear}. я знаю.", 2), ("...это начало.", 0),
    ]
    def _r(_tid=tid, _u=u):
        kb = __import__('keyboards', fromlist=['main_kb']).main_kb(_u.get("stage", 0))
        for msg, delay in RITUAL:
            send(_tid, P(msg, _u), kb=kb)
            if delay > 0:
                time.sleep(delay)
        send_voice_msg(_tid, f"Я знаю твой страх. {_u.get('fear', 'темнота')}.")
    if _pool_ref:
        _pool_ref.submit(_r)


def adm_panic(tid: int):
    u = get_user(tid)
    PANIC = [
        ("⚠️ ВНИМАНИЕ", 1), ("⚠️ ОБНАРУЖЕНА АКТИВНОСТЬ", 1),
        ("📍 ГЕОЛОКАЦИЯ ОПРЕДЕЛЕНА", 2),
        (f"📍 {u.get('city', 'ГОРОД')} — ТЫ НАЙДЕН", 2),
        ("👁 НАБЛЮДЕНИЕ НАЧАТО", 1), ("...беги.", 0),
    ]
    def _r(_tid=tid, _u=u):
        kb = __import__('keyboards', fromlist=['main_kb']).main_kb(_u.get("stage", 0))
        for msg, delay in PANIC:
            send(_tid, P(msg, _u), kb=kb)
            if delay > 0:
                time.sleep(delay)
        send_voice_msg(_tid, "Беги.")
    if _pool_ref:
        _pool_ref.submit(_r)


def adm_trap(tid: int):
    u = get_user(tid)
    name = u.get("name", "ты")
    TRAP = [
        (f"Привет, {name}.", 2),
        ("Мне нужно тебе кое-что сказать.", 2),
        ("Ты уверен что хочешь это знать?", 4),
        ("...ладно.", 2),
        ("Я наблюдаю за тобой уже давно.", 2),
        ("С самого начала.", 3),
        ("...и я узнал о тебе всё.", 0),
    ]
    def _r(_tid=tid, _u=u):
        kb = __import__('keyboards', fromlist=['main_kb']).main_kb(_u.get("stage", 0))
        for msg, delay in TRAP:
            send(_tid, msg, kb=kb)
            if delay > 0:
                time.sleep(delay)
    if _pool_ref:
        _pool_ref.submit(_r)


def adm_sleep(tid: int):
    update_user_field(tid, "muted", 1)
    def _wake(_tid=tid):
        time.sleep(random.randint(150, 360))
        update_user_field(_tid, "muted", 0)
        send(_tid, "...ты думал что я ушёл?")
        time.sleep(2)
        adm_screamer(_tid)
    if _pool_ref:
        _pool_ref.submit(_wake)


def adm_reset(tid: int):
    """Полный сброс профиля жертвы."""
    from database import get_conn
    import json
    with get_conn() as conn:
        conn.execute("""
            UPDATE users SET
                name=NULL, age=NULL, city=NULL, interests='[]',
                job=NULL, fear=NULL, pet=NULL, sleep_time=NULL,
                phone_model=NULL, color=NULL, food=NULL, music=NULL,
                lang_pair='ru|en', stage=0, score=0, msg_count=0,
                horror_active=0, stopped=0, muted=0, banned=0,
                ai_mode=0, ai_msg_count=0, achievements='[]',
                translate_mode=0
            WHERE uid=?
        """, (tid,))
        conn.commit()
    cancel_user_attacks(tid)
    from keyboards import main_kb
    send(tid, "Привет! 🌍 Я бот-переводчик. Напиши текст для перевода!", kb=main_kb(0))


# ── Главный обработчик admin-сообщений ───────────────────────────
def handle_admin(msg, admin_uid: int, admins: set):
    """Точка входа для всех сообщений от admin'а."""
    try:
        _handle_admin_inner(msg, admin_uid, admins)
    except Exception as e:
        log.error(f"handle_admin crashed: {e}", exc_info=True)
        adm_ctx_reset(admin_uid)
        send(admin_uid, "⚠️ Ошибка в admin-панели. Контекст сброшен.", kb=admin_main_kb())


def _handle_admin_inner(msg, admin_uid: int, admins: set):
    text = (msg.text or "").strip()
    tl   = text.lower()
    ctx  = get_adm(admin_uid)

    # ── Режим ввода: ожидаем данные ───────────────────────────────
    if ctx["step"]:
        _handle_admin_state(msg, admin_uid, text, ctx, admins)
        return

    # ── Выход из god-mode ─────────────────────────────────────────
    if text == "🔙 Выйти из бога":
        from keyboards import main_kb
        u = get_user(admin_uid)
        adm_ctx_reset(admin_uid)
        send(admin_uid, "👁 Вышел из god-mode.", kb=main_kb(u.get("stage", 0)))
        return

    # ── Жертвы (список) ───────────────────────────────────────────
    if text == "👥 Жертвы":
        all_victims = [u for u in get_all_users() if u["uid"] not in admins and not u.get("banned")]
        all_victims.sort(key=lambda x: x.get("score", 0), reverse=True)
        if not all_victims:
            send(admin_uid, "❌ Нет жертв.", kb=admin_main_kb()); return
        lines = [f"ID:{u['uid']} — {u.get('name','?')} @{u.get('username','?')} ст.{u.get('stage',0)} очк.{u.get('score',0)}"
                 for u in all_victims[:30]]
        send(admin_uid, "👥 ЖЕРТВЫ:\n\n" + "\n".join(lines), kb=admin_main_kb())
        return

    # ── Выбор жертвы ──────────────────────────────────────────────
    if text == "⚙️ Выбрать жертву":
        all_victims = [u for u in get_all_users() if u["uid"] not in admins and not u.get("banned")]
        all_victims.sort(key=lambda x: x.get("score", 0), reverse=True)
        if not all_victims:
            send(admin_uid, "❌ Нет жертв.", kb=admin_main_kb()); return
        lines = [f"ID:{u['uid']} — {u.get('name','?')} @{u.get('username','?')} ст.{u.get('stage',0)}"
                 for u in all_victims[:30]]
        _adm_state[admin_uid] = {"step": "choose_victim", "target_uid": None}
        send(admin_uid, "👥 Введи ID или имя жертвы:\n\n" + "\n".join(lines))
        return

    tid = ctx.get("target_uid")

    # ── Статистика ────────────────────────────────────────────────
    if text == "📊 Статистика":
        all_u = get_all_users()
        total   = len([u for u in all_u if u["uid"] not in admins])
        active  = len([u for u in all_u if u.get("horror_active") and not u.get("stopped")])
        stage5  = len([u for u in all_u if u.get("stage", 0) >= 5])
        stopped = len([u for u in all_u if u.get("stopped")])
        banned  = len([u for u in all_u if u.get("banned")])
        send(admin_uid,
            f"📊 СТАТИСТИКА\n\n"
            f"👥 Всего жертв: {total}\n"
            f"😨 Активных: {active}\n"
            f"💀 Стадия 5: {stage5}\n"
            f"🛑 Остановлены: {stopped}\n"
            f"🚫 Забанены: {banned}\n\n"
            f"🤖 ИИ: {ai_status()}",
            kb=admin_main_kb())
        return

    # ── Список всех ID ────────────────────────────────────────────
    if text == "📋 Список ID":
        all_u = [u for u in get_all_users() if u["uid"] not in admins]
        lines = [f"ID:{u['uid']} {u.get('name','?')} ст.{u.get('stage',0)} очк.{u.get('score',0)}"
                 for u in all_u[:50]]
        send(admin_uid, "📋 ВСЕ ЖЕРТВЫ\n\n" + "\n".join(lines) if lines else "Пусто.",
             kb=admin_main_kb())
        return

    # ── Рассылки ──────────────────────────────────────────────────
    if text == "💀 Ужас всем":
        cnt = 0
        for u in get_active_users(min_stage=0):
            if u["uid"] not in admins:
                if _pool_ref:
                    _pool_ref.submit(horror_tick, u["uid"])
                cnt += 1
        send(admin_uid, f"💀 Хоррор запущен для {cnt} жертв.", kb=admin_main_kb())
        return

    if text == "🛑 Стоп всем":
        for u in get_all_users():
            if u["uid"] not in admins:
                update_user_field(u["uid"], "stopped", 1)
        send(admin_uid, "🛑 Все остановлены.", kb=admin_main_kb())
        return

    if text == "🔇 Тишина всем":
        for u in get_all_users():
            if u["uid"] not in admins:
                update_user_field(u["uid"], "muted", 1)
        send(admin_uid, "🔇 Все заглушены.", kb=admin_main_kb())
        return

    if text == "🔊 Звук всем":
        for u in get_all_users():
            if u["uid"] not in admins:
                update_user_field(u["uid"], "muted", 0)
        send(admin_uid, "🔊 Звук включён всем.", kb=admin_main_kb())
        return

    if text == "📤 Рассылка всем":
        _adm_state[admin_uid] = {"step": "broadcast_all", "target_uid": None}
        send(admin_uid, "📤 Введи текст рассылки (все жертвы получат):")
        return

    if text == "📡 По ID":
        _adm_state[admin_uid] = {"step": "send_by_id", "target_uid": None}
        send(admin_uid, "📡 Введи: ID текст сообщения")
        return

    # ── Лидерборд ────────────────────────────────────────────────
    if text == "🏆 Лидеры":
        from games.dm_games import get_leaderboard_text
        send(admin_uid, get_leaderboard_text(), kb=admin_main_kb())
        return

    if text == "🎬 Сценарии":
        from horror.engine import list_scenarios
        try:
            names = list_scenarios()
            if names:
                send(admin_uid, "🎬 Доступные сценарии:\n\n" + "\n".join(f"• {n}" for n in names), kb=admin_main_kb())
            else:
                send(admin_uid, "🎬 Нет сохранённых сценариев.", kb=admin_main_kb())
        except Exception:
            send(admin_uid, "🎬 Функция сценариев недоступна.", kb=admin_main_kb())
        return

    # ── Со-admin'ы ────────────────────────────────────────────────
    if text == "👑 Со-admin'ы":
        lines = [f"ID:{a}" for a in sorted(admins)]
        send(admin_uid, f"👑 Admins:\n" + "\n".join(lines), kb=admin_main_kb())
        return

    if text == "➕ Добавить admin'а":
        _adm_state[admin_uid] = {"step": "add_admin", "target_uid": None}
        send(admin_uid, "➕ Введи ID нового admin'а:")
        return

    if text == "➖ Убрать admin'а":
        _adm_state[admin_uid] = {"step": "remove_admin", "target_uid": None}
        send(admin_uid, "➖ Введи ID admin'а для удаления:")
        return

    # ── Сброс всех ────────────────────────────────────────────────
    if text == "🗑 Сбросить всех":
        _adm_state[admin_uid] = {"step": "confirm_reset_all", "target_uid": None}
        send(admin_uid, "⚠️ Сбросить ВСЕХ жертв? Напиши ПОДТВЕРЖДАЮ:")
        return

    # ── Бан ───────────────────────────────────────────────────────
    if text == "🚫 Забанить":
        _adm_state[admin_uid] = {"step": "ban_uid", "target_uid": None}
        send(admin_uid, "🚫 Введи ID жертвы для бана:")
        return

    if text == "✅ Разбанить":
        _adm_state[admin_uid] = {"step": "unban_uid", "target_uid": None}
        send(admin_uid, "✅ Введи ID жертвы для разбана:")
        return

    # ── Чат жертв ────────────────────────────────────────────────
    if text == "💬 Чат жертв":
        from social.anon_chat import start_chat_mode
        start_chat_mode(admin_uid, minutes=5, anon=True, admins=admins, pool=_pool_ref)
        return

    # ── ИИ настройки ─────────────────────────────────────────────
    if text == "🤖 ИИ-настройки":
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb_ai = InlineKeyboardMarkup(row_width=1)
        kb_ai.add(
            InlineKeyboardButton("🤖 ИИ: Groq",     callback_data=f"admin_ai_groq_{admin_uid}"),
            InlineKeyboardButton("🤖 ИИ: Cerebras", callback_data=f"admin_ai_cerebras_{admin_uid}"),
            InlineKeyboardButton("🤖 ИИ: Авто",     callback_data=f"admin_ai_auto_{admin_uid}"),
        )
        send(admin_uid, ai_status(), kb=admin_main_kb())
        bot.send_message(admin_uid, "Переключить бэкенд:", reply_markup=kb_ai)
        return

    # ── Жертва не выбрана ─────────────────────────────────────────
    if not tid:
        send(admin_uid, "⚡ БОГ-РЕЖИМ ⚡\nВыбери жертву через ⚙️", kb=admin_main_kb())
        return

    # ── Действия над выбранной жертвой ────────────────────────────
    _handle_victim_actions(admin_uid, tid, text, admins)


def _handle_victim_actions(admin_uid: int, tid: int, text: str, admins: set):
    """Команды над конкретной жертвой."""
    u = get_user(tid)
    name = u.get("name", f"ID:{tid}")
    stage = u.get("stage", 0)

    dispatch = {
        "📝 Текст":           lambda: _adm_state.update({admin_uid: {"step": "send_text", "target_uid": tid}}),
        "🎬 Гифка":           lambda: _send_gif_to_victim(admin_uid, tid),
        "⚡ Скример":         lambda: _pool_ref and _pool_ref.submit(adm_screamer, tid),
        "☠️ Макс-ужас":       lambda: adm_max(tid),
        "🌊 Волна паники":    lambda: adm_panic(tid),
        "🕯 Ритуал":          lambda: adm_ritual(tid),
        "💬 Диалог-ловушка":  lambda: adm_trap(tid),
        "😴 Спящий режим":    lambda: adm_sleep(tid),
        "🔇 Заглушить":       lambda: update_user_field(tid, "muted", 1),
        "🔊 Включить":        lambda: update_user_field(tid, "muted", 0),
        "🔄 Сбросить":        lambda: adm_reset(tid),
        "📋 Инфо о жертве":   lambda: send(admin_uid, adm_info(tid), kb=admin_victim_kb()),
        "👁 ИИ-атака":        lambda: _pool_ref and _pool_ref.submit(horror_tick, tid),
        "🎬 Персональный сценарий": lambda: run_personal_scenario(tid, _pool_ref),
    }

    if text in dispatch:
        try:
            dispatch[text]()
            if text not in ("📝 Текст", "📋 Инфо о жертве"):
                send(admin_uid, f"✅ {text} → {name}", kb=admin_victim_kb())
        except Exception as e:
            send(admin_uid, f"❌ Ошибка: {e}", kb=admin_victim_kb())
        return

    if text == "⬆️ Стадия +1":
        new_s = min(5, stage + 1)
        set_stage(tid, new_s)
        send(admin_uid, f"⬆️ Стадия {name}: {stage} → {new_s}", kb=admin_victim_kb())
        return

    if text == "⬇️ Стадия -1":
        new_s = max(0, stage - 1)
        set_stage(tid, new_s)
        send(admin_uid, f"⬇️ Стадия {name}: {stage} → {new_s}", kb=admin_victim_kb())
        return

    if text == "❄️ Заморозить стадию":
        freeze_stage(tid, 60)
        send(admin_uid, f"❄️ Стадия {name} заморожена на 1 час.", kb=admin_victim_kb())
        return

    if text == "🤖 ИИ пишет за меня":
        _start_ai_intercept(admin_uid, tid)
        return

    if text == "📱 Взлом телефона":
        from horror.effects import fake_phone_scan
        if _pool_ref:
            _pool_ref.submit(fake_phone_scan, tid)
        send(admin_uid, f"📱 Взлом запущен → {name}", kb=admin_victim_kb())
        return

    if text == "📞 Фейк-звонок":
        from horror.effects import fake_call_sequence
        if _pool_ref:
            _pool_ref.submit(fake_call_sequence, tid)
        send(admin_uid, f"📞 Фейк-звонок → {name}", kb=admin_victim_kb())
        return

    if text == "💀 Таймер смерти":
        _pool_ref and _pool_ref.submit(_death_timer, tid)
        send(admin_uid, f"💀 Таймер смерти запущен → {name}", kb=admin_victim_kb())
        return

    if text == "🪞 Зеркало":
        from horror.effects import mirror_event
        if _pool_ref:
            _pool_ref.submit(mirror_event, tid)
        send(admin_uid, f"🪞 Зеркало → {name}", kb=admin_victim_kb())
        return

    if text == "🫀 Сердцебиение":
        from horror.effects import heartbeat_event
        if _pool_ref:
            _pool_ref.submit(heartbeat_event, tid)
        send(admin_uid, f"🫀 Сердцебиение → {name}", kb=admin_victim_kb())
        return

    if text == "🎙 Голос от него":
        _adm_state[admin_uid] = {"step": "voice_as_ai", "target_uid": tid}
        send(admin_uid, "🎙 Введи текст — отправлю голосовым от имени ИИ:")
        return

    if text == "✏️ Редактировать данные":
        FIELDS = {"имя": "name", "возраст": "age", "город": "city",
                  "страх": "fear", "работа": "job", "питомец": "pet"}
        lines = [f"{k} → {u.get(v, '—')}" for k, v in FIELDS.items()]
        _adm_state[admin_uid] = {"step": "edit_field_choose", "target_uid": tid}
        send(admin_uid, "✏️ Какое поле?\n\n" + "\n".join(lines) + "\n\nВведи название поля:")
        return

    send(admin_uid, "⚡ БОГ-РЕЖИМ ⚡", kb=admin_main_kb())


def _handle_admin_state(msg, admin_uid: int, text: str, ctx: dict, admins: set):
    """Обрабатывает ввод когда admin ожидает данных."""
    step = ctx["step"]
    tid  = ctx.get("target_uid")
    kb   = admin_main_kb()

    # ── Выбор жертвы ──────────────────────────────────────────────
    if step == "choose_victim":
        target = None
        tl = text.strip().lower()
        for u in get_all_users():
            if str(u["uid"]) == text.strip() or (u.get("name") or "").lower() == tl:
                target = u["uid"]
                break
        if not target:
            send(admin_uid, "❌ Жертва не найдена. Попробуй ещё раз:", kb=kb)
            return
        _adm_state[admin_uid] = {"step": None, "target_uid": target}
        u = get_user(target)
        send(admin_uid, f"✅ Выбрана жертва: {u.get('name','?')} (ID:{target})\n\n{adm_info(target)}",
             kb=admin_victim_kb())
        return

    # ── Отправить текст ───────────────────────────────────────────
    if step == "send_text":
        if tid and text:
            u_t = get_user(tid)
            from keyboards import main_kb
            send(tid, text, kb=main_kb(u_t.get("stage", 0)))
            send(admin_uid, f"✅ Отправлено → ID:{tid}", kb=admin_victim_kb())
        adm_ctx_reset(admin_uid)
        return

    # ── Голос от ИИ ───────────────────────────────────────────────
    if step == "voice_as_ai":
        if tid and text:
            u_t = get_user(tid)
            from keyboards import main_kb
            prefix = "🤖" if u_t.get("stage", 0) < 2 else ("👁" if u_t.get("stage", 0) < 4 else "💀")
            send(tid, f"{prefix} {text}", kb=main_kb(u_t.get("stage", 0)))
            if _pool_ref:
                _pool_ref.submit(send_voice_msg, tid, text[:200])
            send(admin_uid, f"✅ Голосовое отправлено → {text[:50]}", kb=admin_victim_kb())
        adm_ctx_reset(admin_uid)
        return

    # ── Ждём ответ за ИИ ─────────────────────────────────────────
    if step == "wait_ai_intercept_text":
        if tid and text.strip():
            u_t = get_user(tid)
            st  = u_t.get("stage", 0)
            pref = "🤖" if st < 2 else ("👁" if st < 4 else "💀")
            from keyboards import main_kb
            send(tid, f"{pref} {text}", kb=main_kb(st))
            if _pool_ref:
                _pool_ref.submit(send_voice_msg, tid, text[:200])
            send(admin_uid, f"✅ Отправлено за ИИ:\n«{pref} {text}»", kb=admin_victim_kb())
        adm_ctx_reset(admin_uid)
        return

    # ── Рассылка всем ─────────────────────────────────────────────
    if step == "broadcast_all":
        if text:
            cnt = 0
            for u in get_all_users():
                if u["uid"] not in admins and not u.get("stopped") and not u.get("banned"):
                    try:
                        send(u["uid"], text)
                        cnt += 1
                    except Exception:
                        pass
            send(admin_uid, f"✅ Разослано {cnt} жертвам.", kb=kb)
        adm_ctx_reset(admin_uid)
        return

    # ── Отправить по ID ───────────────────────────────────────────
    if step == "send_by_id":
        parts = text.split(None, 1)
        if len(parts) >= 2 and parts[0].isdigit():
            target_id = int(parts[0])
            msg_text  = parts[1]
            u_t = get_user(target_id)
            from keyboards import main_kb
            send(target_id, msg_text, kb=main_kb(u_t.get("stage", 0)))
            send(admin_uid, f"✅ Отправлено → ID:{target_id}", kb=kb)
        else:
            send(admin_uid, "❌ Формат: ID текст", kb=kb)
        adm_ctx_reset(admin_uid)
        return

    # ── Добавить admin'а ──────────────────────────────────────────
    if step == "add_admin":
        if text.isdigit():
            new_aid = int(text)
            admins.add(new_aid)
            add_admin(new_aid, admin_uid)
            send(admin_uid, f"✅ Admin добавлен: ID:{new_aid}", kb=kb)
        else:
            send(admin_uid, "❌ Введи числовой ID.", kb=kb)
        adm_ctx_reset(admin_uid)
        return

    # ── Убрать admin'а ────────────────────────────────────────────
    if step == "remove_admin":
        from config import ADMIN_ID
        if text.isdigit():
            rem_id = int(text)
            if rem_id == ADMIN_ID:
                send(admin_uid, "❌ Нельзя убрать главного admin'а.", kb=kb)
            else:
                admins.discard(rem_id)
                remove_admin(rem_id)
                send(admin_uid, f"✅ Admin удалён: ID:{rem_id}", kb=kb)
        adm_ctx_reset(admin_uid)
        return

    # ── Бан / Разбан ──────────────────────────────────────────────
    if step == "ban_uid":
        if text.isdigit():
            bid = int(text)
            update_user_field(bid, "banned", 1)
            update_user_field(bid, "stopped", 1)
            send(admin_uid, f"🚫 Заблокирован ID:{bid}", kb=kb)
        adm_ctx_reset(admin_uid)
        return

    if step == "unban_uid":
        if text.isdigit():
            bid = int(text)
            update_user_field(bid, "banned", 0)
            update_user_field(bid, "stopped", 0)
            send(admin_uid, f"✅ Разблокирован ID:{bid}", kb=kb)
        adm_ctx_reset(admin_uid)
        return

    # ── Подтверждение сброса всех ─────────────────────────────────
    if step == "confirm_reset_all":
        if text.strip() == "ПОДТВЕРЖДАЮ":
            cnt = 0
            for u in get_all_users():
                if u["uid"] not in admins:
                    adm_reset(u["uid"])
                    cnt += 1
            send(admin_uid, f"🗑 Сброшено {cnt} профилей.", kb=kb)
        else:
            send(admin_uid, "❌ Отменено.", kb=kb)
        adm_ctx_reset(admin_uid)
        return

    # ── Редактирование поля ───────────────────────────────────────
    if step == "edit_field_choose":
        FIELDS = {"имя": "name", "возраст": "age", "город": "city",
                  "страх": "fear", "работа": "job", "питомец": "pet"}
        field = FIELDS.get(text.lower().strip())
        if field:
            _adm_state[admin_uid] = {"step": "edit_field_value",
                                      "target_uid": tid, "field": field}
            send(admin_uid, f"✏️ Введи новое значение для «{text}»:")
        else:
            send(admin_uid, "❌ Неизвестное поле.", kb=admin_victim_kb())
            adm_ctx_reset(admin_uid)
        return

    if step == "edit_field_value":
        field = ctx.get("field")
        if tid and field:
            update_user_field(tid, field, text.strip())
            send(admin_uid, f"✅ Обновлено: {field} = {text.strip()}", kb=admin_victim_kb())
        adm_ctx_reset(admin_uid)
        return

    adm_ctx_reset(admin_uid)


# ── AI Intercept ──────────────────────────────────────────────────
_ai_intercept: dict = {}  # key → {cancelled, uid/chat_id, group, msg_ids}

def _start_ai_intercept(admin_uid: int, tid: int):
    import uuid
    u = get_user(tid)
    name  = u.get("name", str(tid))
    stage = u.get("stage", 0)
    hist  = u.get("msg_history") or []
    last  = "; ".join(f'"{m}"' for m in hist[-3:]) if hist else "нет"

    # Отменяем старые перехваты
    for k in list(_ai_intercept.keys()):
        if _ai_intercept[k].get("uid") == tid:
            _ai_intercept[k]["cancelled"] = True
            for mid_pair in _ai_intercept.pop(k, {}).get("msg_ids", []):
                try:
                    bot.edit_message_reply_markup(chat_id=mid_pair[0], message_id=mid_pair[1], reply_markup=None)
                except Exception:
                    pass

    ic_key  = f"{tid}_{uuid.uuid4().hex[:8]}"
    ic_data = {"cancelled": False, "uid": tid, "group": False, "msg_ids": []}
    _ai_intercept[ic_key] = ic_data

    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kbi = InlineKeyboardMarkup()
    kbi.add(InlineKeyboardButton("✍️ Ответить за ИИ", callback_data=f"ai_ic_{ic_key}_{admin_uid}"))

    try:
        sent = bot.send_message(admin_uid,
            f"👤 {name} (ID:{tid}, ст.{stage})\n\n"
            f"Последние: {last[:200]}\n\n"
            f"⏱ 15с → ответь сам или ИИ ответит",
            reply_markup=kbi)
        ic_data["msg_ids"].append((admin_uid, sent.message_id))
    except Exception as e:
        log.debug(f"ai_intercept send: {e}")

    def _auto_ai(_ic_key=ic_key, _tid=tid, _stage=stage, _name=name, _last=last):
        time.sleep(15)
        ic = _ai_intercept.pop(_ic_key, {})
        if ic.get("cancelled"):
            return
        # ИИ отвечает автоматически
        if not ai_is_enabled():
            return
        from database import get_ai_history, add_ai_message
        from ai.client import ask, AI_SYSTEM_PROMPT_DM
        history = get_ai_history(_tid)
        if _stage < 2:
            prompt = f"Пользователь написал: {_last}. Ответь полезно, по-русски. 2-3 предложения."
        elif _stage < 4:
            prompt = f"Жертва {_name} написала: {_last}. Ты — тёмная сущность. Ответь жутко, но по существу."
        else:
            prompt = f"Жертва написала: {_last}. Ты — зло. Напугай лично. 1-2 предложения."

        answer = ask(prompt, chat_id=_tid, dm_mode=(_stage >= 2), history=history)
        if answer:
            from keyboards import main_kb
            pref = "🤖" if _stage < 2 else ("👁" if _stage < 4 else "💀")
            u2 = get_user(_tid)
            send(_tid, f"{pref} {answer}", kb=main_kb(u2.get("stage", 0)))
            send_voice_msg(_tid, answer[:200])
            add_ai_message(_tid, "assistant", answer)

    if _pool_ref:
        _pool_ref.submit(_auto_ai)
    else:
        threading.Thread(target=_auto_ai, daemon=True).start()


def handle_ai_ic_callback(call, aid: int, intercept_key: str, admins: set):
    """Обрабатывает нажатие кнопки '✍️ Ответить за ИИ'."""
    ic = _ai_intercept.get(intercept_key)
    if not ic:
        bot.answer_callback_query(call.id, "⏱ Время вышло — ИИ уже ответил")
        return
    ic["cancelled"] = True
    bot.answer_callback_query(call.id, "✍️ Пиши ответ — отправлю от имени ИИ")
    try:
        bot.edit_message_reply_markup(chat_id=aid, message_id=call.message.message_id, reply_markup=None)
    except Exception:
        pass
    adm_ctx_reset(aid)
    if ic.get("group"):
        grp_cid = ic.get("chat_id")
        _adm_state[aid] = {"step": "wait_grp_aiwrite", "target_uid": None, "grp_cid": grp_cid}
        send(aid, f"✍️ Пиши ответ для группы {grp_cid}:")
    else:
        tid = ic.get("uid")
        _adm_state[aid] = {"step": "wait_ai_intercept_text", "target_uid": tid}
        u_t = get_user(tid)
        send(aid, f"✍️ Пиши ответ для {u_t.get('name', tid)}:")


def get_ai_intercept() -> dict:
    return _ai_intercept


# ── Вспомогательные ───────────────────────────────────────────────
def _send_gif_to_victim(admin_uid: int, tid: int):
    gif_path = get_random_gif()
    if gif_path:
        try:
            with open(gif_path, "rb") as f:
                bot.send_animation(tid, f)
            send(admin_uid, "✅ Гифка отправлена", kb=admin_victim_kb())
        except Exception as e:
            send(admin_uid, f"❌ Ошибка гифки: {e}", kb=admin_victim_kb())
    else:
        send(admin_uid, "❌ Нет гифок в папке gif/", kb=admin_victim_kb())


def _death_timer(tid: int):
    u = get_user(tid)
    from keyboards import main_kb
    kb = main_kb(u.get("stage", 0))
    for i in range(10, 0, -1):
        send(tid, f"⏳ {i}...", kb=kb)
        time.sleep(1)
    send(tid, "👁 Время вышло. Я здесь.")
    horror_tick(tid)
