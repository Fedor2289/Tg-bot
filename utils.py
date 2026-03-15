"""
utils.py — Общие утилиты: отправка, перевод, погода, голос, anti-spam.
"""
import os
import time
import random
import threading
import logging
import traceback
import requests
import datetime

import telebot
from config import BOT_TOKEN, WEATHER_API_KEY, SPY_FORWARD, log

log = logging.getLogger("horror.utils")

# ── Бот ──────────────────────────────────────────────────────────
bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None, threaded=False)

# ── Voice ─────────────────────────────────────────────────────────
from config import VOICE_ENABLED
try:
    from gtts import gTTS
except ImportError:
    gTTS = None
    log.warning("gTTS не установлен — голосовые отключены")

# ── Anti-spam ─────────────────────────────────────────────────────
from config import SPAM_INTERVAL
_last_msg: dict  = {}
_spam_lock = threading.Lock()

def spam_check(uid: int) -> bool:
    with _spam_lock:
        now = time.time()
        if now - _last_msg.get(uid, 0) < SPAM_INTERVAL:
            return False
        _last_msg[uid] = now
        return True

def spam_mark(uid: int):
    with _spam_lock:
        now = time.time()
        if now - _last_msg.get(uid, 0) >= 1:
            _last_msg[uid] = now


# ── Безопасная отправка ───────────────────────────────────────────
def _safe_call(fn, *args, retries=3, **kwargs):
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except telebot.apihelper.ApiTelegramException as e:
            if e.error_code == 429:
                wait = int(e.result_json.get("parameters", {}).get("retry_after", 5))
                time.sleep(wait + 1)
            elif e.error_code in (400, 403):
                return None  # бот заблокирован или чат не найден
            else:
                if attempt < retries - 1:
                    time.sleep(2)
        except Exception as e:
            log.error(f"_safe_call error attempt={attempt}: {e}")
            if attempt < retries - 1:
                time.sleep(1)
    return None


def send(uid: int, text: str, kb=None) -> None:
    try:
        spam_mark(uid)
        if kb:
            _safe_call(bot.send_message, uid, text, reply_markup=kb)
        else:
            _safe_call(bot.send_message, uid, text)
    except Exception as e:
        log.error(f"send() uid={uid}: {e}")


def send_group(chat_id: int, text: str, kb=None) -> None:
    try:
        if kb:
            _safe_call(bot.send_message, chat_id, text, reply_markup=kb)
        else:
            _safe_call(bot.send_message, chat_id, text)
    except Exception as e:
        log.debug(f"send_group() chat={chat_id}: {e}")


def send_typing(uid: int):
    try:
        bot.send_chat_action(uid, "typing")
    except Exception:
        pass


def send_photo(uid: int, photo_src, caption: str = ""):
    try:
        if isinstance(photo_src, str) and photo_src.startswith("http"):
            _safe_call(bot.send_photo, uid, photo_src, caption=caption)
        else:
            with open(photo_src, "rb") as f:
                _safe_call(bot.send_photo, uid, f, caption=caption)
    except Exception as e:
        log.debug(f"send_photo() uid={uid}: {e}")


def send_gif(uid: int, url: str):
    try:
        _safe_call(bot.send_animation, uid, url)
    except Exception as e:
        log.debug(f"send_gif() uid={uid}: {e}")


def send_audio(uid: int, audio_path: str, caption: str = ""):
    """Отправляет mp3/ogg аудиофайл."""
    try:
        with open(audio_path, "rb") as f:
            _safe_call(bot.send_audio, uid, f, caption=caption)
    except Exception as e:
        log.debug(f"send_audio() uid={uid}: {e}")


# ── Голос (TTS) ───────────────────────────────────────────────────
def send_voice_msg(uid: int, text: str, lang: str = "ru"):
    """Синтез речи через gTTS и отправка голосовым сообщением."""
    if not VOICE_ENABLED or not text.strip():
        return
    try:
        import tempfile, os
        # Чистим текст от emoji и спец-символов для TTS
        import re
        clean = re.sub(r'[^\w\s\.,!?;:\-]', '', text, flags=re.UNICODE).strip()
        if not clean:
            return
        clean = clean[:300]
        tts = gTTS(text=clean, lang=lang, slow=False)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tts.save(f.name)
            tmp_path = f.name
        with open(tmp_path, "rb") as f:
            _safe_call(bot.send_voice, uid, f)
        os.unlink(tmp_path)
    except Exception as e:
        log.debug(f"send_voice_msg() uid={uid}: {e}")


def send_group_voice(chat_id: int, text: str):
    """Голосовое в группу."""
    if not VOICE_ENABLED or not text.strip():
        return
    try:
        import tempfile, os, re
        clean = re.sub(r'[^\w\s\.,!?;:\-]', '', text, flags=re.UNICODE).strip()[:300]
        if not clean:
            return
        tts = gTTS(text=clean, lang="ru", slow=False)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tts.save(f.name)
            tmp_path = f.name
        with open(tmp_path, "rb") as f:
            _safe_call(bot.send_voice, chat_id, f)
        os.unlink(tmp_path)
    except Exception as e:
        log.debug(f"send_group_voice() chat={chat_id}: {e}")


