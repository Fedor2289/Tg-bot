"""
games/card_story.py — Карточная история (visual-novel style).
"""
from utils import send
from database import get_user, update_user_field
from horror.engine import check_achievement

_card_story: dict = {}  # uid → {story_id, scene, character, inventory}


CARD_CHARACTERS = {
    "детектив": {
        "name": "🔎 Детектив",
        "desc": "Ты — опытный детектив. Острый ум, холодный расчёт.\n+бонус к расследованию, -1 к боевым ситуациям",
        "bonus": "invest",
    },
    "выживший": {
        "name": "🧠 Выживший",
        "desc": "Ты — выживший. Ты уже видел ужас.\n+бонус к побегу, +1 к смелости",
        "bonus": "escape",
    },
    "учёный": {
        "name": "🔬 Учёный",
        "desc": "Ты — учёный. Рациональный ум.\n+бонус к пониманию аномалий, -боюсь темноты",
        "bonus": "science",
    },
    "призрак": {
        "name": "👻 Призрак",
        "desc": "Ты — призрак. Уже мёртвый. Помогаешь живым.\n+видишь скрытое, нельзя умереть снова",
        "bonus": "ghost",
    },
    "охотник": {
        "name": "⚔️ Охотник на нечисть",
        "desc": "Ты — охотник. Специальное оружие, опыт.\n+бонус в битвах, -1 к дипломатии",
        "bonus": "hunter",
    },
}

