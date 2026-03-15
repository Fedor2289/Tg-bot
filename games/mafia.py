"""
games/mafia.py — Мафия v20: единый движок для ЛС и групп, ИИ-боты.
"""
import time
import random
import threading
import logging

from utils import send, send_group, send_voice_msg, send_gif, get_random_gif
from database import get_user, update_user_field
from ai.client import ask, ask_host
from horror.engine import check_achievement
from config import GROUP_AUTO_VOICE
from keyboards import maf_lobby_kb, maf_vote_kb, maf_night_kb

log = logging.getLogger("horror.mafia")

# Pool reference (set by main.py)
_pool_ref = None
def set_pool(p): 
    global _pool_ref
    _pool_ref = p

class _Pool:
    """Lazy pool proxy."""
    def submit(self, fn, *args, **kwargs):
        if _pool_ref:
            return _pool_ref.submit(fn, *args, **kwargs)
        import threading
        t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
        t.start()
        return t

_pool = _Pool()

# ── Мафия v20: хранилища ────────────────────────────────────
_maf: dict          = {}   # lobby_id → state dict
_maf_uid: dict      = {}   # uid → lobby_id (все участники + боты)
_maf_counter: list  = [0]  # счётчик lobby_id

_MAF_BOT_NAMES = [
    "Алексей","Борис","Виктория","Дмитрий","Елена",
    "Жанна","Захар","Ирина","Кирилл","Людмила",
    "Максим","Наталья","Олег","Павел","Рита",
    "Сергей","Татьяна","Ульяна","Фёдор","Юля",
]
_MAF_BOT_BASE     = -3000   # отрицательные ID для ИИ-ботов
_MAF_LOBBY_TIMEOUT = 300    # 5 минут ожидания лобби
_MAF_MIN_PLAYERS   = 7      # минимум игроков для старта

MAFIA_ROLE_DESC = {
    "мафия":   "🔫 МАФИЯ\n\nТы — мафия. Убивай мирных жителей ночью.\nНикому не раскрывай свою роль!",
    "мирный":  "👤 МИРНЫЙ ЖИТЕЛЬ\n\nТы — обычный житель.\nДнём голосуй против мафии.",
    "шериф":   "🔎 ШЕРИФ\n\nКаждую ночь проверяй игрока — мафия это или нет.\nРаскрывайся осторожно!",
    "доктор":  "🏥 ДОКТОР\n\nКаждую ночь спасай одного игрока от убийства.\nМожешь лечить себя.",
    "маньяк":  "🔪 МАНЬЯК\n\nТы — одиночка. Убивай всех. Побеждаешь если останешься один.",
}

def _maf_new_bot_id(g) -> int:
    existing = [p for p in g["players"] if p < 0]
    return _MAF_BOT_BASE - len(existing)


def _maf_assign_roles(players: list) -> dict:
    n = len(players)
    pool = list(players)
    random.shuffle(pool)
    roles = {}
    # Количество мафии: 2 на 7-8, 3 на 9-11, 4 на 12+
    mafia_n = 2 if n <= 8 else (3 if n <= 11 else 4)
    idx = 0
    for _ in range(mafia_n):
        roles[pool[idx]] = "мафия"; idx += 1
    roles[pool[idx]] = "шериф"; idx += 1
    roles[pool[idx]] = "доктор"; idx += 1
    if n >= 9:
        roles[pool[idx]] = "маньяк"; idx += 1
    for i in range(idx, n):
        roles[pool[i]] = "мирный"
    return roles


def _maf_fill_bots(g, needed: int) -> list:
    """Добавляет needed ИИ-ботов. Возвращает их имена."""
    used = set(g["player_names"].values())
    avail = [x for x in _MAF_BOT_NAMES if x not in used]
    random.shuffle(avail)
    added = []
    for i in range(needed):
        name = avail[i % len(avail)] if avail else f"Бот{i+1}"
        bid = _maf_new_bot_id(g)
        g["players"].append(bid)
        g["player_names"][bid] = name
        g["bots"].add(bid)
        added.append(name)
    return added


def _maf_is_group(g) -> bool:
    return g.get("mode") == "group"


def _maf_send_all(lobby_id: int, text: str, kb=None):
    """Отправляет всем живым реальным игрокам."""
    g = _maf.get(lobby_id)
    if not g:
        return
    bots = g["bots"]
    if _maf_is_group(g):
        cid = g.get("chat_id")
        if cid:
            send_group(cid, text, kb=kb)
    else:
        # В ЛС — рассылаем каждому
        for uid in list(g.get("alive", g["players"])):
            if uid in bots:
                continue
            try:
                if kb:
                    bot.send_message(uid, text, reply_markup=kb)
                else:
                    send(uid, text)
            except Exception:
                pass


def _maf_send_one(uid: int, text: str, kb=None):
    """Отправляет одному реальному игроку."""
    try:
        if kb:
            bot.send_message(uid, text, reply_markup=kb)
        else:
            send(uid, text)
    except Exception:
        pass


def _maf_alive_text(g) -> str:
    bots = g["bots"]
    return "\n".join(
        f"  👤 {g['player_names'].get(uid,'?')}"
        for uid in g["alive"]
    )


# ─── Создание лобби ────────────────────────────────────────

def maf_create(creator_uid: int, mode: str = "dm", chat_id: int = 0) -> int:
    """Создаёт лобби. mode='dm' или 'group'."""
    _maf_counter[0] += 1
    lid = _maf_counter[0]
    # Группа: создатель не добавляется автоматически — вступает через кнопку
    # ЛС: создатель сразу в лобби
    if mode == "dm" and creator_uid and creator_uid > 0:
        u = get_user(creator_uid)
        name = u.get("name") or f"Игрок{creator_uid % 1000}"
        init_players    = [creator_uid]
        init_names      = {creator_uid: name}
    else:
        init_players = []
        init_names   = {}
    _maf[lid] = {
        "lid": lid,
        "mode": mode,
        "chat_id": chat_id,        # для группы
        "creator": creator_uid,
        "players": init_players,
        "player_names": init_names,
        "bots": set(),
        "state": "lobby",          # lobby / playing
        "phase": "day",
        "roles": {},
        "alive": [],
        "votes": {},               # uid → target_uid (None = воздержался)
        "night_actions": {},       # uid → target_uid
        "day_num": 0,
        "msg_ids": [],             # id сообщений лобби (для обновления)
    }
    if mode == "dm" and creator_uid and creator_uid > 0:
        _maf_uid[creator_uid] = lid
    return lid


