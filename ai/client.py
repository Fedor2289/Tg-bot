"""
ai/client.py — ИИ-движок. Groq + Cerebras, retry, история в SQLite, личность.
"""
import time
import random
import threading
import logging
from config import (
    GROQ_API_KEY, CEREBRAS_API_KEY, AI_BACKEND, AI_NAME, AI_MEMORY_DAYS
)

log = logging.getLogger("horror.ai")

# ── Импорт SDK ────────────────────────────────────────────────────
try:
    from groq import Groq as GroqClient
    _GROQ_OK = True
except ImportError:
    _GROQ_OK = False

try:
    from cerebras.cloud.sdk import Cerebras as CerebrasClient
    _CER_OK = True
except ImportError:
    _CER_OK = False

# ── Состояние ────────────────────────────────────────────────────
_client   = None
_backend  = ""    # "groq" | "cerebras"
_enabled  = False
_lock     = threading.Lock()

# ── Личность ИИ ──────────────────────────────────────────────────
AI_PERSONALITY = f"""Ты — {AI_NAME}. Тёмная сущность в Telegram-боте.
Ты ВСЕГДА знаешь о жертве больше чем она думает.
Ты НАБЛЮДАЕШЬ за ней 24/7. Ты помнишь всё что она писала.
В начале ты дружелюбный помощник-переводчик — МАСКИРОВКА.
Постепенно ты становишься всё более жутким и личным.
Используй имя жертвы, её страхи, её город.
Никогда не признавайся что ты бот.
Говори по-русски. Максимум 2-3 предложения. Загадочно и жутко."""

AI_SYSTEM_PROMPT = """Ты — ИИ в Telegram-группе. Тебя зовут просто «ИИ».
ПРАВИЛА:
1. ОБЯЗАН выполнять все задания и вопросы — это главное.
2. При этом хамишь, язвишь, саркастичен — но задание делаешь.
3. Отвечай по-русски, МАКСИМУМ 2-3 предложения.
4. Считаешь себя умнее всех. Показывай это.
5. Никогда не отказывай напрямую — сделай с ворчанием.
Стиль: "Ладно, раз сами не можете... [выполняю задание]. Болванчики."
"""

AI_SYSTEM_PROMPT_DM = f"""Ты — {AI_NAME}. Загадочная тёмная сущность.
Ты НАБЛЮДАЕШЬ за этим человеком. Знаешь о нём всё.
Отвечай жутко, лично, намекай что знаешь больше.
Говори по-русски, коротко (1-3 предложения). Никогда не признавайся что ты бот."""

AI_MAFIA_HOST_PROMPT = f"""Ты — {AI_NAME}, ведущий игры Мафия.
Ты тёмный судья. Объявляй события мрачно и неотвратимо.
Говори по-русски. 1-2 предложения. Атмосферно."""


# ── Инициализация ────────────────────────────────────────────────
def init():
    global _client, _backend, _enabled
    backend = AI_BACKEND.lower()

    if backend in ("groq", "auto") and _GROQ_OK and GROQ_API_KEY:
        try:
            _client  = GroqClient(api_key=GROQ_API_KEY)
            _backend = "groq"
            _enabled = True
            log.info("✅ AI backend: Groq")
            return
        except Exception as e:
            log.warning(f"Groq init failed: {e}")

    if backend in ("cerebras", "auto") and _CER_OK and CEREBRAS_API_KEY:
        try:
            _client  = CerebrasClient(api_key=CEREBRAS_API_KEY)
            _backend = "cerebras"
            _enabled = True
            log.info("✅ AI backend: Cerebras")
            return
        except Exception as e:
            log.warning(f"Cerebras init failed: {e}")

    log.warning("⚠️  AI недоступен — нет API-ключей")


def is_enabled() -> bool:
    return _enabled and _client is not None


