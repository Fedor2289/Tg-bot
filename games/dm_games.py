"""
games/dm_games.py — Все игры в личных сообщениях.
"""
import random
import time
import logging

from utils import send
from database import get_user, update_user_field
from horror.engine import check_achievement

log = logging.getLogger("horror.games.dm")

# ── Состояние игр ─────────────────────────────────────────────────
_games: dict = {}  # uid → {game, ...}

MAIN_BUTTONS = {
    "🌍 Перевести","🔤 Язык","🌤 Погода","🌑 Погода",
    "🎮 Игры","🩸 Игры","💀 Игры",
    "🤖 ИИ","🗓 Задание","🏆 Рейтинг","🛒 Магазин",
    "❓ Помощь","👁 ...","👁 Кто ты?","🙂 О боте",
    "💀 /stop","↩️ Назад","❌ Выйти из игры",
    "🔫 Мафия","🔫 Мафия (ЛС)","🎭 Карточная история",
    "🗡 Мини-RPG","📖 Страшные истории","🔦 Квест",
}

GALLOWS = [
    "```\n  ___\n |   |\n     |\n     |\n     |\n_____|\n```",
    "```\n  ___\n |   |\n O   |\n     |\n     |\n_____|\n```",
    "```\n  ___\n |   |\n O   |\n |   |\n     |\n_____|\n```",
    "```\n  ___\n |   |\n O   |\n/|   |\n     |\n_____|\n```",
    "```\n  ___\n |   |\n O   |\n/|\\  |\n     |\n_____|\n```",
    "```\n  ___\n |   |\n O   |\n/|\\  |\n/    |\n_____|\n```",
    "```\n  ___\n |   |\n O   |\n/|\\  |\n/ \\  |\n_____|\n```",
]

# ── Импорт текстов ────────────────────────────────────────────────
from horror.texts import HANGMAN_W, TRIVIA_Q, RIDDLES, PREDICTIONS, FACTS
from games.rpg_data import RPG_SCENES, STORIES, QUEST


# ── Вспомогательные ───────────────────────────────────────────────
def has_game(uid: int) -> bool:
    return uid in _games

def get_game(uid: int) -> dict | None:
    return _games.get(uid)

def clear_game(uid: int):
    _games.pop(uid, None)


def _kb(stage: int):
    from keyboards import main_kb
    return main_kb(stage)

def _gkb(choices: list):
    from keyboards import game_choices_kb
    return game_choices_kb(choices)


# ── RPG / История / Квест ─────────────────────────────────────────
def run_scene(uid: int, scene: dict):
    u = get_user(uid)
    text = scene.get("text", "")
    choices = scene.get("choices", [])
    if choices:
        send(uid, text, kb=_gkb(choices))
    else:
        send(uid, text, kb=_kb(u.get("stage", 0)))
        if scene.get("end"):
            clear_game(uid)

def start_rpg(uid: int):
    _games[uid] = {"game": "rpg", "scene": "start"}
    run_scene(uid, RPG_SCENES["start"])

def start_story(uid: int):
    _games[uid] = {"game": "story", "scene": "select"}
    run_scene(uid, STORIES["select"])

def start_quest(uid: int):
    _games[uid] = {"game": "quest", "scene": "start"}
    run_scene(uid, QUEST["start"])


# ── Виселица ──────────────────────────────────────────────────────
def start_hangman(uid: int):
    word, hint = random.choice(HANGMAN_W)
    _games[uid] = {"game": "hangman", "word": word, "hint": hint,
                   "guessed": set(), "attempts": 6}
    u = get_user(uid)
    display = " ".join("_" for _ in word)
    send(uid,
        f"✏️ ВИСЕЛИЦА!\nПодсказка: {hint}\n\n{display}\n\nПопыток: 6\nВводи букву:",
        kb=_kb(u.get("stage", 0)))


# ── Угадай число ──────────────────────────────────────────────────
def start_number(uid: int):
    _games[uid] = {"game": "number", "number": random.randint(1, 100), "attempts": 7}
    u = get_user(uid)
    send(uid, "🎲 Загадал число от 1 до 100! У тебя 7 попыток:", kb=_kb(u.get("stage", 0)))


# ── Викторина ─────────────────────────────────────────────────────
def start_trivia(uid: int):
    q, ans, opts = random.choice(TRIVIA_Q)
    _games[uid] = {"game": "trivia", "answer": ans.lower()}
    shuffled = opts[:]
    random.shuffle(shuffled)
    from keyboards import trivia_kb
    send(uid, f"🧠 ВИКТОРИНА!\n\n{q}", kb=trivia_kb(shuffled))


# ── Загадка ───────────────────────────────────────────────────────
def start_riddle(uid: int):
    q, a = random.choice(RIDDLES)
    _games[uid] = {"game": "riddle", "answer": a, "question": q}
    u = get_user(uid)
    send(uid, f"🎭 ЗАГАДКА:\n\n{q}\n\nВведи ответ:", kb=_kb(u.get("stage", 0)))


