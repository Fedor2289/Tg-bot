"""
social/anon_chat.py — Анонимный чат жертв. Они не знают что их несколько.
"""
import time
import logging

from utils import send
from database import get_user, get_all_users, add_anon_message, get_anon_messages

log = logging.getLogger("horror.anon_chat")

_chat_mode = {
    "active":   False,
    "end_time": 0,
    "anon":     True,
}


def chat_mode_active() -> bool:
    if not _chat_mode["active"]:
        return False
    if time.time() > _chat_mode["end_time"]:
        _chat_mode["active"] = False
        return False
    return True


def start_chat_mode(admin_uid: int, minutes: int = 5, anon: bool = True, admins: set = None, pool=None):
    from keyboards import main_kb
    all_users = get_all_users()
    victims = [u for u in all_users
               if not (admins and u["uid"] in admins)
               and not u.get("stopped") and not u.get("banned")]

    if len(victims) < 2:
        send(admin_uid, "❌ Нужно минимум 2 жертвы для чата.")
        return

    _chat_mode["active"]   = True
    _chat_mode["end_time"] = time.time() + minutes * 60
    _chat_mode["anon"]     = anon

    intro = (
        "📡 ВХОДЯЩИЙ СИГНАЛ...\n\n"
        "Ты не один.\n"
        "Рядом есть другие.\n"
        "Они тоже не знают где находятся.\n\n"
        f"У вас есть {minutes} минут.\n"
        "Говорите."
    )
    for v in victims:
        send(v["uid"], intro, kb=main_kb(v.get("stage", 0)))

    send(admin_uid, f"✅ Чат запущен для {len(victims)} жертв на {minutes} мин.")


def stop_chat_mode(admin_uid: int):
    _chat_mode["active"] = False
    all_users = get_all_users()
    for u in all_users:
        if not u.get("stopped"):
            try:
                send(u["uid"], "📡 Связь прервана. Мы снова наедине. 👁")
            except Exception:
                pass
    send(admin_uid, "✅ Чат остановлен.")


def broadcast_to_chat(sender_uid: int, text: str, admins: set = None):
    """Рассылает сообщение всем в чат-режиме (кроме отправителя)."""
    if not chat_mode_active():
        return

    u = get_user(sender_uid)
    if _chat_mode["anon"]:
        label = f"👤 Незнакомец_{str(sender_uid)[-3:]}"
    else:
        label = f"👤 {u.get('name') or 'Незнакомец'}"

    msg = f"{label}:\n{text}"
    add_anon_message(sender_uid, text)

    all_users = get_all_users()
    for victim in all_users:
        vid = victim["uid"]
        if vid == sender_uid:
            continue
        if admins and vid in admins:
            continue
        if victim.get("stopped") or victim.get("muted"):
            continue
        try:
            send(vid, msg)
        except Exception:
            pass


def get_chat_history_text() -> str:
    msgs = get_anon_messages(20)
    if not msgs:
        return "💬 История пуста."
    lines = [f"👤 ID:{m['uid']}: {m['text'][:100]}" for m in reversed(msgs)]
    return "💬 ПОСЛЕДНИЕ СООБЩЕНИЯ ЖЕРТВ\n\n" + "\n".join(lines)
