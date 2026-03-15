"""
keyboards.py — Все клавиатуры бота в одном месте.
Кнопки организованы по уровням: при нажатии появляются подменю.
"""
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)

# ════════════════════════════════════════════════════════════════
#  ГЛАВНОЕ МЕНЮ (Reply-клавиатуры по стадиям)
# ════════════════════════════════════════════════════════════════

def main_kb(stage: int = 0) -> ReplyKeyboardMarkup:
    """Главная клавиатура. Меняется с ростом стадии страха."""
    k = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if stage < 2:
        # 0-1: дружелюбный переводчик
        k.add(KeyboardButton("🌍 Перевести"),    KeyboardButton("🔤 Язык"))
        k.add(KeyboardButton("🌤 Погода"),       KeyboardButton("🎮 Игры"))
        k.add(KeyboardButton("🤖 ИИ"),           KeyboardButton("🗓 Задание"))
        k.add(KeyboardButton("🏆 Рейтинг"),      KeyboardButton("🛒 Магазин"))
        k.add(KeyboardButton("❓ Помощь"),        KeyboardButton("🔫 Мафия"))
    elif stage < 4:
        # 2-3: нарастающая тьма
        k.add(KeyboardButton("🌍 Перевести"),    KeyboardButton("🔤 Язык"))
        k.add(KeyboardButton("🌑 Погода"),       KeyboardButton("🎮 Игры"))
        k.add(KeyboardButton("🤖 ИИ"),           KeyboardButton("🗓 Задание"))
        k.add(KeyboardButton("🏆 Рейтинг"),      KeyboardButton("🛒 Магазин"))
        k.add(KeyboardButton("👁 ..."),          KeyboardButton("🔫 Мафия"))
    else:
        # 4+: тьма
        k.add(KeyboardButton("🌍 Перевести"),    KeyboardButton("🔤 Язык"))
        k.add(KeyboardButton("🌑 Погода"),       KeyboardButton("🩸 Игры"))
        k.add(KeyboardButton("🤖 ИИ"),           KeyboardButton("🗓 Задание"))
        k.add(KeyboardButton("🏆 Рейтинг"),      KeyboardButton("🛒 Магазин"))
        k.add(KeyboardButton("👁 Кто ты?"),      KeyboardButton("🔫 Мафия"))
        k.add(KeyboardButton("💀 /stop"))
    return k

# Все кнопки которые НЕ должны идти в ИИ-диалог
MAIN_BUTTONS = {
    "🌍 Перевести", "🔤 Язык", "🌤 Погода", "🌑 Погода",
    "🎮 Игры", "🩸 Игры", "💀 Игры",
    "🤖 ИИ", "🗓 Задание", "🏆 Рейтинг", "🛒 Магазин",
    "❓ Помощь", "👁 ...", "👁 Кто ты?", "🙂 О боте",
    "💀 /stop", "↩️ Назад", "❌ Выйти из игры",
    "🔫 Мафия", "🔫 Мафия (ЛС)", "🎭 Карточная история",
    "🗡 Мини-RPG", "📖 Страшные истории", "🔦 Квест",
}


# ════════════════════════════════════════════════════════════════
#  ПОДМЕНЮ ИГРЫ
# ════════════════════════════════════════════════════════════════

def games_kb(stage: int = 0) -> ReplyKeyboardMarkup:
    """Подменю игр (открывается при нажатии 🎮 Игры)."""
    k = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    k.add(KeyboardButton("🗡 Мини-RPG"),         KeyboardButton("📖 Страшные истории"))
    k.add(KeyboardButton("🔦 Квест"),            KeyboardButton("🎭 Карточная история"))
    k.add(KeyboardButton("🔫 Мафия (ЛС)"),      KeyboardButton("🎲 Угадай число"))
    k.add(KeyboardButton("🧠 Викторина"),        KeyboardButton("✏️ Виселица"))
    k.add(KeyboardButton("🎭 Загадка"),          KeyboardButton("🔮 Предсказание"))
    k.add(KeyboardButton("📖 Факт"),             KeyboardButton("🏅 Ачивки"))
    k.add(KeyboardButton("↩️ Назад"))
    return k


# ════════════════════════════════════════════════════════════════
#  ПОДМЕНЮ ПОМОЩИ
# ════════════════════════════════════════════════════════════════

def help_kb() -> ReplyKeyboardMarkup:
    k = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    k.add(KeyboardButton("📋 Команды"),      KeyboardButton("🙂 О боте"))
    k.add(KeyboardButton("👥 Анонимный чат"),KeyboardButton("🤝 Пригласить друга"))
    k.add(KeyboardButton("↩️ Назад"))
    return k


# ════════════════════════════════════════════════════════════════
#  МАГАЗИН (Inline)
# ════════════════════════════════════════════════════════════════

