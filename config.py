"""
╔══════════════════════════════════════════════════════════════════╗
║                  👁  HORROR BOT — config.py                     ║
║         Все настройки читаются из переменных окружения           ║
╚══════════════════════════════════════════════════════════════════╝
"""
import os
import logging

# ── Основные настройки ────────────────────────────────────────────
BOT_TOKEN        = os.environ.get("BOT_TOKEN", "")
WEATHER_API_KEY  = os.environ.get("WEATHER_API_KEY", "")
ADMIN_ID         = int(os.environ.get("ADMIN_ID", "0"))

# ── ИИ ───────────────────────────────────────────────────────────
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY", "")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "")
AI_BACKEND       = os.environ.get("AI_BACKEND", "auto")   # groq | cerebras | auto

# ── Параметры хоррора ─────────────────────────────────────────────
STAGE_SEC        = int(os.environ.get("STAGE_SEC", "900"))    # 15 мин между стадиями
HORROR_DELAY_SEC = int(os.environ.get("HORROR_DELAY_SEC", "45"))
SPAM_INTERVAL    = int(os.environ.get("SPAM_INTERVAL", "8"))  # мин. интервал сообщений

# ── Группы ───────────────────────────────────────────────────────
GROUP_AUTO_VOICE = os.environ.get("GROUP_AUTO_VOICE", "1") == "1"

# ── Прочее ───────────────────────────────────────────────────────
SPY_FORWARD      = True     # пересылать сообщения жертв admin'ам
GIF_DIR          = "gifs"   # папка с гифками
DB_PATH          = os.environ.get("DB_PATH", "horror.db")  # SQLite база данных

# ── ИИ-личность ──────────────────────────────────────────────────
AI_NAME          = os.environ.get("AI_NAME", "Наблюдатель")
AI_MEMORY_DAYS   = 7  # помнит последнюю неделю

# ── Поддерживаемые языки ─────────────────────────────────────────
LANG_NAMES = {
    "ru|en":    "🇷🇺 Русский → 🇬🇧 Английский",
    "en|ru":    "🇬🇧 Английский → 🇷🇺 Русский",
    "ru|de":    "🇷🇺 Русский → 🇩🇪 Немецкий",
    "ru|fr":    "🇷🇺 Русский → 🇫🇷 Французский",
    "ru|es":    "🇷🇺 Русский → 🇪🇸 Испанский",
    "ru|zh-CN": "🇷🇺 Русский → 🇨🇳 Китайский",
    "ru|ja":    "🇷🇺 Русский → 🇯🇵 Японский",
    "ru|ar":    "🇷🇺 Русский → 🇸🇦 Арабский",
}

# ── Логгер ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("horror")

# ── Валидация ────────────────────────────────────────────────────
def validate():
    errors = []
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN не задан")
    if not ADMIN_ID:
        errors.append("ADMIN_ID не задан")
    if errors:
        for e in errors:
            log.error(f"❌ Конфиг: {e}")
        return False
    return True