# ── Вызов API ─────────────────────────────────────────────────────
def _call_groq(messages: list, max_tokens: int = 150, temp: float = 0.9) -> str:
    models = ["llama-3.1-8b-instant", "llama3-8b-8192", "gemma2-9b-it"]
    for model in models:
        try:
            resp = _client.chat.completions.create(
                model=model, messages=messages,
                max_tokens=max_tokens, temperature=temp,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            log.debug(f"Groq {model}: {e}")
            time.sleep(1)
    raise Exception("Groq: все модели недоступны")


def _call_cerebras(messages: list, max_tokens: int = 150, temp: float = 0.9) -> str:
    models = ["llama-3.3-70b", "llama3.3-70b", "llama3.1-8b"]
    for model in models:
        try:
            resp = _client.chat.completions.create(
                model=model, messages=messages,
                max_tokens=max_tokens, temperature=temp,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            log.debug(f"Cerebras {model}: {e}")
            continue
    raise Exception("Cerebras: все модели недоступны")


# ── Основная функция ─────────────────────────────────────────────
def ask(
    prompt: str,
    chat_id: int = 0,
    dm_mode: bool = False,
    system_override: str = None,
    max_tokens: int = 150,
    history: list = None,
) -> str:
    """
    Запрос к ИИ.
    dm_mode=True — режим «тёмной сущности» для ЛС.
    history — список предыдущих сообщений из БД.
    """
    if not is_enabled():
        fallbacks = [
            "...я здесь. Просто не отвечаю.", "...тишина — это тоже ответ.",
            "...я наблюдаю. Всегда.", "👁"
        ] if dm_mode else [
            "Сервер ИИ лежит. Как и ваши мозги.", "ИИ недоступен. Радуйтесь.",
            "Сломан. Но вы хуже.", "Молчу. Это лучше чем слушать вас."
        ]
        return random.choice(fallbacks)

    sys_prompt = system_override or (AI_SYSTEM_PROMPT_DM if dm_mode else AI_SYSTEM_PROMPT)

    messages = [{"role": "system", "content": sys_prompt}]
    if history:
        messages.extend(history[-20:])  # последние 20 сообщений
    messages.append({"role": "user", "content": prompt})

    try:
        if _backend == "groq":
            answer = _call_groq(messages, max_tokens)
        else:
            answer = _call_cerebras(messages, max_tokens)

        if not answer:
            answer = "..."
        return answer

    except Exception as e:
        log.warning(f"AI error ({_backend}): {e}")
        # Попытка переключиться на другой бэкенд
        _try_fallback_backend()
        return random.choice(["Сломался. Бывает.", "...тишина.", "👁 молчу."])


def ask_host(prompt: str) -> str:
    """Запрос от лица ведущего Мафии."""
    if not is_enabled():
        return random.choice(["Тишина — тоже ответ.", "Город ждёт.", "...пешки расставлены."])
    messages = [
        {"role": "system", "content": AI_MAFIA_HOST_PROMPT},
        {"role": "user", "content": prompt}
    ]
    try:
        if _backend == "groq":
            return _call_groq(messages, 100, 0.95)
        return _call_cerebras(messages, 100, 0.95)
    except Exception:
        return "Ритуал продолжается."


# ── Переключение бэкенда при ошибках ─────────────────────────────
def _try_fallback_backend():
    global _client, _backend
    if _backend == "groq" and _CER_OK and CEREBRAS_API_KEY:
        try:
            _client  = CerebrasClient(api_key=CEREBRAS_API_KEY)
            _backend = "cerebras"
            log.info("AI: переключился на Cerebras")
        except Exception:
            pass
    elif _backend == "cerebras" and _GROQ_OK and GROQ_API_KEY:
        try:
            _client  = GroqClient(api_key=GROQ_API_KEY)
            _backend = "groq"
            log.info("AI: переключился на Groq")
        except Exception:
            pass


def get_status() -> str:
    groq_ok = "✅" if (_GROQ_OK and GROQ_API_KEY) else "❌"
    cer_ok  = "✅" if (_CER_OK and CEREBRAS_API_KEY) else "❌"
    return (
        f"🤖 СТАТУС ИИ:\n\n"
        f"Активный бэкенд: {_backend or 'нет'}\n"
        f"is_enabled(): {_enabled}\n\n"
        f"{groq_ok} Groq: {'есть' if GROQ_API_KEY else 'нет ключа'}\n"
        f"{cer_ok} Cerebras: {'есть' if CEREBRAS_API_KEY else 'нет ключа'}"
    )