def maf_join(uid: int, lobby_id: int) -> tuple:
    """Вступить в лобби. → (ok: bool, msg: str)."""
    g = _maf.get(lobby_id)
    if not g:
        return False, "❌ Лобби не найдено."
    if g["state"] != "lobby":
        return False, "❌ Игра уже началась."
    if uid in g["players"]:
        return False, "⚠️ Ты уже участвуешь!"
    if len(g["players"]) >= 15:
        return False, "❌ Лобби заполнено (макс 15)."
    u = get_user(uid)
    name = u.get("name") or f"Игрок{uid % 1000}"
    g["players"].append(uid)
    g["player_names"][uid] = name
    _maf_uid[uid] = lobby_id
    return True, f"✅ {name} вступил в лобби!"


def _maf_lobby_kb(lid: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("✅ Участвую!", callback_data=f"maf_join_{lid}"),
        InlineKeyboardButton("▶️ Старт (добавить ботов если мало)", callback_data=f"maf_start_{lid}"),
        InlineKeyboardButton("❌ Отменить", callback_data=f"maf_cancel_{lid}"),
    )
    return kb


def _maf_lobby_text(lid: int) -> str:
    g = _maf.get(lid)
    if not g:
        return "Лобби не найдено."
    bots = g.get("bots", set())
    names = "\n".join(
        f"  👤 {g['player_names'].get(p,'?')}"
        for p in g["players"]
    )
    real_count = len([p for p in g["players"] if p not in g.get("bots", set())])
    need = max(0, _MAF_MIN_PLAYERS - real_count)
    need_str = f"\n⏳ Нужно ещё игроков: {need} (или нажми Старт — добавим ботов)" if need > 0 else "\n✅ Достаточно игроков!"
    names_str = names if names.strip() else "  (пока никого)"
    return (
        f"🔫 МАФИЯ — Лобби #{lid}\n\n"
        f"Реальных игроков: {real_count}/{_MAF_MIN_PLAYERS}+{need_str}\n\n"
        f"Участники:\n{names_str}\n\n"
        f"⏱ Лобби ждёт 5 мин, затем ИИ-боты заполнят свободные места.\n"
        f"Или нажми «▶️ Старт» прямо сейчас!"
    )


# ─── Старт лобби в ЛС ──────────────────────────────────────

def maf_open_dm(uid: int):
    """Открывает лобби мафии в ЛС."""
    if uid in _maf_uid:
        lid = _maf_uid[uid]
        send(uid, f"⚠️ Ты уже в лобби #{lid}.\nНапиши /leavem чтобы выйти.")
        return
    lid = maf_create(uid, mode="dm")
    g = _maf[lid]
    msg = bot.send_message(uid, _maf_lobby_text(lid), reply_markup=_maf_lobby_kb(lid))
    g["msg_ids"].append((uid, msg.message_id))

    # Таймер 5 минут
    def _timer(_lid=lid):
        time.sleep(_MAF_LOBBY_TIMEOUT)
        g2 = _maf.get(_lid)
        if g2 and g2["state"] == "lobby":
            _maf_send_all(_lid, "⏱ Время вышло! Добавляем ИИ-ботов...")
            _pool.submit(maf_begin, _lid)
    _pool.submit(_timer)

    send(uid,
        f"🔫 Лобби #{lid} открыто!\n\n"
        f"Поделись ID с друзьями — пусть напишут боту /joinm {lid}\n"
        f"Или перешли им сообщение выше.\n\n"
        f"Мин. {_MAF_MIN_PLAYERS} игроков. Лобби ждёт 5 мин."
    )


# ─── Старт лобби в группе ──────────────────────────────────

def maf_open_group(chat_id: int, creator_uid: int):
    """Открывает лобби мафии в группе."""
    if chat_id in _group_mafia:
        info = _group_mafia[chat_id]
        if info.get("state") == "playing":
            send_group(chat_id, "⚠️ Мафия уже идёт!")
            return
        # Если уже есть лобби — показываем его
        lid_existing = info.get("lid")
        if lid_existing and _maf.get(lid_existing, {}).get("state") == "lobby":
            send_group(chat_id, _maf_lobby_text(lid_existing), kb=_maf_lobby_kb(lid_existing))
            return
    lid = maf_create(creator_uid, mode="group", chat_id=chat_id)
    _group_mafia[chat_id] = {"state": "lobby", "lid": lid}

    # Если создатель реальный — добавляем его сразу в лобби
    if creator_uid and creator_uid > 0:
        u_cr = get_user(creator_uid)
        cr_name = u_cr.get("name") or f"Игрок{creator_uid % 1000}"
        g_cr = _maf.get(lid)
        if g_cr and creator_uid not in g_cr["players"]:
            g_cr["players"].append(creator_uid)
            g_cr["player_names"][creator_uid] = cr_name
            _maf_uid[creator_uid] = lid

    msg = bot.send_message(chat_id, _maf_lobby_text(lid), reply_markup=_maf_lobby_kb(lid))

    # Таймер 5 минут
    def _timer(_lid=lid, _cid=chat_id):
        time.sleep(_MAF_LOBBY_TIMEOUT)
        g2 = _maf.get(_lid)
        if g2 and g2["state"] == "lobby":
            send_group(_cid, "⏱ Время вышло! Добавляем ИИ-ботов и начинаем!")
            _pool.submit(maf_begin, _lid)
    _pool.submit(_timer)


# ─── Запуск игры ───────────────────────────────────────────