def shop_kb(uid: int) -> InlineKeyboardMarkup:
    k = InlineKeyboardMarkup(row_width=1)
    k.add(
        InlineKeyboardButton("🛡 Щит 1 час — 50 очков",    callback_data=f"shop_shield_1h_{uid}"),
        InlineKeyboardButton("🛡 Щит 24 часа — 150 очков", callback_data=f"shop_shield_24h_{uid}"),
        InlineKeyboardButton("🔕 Тишина 2 часа — 35 очков",callback_data=f"shop_silence_2h_{uid}"),
        InlineKeyboardButton("💡 Подсказка в квесте — 30", callback_data=f"shop_hint_quest_{uid}"),
        InlineKeyboardButton("😈 Ужас другому — 40 очков", callback_data=f"shop_boost_fear_{uid}"),
        InlineKeyboardButton("📋 Доп. задание — 20 очков", callback_data=f"shop_extra_daily_{uid}"),
    )
    return k


# ════════════════════════════════════════════════════════════════
#  ADMIN — главная панель
# ════════════════════════════════════════════════════════════════

def admin_main_kb() -> ReplyKeyboardMarkup:
    k = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    k.add(KeyboardButton("👥 Жертвы"),               KeyboardButton("📊 Статистика"))
    k.add(KeyboardButton("💀 Ужас всем"),            KeyboardButton("🛑 Стоп всем"))
    k.add(KeyboardButton("📤 Рассылка всем"),        KeyboardButton("🔇 Тишина всем"))
    k.add(KeyboardButton("🔊 Звук всем"),            KeyboardButton("💬 Чат жертв"))
    k.add(KeyboardButton("⚙️ Выбрать жертву"),       KeyboardButton("📋 Список ID"))
    k.add(KeyboardButton("🏆 Лидеры"),               KeyboardButton("🎬 Сценарии"))
    k.add(KeyboardButton("🤖 ИИ-настройки"),         KeyboardButton("👑 Со-admin'ы"))
    k.add(KeyboardButton("🚫 Забанить"),             KeyboardButton("✅ Разбанить"))
    k.add(KeyboardButton("🗑 Сбросить всех"),        KeyboardButton("📡 По ID"))
    k.add(KeyboardButton("🔙 Выйти из бога"))
    return k


def admin_victim_kb() -> ReplyKeyboardMarkup:
    """Панель управления конкретной жертвой."""
    k = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    k.add(KeyboardButton("📝 Текст"),              KeyboardButton("🎬 Гифка"))
    k.add(KeyboardButton("⚡ Скример"),            KeyboardButton("☠️ Макс-ужас"))
    k.add(KeyboardButton("🌊 Волна паники"),       KeyboardButton("🕯 Ритуал"))
    k.add(KeyboardButton("💬 Диалог-ловушка"),     KeyboardButton("😴 Спящий режим"))
    k.add(KeyboardButton("⬆️ Стадия +1"),          KeyboardButton("⬇️ Стадия -1"))
    k.add(KeyboardButton("🔇 Заглушить"),          KeyboardButton("🔊 Включить"))
    k.add(KeyboardButton("📱 Взлом телефона"),     KeyboardButton("🎙 Голос от него"))
    k.add(KeyboardButton("📞 Фейк-звонок"),        KeyboardButton("💀 Таймер смерти"))
    k.add(KeyboardButton("🪞 Зеркало"),            KeyboardButton("🫀 Сердцебиение"))
    k.add(KeyboardButton("👁 ИИ-атака"),           KeyboardButton("🎬 Персональный сценарий"))
    k.add(KeyboardButton("🤖 ИИ пишет за меня"),   KeyboardButton("✏️ Редактировать данные"))
    k.add(KeyboardButton("❄️ Заморозить стадию"),  KeyboardButton("📋 Инфо о жертве"))
    k.add(KeyboardButton("🔄 Сбросить"),           KeyboardButton("🔙 Назад"))
    return k


# ════════════════════════════════════════════════════════════════
#  ГРУППА
# ════════════════════════════════════════════════════════════════

def group_main_kb() -> ReplyKeyboardMarkup:
    k = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    k.add(KeyboardButton("🎮 Игры"),    KeyboardButton("🤖 Спросить ИИ"), KeyboardButton("🔫 Мафия"))
    k.add(KeyboardButton("🏆 Рейтинг"),KeyboardButton("🌤 Погода"),       KeyboardButton("🌍 Перевести"))
    k.add(KeyboardButton("🔤 Язык"),   KeyboardButton("❓ Помощь"))
    return k


