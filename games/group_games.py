"""
games/group_games.py — Групповые игры.
"""
import time
import random
import logging

from utils import send, send_group, send_voice_msg
from database import get_user, update_user_field
from ai.client import ask as ask_ai, is_enabled as ai_ok

log = logging.getLogger("horror.group_games")

# Pool proxy
_pool_ref = None
def set_pool(p):
    global _pool_ref
    _pool_ref = p

class _PoolProxy:
    def submit(self, fn, *args, **kwargs):
        if _pool_ref:
            return _pool_ref.submit(fn, *args, **kwargs)
        import threading
        threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()

_pool = _PoolProxy()

_group_games: dict  = {}
_rr_games: dict     = {}
_tod_games: dict    = {}
_wr_games: dict     = {}
_group_trivia: dict = {}


def _members(chat_id):
    try:
        from handlers.group import get_group_users
        return list(get_group_users(chat_id))
    except Exception:
        return []

def _name(uid):
    return get_user(uid).get("name") or f"ID:{uid}"


# ── Бутылочка ─────────────────────────────────────────────────────
def start_bottle(chat_id: int, spin_uid: int = 0):
    members = _members(chat_id)
    if len(members) < 2:
        send_group(chat_id, "❌ Нужно минимум 2 человека!"); return
    spinner_name = _name(spin_uid)
    others = [m for m in members if m != spin_uid] or members
    chosen = random.choice(others)
    def _run():
        send_group(chat_id, f"🍾 {spinner_name} крутит бутылочку...")
        time.sleep(1.5)
        for e in random.choices(["🔄","↩️","↪️"], k=3):
            send_group(chat_id, e); time.sleep(0.6)
        send_group(chat_id, f"🍾 Бутылочка указывает на: {_name(chosen)}!")
        if ai_ok():
            c = ask_ai(f"Бутылочка на {_name(chosen)}. Придумай задание (1 предл.).", chat_id=chat_id)
            if c: send_group(chat_id, f"🤖 ИИ: {c}")
    _pool.submit(_run)

# ── Монетка ────────────────────────────────────────────────────────
def group_coin_flip(chat_id: int, uid: int):
    uname = _name(uid)
    def _run():
        send_group(chat_id, f"🪙 {uname} подбрасывает монету...")
        time.sleep(1.2)
        result = random.choice(["🦅 ОРЁЛ", "🔵 РЕШКА"])
        send_group(chat_id, f"🪙 Выпало: {result}!")
        if ai_ok() and random.random() < 0.5:
            c = ask_ai(f"{uname} бросил монету, выпало {result}. Коротко.", chat_id=chat_id)
            if c: send_group(chat_id, f"🤖 {c}")
    _pool.submit(_run)

# ── Кубик ─────────────────────────────────────────────────────────
def group_dice_roll(chat_id: int, uid: int, sides: int = 6):
    uname = _name(uid)
    def _run():
        send_group(chat_id, f"🎲 {uname} бросает d{sides}...")
        time.sleep(1)
        val = random.randint(1, sides)
        send_group(chat_id, f"🎲 Выпало: {val}!")
    _pool.submit(_run)

# ── Русская рулетка ────────────────────────────────────────────────
_rr_games: dict = {}

def start_roulette(chat_id: int, uid: int):
    uname = _name(uid)
    _rr_games[chat_id] = {"bullet": random.randint(1, 6), "shot": 0}
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔫 Выстрелить", callback_data=f"rr_shoot_{chat_id}_{uid}"))
    send_group(chat_id,
        f"🔫 {uname} запускает русскую рулетку!\n"
        f"В барабане 1 патрон из 6.\n"
        f"Кто решится нажать курок?",
        kb=kb)