# ── Перевод ───────────────────────────────────────────────────────
_translate_cache: dict = {}

def translate(text: str, lang_pair: str = "ru|en") -> str | None:
    key = (text[:100], lang_pair)
    if key in _translate_cache:
        return _translate_cache[key]
    try:
        r = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": lang_pair},
            timeout=8,
        ).json()
        result = r.get("responseData", {}).get("translatedText", "")
        if (result
                and "INVALID LANGUAGE PAIR" not in result
                and "QUERY LENGTH LIMIT" not in result
                and result.strip().lower() != text.strip().lower()):
            _translate_cache[key] = result
            if len(_translate_cache) > 200:
                del _translate_cache[next(iter(_translate_cache))]
            return result
        return None
    except Exception:
        return None


# ── Погода ────────────────────────────────────────────────────────
def get_weather(city: str) -> str | None:
    if not WEATHER_API_KEY:
        return None
    try:
        r = requests.get(
            "http://api.openweathermap.org/data/2.5/weather",
            params=dict(q=city, appid=WEATHER_API_KEY, units="metric", lang="ru"),
            timeout=5,
        ).json()
        if r.get("cod") != 200:
            return None
        t   = r["main"]["temp"]
        fl  = r["main"]["feels_like"]
        hm  = r["main"]["humidity"]
        ds  = r["weather"][0]["description"]
        ws  = r.get("wind", {}).get("speed", "?")
        return (f"🌤 Погода в {r['name']}:\n"
                f"🌡 {t}°C (ощущается {fl}°C)\n"
                f"💧 Влажность: {hm}%   💨 Ветер: {ws} м/с\n"
                f"☁️ {ds.capitalize()}")
    except Exception:
        return None


# ── Новости из города ─────────────────────────────────────────────
_news_cache: dict = {}
_NEWS_TTL = 1800  # 30 минут

def get_city_news(city: str, max_chars: int = 200) -> str:
    if not city:
        return ""
    now = time.time()
    cached = _news_cache.get(city)
    if cached and now - cached[0] < _NEWS_TTL:
        return cached[1]
    try:
        import urllib.request, urllib.parse, re as _re
        query = urllib.parse.quote(f"{city} сегодня")
        url   = f"https://news.google.com/rss/search?q={query}&hl=ru&gl=RU&ceid=RU:ru"
        req   = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            xml = resp.read().decode("utf-8", errors="ignore")
        titles = _re.findall(r"<title><!\[CDATA\[(.+?)\]\]></title>", xml)
        titles = [t for t in titles if len(t) > 10 and "Google" not in t]
        news = titles[0][:max_chars] if titles else ""
    except Exception:
        news = ""
    _news_cache[city] = (now, news)
    return news


# ── Шпионаж ───────────────────────────────────────────────────────
def spy_forward(uid: int, text: str, admins: set, admin_states: dict):
    """Пересылает сообщение жертвы всем admin'ам."""
    if not SPY_FORWARD:
        return
    from database import get_user
    u = get_user(uid)
    if not u.get("spy", True):
        return
    name  = u.get("name") or f"ID:{uid}"
    stage = u.get("stage", 0)
    for aid in list(admins):
        # Если admin сейчас редактирует — не засоряем
        step = admin_states.get(aid, {}).get("step", "")
        if step in ("wait_grp_broadcast", "wait_ai_intercept_text"):
            continue
        try:
            bot.send_message(
                aid,
                f"👁 [{name} | ст.{stage}]: {text[:300]}",
            )
        except Exception:
            pass


# ── Вспомогательные ───────────────────────────────────────────────
def dnight() -> bool:
    """True если сейчас ночь (00:00 – 04:00)."""
    return 0 <= datetime.datetime.now().hour <= 4

def P(template: str, user: dict) -> str:
    """Подставляет данные пользователя в шаблон хоррора."""
    name  = user.get("name")  or "ты"
    city  = user.get("city")  or "твоём городе"
    fear  = user.get("fear")  or "темнота"
    age   = user.get("age")   or "?"
    pet   = user.get("pet")   or ""
    job   = user.get("job")   or ""
    phone = user.get("phone_model") or "телефон"
    return (template
            .replace("{name}",  name)
            .replace("{city}",  city)
            .replace("{fear}",  fear)
            .replace("{age}",   str(age))
            .replace("{pet}",   pet)
            .replace("{job}",   job)
            .replace("{phone}", phone))


# ── Гифки ────────────────────────────────────────────────────────
_gif_cache: list = []
_gif_mtime: float = 0

def get_random_gif(gif_dir: str = "gifs") -> str | None:
    global _gif_cache, _gif_mtime
    try:
        mtime = os.path.getmtime(gif_dir) if os.path.isdir(gif_dir) else 0
        if mtime != _gif_mtime:
            _gif_mtime = mtime
            _gif_cache = [
                os.path.join(gif_dir, f)
                for f in os.listdir(gif_dir)
                if f.lower().endswith((".gif", ".mp4"))
            ]
        return random.choice(_gif_cache) if _gif_cache else None
    except Exception:
        return None