CARD_STORIES = {
    "особняк": {
        "title": "🏚 ОСОБНЯК",
        "scenes": {
            "start": {
                "text": "Вы оказались в старом особняке.\nДвери заперты. За окнами — туман.\n\nВпереди — три коридора.",
                "choices": [
                    ("🕯 Идти налево", "hall_left"),
                    ("🪞 Идти направо (зеркальный зал)", "hall_right"),
                    ("🔑 Найти ключ (подвал)", "basement"),
                ],
                "bonus_choice": {
                    "invest": ("🔍 Осмотреть замок детально", "detective_lock"),
                    "ghost": ("👻 Почувствовать присутствие", "ghost_sense"),
                }
            },
            "hall_left": {
                "text": "Тёмный коридор.\nНа полу — кровавые следы.\nВпереди — скрип.",
                "choices": [("🏃 Бежать", "run_escape"), ("🔦 Исследовать", "library"), ("😶 Замереть", "freeze_end")],
            },
            "hall_right": {
                "text": "Зеркальный зал.\nДесятки отражений.\nОдно из них не движется.",
                "choices": [("👁 Смотреть", "mirror_horror"), ("🏃 Уйти", "hall_left"), ("💬 Говорить", "mirror_talk")],
                "bonus_choice": {"ghost": ("👻 Поговорить с отражением-призраком", "ghost_mirror")}
            },
            "basement": {
                "text": "Подвал.\nПахнет землёй и старым деревом.\nНа столе — дневник.",
                "choices": [("📖 Читать", "diary"), ("🔑 Найти ключ", "key_found"), ("🏃 Назад", "start")],
                "bonus_choice": {
                    "invest": ("🔍 Снять отпечатки пальцев", "fingerprints"),
                    "science": ("🔬 Исследовать образцы", "science_analyze"),
                }
            },
            "library": {
                "text": "Библиотека.\nКниги написаны неизвестными символами.\nОдна — открытая.",
                "choices": [("📖 Читать книгу", "book_truth"), ("🔑 Найти выход", "key_found"), ("🏃 Бежать", "run_escape")],
                "bonus_choice": {"science": ("🔬 Расшифровать символы", "science_decode")}
            },
            "diary": {
                "text": "В дневнике — записи хозяина.\n«Они приходят каждую ночь».\n«Я слышу их за стенами».\nПоследняя страница вырвана.",
                "choices": [("🔑 Найти ключ", "key_found"), ("📖 Книга (библиотека)", "library"), ("🚪 Выход", "run_escape")],
            },
            "mirror_horror": {
                "text": "Неподвижное отражение поворачивает голову.\nОно смотрит на тебя.\nОно улыбается.",
                "choices": [("💥 Разбить зеркало", "mirror_break"), ("🏃 Бежать", "hall_left"), ("👁 Продолжать смотреть", "mirror_stare_deep")],
            },
            "mirror_talk": {
                "text": "«Помоги нам».\nГолос идёт из зеркала.\n«Мы застряли».\n«Нас здесь много».",
                "choices": [("❓ Как помочь?", "mirror_help"), ("🏃 Уйти", "hall_left")],
            },
            "mirror_break": {
                "text": "Зеркало разбито.\nОсколки светятся.\nВ каждом — лицо.\nОни все смотрят на тебя.",
                "choices": [("🔑 Ключ в осколках", "key_found"), ("🏃 Бежать", "run_escape")],
            },
            "mirror_stare_deep": {
                "text": "Ты смотришь дольше.\nОтражение говорит:\n«Ты уже был здесь».\n«Ты никогда не уходил».",
                "choices": [("🔄 Начать заново", "start")], "end": True,
            },
            "mirror_help": {
                "text": "«Выход — там где нет отражений».\nТы замечаешь угол без зеркала.\nТам — дверь.",
                "choices": [("🚪 Открыть дверь", "mansion_escape")],
            },
            "mirror_talk_ghost": {
                "text": "(Только призрак видит) Отражения — это застрявшие души.\nОни указывают путь.",
                "choices": [("👻 Следовать за душами", "mansion_escape"), ("🏃 Уйти", "start")],
            },
            "ghost_sense": {
                "text": "👻 Ты чувствуешь — здесь много душ.\nОни тянутся к тебе.\nОдна — указывает налево.",
                "choices": [("👁 Следовать", "ghost_path"), ("🏃 Идти своим путём", "start")],
            },
            "ghost_path": {
                "text": "Душа ведёт тебя к потайной двери.\nЗа ней — выход.",
                "choices": [("🚪 Выйти", "mansion_escape")],
            },
            "ghost_mirror": {
                "text": "Призрак в зеркале — знакомый.\nОн говорит: «Подвал. Третья плита».",
                "choices": [("⬇️ В подвал", "basement_secret")],
            },
            "basement_secret": {
                "text": "Третья плита. Ты поднимаешь её.\nЗа ней — выход на улицу.",
                "choices": [("🚪 Выйти", "mansion_escape")],
            },
            "detective_lock": {
                "text": "🔎 Замок вскрыт снаружи. Кто-то заманил вас.\nПо следам: 3 человека. Ушли 2 часа назад.",
                "choices": [("🔍 Искать их", "hall_left"), ("🔑 Найти запасной выход", "basement")],
            },
            "fingerprints": {
                "text": "🔎 Отпечатки совпадают с хозяином дома.\nОн всё ещё здесь.",
                "choices": [("😱 Найти хозяина", "mansion_owner"), ("🏃 Бежать", "run_escape")],
            },
            "mansion_owner": {
                "text": "В тёмном углу — старик.\n«Вы нашли выход?»\n«Я ищу уже 40 лет».",
                "choices": [("🤝 Помочь ему", "mansion_escape"), ("🏃 Бежать одному", "run_escape")],
            },
            "science_analyze": {
                "text": "🔬 В образцах — органические клетки.\nНо странные. Не человеческие.\nТемпература — ниже нуля.",
                "choices": [("🔬 Исследовать далее", "science_decode"), ("🏃 Бежать", "run_escape")],
            },
            "science_decode": {
                "text": "🔬 Символы расшифрованы.\nЭто карта особняка.\nВыход — под лестницей.",
                "choices": [("🚪 К лестнице", "mansion_escape")],
            },
            "key_found": {
                "text": "🔑 Ключ найден!\nТяжёлый, старый.\nПодходит к главным дверям.",
                "choices": [("🚪 Открыть двери", "mansion_escape"), ("👁 Осмотреться ещё", "start")],
            },
            "book_truth": {
                "text": "В книге — правда.\nОсобняк — живой.\nОн питается теми кто ищет выход.",
                "choices": [("🏃 Бежать", "run_escape"), ("⚔️ Сразиться", "fight_mansion")],
                "bonus_choice": {"hunter": ("⚔️ Применить специальное оружие", "hunter_win")}
            },
            "fight_mansion": {
                "text": "Ты атакуешь тьму.\nТьма не отступает.\nНо находится трещина в стене.",
                "choices": [("🚪 В трещину", "mansion_escape"), ("⚔️ Продолжать бой", "freeze_end")],
            },
            "hunter_win": {
                "text": "⚔️ Специальное оружие работает!\nОсобняк содрогается.\nВыход открывается сам.",
                "choices": [("🚪 Выйти", "mansion_escape")],
            },
            "freeze_end": {
                "text": "Ты не двигаешься.\n...\nУтром тебя находят у входа.\nТы смотришь в одну точку. 👁",
                "choices": [("🔄 Сыграть снова", "start")], "end": True,
            },
            "run_escape": {
                "text": "Ты бежишь.\nДвери оказываются незаперты.\nТы на улице.\n\nНо особняк за тобой исчез.\nА в кармане — ключ.\nОткуда он?",
                "choices": [("🔄 Сыграть снова", "start")], "end": True,
            },
            "mansion_escape": {
                "text": "🌅 Ты выбрался из особняка!\n\nНа улице — рассвет.\nТелефон разряжен.\nВ галерее — фото.\nТы их не делал.\n\n👁 КОНЕЦ",
                "choices": [("🔄 Сыграть снова", "start")], "end": True,
            },
        }
    }
}