def maf_begin(lobby_id: int):
    """Запускает игру. Добавляет ботов если нужно."""
    g = _maf.get(lobby_id)
    if not g or g["state"] != "lobby":
        return

    # Добавляем ботов
    cur = len(g["players"])
    if cur < _MAF_MIN_PLAYERS:
        needed = _MAF_MIN_PLAYERS - cur
        added = _maf_fill_bots(g, needed)
        bots_note = ""  # Скрываем что добавили ботов
    else:
        bots_note = ""

    # Назначаем роли
    roles = _maf_assign_roles(g["players"])
    g["roles"] = roles
    g["alive"] = list(g["players"])
    g["state"] = "playing"
    g["phase"] = "day"
    g["day_num"] = 1
    g["votes"] = {}
    g["night_actions"] = {}
    g["chat_log"] = []  # [(name, text), ...] — история чата для контекста ботов
    bots = g["bots"]
    is_group = _maf_is_group(g)
    # Синхронизируем состояние группы
    if is_group and g.get("chat_id"):
        _group_mafia[g["chat_id"]]["state"] = "playing"

    # Статистика состава
    n = len(g["players"])
    bots_n = len(bots)
    real_n = n - bots_n

    # Объявление старта
    start_text = (
        f"🎭 МАФИЯ НАЧИНАЕТСЯ!\n\n"
        f"Игроков: {n}\n\n"
        f"{'💬 Общайтесь! Ваши сообщения видят все живые игроки.' if not is_group else '💬 Общайтесь прямо в группе!'}\n"
        f"Ночные действия (шериф/доктор/мафия) — приходят в личку бота."
    )
    _maf_send_all(lobby_id, start_text)

    # Рассылаем роли реальным игрокам
    for uid in g["players"]:
        if uid in bots:
            continue
        role = roles.get(uid, "мирный")
        role_text = MAFIA_ROLE_DESC.get(role, "")
        _maf_send_one(uid,
            f"🎭 Твоя роль:\n\n{role_text}"
        )

    # ИИ-ведущий — вступительное слово (в фоне)
    def _intro(_lid=lobby_id):
        g2 = _maf.get(_lid)
        if not g2:
            return
        names = [g2["player_names"].get(p, "?") for p in g2["players"] if p not in g2["bots"]]
        intro = ask(
            f"Игроки: {', '.join(names[:8])}. Начало. Объяви — 2 предложения, зловеще.",
            chat_id=_lid)
        _maf_send_all(_lid, f"🎭 Ведущий:\n\n{intro}")
        time.sleep(3)
        _maf_day(_lid)

    _pool.submit(_intro)


# ─── День ──────────────────────────────────────────────────

def _maf_vote_kb(lid: int) -> InlineKeyboardMarkup:
    g = _maf.get(lid)
    if not g:
        return InlineKeyboardMarkup()
    bots = g["bots"]
    kb = InlineKeyboardMarkup(row_width=1)
    for uid in g["alive"]:
        name = g["player_names"].get(uid, "?")
        kb.add(InlineKeyboardButton(
            f"⚖️ {name}",
            callback_data=f"maf_v_{lid}_{uid}"
        ))
    kb.add(InlineKeyboardButton("⏭ Воздержаться", callback_data=f"maf_vs_{lid}"))
    return kb


