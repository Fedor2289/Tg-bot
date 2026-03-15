"""
handlers/callbacks.py — Все inline callback-обработчики.
"""
import time
import logging

from utils import send, send_group, bot
from database import get_user, update_user_field

log = logging.getLogger("horror.callbacks")

_pool_ref   = None
_admins_ref = None

def init(pool, admins: set):
    global _pool_ref, _admins_ref
    _pool_ref   = pool
    _admins_ref = admins


def handle_callback(call, uid: int, data: str):
    """Главный диспетчер всех inline-кнопок."""
    try:
        _dispatch(call, uid, data)
    except Exception as e:
        log.error(f"callback crashed uid={uid} data={data}: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "⚠️ Ошибка")
        except Exception:
            pass


def _dispatch(call, uid: int, data: str):
    chat_id = call.message.chat.id

    # ── ИИ-перехват ───────────────────────────────────────────────
    if data.startswith("ai_ic_"):
        parts = data.split("_")
        try:
            aid = int(parts[-1])
            intercept_key = "_".join(parts[2:-1])
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка"); return

        from handlers.admin import get_ai_intercept, handle_ai_ic_callback
        handle_ai_ic_callback(call, aid, intercept_key, _admins_ref or set())
        return

    # ── Магазин ───────────────────────────────────────────────────
    if data.startswith("shop_"):
        parts = data.split("_", 2)
        if len(parts) >= 3:
            item_id = parts[1] + "_" + parts[2].rsplit("_", 1)[0]
            # Format: shop_{item_id}_{uid}
            try:
                target_uid = int(data.rsplit("_", 1)[-1])
            except Exception:
                target_uid = uid
            from horror.engine import shop_buy, get_shop_text
            ok, msg = shop_buy(target_uid, item_id, pool=_pool_ref)
            bot.answer_callback_query(call.id, msg[:200])
            if ok:
                try:
                    from keyboards import shop_kb
                    bot.edit_message_text(
                        get_shop_text(target_uid),
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=shop_kb(target_uid)
                    )
                except Exception:
                    pass
        return

    # ── Ачивки ────────────────────────────────────────────────────
    if data.startswith("achievements_"):
        try:
            target_uid = int(data.split("_")[1])
        except Exception:
            target_uid = uid
        from horror.engine import get_achievements_text
        bot.answer_callback_query(call.id)
        send(uid, get_achievements_text(target_uid))
        return

    # ── Групповые игры ────────────────────────────────────────────
    if data.startswith("gg_"):
        _handle_group_game_callback(call, uid, chat_id, data)
        return

    # ── Admin: gadm_ ─────────────────────────────────────────────
    if data.startswith("gadm_") and _admins_ref and uid in _admins_ref:
        _handle_gadm_callback(call, uid, chat_id, data)
        return

    # ── Мафия v20 ─────────────────────────────────────────────────
    if data.startswith("maf_"):
        _handle_mafia_callback(call, uid, chat_id, data)
        return

    # ── AI backend switch ─────────────────────────────────────────
    if data.startswith("admin_ai_") and _admins_ref and uid in _admins_ref:
        backend = data.split("_")[-1]
        bot.answer_callback_query(call.id, f"Переключено на {backend}")
        # TODO: reload ai client
        return

    bot.answer_callback_query(call.id)


# ── Групповые игры ────────────────────────────────────────────────
def _handle_group_game_callback(call, uid: int, chat_id: int, data: str):
    parts = data.split("_")
    action = parts[1]
    try:
        cid = int(parts[-1])
    except Exception:
        cid = chat_id

    from handlers.group import get_group_users
    uname = call.from_user.first_name or f"ID:{uid}"
    u = get_user(uid)

    bot.answer_callback_query(call.id)

    if action == "bottle":
        members = list(get_group_users(cid) - {uid})
        if not members:
            send_group(cid, "❌ Нужно больше участников!"); return
        chosen = __import__('random').choice(members)
        c_name = get_user(chosen).get("name") or f"ID:{chosen}"
        send_group(cid, f"🍾 {uname} крутит бутылку...\n\n🎯 Бутылка указывает на: {c_name}!")
        if __import__('random').random() < 0.4 and _pool_ref:
            from ai.client import ask
            _pool_ref.submit(lambda: send_group(cid, f"🤖 ИИ: {ask(f'Придумай задание для {c_name} после того как бутылка указала на него. 1-2 предложения.', chat_id=cid)}"))
        return

    if action == "coin":
        result = __import__('random').choice(["ОРЁЛ 🦅", "РЕШКА 🪙"])
        send_group(cid, f"🪙 {uname} бросает монетку...\n\n{result}!"); return

    if action == "dice":
        val = __import__('random').randint(1, 6)
        send_group(cid, f"🎲 {uname} бросает кубик... выпало {val}!"); return

    if action == "roulette":
        chamber = __import__('random').randint(1, 6)
        if chamber == 1:
            send_group(cid, f"🔫 {uname} нажимает курок...\n\n💥 БАМ! ...ты выбываешь!")
        else:
            send_group(cid, f"🔫 {uname} нажимает курок...\n\n*щелчок* Повезло. Пока.")
        return

    if action == "tod":
        choice = __import__('random').choice(["ПРАВДА", "ДЕЙСТВИЕ"])
        send_group(cid, f"🎭 {uname} выбирает...\n\n{choice}!")
        if _pool_ref:
            from ai.client import ask
            prompt = f"Игрок {uname} выбрал {'правду' if choice == 'ПРАВДА' else 'действие'}. Придумай вопрос/задание. 1 предложение."
            _pool_ref.submit(lambda p=prompt: send_group(cid, f"🤖 {ask(p, chat_id=cid)}"))
        return

    if action == "number":
        num = __import__('random').randint(1, 100)
        send_group(cid, f"🎲 {uname} загадал число от 1 до 100!\nПишите число в чат — угадаете?")
        return

    if action == "mafia":
        from games.mafia import maf_open_group
        maf_open_group(cid, uid)
        return

    if action == "aistory":
        from ai.client import ask
        if _pool_ref:
            _pool_ref.submit(lambda: send_group(cid,
                f"📖 ИИ начинает историю...\n\n{ask('Начни короткую мистическую историю для группы. 3-4 предложения.', chat_id=cid)}"))
        return

    if action == "stop":
        from games.group_games import _group_games
        _group_games.pop(cid, None)
        send_group(cid, "❌ Игра остановлена.", kb=__import__('keyboards', fromlist=['group_main_kb']).group_main_kb())
        return

    if action == "trivia":
        from games.rpg_data import TRIVIA_Q
        q, ans, opts = __import__('random').choice(TRIVIA_Q)
        shuffled = opts[:]
        __import__('random').shuffle(shuffled)
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(row_width=2)
        for o in shuffled:
            kb.add(InlineKeyboardButton(o, callback_data=f"gtrivia_{cid}_{o[:20]}_{ans[:20]}"))
        try:
            bot.send_message(cid, f"🧠 ГРУППОВАЯ ВИКТОРИНА!\n\n{q}", reply_markup=kb)
        except Exception:
            pass
        return


# ── Admin группа ─────────────────────────────────────────────────
def _handle_gadm_callback(call, uid: int, chat_id: int, data: str):
    from handlers.group import get_group_users
    bot.answer_callback_query(call.id)

    if data.startswith("gadm_aiwrite_manual_"):
        sub = data[len("gadm_aiwrite_manual_"):]
        try:
            cid_s, uid_s = sub.rsplit("_", 1)
            _cid = int(cid_s)
            _uid = int(uid_s)
        except Exception:
            return
        from handlers.admin import _adm_state, adm_ctx_reset
        adm_ctx_reset(_uid)
        _adm_state[_uid] = {"step": "wait_grp_aiwrite", "grp_cid": _cid}
        send(_uid, f"✍️ Пиши ответ для группы {_cid}:")
        return

    parts = data.split("_")
    action = parts[1]
    try:
        cid = int(parts[2])
    except Exception:
        return

    if action == "horror":
        cnt = 0
        from horror.engine import horror_tick, start_horror
        for vid in get_group_users(cid):
            if _admins_ref and vid not in _admins_ref:
                if _pool_ref:
                    _pool_ref.submit(horror_tick, vid)
                cnt += 1
        send_group(cid, f"💀 Хоррор запущен для {cnt} участников группы!")
        send(uid, f"✅ Хоррор → {cnt} участников")
        return

    if action == "stopgame":
        from games.group_games import _group_games
        _group_games.pop(cid, None)
        send_group(cid, "🛑 Все игры остановлены.")
        send(uid, "✅ Игры остановлены")
        return

    if action == "list":
        members = get_group_users(cid)
        lines = [f"  {get_user(v).get('name','?')} (ID:{v})" for v in members]
        send(uid, f"👥 Участников в группе {cid}: {len(members)}\n" + "\n".join(lines[:30]))
        return

    if action == "broadcast":
        from handlers.admin import _adm_state, adm_ctx_reset
        adm_ctx_reset(uid)
        _adm_state[uid] = {"step": "wait_grp_broadcast", "grp_cid": cid}
        bot.send_message(uid, f"Введи текст рассылки в группу {cid}:",
                        reply_markup=__import__('telebot.types', fromlist=['ReplyKeyboardRemove']).ReplyKeyboardRemove())
        return

    if action == "aiwrite":
        from ai.client import is_enabled
        if not is_enabled():
            send(uid, "❌ ИИ недоступен"); return
        members = get_group_users(cid)
        ctx_parts = []
        for mid in list(members)[:5]:
            h = get_user(mid).get("msg_history") or []
            if h:
                ctx_parts.append(f"{get_user(mid).get('name','?')}: {h[-1]}")
        ctx = "; ".join(ctx_parts) or "тихо в группе"

        import uuid
        from handlers.admin import _ai_intercept
        ic_key  = f"grp_{cid}_{uuid.uuid4().hex[:8]}"
        ic_data = {"cancelled": False, "chat_id": cid, "group": True, "msg_ids": []}
        _ai_intercept[ic_key] = ic_data

        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
        kbi = InlineKeyboardMarkup()
        kbi.add(InlineKeyboardButton("✍️ Написать самому", callback_data=f"gadm_aiwrite_manual_{cid}_{uid}"))
        sent = bot.send_message(uid,
            f"🤖 ИИ напишет в группу {cid}\nКонтекст: {ctx[:200]}\n\nНажми «✍️» за 15с иначе ИИ напишет сам.",
            reply_markup=kbi)
        ic_data["msg_ids"].append((uid, sent.message_id))

        def _auto(_cid=cid, _uid=uid, _mid=sent.message_id, _ctx=ctx, _ic_key=ic_key):
            time.sleep(15)
            ic = _ai_intercept.pop(_ic_key, {})
            if ic.get("cancelled"): return
            from ai.client import ask
            resp = ask(f"Напиши что-нибудь интересное или провокационное в чат группы. Контекст: {_ctx[:150]}. 1-2 предложения.", chat_id=_cid)
            if resp:
                send_group(_cid, f"🤖 {resp}")
                try:
                    bot.edit_message_text(f"✅ ИИ написал:\n«{resp}»", chat_id=_uid, message_id=_mid)
                except Exception:
                    pass

        if _pool_ref:
            _pool_ref.submit(_auto)
        return


# ── Мафия v20 callbacks ───────────────────────────────────────────
def _handle_mafia_callback(call, uid: int, chat_id: int, data: str):
    bot.answer_callback_query(call.id)
    parts = data.split("_")

    try:
        if data.startswith("maf_join_"):
            lid = int(parts[2])
            from games.mafia import maf_join, _maf
            ok, msg = maf_join(uid, lid)
            if ok:
                g = _maf.get(lid)
                if g:
                    players = len([p for p in g["players"] if p not in g["bots"]])
                    bot.send_message(chat_id, f"✅ {call.from_user.first_name} вступил! Игроков: {players}")
            else:
                send(uid, msg)
            return

        if data.startswith("maf_start_"):
            lid = int(parts[2])
            from games.mafia import maf_begin, _maf
            g = _maf.get(lid)
            if g and g.get("creator") == uid:
                if _pool_ref:
                    _pool_ref.submit(maf_begin, lid)
            else:
                send(uid, "❌ Только создатель может запустить игру.")
            return

        if data.startswith("maf_cancel_"):
            lid = int(parts[2])
            from games.mafia import _maf, _maf_send_all
            g = _maf.get(lid)
            if g and g.get("creator") == uid:
                _maf_send_all(lid, "❌ Лобби отменено.")
                _maf.pop(lid, None)
            return

        if data.startswith("maf_v_"):
            lid = int(parts[2])
            target_uid = int(parts[3])
            from games.mafia import _maf, _maf_check_votes, _maf_send_all
            g = _maf.get(lid)
            if g and g["phase"] == "day" and uid in g["alive"] and uid not in g["votes"]:
                g["votes"][uid] = target_uid
                voted = len(g["votes"])
                total = len(g["alive"])
                _maf_send_all(lid, f"🗳 Проголосовало: {voted}/{total}")
                if _pool_ref:
                    _pool_ref.submit(_maf_check_votes, lid)
            return

        if data.startswith("maf_vs_"):
            lid = int(parts[2])
            from games.mafia import _maf, _maf_check_votes, _maf_send_all
            g = _maf.get(lid)
            if g and g["phase"] == "day" and uid in g["alive"] and uid not in g["votes"]:
                g["votes"][uid] = None
                _maf_send_all(lid, f"🗳 {g['player_names'].get(uid,'?')} воздержался.")
                if _pool_ref:
                    _pool_ref.submit(_maf_check_votes, lid)
            return

        if data.startswith("maf_n_"):
            lid = int(parts[2])
            voter_uid  = int(parts[3])
            target_uid = int(parts[4])
            from games.mafia import _maf, _maf_check_night
            g = _maf.get(lid)
            if g and g["phase"] == "night" and voter_uid == uid and uid in g["alive"]:
                g.setdefault("night_actions", {})[uid] = target_uid
                send(uid, f"✅ Выбор сделан.")
                if _pool_ref:
                    _pool_ref.submit(_maf_check_night, lid)
            return

    except Exception as e:
        log.debug(f"Mafia callback error: {e}")