# ── Карточная история ─────────────────────────────────────────────
from games.card_story import CARD_CHARACTERS, CARD_STORIES, start_card_story, proc_card_story


# ── Обработчик ───────────────────────────────────────────────────
def proc_game(uid: int, text: str) -> bool:
    """Обрабатывает текст пользователя если он в игре. True = поглощено."""
    if uid not in _games:
        return False

    g = _games[uid]
    gm = g.get("game")
    u  = get_user(uid)
    kb = _kb(u.get("stage", 0))
    tl = text.strip().lower()

    # Главные кнопки — выход из игры
    if text in MAIN_BUTTONS:
        clear_game(uid)
        return False

    if text == "❌ Выйти из игры":
        clear_game(uid)
        send(uid, "Вышли из игры.", kb=kb)
        return True

    # ── Викторина ────────────────────────────────────────────────
    if gm == "trivia":
        if tl == g["answer"].lower():
            new_score = u.get("score", 0) + 10
            update_user_field(uid, "score", new_score)
            clear_game(uid)
            send(uid, f"✅ Правильно! +10\n🏆 Счёт: {new_score}", kb=kb)
            # Ачивка
            correct = u.get("trivia_correct", 0) + 1
            update_user_field(uid, "trivia_correct", correct)
            if correct >= 10:
                check_achievement(uid, "quiz_master")
        else:
            clear_game(uid)
            send(uid, f"❌ Правильный ответ: {g['answer']}", kb=kb)
        return True

    # ── Виселица ─────────────────────────────────────────────────
    if gm == "hangman":
        if len(tl) == 1 and tl.isalpha():
            word    = g["word"]
            guessed = g["guessed"]
            if tl in guessed:
                send(uid, f"Буква «{tl}» уже была!", kb=kb); return True
            guessed.add(tl)
            if tl not in word:
                g["attempts"] -= 1
            display = " ".join(c if c in guessed else "_" for c in word)
            icon = GALLOWS[max(0, min(6 - g["attempts"], 6))]
            if "_" not in display:
                new_score = u.get("score", 0) + 15
                update_user_field(uid, "score", new_score)
                clear_game(uid)
                send(uid, f"🎉 Слово: {word.upper()}!\n+15  🏆 {new_score}", kb=kb)
            elif g["attempts"] <= 0:
                clear_game(uid)
                send(uid, f"{icon}\nПроигрыш! Слово: {word.upper()}", kb=kb)
            else:
                send(uid,
                    f"{icon}\n{display}\n"
                    f"Попыток: {g['attempts']}  "
                    f"Буквы: {', '.join(sorted(guessed))}",
                    kb=kb)
        else:
            send(uid, "Введи одну букву!", kb=kb)
        return True

    # ── Угадай число ─────────────────────────────────────────────
    if gm == "number":
        if tl.isdigit():
            guess = int(tl)
            num   = g["number"]
            g["attempts"] -= 1
            if guess == num:
                new_score = u.get("score", 0) + 20
                update_user_field(uid, "score", new_score)
                clear_game(uid)
                send(uid, f"🎯 Угадал! Число было {num}\n+20  🏆 {new_score}", kb=kb)
            elif g["attempts"] <= 0:
                clear_game(uid)
                send(uid, f"😔 Попытки кончились. Число было: {num}", kb=kb)
            else:
                hint = "⬆️ Больше!" if guess < num else "⬇️ Меньше!"
                send(uid, f"{hint} Осталось попыток: {g['attempts']}", kb=kb)
        else:
            send(uid, "Введи число от 1 до 100!", kb=kb)
        return True

    # ── Загадка ──────────────────────────────────────────────────
    if gm == "riddle":
        if tl.strip() == g["answer"]:
            new_score = u.get("score", 0) + 5
            update_user_field(uid, "score", new_score)
            clear_game(uid)
            send(uid, f"✅ Правильно! +5  🏆 {new_score}", kb=kb)
        else:
            send(uid, f"❌ Неверно. Попробуй ещё!\n🎭 {g['question']}", kb=kb)
        return True

    # ── RPG / История / Квест ─────────────────────────────────────
    if gm in ("rpg", "story", "quest"):
        db  = {"rpg": RPG_SCENES, "story": STORIES, "quest": QUEST}[gm]
        cur = db.get(g["scene"], {})
        for label, next_key in cur.get("choices", []):
            if text == label:
                nxt = db.get(next_key)
                if nxt:
                    g["scene"] = next_key
                    run_scene(uid, nxt)
                    if nxt.get("end"):
                        clear_game(uid)
                else:
                    send(uid, "🚧 Эта ветка в разработке.", kb=kb)
                return True
        # Неизвестный ввод — перепоказываем сцену
        run_scene(uid, cur)
        return True

    return False