def _maf_day(lobby_id: int):
    g = _maf.get(lobby_id)
    if not g or g["state"] != "playing":
        return
    g["phase"] = "day"
    g["votes"] = {}
    bots = g["bots"]

    alive_text = _maf_alive_text(g)

    # ИИ-ведущий объявляет день
    host = ask_host(
                f"День {g['day_num']}. Живых: {len(g['alive'])}. Кто следующий? 1-2 предложения.",
                chat_id=lobby_id
            )

    vote_kb = _maf_vote_kb(lobby_id)
    day_msg = (
        f"☀️ ДЕНЬ {g['day_num']}\n\n"
        f"🎭 Ведущий: {host}\n\n"
        f"Живые игроки:\n{alive_text}\n\n"
        f"💬 Обсуждайте! Голосуй кого устранить:"
    )

    if _maf_is_group(g):
        send_group(g["chat_id"], day_msg, kb=vote_kb)
    else:
        for uid in g["alive"]:
            if uid in bots:
                continue
            _maf_send_one(uid, day_msg, kb=vote_kb)

    # ИИ-боты пишут обсуждение — реалистичный чат с паузами
    def _bots_day(_lid=lobby_id):
        g2 = _maf.get(_lid)
        if not g2 or g2["phase"] != "day":
            return
        bots2 = g2["bots"]
        is_grp_mode = _maf_is_group(g2)

        # Shuffled порядок — каждый раз разный
        bot_list = [b for b in list(bots2) if b in g2["alive"]]
        random.shuffle(bot_list)

        # Список последних сказанных фраз — боты цепляются друг за друга
        recent_chat: list = []  # [(имя, фраза), ...]

        for i, bid in enumerate(bot_list):
            # Индивидуальная пауза перед первым словом
            time.sleep(random.uniform(5, 15))
            g3 = _maf.get(_lid)
            if not g3 or g3["phase"] != "day":
                return  # фаза кончилась — выходим полностью
            if bid not in g3["alive"]:
                continue  # этот бот умер — пропускаем, остальные говорят

            bname = g3["player_names"].get(bid, "?")
            brole = g3["roles"].get(bid, "мирный")
            is_mafia = brole == "мафия"
            all_alive_names = [g3["player_names"].get(p, "?") for p in g3["alive"] if p != bid]

            # Имена РЕАЛЬНЫХ игроков в игре (не ботов)
            real_player_names = [g3["player_names"].get(p,"?") for p in g3["alive"] if p not in bots2]
            real_ctx = f"Реальные игроки рядом с тобой: {', '.join(real_player_names[:4])}. " if real_player_names else ""

            # Контекст последних реплик (включая реальных игроков!)
            ctx = real_ctx
            full_chat = list(g3.get("chat_log", [])) + recent_chat
            full_chat = full_chat[-4:]  # последние 4 реплики
            if full_chat:
                ctx_lines = [f"{n}: «{t}»" for n, t in full_chat]
                ctx += f"Последнее в чате: {'; '.join(ctx_lines)}. "

            # Тип поведения зависит от роли
            strats = ["подозрение", "защита", "вопрос", "уклонение"]
            if is_mafia:
                strats = ["защита", "ложное_обвинение", "уклонение", "отвлечение"]

            strat = random.choice(strats)
            suspect = random.choice([n for n in all_alive_names if n != bname] or ["кто-то"])

            # Стиль: незнакомцы, которых насильно втянули в игру
            # Мирные — растеряны, напуганы, пытаются разобраться
            # Мафия — притворяются такими же растерянными
            strategy_hints = {
                "подозрение":       f"Ты не знаешь никого здесь. Скажи что {suspect} ведёт себя странно. 6-9 слов.",
                "защита":           f"Ты растерян и защищаешься. Скажи что не понимаешь зачем тебя обвиняют. 6-9 слов.",
                "вопрос":           f"Ты в панике. Спроси у кого-то из игроков что вообще происходит. 5-8 слов.",
                "уклонение":        f"Ты нервничаешь. Скажи что-то расплывчатое, как будто скрываешь страх. 5-8 слов.",
                "ложное_обвинение": f"Притворись напуганным мирным. Намекни что {suspect} подозрителен — хотя сам мафия. 7-10 слов.",
                "отвлечение":       f"Смени тему — скажи что-то неожиданное, как будто вспомнил что-то важное. 5-8 слов.",
            }

            hint = strategy_hints.get(strat, "1 фраза, 6-9 слов.")
            if is_grp_mode:
                # Группа: боты общаются как знакомые по контексту чата
                if is_mafia:
                    role_ctx = "Ты в компании знакомых. Но ты тайный предатель — веди себя непринуждённо, не выдавай себя."
                else:
                    role_ctx = "Ты среди знакомых людей. Общайся непринуждённо, реагируй на то что они говорили."
                prompt = (
                    f"Тебя зовут {bname}. {role_ctx} "
                    f"День {g3['day_num']} в Мафии. Живые: {', '.join(all_alive_names[:5])}. "
                    f"{ctx}"
                    f"{hint} "
                    f"Отвечай коротко, как в живом чате с друзьями. Без смайлов. От первого лица. "
                    f"НЕ говори 'игрок', 'раунд', 'ход'."
                )
            else:
                # ЛС: боты — незнакомцы которых затащили в игру
                if is_mafia:
                    role_ctx = "Ты тайная мафия. Притворяйся растерянным мирным — не выдавай себя."
                else:
                    role_ctx = "Ты обычный человек которого непонятно зачем сюда затащили. Ты растерян и напуган."
                prompt = (
                    f"Тебя зовут {bname}. Тебя внезапно втянули в игру Мафия с незнакомцами. "
                    f"{role_ctx} "
                    f"День {g3['day_num']}. Живые игроки: {', '.join(all_alive_names[:5])}. "
                    f"{ctx}"
                    f"{hint} "
                    f"Отвечай от первого лица. Без смайлов. Коротко, как в живом чате. "
                    f"НЕ используй слова 'игрок', 'раунд', 'ход' — говори как реальный человек."
                )

            comment = ask(prompt, chat_id=_lid)
            if comment:
                recent_chat.append((bname, comment[:50]))
                if len(recent_chat) > 5:
                    recent_chat.pop(0)
                # Боты пишут напрямую — без эхо-пометки
                g_send = _maf.get(_lid)
                if g_send:
                    out_txt = f"💬 {bname}: {comment}"
                    if _maf_is_group(g_send) and g_send.get("chat_id"):
                        send_group(g_send["chat_id"], out_txt)
                    else:
                        # ЛС: всем реальным живым
                        for _rp in g_send.get("alive", []):
                            if _rp not in g_send["bots"]:
                                try: send(_rp, out_txt)
                                except: pass

            # Пауза между ботами — как будто набирают текст
            time.sleep(random.uniform(4, 11))

            # С 25% шансом — второй бот тут же реагирует на первого
            if i < len(bot_list) - 1 and recent_chat and random.random() < 0.25:
                responder = bot_list[i + 1]
                g4 = _maf.get(_lid)
                if g4 and g4["phase"] == "day" and responder in g4["alive"]:
                    time.sleep(random.uniform(2, 5))
                    rname  = g4["player_names"].get(responder, "?")
                    rrole  = g4["roles"].get(responder, "мирный")
                    last_n, last_t = recent_chat[-1]
                    if rrole == "мафия":
                        r_role_ctx = "Ты тайная мафия, притворяешься обычным растерянным человеком."
                    else:
                        r_role_ctx = "Ты обычный человек — тебя затащили в эту игру с незнакомцами."
                    r_prompt = (
                        f"Тебя зовут {rname}. {r_role_ctx} "
                        f"{last_n} только что сказал: «{last_t}». "
                        f"Коротко отреагируй — как незнакомый человек. 5-7 слов. Без смайлов."
                    )
                    r_comment = ask(r_prompt, chat_id=_lid)
                    if r_comment:
                        recent_chat.append((rname, r_comment[:50]))
                        # Используем send_group напрямую чтобы не триггерить цепочку реакций
                        g5 = _maf.get(_lid)
                        if g5 and _maf_is_group(g5):
                            send_group(g5["chat_id"], f"💬 {rname}: {r_comment}")
                        else:
                            # Прямая отправка без рекурсии
                            g6x = _maf.get(_lid)
                            if g6x:
                                for _rp in g6x.get("alive", []):
                                    if _rp not in g6x["bots"]:
                                        try: send(_rp, f"💬 {rname}: {r_comment}")
                                        except: pass

        # ── Голосование ботов (после обсуждения) ──────────────────
        time.sleep(random.uniform(20, 40))
        g4 = _maf.get(_lid)
        if not g4 or g4["phase"] != "day":
            return
        for bid in list(g4["bots"]):
            if bid not in g4["alive"] or bid in g4["votes"]:
                continue
            targets = [p for p in g4["alive"] if p != bid]
            if not targets:
                continue
            brole = g4["roles"].get(bid, "мирный")
            if brole == "мафия":
                safe_targets = [p for p in targets if g4["roles"].get(p) not in ("мафия",)]
                target = random.choice(safe_targets) if safe_targets else random.choice(targets)
            else:
                target = random.choice(targets)
            g4["votes"][bid] = target
            voted_n4 = len(g4["votes"])
            total_n4 = len(g4["alive"])
            _maf_send_all(_lid, f"🗳 Проголосовало: {voted_n4}/{total_n4}")

        # Проверяем один раз после всех ботов
        _pool.submit(_maf_check_votes, _lid)

        # Таймаут: если реальные не проголосовали за 120 сек — воздержание
        time.sleep(120)
        g5 = _maf.get(_lid)
        if g5 and g5["phase"] == "day":
            for p in g5["alive"]:
                if p not in g5["votes"] and p not in g5["bots"]:
                    g5["votes"][p] = None  # авто-воздержание
            _pool.submit(_maf_check_votes, _lid)

    _pool.submit(_bots_day)


