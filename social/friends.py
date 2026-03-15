"""
social/friends.py — Система приглашений. Жертва приводит друга.
"""
import uuid
import logging

from utils import send, bot
from database import get_user, update_user_field, create_invite, use_invite
from horror.engine import check_achievement, start_horror

log = logging.getLogger("horror.friends")


def generate_invite_link(uid: int) -> str:
    """Создаёт уникальную ссылку-приглашение."""
    code = f"inv_{uid}_{uuid.uuid4().hex[:8]}"
    create_invite(code, uid)
    bot_info = bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={code}"
    return link, code


def send_invite_to_user(uid: int):
    """Генерирует и отправляет invite-ссылку пользователю."""
    u = get_user(uid)
    stage = u.get("stage", 0)
    link, code = generate_invite_link(uid)

    if stage < 2:
        msg = (
            f"🤝 ПРИГЛАСИ ДРУГА\n\n"
            f"Отправь другу эту ссылку:\n{link}\n\n"
            f"Когда он начнёт — ты получишь 50 очков!"
        )
    else:
        msg = (
            f"👁 ...ты не один в этом.\n\n"
            f"Приведи ещё одного. Вот ссылка:\n{link}\n\n"
            f"...мне нужно больше."
        )
    from keyboards import main_kb
    send(uid, msg, kb=main_kb(stage))


def process_invite(new_uid: int, code: str, pool=None) -> bool:
    """Обрабатывает использование invite-кода."""
    inviter_uid = use_invite(code, new_uid)
    if not inviter_uid:
        return False

    inviter = get_user(inviter_uid)
    new_user = get_user(new_uid)

    # Награждаем пригласившего
    new_score = inviter.get("score", 0) + 50
    update_user_field(inviter_uid, "score", new_score)
    check_achievement(inviter_uid, "invited_friend", pool)

    from keyboards import main_kb
    send(inviter_uid,
        f"👤 Твой друг {new_user.get('name') or 'Новая жертва'} принял приглашение!\n"
        f"🏆 +50 очков. Итого: {new_score}",
        kb=main_kb(inviter.get("stage", 0)))

    log.info(f"Invite used: inviter={inviter_uid}, new={new_uid}")
    return True
