"""
handlers/group.py — Обработчик групповых сообщений.
"""
import time
import random
import logging

from utils import send, send_group, send_voice_msg, send_gif, get_random_gif, translate, get_weather
from database import get_user, update_user_field
from keyboards import group_main_kb, group_games_kb, lang_kb
from config import LANG_NAMES, GROUP_AUTO_VOICE

log = logging.getLogger("horror.group")

_group_users: dict = {}   # chat_id → set(uid)
_group_awaiting: dict = {}  # chat_id → (mode, uid)
_pool_ref = None
_admins_ref = None

def init(pool, admins: set):
    global _pool_ref, _admins_ref
    _pool_ref  = pool
    _admins_ref = admins


def handle_group_message(msg, uid: int, chat_id: int, text: str):
    """Точка входа для сообщений из группы."""
    try:
        _handle_group_inner(msg, uid, chat_id, text)
    except Exception as e:
        log.error(f"handle_group crashed chat={chat_id}: {e}", exc_info=True)


def _handle_group_inner(msg, uid: int, chat_id: int, text: str):
    # Регистрируем участника
    if chat_id not in _group_users:
        _group_users[chat_id] = set()
    _group_users[chat_id].add(uid)

    u     = get_user(uid)
    uname = msg.from_user.first_name or msg.from_user.username or f"ID:{uid}"
    tl    = text.lower()

    # ── Admin-команда в группе ────────────────────────────────────
    if _admins_ref and uid in _admins_ref and text == "/gadmin":
        _send_gadm_panel(uid, chat_id)
        return

    # ── Мафия v20 ────────────────────────────────────────────────
    from games.mafia import _maf_uid, maf_proc_dm, _group_mafia
    if chat_id in _group_mafia:
        grp = _group_mafia[chat_id]
        lid = grp.get("lid")
        if lid and uid in _group_users.get(chat_id, set()):
            # Команды выхода
            if tl in ("/leavem", "мафия выйти"):
                maf_proc_dm(uid, "/leavem")
                return

    # ── Ожидание ввода ────────────────────────────────────────────
    awaiting = _group_awaiting.get(chat_id)
    if awaiting:
        mode, awaiting_uid = awaiting
        if uid == awaiting_uid:
            if mode == "translate":
                _group_awaiting.pop(chat_id, None)
                lang = u.get("lang_pair", "ru|en")
                result = translate(text, lang)
                send_group(chat_id, f"🌍 {result}" if result else "❌ Не удалось перевести.")
                return
            elif mode == "weather":
                _group_awaiting.pop(chat_id, None)
                w = get_weather(text.strip())
                if w:
                    send_group(chat_id, w)
                else:
                    send_group(chat_id, f"❌ Город «{text}» не найден.")
                return
            elif mode == "ai":
                _group_awaiting.pop(chat_id, None)
                def _ask(_p=text, _uname=uname, _cid=chat_id):
                    _group_ai_respond(_cid, _p, _uname)
                if _pool_ref:
                    _pool_ref.submit(_ask)
                return

    # ── Кнопки ────────────────────────────────────────────────────
    if text == "🎮 Игры":
        from utils import bot
        bot.send_message(chat_id, "🎮 Выбери игру:", reply_markup=group_games_kb(chat_id))
        return

    if text == "🤖 Спросить ИИ":
        from ai.client import is_enabled
        if not is_enabled():
            send_group(chat_id, "❌ ИИ недоступен.")
            return
        _group_awaiting[chat_id] = ("ai", uid)
        send_group(chat_id, f"🤖 {uname}, задай вопрос — напиши его следующим сообщением:")
        return

    if text == "🌍 Перевести":
        _group_awaiting[chat_id] = ("translate", uid)
        send_group(chat_id, f"🌍 {uname}, напиши текст для перевода:")
        return

    if text == "🌤 Погода":
        _group_awaiting[chat_id] = ("weather", uid)
        send_group(chat_id, f"🌤 {uname}, напиши название города:")
        return

    if text == "🔤 Язык":
        from utils import bot
        bot.send_message(chat_id, "Выбери направление:", reply_markup=lang_kb(LANG_NAMES))
        return

    if text in LANG_NAMES.values():
        for code, name in LANG_NAMES.items():
            if text == name:
                update_user_field(uid, "lang_pair", code)
                send_group(chat_id, f"✅ {uname}: {name}")
                return

    if text == "🏆 Рейтинг":
        from games.dm_games import get_leaderboard_text
        send_group(chat_id, get_leaderboard_text())
        return

    if text == "❓ Помощь":
        send_group(chat_id,
            "🎮 Игры | 🤖 ИИ | 🌍 Перевести | 🌤 Погода | 🏆 Рейтинг\n"
            "/gadmin — панель admin'а (только admin)\n"
            "🔫 Мафия — запуск игры")
        return

    if text == "🔫 Мафия":
        from games.mafia import maf_open_group
        maf_open_group(chat_id, uid)
        return

    # ── /ai команда в группе ─────────────────────────────────────
    if tl.startswith("/ai ") or tl.startswith("спроси ии "):
        q = text.split(" ", 1)[1].strip() if " " in text else ""
        if q and _pool_ref:
            _pool_ref.submit(_group_ai_respond, chat_id, q, uname)
        return

    # ── Упоминание бота ───────────────────────────────────────────
    bot_name = None
    try:
        from utils import bot as _bot
        bot_name = _bot.get_me().username
    except Exception:
        pass

    if bot_name and f"@{bot_name}" in text:
        q = text.replace(f"@{bot_name}", "").strip()
        if q and _pool_ref:
            _pool_ref.submit(_group_ai_respond, chat_id, q, uname)
        return