def _maf_chat_broadcast(lobby_id: int, sender_uid: int, text: str):
    """Рассылает чат-сообщение всем живым (от имени отправителя).
    После рассылки — ИИ-боты могут отреагировать на сообщение.
    """
    g = _maf.get(lobby_id)
    if not g:
        return
    bots = g["bots"]
    sender_name = g["player_names"].get(sender_uid, "?")
    out = f"💬 {sender_name}: {text}"

    # Сохраняем в историю чата для контекста ботов
    log_entry = g.setdefault("chat_log", [])
    log_entry.append((sender_name, text[:80]))
    if len(log_entry) > 8:
        log_entry.pop(0)

    if _maf_is_group(g):
        # В группе — сообщения реальных игроков уже видны всем в чате
        # Боты ВСЕГДА реагируют (1 бот), чтобы чат был живым
        if g.get("phase") == "day" and sender_uid not in bots:
            _pool.submit(_maf_bots_react, lobby_id, sender_uid, sender_name, text)
    else:
        # ЛС: рассылаем всем живым реальным ВКЛЮЧАЯ отправителя (чтобы видел чат)
        real_alive = [uid for uid in g["alive"] if uid not in bots]
        for uid in real_alive:
            try:
                if uid == sender_uid:
                    # Отправителю — его сообщение с подтверждением
                    send(uid, f"📤 {out}")
                else:
                    send(uid, out)
            except Exception:
                pass

        # Боты всегда реагируют (чтобы чат не был мёртвым)
        if g.get("phase") == "day" and sender_uid not in bots:
            _pool.submit(_maf_bots_react, lobby_id, sender_uid, sender_name, text)


def _maf_bots_react(lobby_id: int, sender_uid: int, sender_name: str, msg_text: str):
    """ИИ-боты живо реагируют на сообщение (от игрока или другого бота).
    Только 1-2 бота отвечают, с паузами — как живой чат.
    """
    g = _maf.get(lobby_id)
    if not g or g.get("phase") != "day":
        return
    bots = g["bots"]
    alive_bots = [b for b in bots if b in g["alive"]]
    if not alive_bots:
        return

    # В группе — 1 бот (люди уже видят чат), в ЛС — 1-2 (оживляем чат)
    is_grp = _maf_is_group(g)
    how_many = 1 if (is_grp or random.random() < 0.5) else 2
    responders = random.sample(alive_bots, min(how_many, len(alive_bots)))

    for i, bid in enumerate(responders):
        # Пауза между ответами — как живой набор текста
        time.sleep(random.uniform(3, 9) + i * random.uniform(4, 10))

        g2 = _maf.get(lobby_id)
        if not g2 or g2.get("phase") != "day":
            return  # игра закончилась
        if bid not in g2["alive"]:
            continue  # этот бот умер — следующий реагирует

        bname     = g2["player_names"].get(bid, "?")
        brole     = g2["roles"].get(bid, "мирный")
        all_alive = [g2["player_names"].get(p, "?") for p in g2["alive"] if p != bid]
        is_mafia  = brole == "мафия"
        # Контекст последних реплик для более живой реакции
        chat_hist = g2.get("chat_log", [])[-3:]
        chat_ctx  = ("; ".join(f"{n}: «{t}»" for n, t in chat_hist) + ". ") if chat_hist else ""

        # Реакции незнакомца — растерянного, напуганного или подозрительного
        react_type = random.choice(["agree", "doubt", "accuse", "defend", "nervous", "confused"])
        targets_for_accuse = [n for n in all_alive if n != bname]
        suspect = random.choice(targets_for_accuse) if targets_for_accuse else sender_name

        is_grp_react = _maf_is_group(g2)
        if is_grp_react:
            # Группа: как знакомые
            if is_mafia:
                role_hint = "Ты среди знакомых, но ты тайный предатель — веди себя как все."
            else:
                role_hint = "Ты в компании знакомых людей. Общайся непринуждённо."
        else:
            # ЛС: незнакомцы
            if is_mafia:
                role_hint = "Ты тайная мафия. Притворяйся обычным растерянным человеком."
            else:
                role_hint = "Ты обычный человек — тебя непонятно зачем сюда затащили, ты никого не знаешь."

        base_ctx = (
            f"Тебя зовут {bname}. {role_hint} "
            f"{'Контекст чата: ' + chat_ctx if chat_ctx else ''}"
            f"{sender_name} только что написал: «{msg_text[:80]}». "
        )
        if react_type == "agree":
            prompt = base_ctx + (
                f"Согласись или поддержи — как незнакомый человек в странной ситуации. "
                f"1 фраза, 6-8 слов. Без смайлов. От первого лица."
            )
        elif react_type == "doubt":
            prompt = base_ctx + (
                f"Вырази недоверие — ты не знаешь этих людей и не понимаешь зачем тут. "
                f"1 фраза, 6-8 слов. Без смайлов. От первого лица."
            )
        elif react_type == "accuse":
            prompt = base_ctx + (
                f"Намекни что {suspect} ведёт себя странно — ты пытаешься разобраться кто тут свой. "
                f"1 фраза, 6-9 слов. Без смайлов. От первого лица."
            )
        elif react_type == "defend":
            prompt = base_ctx + (
                f"Защити себя — ты не виноват, ты сам не понимаешь что здесь происходит. "
                f"1 фраза, 6-8 слов. Без смайлов. От первого лица."
            )
        elif react_type == "nervous":
            prompt = base_ctx + (
                f"Ответь нервно и уклончиво — ты боишься и растерян среди чужих людей. "
                f"1 фраза, 5-8 слов. Без смайлов. От первого лица."
            )
        else:  # confused
            prompt = (
                f"Тебя зовут {bname}. Тебя внезапно затащили в игру с чужими людьми. "
                f"{'Контекст: ' + chat_ctx if chat_ctx else ''}"
                f"{sender_name} написал: «{msg_text[:80]}». "
                f"Ответь растеряно — ты не понимаешь что происходит. 1 фраза, 5-7 слов. Без смайлов."
            )

        reaction = ask(prompt, chat_id=lobby_id)
        if reaction:
            # Используем send_group напрямую — НЕ через broadcast (избегаем рекурсии)
            g_r = _maf.get(lobby_id)
            if g_r and _maf_is_group(g_r) and g_r.get("chat_id"):
                send_group(g_r["chat_id"], f"💬 {bname}: {reaction}")
            else:
                # ЛС: рассылаем всем живым реальным кроме бота
                g_r2 = _maf.get(lobby_id)
                if g_r2:
                    for _p in g_r2.get("alive", []):
                        if _p in g_r2["bots"]: continue
                        try: send(_p, f"💬 {bname}: {reaction}")
                        except: pass