def rr_shoot(chat_id: int, uid: int):
    g = _rr_games.get(chat_id)
    if not g: return
    g["shot"] += 1
    uname = _name(uid)
    def _run():
        send_group(chat_id, f"🔫 {uname} нажимает курок...")
        time.sleep(1.5)
        if g["shot"] == g["bullet"]:
            del _rr_games[chat_id]
            send_group(chat_id, f"💥 БАХ! {uname} выбывает!")
            if ai_ok():
                c = ask_ai(f"{uname} проиграл в русскую рулетку. Злобный комментарий.", chat_id=chat_id)
                if c: send_group(chat_id, f"🤖 {c}")
        elif g["shot"] >= 6:
            del _rr_games[chat_id]
            send_group(chat_id, f"😅 Все 6 выстрелов — патрона не было! {uname} выжил!")
        else:
            send_group(chat_id, f"*щелчок* {uname} выжил. Пока.")
    _pool.submit(_run)

# ── Правда или действие ────────────────────────────────────────────
def start_truth_or_dare(chat_id: int, uid: int):
    uname = _name(uid)
    _tod_games[chat_id] = {"player": uid, "player_name": uname}
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("😇 ПРАВДА",    callback_data=f"tod_truth_{chat_id}_{uid}"),
        InlineKeyboardButton("😈 ДЕЙСТВИЕ",  callback_data=f"tod_dare_{chat_id}_{uid}"),
    )
    send_group(chat_id, f"🎭 {uname}, выбери:", kb=kb)

def execute_truth(chat_id: int, uid: int):
    uname = _name(uid)
    def _run():
        if ai_ok():
            q = ask_ai(f"Придумай вопрос «правда» для {uname}. 1 вопрос.", chat_id=chat_id)
            send_group(chat_id, f"😇 ПРАВДА для {uname}:\n\n{q}")
        else:
            qs = ["Что ты больше всего скрываешь?", "Твой самый странный страх?",
                  "Самый неловкий момент в жизни?", "Кому ты больше всего завидуешь?"]
            send_group(chat_id, f"😇 ПРАВДА для {uname}:\n\n{random.choice(qs)}")
    _pool.submit(_run)

def execute_dare(chat_id: int, uid: int):
    uname = _name(uid)
    def _run():
        if ai_ok():
            d = ask_ai(f"Придумай смешное задание «действие» для {uname}. 1 задание.", chat_id=chat_id)
            send_group(chat_id, f"😈 ДЕЙСТВИЕ для {uname}:\n\n{d}")
        else:
            ds = ["Напиши «Я буду слушаться бота» 3 раза.",
                  "Отправь голосовое с пением.",
                  "Расскажи свой самый страшный сон."]
            send_group(chat_id, f"😈 ДЕЙСТВИЕ для {uname}:\n\n{random.choice(ds)}")
    _pool.submit(_run)

# ── Дуэль ─────────────────────────────────────────────────────────
def start_duel(chat_id: int, challenger_uid: int, defender_uid: int):
    c_name = _name(challenger_uid)
    d_name = _name(defender_uid)
    _group_games[chat_id] = {"game": "duel", "challenger": challenger_uid, "defender": defender_uid, "ready": set()}
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⚔️ Принять вызов!", callback_data=f"duel_accept_{chat_id}_{defender_uid}"))
    send_group(chat_id, f"⚔️ {c_name} вызывает {d_name} на дуэль!", kb=kb)

def _duel_start(chat_id: int):
    g = _group_games.get(chat_id)
    if not g: return
    c = g["challenger"]; d = g["defender"]
    def _run():
        send_group(chat_id, "⚔️ ДУЭЛЬ!\n\nОба пишут число от 1 до 10. Кто ближе к 7 — победит!")
        import time; time.sleep(20)
        g2 = _group_games.get(chat_id)
        if g2 and g2.get("game") == "duel":
            del _group_games[chat_id]
            winner = random.choice([c, d])
            send_group(chat_id, f"⚔️ Победитель дуэли: {_name(winner)}!")
    _pool.submit(_run)