def _group_ai_respond(chat_id: int, prompt: str, sender_name: str = ""):
    """ИИ отвечает в группу. Сначала 15с перехват для admin'а."""
    import uuid
    from ai.client import ask, is_enabled
    from handlers.admin import _ai_intercept

    if not is_enabled():
        send_group(chat_id, "❌ ИИ недоступен.")
        return

    full_prompt = f"{sender_name}: {prompt}" if sender_name else prompt

    # Перехват для admin'а
    ic_key  = f"grp_{chat_id}_{uuid.uuid4().hex[:8]}"
    ic_data = {"cancelled": False, "chat_id": chat_id, "group": True, "msg_ids": []}
    _ai_intercept[ic_key] = ic_data

    # Отменяем старые перехваты этой группы
    for k in list(_ai_intercept.keys()):
        if k != ic_key and _ai_intercept[k].get("chat_id") == chat_id and _ai_intercept[k].get("group"):
            _ai_intercept[k]["cancelled"] = True
            for mid_pair in _ai_intercept.pop(k, {}).get("msg_ids", []):
                try:
                    from utils import bot
                    bot.edit_message_reply_markup(chat_id=mid_pair[0], message_id=mid_pair[1], reply_markup=None)
                except Exception:
                    pass

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
                    f"👥 Группа | {sender_name}: «{prompt[:150]}»\n⏱ 15с → ответь или ИИ ответит",
                    reply_markup=kbi)
                ic_data["msg_ids"].append((aid, sent.message_id))
            except Exception:
                pass

    time.sleep(15)

    ic = _ai_intercept.pop(ic_key, {})
    if ic.get("cancelled"):
        return

    answer = ask(full_prompt, chat_id=chat_id)
    if answer:
        send_group(chat_id, f"🤖 ИИ: {answer}")
        if GROUP_AUTO_VOICE and _pool_ref:
            _pool_ref.submit(send_voice_msg, chat_id, answer[:200])


def _send_gadm_panel(uid: int, chat_id: int):
    """Отправляет admin-панель для группы."""
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    members = _group_users.get(chat_id, set())
    cnt = len(members)
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(f"💀 Хоррор всем ({cnt}чел)", callback_data=f"gadm_horror_{chat_id}"),
        InlineKeyboardButton("🛑 Стоп все игры",            callback_data=f"gadm_stopgame_{chat_id}"),
        InlineKeyboardButton("📤 Рассылка в группу",        callback_data=f"gadm_broadcast_{chat_id}"),
        InlineKeyboardButton(f"📊 Кто в группе ({cnt})",   callback_data=f"gadm_list_{chat_id}"),
        InlineKeyboardButton("🤖 ИИ пишет в группу",       callback_data=f"gadm_aiwrite_{chat_id}"),
    )
    try:
        from utils import bot
        bot.send_message(chat_id, "⚡ Панель управления группой:", reply_markup=kb)
    except Exception:
        send(uid, "⚠️ Бот не может писать в группу. Проверь права.")


def get_group_users(chat_id: int) -> set:
    return _group_users.get(chat_id, set())


def add_group_user(chat_id: int, uid: int):
    if chat_id not in _group_users:
        _group_users[chat_id] = set()
    _group_users[chat_id].add(uid)