def _maf_check_votes(lobby_id: int):
    """Проверяет: все ли проголосовали. Если да — разрешает."""
    g = _maf.get(lobby_id)
    if not g or g["phase"] != "day":
        return
    # Ждём всех живых игроков
    if not set(g["alive"]).issubset(set(g["votes"].keys())):
        return

    def _resolve(_lid=lobby_id):
        g2 = _maf.get(_lid)
        if not g2 or g2["phase"] != "day":
            return
        bots2 = g2["bots"]
        count = {}
        for v in g2["votes"].values():
            if v is not None:
                count[v] = count.get(v, 0) + 1

        if not count:
            host = ask_host(
                "Все промолчали. Никто не устранён. Объяви — с презрением. 1 предложение.",
                chat_id=_lid
            )
            _maf_send_all(_lid, f"🎭 Ведущий: {host}\n\nНикого не устранили.")
        else:
            max_v = max(count.values())
            top = [p for p, c in count.items() if c == max_v]
            if len(top) > 1:
                names_tie = ", ".join(g2["player_names"].get(p, "?") for p in top)
                host = ask_host(
                f"Ничья между {names_tie}. Никто не устранён сегодня. 1 предложение.",
                chat_id=_lid
            )
                _maf_send_all(_lid, f"⚖️ Ничья!\n\n🎭 Ведущий: {host}\n\nНикого не устранили.")
            else:
                eliminated = top[0]
                ename = g2["player_names"].get(eliminated, "?")
                erole = g2["roles"].get(eliminated, "мирный")
                if eliminated in g2["alive"]:
                    g2["alive"].remove(eliminated)
                _maf_uid.pop(eliminated, None)

                host = ask_host(
                f"'{ename}' устранён толпой. НЕ НАЗЫВАЙ роль. Объяви — жутко. 1-2 предложения.",
                chat_id=_lid
            )
                role_line = MAFIA_ROLE_DESC.get(erole, "").split("\n")[0]
                _maf_send_all(_lid,
                    f"⚖️ Устранён: {ename}\n\n"
                    f"🎭 Ведущий: {host}\n\n"
                    f"Роль: {role_line}"
                )
                if eliminated not in bots2:
                    _maf_send_one(eliminated,
                        "💀 Ты устранён голосованием.\n\nМожешь наблюдать за игрой.")

        g2["votes"] = {}
        winner = _maf_check_win(_lid)
        if winner:
            _maf_end(_lid, winner)
            return
        g2["day_num"] += 1
        time.sleep(2)
        _maf_night(_lid)

    _pool.submit(_resolve)


# ─── Ночь ──────────────────────────────────────────────────

def _maf_night_kb(lid: int, player_uid: int) -> InlineKeyboardMarkup:
    g = _maf.get(lid)
    if not g:
        return InlineKeyboardMarkup()
    bots = g["bots"]
    role = g["roles"].get(player_uid, "мирный")
    labels = {"мафия": "Убить", "маньяк": "Убить", "шериф": "Проверить", "доктор": "Вылечить"}
    label = labels.get(role, "Выбрать")
    kb = InlineKeyboardMarkup(row_width=1)
    for uid in g["alive"]:
        if role not in ("доктор",) and uid == player_uid:
            continue
        name = g["player_names"].get(uid, "?")
        kb.add(InlineKeyboardButton(
            f"🎯 {label}: {name}",
            callback_data=f"maf_n_{lid}_{player_uid}_{uid}"
        ))
    return kb