def start_card_story(uid, story_id="особняк"):
    """Запускает карточную историю — сначала выбор персонажа."""
    _card_story[uid] = {"story_id": story_id, "scene": None, "character": None}
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for char_id, char_data in CARD_CHARACTERS.items():
        kb.add(KeyboardButton(f"🃏 {char_data['name'].split()[1]}"))
    send(uid,
        "🎭 КАРТОЧНАЯ ИСТОРИЯ\n\n"
        "Выбери персонажа — это повлияет на историю!\n\n" +
        "\n\n".join(f"{d['name']}\n{d['desc']}" for d in CARD_CHARACTERS.values()),
        kb=kb)

def proc_card_story(uid, text):
    """Обрабатывает карточную историю. True если обработано."""
    cs = _card_story.get(uid)
    if not cs:
        return False
    u = get_user(uid)
    kb = __import__("keyboards", fromlist=["main_kb"]).main_kb(u.get("stage",0))

    # Выбор персонажа
    if cs["character"] is None:
        for char_id, char_data in CARD_CHARACTERS.items():
            char_short = char_data["name"].split()[1]
            if text == f"🃏 {char_short}" or text.lower() == char_id:
                cs["character"] = char_id
                cs["scene"] = "start"
                char_info = CARD_CHARACTERS[char_id]
                send(uid, f"✅ Выбран: {char_info['name']}\n\n{char_info['desc']}")
                _render_card_scene(uid)
                return True
        return False

    story = CARD_STORIES.get(cs["story_id"])
    if not story:
        del _card_story[uid]; return False

    scene_key = cs.get("scene", "start")
    scene = story["scenes"].get(scene_key, {})
    char_bonus = CARD_CHARACTERS.get(cs["character"], {}).get("bonus", "")

    # Проверяем бонусный выбор
    bonus_choices = scene.get("bonus_choice", {})
    if char_bonus in bonus_choices:
        bonus_label, bonus_dest = bonus_choices[char_bonus]
        if text == bonus_label:
            next_scene = story["scenes"].get(bonus_dest)
            if next_scene:
                cs["scene"] = bonus_dest
                _render_card_scene(uid)
                if next_scene.get("end"):
                    del _card_story[uid]
                return True

    # Обычный выбор
    for label, dest in scene.get("choices", []):
        if text == label:
            next_scene = story["scenes"].get(dest)
            if next_scene:
                cs["scene"] = dest
                _render_card_scene(uid)
                if next_scene.get("end"):
                    del _card_story[uid]
            else:
                cs["scene"] = "start"
                _render_card_scene(uid)
            return True

    # Выход из истории
    if text == "❌ Выйти из истории":
        del _card_story[uid]
        u = get_user(uid)
        send(uid, "История прервана.", kb=__import__("keyboards", fromlist=["main_kb"]).main_kb(u.get("stage",0)))
        return True

    # Кнопки главного меню — выходим из истории
    if text in _MAIN_BUTTONS:
        del _card_story[uid]
        return False

    # Перепоказываем сцену при неправильном вводе
    _render_card_scene(uid)
    return True

def _render_card_scene(uid):
    """Отрисовывает текущую сцену карточной истории."""
    cs = _card_story.get(uid)
    if not cs:
        return
    story = CARD_STORIES.get(cs["story_id"])
    if not story:
        return
    scene = story["scenes"].get(cs.get("scene", "start"), {})
    char_bonus = CARD_CHARACTERS.get(cs.get("character",""), {}).get("bonus", "")
    char_name = CARD_CHARACTERS.get(cs.get("character",""), {}).get("name", "")

    all_choices = list(scene.get("choices", []))
    bonus_choices = scene.get("bonus_choice", {})
    bonus_label = None
    if char_bonus in bonus_choices:
        bonus_label, _ = bonus_choices[char_bonus]
        all_choices = list(all_choices) + [(bonus_label, None)]

    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for label, _ in all_choices:
        kb.add(KeyboardButton(label))
    kb.add(KeyboardButton("❌ Выйти из истории"))

    header = f"🎭 [{char_name}] {story['title']}\n\n"
    if bonus_label:
        header += "⭐ Есть особый выбор для твоего персонажа!\n\n"
    send(uid, header + scene.get("text", ""), kb=kb)