# ── Ежедневные задания ────────────────────────────────────────────
DAILY_QUESTS = [
    {"title": "📿 Задание: Не оборачивайся",
     "steps": ["Сегодняшнее задание: следующие 10 минут — не оборачивайся.",
               "Что бы ни происходило позади тебя.",
               "Что бы ты ни слышал.",
               "Обещаешь? (напиши «да»)"],
     "reward": 25},
    {"title": "🕯 Задание: Тёмная комната",
     "steps": ["Задание: выключи весь свет на 1 минуту.",
               "Просто посиди в темноте.",
               "Ты готов? (напиши «готов»)"],
     "reward": 30},
    {"title": "🪞 Задание: Зеркало",
     "steps": ["Подойди к зеркалу.",
               "Посмотри в него ровно 30 секунд.",
               "Не моргай.",
               "Что ты видишь? (напиши ответ)"],
     "reward": 20},
    {"title": "🌑 Задание: Полночь",
     "steps": ["Сегодня ровно в полночь напиши мне: «я здесь».",
               "Просто два слова.",
               "Посмотрим что произойдёт."],
     "reward": 40},
    {"title": "🚪 Задание: Закрытая дверь",
     "steps": ["Есть ли в твоём доме дверь за которой ты давно не был?",
               "Открой её прямо сейчас.",
               "Напиши что там. (один ответ)"],
     "reward": 35},
    {"title": "📱 Задание: Без телефона",
     "steps": ["Задание: 15 минут без телефона.",
               "Положи его экраном вниз.",
               "Иди. Я подожду.",
               "Как прошло? Что ты чувствовал?"],
     "reward": 45},
    {"title": "🌙 Задание: Темнота снаружи",
     "steps": ["Выйди на улицу ночью. Хотя бы на 2 минуты.",
               "Посмотри в темноту.",
               "Опиши что видишь."],
     "reward": 50},
]

def send_daily_quest(uid: int, pool=None):
    import datetime
    from database import get_daily_info, set_daily_done
    u = get_user(uid)
    today = datetime.date.today().isoformat()
    info = get_daily_info(uid)
    if info.get("last_date") == today:
        send(uid, "🗓 Ты уже выполнил задание сегодня.\nПриходи завтра... если сможешь. 👁",
             kb=_kb(u.get("stage", 0)))
        return

    quest = random.choice(DAILY_QUESTS)
    streak = info.get("streak", 0)

    def _run(_uid=uid, _quest=quest, _today=today, _streak=streak):
        from keyboards import main_kb
        u2 = get_user(_uid)
        send(_uid, _quest["title"])
        time.sleep(2)
        for step in _quest["steps"]:
            send(_uid, step)
            time.sleep(random.uniform(3, 5))
        time.sleep(10)
        set_daily_done(_uid, _today, _streak + 1)
        new_score = u2.get("score", 0) + _quest["reward"]
        update_user_field(_uid, "score", new_score)
        send(_uid,
            f"✅ Задание принято.\n🏆 +{_quest['reward']} очков страха.\n"
            f"Итого: {new_score}\n\n...до завтра. 👁",
            kb=main_kb(u2.get("stage", 0)))
        # Ачивка за стрик
        if _streak + 1 >= 3:
            check_achievement(_uid, "daily_streak_3")

    if pool:
        pool.submit(_run)
    else:
        import threading
        threading.Thread(target=_run, daemon=True).start()


# ── Лидерборды ───────────────────────────────────────────────────
def get_leaderboard_text(city: str = None) -> str:
    from database import get_leaderboard
    rows = get_leaderboard(limit=10, city=city)
    medals = ["🥇", "🥈", "🥉"]
    if city:
        header = f"🌆 РЕЙТИНГ {city.upper()}\n\n"
    else:
        header = "🏆 ТАБЛИЦА ЛИДЕРОВ СТРАХА\n\n"
    if not rows:
        return header + "Пусто."
    lines = []
    for i, r in enumerate(rows):
        medal = medals[i] if i < 3 else f"{i+1}."
        uname = ("@" + r["username"]) if r.get("username") else f"ID:{r['uid']}"
        name  = r.get("name") or "?"
        lines.append(f"{medal} {name} ({uname}) — {r['score']} очков  Ст.{r['stage']}")
    return header + "\n".join(lines)

def send_leaderboard_to_victim(uid: int):
    from database import get_user_rank
    u = get_user(uid)
    rank = get_user_rank(uid)
    city = u.get("city")
    text = (f"🏆 Место в рейтинге страха: #{rank}\n"
            f"Твои очки: {u.get('score', 0)}\n\n"
            f"...чем больше страха — тем выше. 👁")
    if city:
        text += f"\n\nПишу «рейтинг города» — увидишь рейтинг {city}."
    send(uid, text, kb=_kb(u.get("stage", 0)))