def _maf_night(lobby_id: int):
    g = _maf.get(lobby_id)
    if not g:
        return
    g["phase"] = "night"
    g["night_actions"] = {}
    bots = g["bots"]

    host = ask_host(
                f"Ночь {g['day_num']}. Убийцы выходят. 1-2 предложения.",
                chat_id=lobby_id
            )
    night_text = (
        f"🌙 НОЧЬ {g['day_num']}\n\n"
        f"🎭 Ведущий: {host}\n\n"
        f"Город засыпает... Если у тебя особая роль — кнопки придут в личку бота."
    )
    _maf_send_all(lobby_id, night_text)

    # Реальным игрокам с ролями — кнопки ночного хода (в ЛС)
    for uid in g["alive"]:
        if uid in bots:
            continue
        role = g["roles"].get(uid, "мирный")
        if role == "мирный":
            continue
        desc = {
            "мафия": "кого убить этой ночью",
            "маньяк": "кого убить этой ночью",
            "шериф": "кого проверить",
            "доктор": "кого спасти"
        }.get(role, "действие")
        kb_n = _maf_night_kb(lobby_id, uid)
        try:
            bot.send_message(uid,
                f"🌙 Твой ход! Ты — {role.upper()}\n\nВыбери {desc}:",
                reply_markup=kb_n
            )
        except Exception:
            pass

    # ИИ-боты делают ночные ходы
    def _bots_night(_lid=lobby_id):
        time.sleep(random.uniform(5, 15))
        g2 = _maf.get(_lid)
        if not g2 or g2["phase"] != "night":
            return
        for bid in list(g2["bots"]):
            if bid not in g2["alive"] or bid in g2["night_actions"]:
                continue
            brole = g2["roles"].get(bid, "мирный")
            if brole == "мирный":
                continue
            if brole == "мафия":
                targets = [p for p in g2["alive"] if p != bid and g2["roles"].get(p) not in ("мафия","маньяк")]
            elif brole == "маньяк":
                targets = [p for p in g2["alive"] if p != bid]
            elif brole == "шериф":
                # Шериф старается проверить подозрительных (не-ботов приоритет)
                real_targets = [p for p in g2["alive"] if p != bid and p not in g2["bots"]]
                targets = real_targets if real_targets else [p for p in g2["alive"] if p != bid]
            elif brole == "доктор":
                # Доктор иногда лечит себя
                targets = list(g2["alive"])
            else:
                continue
            if not targets:
                continue
            target = random.choice(targets)
            g2["night_actions"][bid] = target
            time.sleep(random.uniform(2, 6))
        # Проверяем один раз после всех ботов
        _pool.submit(_maf_check_night, _lid)

        # Таймаут: если реальные не сходили за 90 секунд — принудительно завершаем ночь
        time.sleep(90)
        g3 = _maf.get(_lid)
        if g3 and g3["phase"] == "night":
            # Заполняем пропущенные ночные ходы реальных игроков
            night_roles_t = [p for p in g3["alive"] if g3["roles"].get(p) in ("мафия","шериф","доктор","маньяк")]
            for p in night_roles_t:
                if p not in g3["night_actions"] and p not in g3["bots"]:
                    # Пропуск хода
                    g3["night_actions"][p] = None
            _pool.submit(_maf_check_night, _lid)
    _pool.submit(_bots_night)


def _maf_check_night(lobby_id: int):
    """Проверяет все ли ночные роли сделали ход."""
    g = _maf.get(lobby_id)
    if not g or g["phase"] != "night":
        return
    night_roles = [p for p in g["alive"] if g["roles"].get(p) in ("мафия","шериф","доктор","маньяк")]
    if night_roles and not set(night_roles).issubset(set(g["night_actions"].keys())):
        return
    # Все ночные роли сходили (или ночных ролей нет) — разбираем утро

    def _morning(_lid=lobby_id):
        g2 = _maf.get(_lid)
        if not g2:
            return
        bots2 = g2["bots"]
        actions = g2["night_actions"]

        mafia_kill = None
        maniac_kill = None
        doctor_save = None

        for uid, target in actions.items():
            if target is None:  # игрок пропустил ход
                continue
            role = g2["roles"].get(uid)
            if role == "мафия" and mafia_kill is None:
                mafia_kill = target
            elif role == "маньяк":
                maniac_kill = target
            elif role == "доктор":
                doctor_save = target
            elif role == "шериф" and uid not in bots2:
                # Шерифу — результат в личку
                trole = g2["roles"].get(target, "мирный")
                tname = g2["player_names"].get(target, "?")
                is_bad = trole in ("мафия", "маньяк")
                _maf_send_one(uid,
                    f"🔎 Результат проверки:\n"
                    f"{'🤖' if target in bots2 else '👤'} {tname} — "
                    f"{'🔫 МАФИЯ!' if trole=='мафия' else ('🔪 МАНЬЯК!' if trole=='маньяк' else '✅ мирный')}"
                )

        # Определяем жертв
        victims = []
        if mafia_kill and mafia_kill != doctor_save:
            victims.append(mafia_kill)
        if maniac_kill and maniac_kill != doctor_save and maniac_kill not in victims:
            victims.append(maniac_kill)

        # Убираем жертв
        dead_strs = []
        for v in victims:
            vname = g2["player_names"].get(v, "?")
            vrole = g2["roles"].get(v, "мирный")
            role_line = MAFIA_ROLE_DESC.get(vrole, "").split("\n")[0]
            dead_strs.append(f"💀 {vname} ({role_line})")
            if v in g2["alive"]:
                g2["alive"].remove(v)
            _maf_uid.pop(v, None)
            if v not in bots2:
                _maf_send_one(v, "💀 Тебя убили этой ночью.\n\nМожешь наблюдать за игрой.")

        # Утреннее объявление
        if victims:
            dead_list = "\n".join(dead_strs)
            host = ask_host(
                f"Ты ведущий Мафии. Утро дня {g2['day_num']}. "
                f"Погибли: {', '.join(g2['player_names'].get(v,'?') for v in victims)}. "
                f"Объяви жутко. НЕ НАЗЫВАЙ роли убитых. 1-2 предложения.",
                chat_id=_lid
            )
            _maf_send_all(_lid,
                f"☀️ УТРО\n\n🎭 Ведущий: {host}\n\n"
                f"Этой ночью погибли:\n{dead_list}"
            )
        elif doctor_save and (mafia_kill == doctor_save or maniac_kill == doctor_save):
            host = ask_host(
                "Утро. Никто не погиб. Объяви с тревогой — это ненадолго. 1 предложение.",
                chat_id=_lid
            )
            _maf_send_all(_lid, f"☀️ УТРО\n\n🎭 Ведущий: {host}\n\nНикто не погиб этой ночью.")
        else:
            host = ask_host(
                "Тихая ночь. Никто не погиб. Объяви — с угрозой. 1 предложение.",
                chat_id=_lid
            )
            _maf_send_all(_lid, f"☀️ УТРО\n\n🎭 Ведущий: {host}\n\nНикто не погиб.")

        g2["night_actions"] = {}
        winner = _maf_check_win(_lid)
        if winner:
            _maf_end(_lid, winner)
            return
        time.sleep(2)
        _maf_day(_lid)

    _pool.submit(_morning)


# ─── Победа / конец ────────────────────────────────────────