# ── Что лучше? ────────────────────────────────────────────────────
WOULD_RATHER = [
    ("Суперсила", "Суперинтеллект"),
    ("Жить 100 лет обычно", "50 лет счастливо"),
    ("Всегда врать", "Всегда говорить правду"),
    ("Стать невидимым", "Уметь летать"),
    ("Потерять все воспоминания", "Не иметь будущего"),
]

def start_would_rather(chat_id: int, uid: int):
    a, b = random.choice(WOULD_RATHER)
    _wr_games[chat_id] = {"a": a, "b": b, "votes_a": 0, "votes_b": 0, "answered": set()}
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(f"🅰 {a}", callback_data=f"wr_a_{chat_id}"),
        InlineKeyboardButton(f"🅱 {b}", callback_data=f"wr_b_{chat_id}"),
    )
    send_group(chat_id, f"⚖️ ЧТО ЛУЧШЕ?\n\n🅰 {a}\n\nили\n\n🅱 {b}\n\nГолосуйте!", kb=kb)
    if ai_ok():
        def _ai_vote():
            time.sleep(2)
            c = ask_ai(f"Что лучше: '{a}' или '{b}'? Ответь с сарказмом.", chat_id=chat_id)
            if c: send_group(chat_id, f"🤖 ИИ: {c}")
        _pool.submit(_ai_vote)

def wr_vote(chat_id: int, uid: int, choice: str):
    g = _wr_games.get(chat_id)
    if not g or uid in g["answered"]: return
    g["answered"].add(uid)
    if choice == "a": g["votes_a"] += 1
    else: g["votes_b"] += 1
    total = g["votes_a"] + g["votes_b"]
    send_group(chat_id, f"🅰 {g['a']}: {g['votes_a']} голосов\n🅱 {g['b']}: {g['votes_b']} голосов\n({total} всего)")

# ── Горячий вопрос ────────────────────────────────────────────────
def start_hot_take(chat_id: int, uid: int):
    uname = _name(uid)
    if ai_ok():
        def _run():
            q = ask_ai(f"Задай провокационный вопрос группе для голосования. 1 вопрос.", chat_id=chat_id)
            if not q: q = "Кто в этой группе самый загадочный?"
            members = _members(chat_id)
            if not members: return
            from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(row_width=2)
            for mid in members[:8]:
                kb.add(InlineKeyboardButton(_name(mid), callback_data=f"hottake_{chat_id}_{mid}"))
            _group_games[chat_id] = {"game": "hot_take", "question": q, "votes": {}}
            send_group(chat_id, f"🔥 {uname} спрашивает:\n\n{q}", kb=kb)
        _pool.submit(_run)
    else:
        questions = ["Кто в группе самый загадочный?", "Кто бы первым сбежал в хоррор-фильме?"]
        q = random.choice(questions)
        members = _members(chat_id)
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(row_width=2)
        for mid in members[:8]:
            kb.add(InlineKeyboardButton(_name(mid), callback_data=f"hottake_{chat_id}_{mid}"))
        _group_games[chat_id] = {"game": "hot_take", "question": q, "votes": {}}
        send_group(chat_id, f"🔥 {q}", kb=kb)

# ── Угадай число (группа) ─────────────────────────────────────────
def start_group_number(chat_id: int, uid: int):
    uname = _name(uid)
    number = random.randint(1, 100)
    _group_games[chat_id] = {"game": "number", "number": number, "attempts": 10, "host": uid}
    send_group(chat_id, f"🎲 {uname} загадал число от 1 до 100!\nУ группы 10 попыток. Пишите числа в чат!")

def group_number_guess(chat_id: int, uid: int, guess: int):
    g = _group_games.get(chat_id)
    if not g or g.get("game") != "number": return False
    if g.get("host") == uid: return False
    num = g["number"]
    g["attempts"] -= 1
    uname = _name(uid)
    if guess == num:
        del _group_games[chat_id]
        send_group(chat_id, f"🎯 {uname} угадал число {num}!"); return True
    elif g["attempts"] <= 0:
        del _group_games[chat_id]
        send_group(chat_id, f"😔 Попытки кончились. Число было {num}."); return True
    else:
        hint = "⬆️ Больше!" if guess < num else "⬇️ Меньше!"
        send_group(chat_id, f"{hint} {uname} → {guess}. Осталось: {g['attempts']}"); return True