def group_games_kb(chat_id: int) -> InlineKeyboardMarkup:
    k = InlineKeyboardMarkup(row_width=2)
    k.add(
        InlineKeyboardButton("🍾 Бутылочка",       callback_data=f"gg_bottle_{chat_id}"),
        InlineKeyboardButton("🪙 Монетка",         callback_data=f"gg_coin_{chat_id}"),
        InlineKeyboardButton("🎲 Кубик",           callback_data=f"gg_dice_{chat_id}"),
        InlineKeyboardButton("🔫 Рулетка",         callback_data=f"gg_roulette_{chat_id}"),
        InlineKeyboardButton("🎭 Правда/Действие", callback_data=f"gg_tod_{chat_id}"),
        InlineKeyboardButton("⚖️ Что лучше?",      callback_data=f"gg_wr_{chat_id}"),
        InlineKeyboardButton("🔥 Кто в группе?",   callback_data=f"gg_hottake_{chat_id}"),
        InlineKeyboardButton("🧠 Викторина",       callback_data=f"gg_trivia_{chat_id}"),
        InlineKeyboardButton("🎲 Угадай число",    callback_data=f"gg_number_{chat_id}"),
        InlineKeyboardButton("✏️ Виселица",        callback_data=f"gg_hangman_{chat_id}"),
        InlineKeyboardButton("🔫 Мафия",           callback_data=f"gg_mafia_{chat_id}"),
        InlineKeyboardButton("🗡 RPG",             callback_data=f"gg_rpg_{chat_id}"),
        InlineKeyboardButton("📖 История с ИИ",    callback_data=f"gg_aistory_{chat_id}"),
        InlineKeyboardButton("🤖 Добавить ИИ",     callback_data=f"gg_addai_{chat_id}"),
        InlineKeyboardButton("❌ Стоп",            callback_data=f"gg_stop_{chat_id}"),
    )
    return k


# ════════════════════════════════════════════════════════════════
#  ЯЗЫК
# ════════════════════════════════════════════════════════════════

def lang_kb(lang_names: dict) -> ReplyKeyboardMarkup:
    k = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for name in lang_names.values():
        k.add(KeyboardButton(name))
    k.add(KeyboardButton("↩️ Назад"))
    return k


# ════════════════════════════════════════════════════════════════
#  ИГРОВЫЕ КЛАВИАТУРЫ
# ════════════════════════════════════════════════════════════════

def game_choices_kb(choices: list) -> ReplyKeyboardMarkup:
    """Клавиатура для RPG/квестов с вариантами."""
    k = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for label, _ in choices:
        k.add(KeyboardButton(label))
    k.add(KeyboardButton("❌ Выйти из игры"))
    return k


def trivia_kb(options: list) -> ReplyKeyboardMarkup:
    k = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for o in options:
        k.add(KeyboardButton(o))
    k.add(KeyboardButton("❌ Выйти из игры"))
    return k


# ════════════════════════════════════════════════════════════════
#  МАФИЯ
# ════════════════════════════════════════════════════════════════

def maf_lobby_kb(lid: int) -> InlineKeyboardMarkup:
    k = InlineKeyboardMarkup(row_width=1)
    k.add(
        InlineKeyboardButton("✅ Участвую!", callback_data=f"maf_join_{lid}"),
        InlineKeyboardButton("▶️ Старт", callback_data=f"maf_start_{lid}"),
        InlineKeyboardButton("❌ Отменить", callback_data=f"maf_cancel_{lid}"),
    )
    return k


def maf_vote_kb(lid: int, players: dict, alive: list) -> InlineKeyboardMarkup:
    k = InlineKeyboardMarkup(row_width=1)
    for uid in alive:
        name = players.get(uid, "?")
        k.add(InlineKeyboardButton(f"⚖️ {name}", callback_data=f"maf_v_{lid}_{uid}"))
    k.add(InlineKeyboardButton("⏭ Воздержаться", callback_data=f"maf_vs_{lid}"))
    return k


def maf_night_kb(lid: int, player_uid: int, players: dict, alive: list) -> InlineKeyboardMarkup:
    k = InlineKeyboardMarkup(row_width=1)
    for uid in alive:
        if uid == player_uid:
            continue
        name = players.get(uid, "?")
        k.add(InlineKeyboardButton(f"🎯 {name}", callback_data=f"maf_n_{lid}_{player_uid}_{uid}"))
    return k


# ════════════════════════════════════════════════════════════════
#  АЧИВКИ
# ════════════════════════════════════════════════════════════════

def achievements_kb(uid: int) -> InlineKeyboardMarkup:
    k = InlineKeyboardMarkup()
    k.add(InlineKeyboardButton("📋 Показать все ачивки", callback_data=f"achievements_{uid}"))
    return k


# Пустая клавиатура (убрать)
remove_kb = ReplyKeyboardRemove()