def _maf_check_win(lobby_id: int):
    g = _maf.get(lobby_id)
    if not g:
        return None
    alive = g["alive"]
    roles = g["roles"]
    mafia_a = [p for p in alive if roles.get(p) == "мафия"]
    maniac_a = [p for p in alive if roles.get(p) == "маньяк"]
    others_a = [p for p in alive if roles.get(p) not in ("мафия","маньяк")]
    if not mafia_a and not maniac_a:
        return "мирные"
    if maniac_a and len(maniac_a) >= len([p for p in alive if p not in maniac_a]):
        return "маньяк"
    if mafia_a and len(mafia_a) >= len(others_a):
        return "мафия"
    return None


def _maf_end(lobby_id: int, winner: str):
    g = _maf.pop(lobby_id, None)
    if not g:
        return
    bots = g["bots"]
    is_group = _maf_is_group(g)

    # Убираем маппинг группы
    if is_group:
        _group_mafia.pop(g.get("chat_id"), None)

    # Очищаем игроков
    for uid in g["players"]:
        _maf_uid.pop(uid, None)

    roles_all = "\n".join(
        f"  👤 {g['player_names'].get(uid,'?')} — {role}"
        for uid, role in g["roles"].items()
    )
    win_text = {
        "мирные": "🎉 МИРНЫЕ ПОБЕДИЛИ!\nМафия уничтожена!",
        "мафия":  "🔫 МАФИЯ ПОБЕДИЛА!\nГород во тьме.",
        "маньяк": "🔪 МАНЬЯК ПОБЕДИЛ!\nВсе пали его жертвами.",
    }.get(winner, "Игра завершена.")

    finale = ask_host(
        f"Конец игры. Победители: {winner}. Финальный монолог — мрачно, как тёмный судья. 2-3 предложения.",
        chat_id=lobby_id
    )

    final_msg = (
        f"{win_text}\n\n"
        f"🎭 Ведущий: {finale}\n\n"
        f"📋 Все роли:\n{roles_all}"
    )

    if is_group:
        send_group(g["chat_id"], final_msg)
    else:
        for uid in g["players"]:
            if uid in bots:
                continue
            u = get_user(uid)
            try:
                send(uid, final_msg, kb=__import__("keyboards", fromlist=["main_kb"]).main_kb(u.get("stage",0)))
            except Exception:
                pass


# ─── Обработка текста игрока в ЛС ──────────────────────────

def maf_proc_dm(uid: int, text: str) -> bool:
    """Обрабатывает сообщение игрока в ЛС мафии. True если поглощено."""
    lid = _maf_uid.get(uid)
    if not lid:
        return False
    g = _maf.get(lid)
    if not g or _maf_is_group(g):
        return False

    tl = text.strip().lower()

    # Выход
    if tl in ("/leavem", "выйти из мафии", "/stopm"):
        _maf_uid.pop(uid, None)
        name = g["player_names"].get(uid, "?")
        if uid in g["players"]:
            g["players"].remove(uid)
        if uid in g["alive"]:
            g["alive"].remove(uid)
            _maf_send_all(lid, f"⚠️ {name} покинул игру.")
            winner = _maf_check_win(lid)
            if winner:
                _maf_end(lid, winner)
        u = get_user(uid)
        _maf_send_one(uid, "Ты вышел из мафии.", kb=__import__("keyboards", fromlist=["main_kb"]).main_kb(u.get("stage",0)))
        return True

    # Чат во время игры (не команды)
    if g["state"] == "playing" and uid in g["alive"] and not tl.startswith("/"):
        if text in _MAIN_BUTTONS:
            return False  # кнопки меню работают даже в мафии
        get_user(uid)["ai_mode"] = False
        _maf_chat_broadcast(lid, uid, text)
        return True

    return False


# ─── ИИ-АТАКА (для админа) ─────────────────────────────────

_ai_scare_active: dict = {}  # uid → True (жертвы под ИИ-атакой)


def start_ai_scare(target_uid: int):
    """Запускает ИИ-атаку на жертву. Пишет жутко, отвечает на ответы."""
    _ai_scare_active[target_uid] = True
    u = U(target_uid)
    name = u.get("name") or "ты"
    city = u.get("city") or ""
    city_hint = f" Ты живёшь в {city}." if city else ""

    def _scare_loop(_uid=target_uid, _name=name):
        # Первые 3 волны — без ответа пользователя
        openers = [
            f"Напиши жертве по имени '{_name}' жуткое первое сообщение. "
            f"Намекни что следишь.{city_hint} 1-2 предложения.",

            f"Продолжай пугать '{_name}'. Упомяни что знаешь её действия. "
            f"Будь загадочным. 1 предложение.",

            f"Напиши '{_name}' — финальный жуткий намёк. "
            f"Скажи что видишь её прямо сейчас. 1 предложение.",
        ]
        for prompt in openers:
            if not _ai_scare_active.get(_uid):
                return
            msg = ask(prompt, chat_id=_uid)
            _maf_send_one(_uid, f"👁 {msg}")
            time.sleep(random.uniform(12, 25))

    _pool.submit(_scare_loop)


def stop_ai_scare(target_uid: int):
    _ai_scare_active.pop(target_uid, None)


def maf_ai_scare_reply(uid: int, text: str) -> bool:
    """Если жертва под ИИ-атакой — иногда отвечает. True если поглощено."""
    if not _ai_scare_active.get(uid):
        return False
    # Отвечает с вероятностью ~40%
    if random.random() > 0.40:
        return False
    u = get_user(uid)
    name = u.get("name") or "ты"

    def _reply(_t=text, _uid=uid, _name=name):
        time.sleep(random.uniform(3, 10))
        if not _ai_scare_active.get(_uid):
            return
        answer = ask_host(
                f"Жертва по имени '{_name}' ответила мне: '{_t[:100]}'. "
            f"Ответь жутко, загадочно, намекни что это всё видишь. 1-2 предложения.",
                chat_id=_uid
            )
        _maf_send_one(_uid, f"👁 {answer}")
    _pool.submit(_reply)
    return True

#  v13: КАРТОЧНАЯ ИСТОРИЯ (visual-novel style с выбором персонажа)
# ══════════════════════════════════════════════════════════════