# ── Виселица (группа) ─────────────────────────────────────────────
def start_group_hangman(chat_id: int, uid: int):
    from horror.texts import HANGMAN_W
    word, hint = random.choice(HANGMAN_W)
    _group_games[chat_id] = {"game": "hangman", "word": word, "hint": hint, "guessed": set(), "attempts": 8}
    display = " ".join("_" for _ in word)
    send_group(chat_id, f"✏️ ГРУППОВАЯ ВИСЕЛИЦА!\nПодсказка: {hint}\n\n{display}\n\nПопыток: 8\nВводите буквы!")

def group_hangman_guess(chat_id: int, uid: int, letter: str):
    g = _group_games.get(chat_id)
    if not g or g.get("game") != "hangman": return False
    tl = letter.strip().lower()
    if len(tl) != 1 or not tl.isalpha(): return False
    word = g["word"]; guessed = g["guessed"]
    if tl in guessed: return True
    guessed.add(tl)
    if tl not in word: g["attempts"] -= 1
    display = " ".join(c if c in guessed else "_" for c in word)
    uname = _name(uid)
    if "_" not in display:
        del _group_games[chat_id]
        send_group(chat_id, f"🎉 {uname} угадал! Слово: {word.upper()}!")
    elif g["attempts"] <= 0:
        del _group_games[chat_id]
        send_group(chat_id, f"💀 Слово было: {word.upper()}")
    else:
        send_group(chat_id, f"{display}\nБуквы: {', '.join(sorted(guessed))}  Попыток: {g['attempts']}")
    return True

# ── Групповая викторина ────────────────────────────────────────────
def start_group_trivia(chat_id: int, uid: int):
    from games.rpg_data import TRIVIA_Q
    q, ans, opts = random.choice(TRIVIA_Q)
    shuffled = opts[:]
    random.shuffle(shuffled)
    _group_trivia[chat_id] = {"question": q, "answer": ans.lower(), "answered": set()}
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(row_width=2)
    for o in shuffled:
        kb.add(InlineKeyboardButton(o, callback_data=f"gtrivia_{chat_id}_{o[:20]}_{ans[:20]}"))
    kb.add(InlineKeyboardButton("❌ Стоп", callback_data=f"gg_stop_{chat_id}"))
    send_group(chat_id, f"🧠 ГРУППОВАЯ ВИКТОРИНА!\n\n{q}", kb=kb)

def group_trivia_answer(chat_id: int, uid: int, answer: str) -> bool:
    g = _group_trivia.get(chat_id)
    if not g or uid in g["answered"]: return False
    g["answered"].add(uid)
    uname = _name(uid)
    if answer.lower() == g["answer"]:
        update_user_field(uid, "score", get_user(uid).get("score", 0) + 10)
        del _group_trivia[chat_id]
        send_group(chat_id, f"✅ {uname} ответил правильно: {answer}! +10 очков")
        return True
    send_group(chat_id, f"❌ {uname}: {answer} — неверно")
    return True

# ── Обработчик текста в группе ────────────────────────────────────
def process_group_text(chat_id: int, uid: int, text: str) -> bool:
    """Проверяет числа/буквы для активных игр. True = поглощено."""
    tl = text.strip().lower()

    g = _group_games.get(chat_id)
    if g:
        gm = g.get("game")
        if gm == "number" and tl.isdigit():
            return group_number_guess(chat_id, uid, int(tl))
        if gm == "hangman" and len(tl) == 1 and tl.isalpha():
            return group_hangman_guess(chat_id, uid, tl)

    return False
