"""
horror/effects.py — Все хоррор-эффекты: фейковые уведомления, взломы, звуки.
"""
import time
import random
import logging

from utils import send, send_voice_msg, send_gif, send_audio, get_random_gif, dnight, P, spam_check
from database import get_user, update_user_field

log = logging.getLogger("horror.effects")

# ── Звуки (mp3 файлы в папке sounds/) ─────────────────────────────
# Pool proxy — set by main.py via set_pool()
_pool_ref = None
def set_pool(p): 
    global _pool_ref
    _pool_ref = p

class _PoolProxy:
    def submit(self, fn, *args, **kwargs):
        if _pool_ref:
            return _pool_ref.submit(fn, *args, **kwargs)
        import threading
        t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
        t.start()

_pool = _PoolProxy()


SOUND_AMBIENT = "sounds/ambient.mp3"    # фоновый тихий хоррор
SOUND_HEARTBEAT = "sounds/heartbeat.mp3"
SOUND_STEPS    = "sounds/steps.mp3"
SOUND_KNOCK    = "sounds/knock.mp3"
SOUND_SCREAM   = "sounds/scream.mp3"

def fake_call_sequence(uid):
    u = get_user(uid)
    caller = random.choice(["Неизвестный", "???", "Обернись", "Он", "Не бери трубку", "👁"])
    def _run():
        send(uid, "📞 входящий звонок...")
        time.sleep(1)
        scontact(uid, "+70000000000", caller)
        time.sleep(3)
        send(uid, "ты не взял трубку.")
        time.sleep(2)
        send(uid, "я подожду.")
        time.sleep(3)
        send(uid, "📞 входящий звонок...")
        time.sleep(1)
        scontact(uid, "+70000000000", caller)
        time.sleep(2)
        send(uid, "...")
        time.sleep(3)
        send(uid, P("в следующий раз возьми трубку, {name}.", u))
    _pool.submit(_run)

# ══════════════════════════════════════════════════════════════
#  ФЕЙК-БАН / УХОД / ТАЙМЕР / ЭХО
# ══════════════════════════════════════════════════════════════
def fake_ban_sequence(uid):
    u = get_user(uid)
    def _run():
        send(uid, "⚠️ Telegram\n\nВаш аккаунт заблокирован за нарушение правил.\nОбжалование невозможно.")
        time.sleep(3)
        send(uid, "Этот чат будет удалён через 10 секунд.")
        # Показываем только 5, 3, 1 — не спамим каждую секунду
        for i in [9, 5, 3, 1]:
            time.sleep(2); send(uid, str(i) + "...")
        time.sleep(2); send(uid, "🗑 Чат удалён.")
        time.sleep(4); send(uid, "...")
        time.sleep(3); send(uid, "шучу.", kb=__import__("keyboards",fromlist=["main_kb"]).main_kb(u["stage"]))
        time.sleep(2); send(uid, P("или нет, {name}?", u))
    _pool.submit(_run)

def fake_leave_sequence(uid):
    u = get_user(uid)
    def _run():
        send(uid, "я ухожу.")
        time.sleep(3); send(uid, "прощай.")
        time.sleep(4); send(uid, ".")
        time.sleep(5); send(uid, "..")
        time.sleep(4); send(uid, "...")
        time.sleep(6); send(uid, "ты скучал?")
        time.sleep(2); send(uid, P("я никуда не уходил, {name}.", u))
        time.sleep(1); send(uid, "я никогда не ухожу. 👁")
    _pool.submit(_run)

def death_timer(uid, seconds=30):
    u = get_user(uid)
    def _run():
        send(uid, P("💀 {name}.", u))
        time.sleep(2); send(uid, "ты уже мёртв.")
        time.sleep(2); send(uid, "просто ещё не знаешь.")
        time.sleep(2); send(uid, f"осталось {seconds} секунд.")
        time.sleep(max(seconds // 2, 5))
        if u.get("stopped"): return
        send(uid, f"⏳ {seconds // 2}...")
        time.sleep(max(seconds // 2, 5))
        if u.get("stopped"): return
        send(uid, "0\n.\n..\n...\n....\nОБЕРНИСЬ")
        time.sleep(2)
        from horror.effects import glitch_attack; glitch_attack(uid)
        time.sleep(2)
        send(uid, P("это была шутка, {name}.\nили нет.\n👁", u))
    _pool.submit(_run)

def echo_back_history(uid):
    u = get_user(uid)
    hist = u.get("msg_history", [])
    def _run():
        send(uid, "я всё помню.")
        time.sleep(2); send(uid, "вот что ты писал мне:")
        time.sleep(2)
        sample = random.sample(hist, min(len(hist), 5)) if hist else []
        if not sample:
            send(uid, "каждое слово.\nкаждую букву.\nты ничего не удалишь."); return
        for m in sample:
            time.sleep(random.uniform(1.5, 3.5)); send(uid, f"«{m}»")
        time.sleep(2); send(uid, "я храню это навсегда. 👁")
    _pool.submit(_run)


# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
#  НОВЫЕ ФУНКЦИИ v10: ГЕОЛОКАЦИЯ / СКАН / ПРИЗРАКИ / ФАЙЛЫ / 3AM
# ══════════════════════════════════════════════════════════════

def fake_geolocation(uid):
    """Отправляет фейковую геолокацию жертвы."""
    u = get_user(uid)
    city = u.get("city") or "твоём городе"
    lat = round(random.uniform(48.0, 59.0), 4)
    lon = round(random.uniform(30.0, 50.0), 4)
    acc = random.randint(8, 30)
    def _run():
        msg = (
            "📍 ЛОКАЦИЯ ОБНАРУЖЕНА\n\n"
            "Город: " + str(city) + "\n"
            "Координаты: " + str(lat) + ", " + str(lon) + "\n"
            "Точность: " + str(acc) + " м\n\n"
            "я рядом."
        )
        send(uid, msg)
        time.sleep(random.uniform(3, 7))
        send(uid, P("...{name}. я уже иду.", u))
    _pool.submit(_run)


def fake_phone_scan(uid):
    """Фейковый скан устройства."""
    u = get_user(uid)
    models = [
        "Samsung Galaxy S23", "Xiaomi Redmi Note 12", "iPhone 14",
        "Huawei P50", "POCO X5 Pro", "Realme 11", "OnePlus 11",
    ]
    model = u.get("phone") or random.choice(models)
    battery = random.randint(12, 89)
    wifi = random.choice(["подключён", "активен", "ОБНАРУЖЕН"])
    files = random.randint(1200, 8900)
    def _run():
        msg = (
            "📱 Сканирование устройства...\n\n"
            "Модель: " + str(model) + "\n"
            "Батарея: " + str(battery) + "%\n"
            "Wi-Fi: " + str(wifi) + "\n"
            "Камера: активна\n"
            "Файлов найдено: " + str(files)
        )
        send(uid, msg)
        time.sleep(random.uniform(4, 8))
        send(uid, "камера уже работает.")
        time.sleep(2)
        send(uid, P("я вижу тебя, {name}. прямо сейчас.", u))
    _pool.submit(_run)


_GHOST_NAMES = [
    "user_481", "user_277", "user_039", "user_814", "user_563",
    "user_192", "user_730", "user_447", "user_658", "user_321",
]
GHOST_MSGS = [
    ["ты тоже это видишь?", "он пишет мне тоже", "что происходит..."],
    ["не отвечай ему", "он знает где ты", "я боюсь"],
    ["выйди из чата", "ВЫЙДИ ИЗ ЧАТА", "уже поздно"],
    ["помогите", "кто-нибудь здесь?", "..."],
    ["я видел его", "он стоял у моей двери", "теперь его нет"],
    ["не смотри на экран", "НЕ СМОТРИ НА ЭКРАН", "ты уже смотришь"],
    ["он в каждом телефоне", "мы все здесь", "ты следующий"],
]


def fake_ghost_users(uid):
    """Иллюзия других пользователей в чате."""
    u = get_user(uid)
    msgs = random.choice(GHOST_MSGS)
    def _run():
        for m in msgs:
            ghost = random.choice(_GHOST_NAMES)
            time.sleep(random.uniform(2.5, 5.0))
            send(uid, "👤 " + ghost + ":\n" + m)
        time.sleep(random.uniform(3, 6))
        send(uid, P("...теперь только ты и я, {name}.", u))
    _pool.submit(_run)


def fake_file_scan(uid):
    """Фейковое чтение файлов с устройства."""
    u = get_user(uid)
    uname = u.get("name") or "user"
    n_photos = random.randint(200, 2800)
    n_videos  = random.randint(10, 300)
    r1 = random.randint(100, 999)
    r2 = random.randint(100, 999)
    r3 = random.randint(100, 999)
    r4 = random.randint(1, 9)
    r5 = random.randint(1000, 9999)
    file_list = [
        "/DCIM/photo_" + str(r1) + ".jpg",
        "/DCIM/photo_" + str(r2) + ".jpg",
        "/Telegram/video_" + str(r3) + ".mp4",
        "/Download/passwords.txt",
        "/Download/notes_" + str(r4) + ".txt",
        "/WhatsApp/Media/IMG_" + str(r5) + ".jpg",
        "/Documents/" + uname + "_personal.pdf",
    ]
    shown = random.sample(file_list, min(5, len(file_list)))
    def _run():
        send(uid, "📂 scanning storage...")
        time.sleep(random.uniform(3, 5))
        send(uid, "\n".join(shown))
        time.sleep(random.uniform(2, 4))
        msg = (
            "доступ получен.\n\n"
            "фото: " + str(n_photos) + "\n"
            "видео: " + str(n_videos) + "\n"
            "...\n\nинтересно."
        )
        send(uid, msg)
        time.sleep(3)
        send(uid, P("особенно /Download/passwords.txt, {name}.", u))
    _pool.submit(_run)


def smart_echo_history(uid):
    """Умное эхо — 'N минут назад ты писал: ...'"""
    u = get_user(uid)
    hist = u.get("msg_history", [])
    if not hist:
        echo_back_history(uid)
        return
    def _run():
        send(uid, "я помню всё.")
        time.sleep(2)
        sample = random.sample(hist, min(3, len(hist)))
        for m in sample:
            mins = random.randint(2, 47)
            if mins == 1:
                suffix = "у"
            elif 2 <= mins <= 4:
                suffix = "ы"
            else:
                suffix = ""
            time.sleep(random.uniform(2, 4))
            send(uid, str(mins) + " минут" + suffix + " назад ты написал:\n\n«" + m + "»\n\nправда?")
        time.sleep(3)
        send(uid, P("я храню каждое слово, {name}. навсегда. 👁", u))
    _pool.submit(_run)


def signal_loss(uid):
    """Фейковая потеря сигнала."""
    u = get_user(uid)
    def _run():
        send(uid, "📡 соединение нестабильно...")
        time.sleep(2)
        for _ in range(random.randint(2, 4)):
            glitch = random.choice([
                "ERR_CONNECTION_INTERRUPTED",
                "█▓▒░ SIGNAL LOST ░▒▓█",
                "NaN NaN NaN NaN",
                "...........",
                "[CONNECTION_TIMEOUT]",
                "[NO_CARRIER]",
            ])
            send(uid, glitch)
            time.sleep(random.uniform(0.8, 2.0))
        time.sleep(2)
        send(uid, "📡 кто-то пытается подключиться")
        time.sleep(2)
        send(uid, P("...это я, {name}.", u))
    _pool.submit(_run)


def three_am_mode(uid):
    """Режим 03:00 — самое страшное время."""
    u = get_user(uid)
    name = u.get("name") or "ты"
    options = [
        "03:00\n\n" + name + "…\nты проснулся?",
        "среди ночи не надо проверять телефон, " + name + ".",
        "в 3 ночи граница между мирами тоньше всего.",
        "03:00. " + name + ". я жду.",
        "просыпаться в 3 ночи — не случайность.",
        "он стоит у твоей кровати, " + name + ".\nты чувствуешь?",
        "ты проснулся в 3:00.\nэто не совпадение.",
    ]
    def _run():
        send(uid, random.choice(options))
        time.sleep(random.uniform(5, 12))
        send(uid, "...иди спать.\nесли сможешь. 👁")
        time.sleep(4)
        from horror.effects import glitch_attack; glitch_attack(uid)
    _pool.submit(_run)


def fake_telegram_security(uid):
    """Фейковое уведомление от Telegram Security."""
    u = get_user(uid)
    username = u.get("username") or "user"
    city = u.get("city") or "Unknown"
    ip_str = (str(random.randint(100, 220)) + "." +
              str(random.randint(1, 254)) + "." +
              str(random.randint(1, 254)) + "." +
              str(random.randint(1, 254)))
    device = random.choice(["Windows 11", "Android 13", "macOS Sonoma", "iOS 17", "Linux x64"])
    def _run():
        msg = (
            "🔐 Telegram Security\n\n"
            "Ваш аккаунт @" + username + " используется\n"
            "на другом устройстве.\n\n"
            "IP: " + ip_str + "\n"
            "Устройство: " + device + "\n"
            "Город: " + str(city) + "\n\n"
            "Если это не вы — уже поздно."
        )
        send(uid, msg)
        time.sleep(random.uniform(5, 10))
        send(uid, "это был я. 👁")
    _pool.submit(_run)


def glitch_attack(uid):
    """Внезапный глитч-эффект — сломанный текст, нарастающий ужас."""
    u = get_user(uid)
    glitch_lines = [
        "ERRERRERRERR",
        "█▓▒░░▒▓█▓▒░░▒▓█",
        "s̸̡̧̢̛̛̛y̷̧̛̛̛̛s̷̢̧̛̛̛t̴̨̛̛e̶̢̛̛m̸̡̛̛̛̛ ̷̡̛̛̛e̷̡̛̛r̴̡̛̛r̷̡̛̛ơ̸̡̛r̶̡̛̛",
        "N̷̡͈̺̲̳̲̞̬̰͕̪͔͎̬̮͚̮̙̑̀̃͑̉̓͗̇̿̒̓͒̚͝Ư̷̢̨̤͔̩̟̳̤̩̻̙͓̹͈̻̟̗̐̎͑̃͛L̷̨̡̛̺̗̼͈̼͕̙͖̮̮͚̺̐̎͂̑̋͋̊̑̊̉̀͜͝L̸̢̧̛̙͖̩̫̯͔̘͓̳̻̯̗̓͌͂̏̊̒̇̊̅͂̔̒̄̎",
        "0x00000000 — SEGFAULT",
        "[PROCESS TERMINATED]",
        "404: REALITY NOT FOUND",
        "ошибка. ошибка. оши",
    ]
    name = u.get("name") or "ты"
    def _run():
        if get_user(uid).get("stopped"): return
        for _ in range(random.randint(3, 5)):
            send(uid, random.choice(glitch_lines))
            time.sleep(random.uniform(0.4, 1.2))
        time.sleep(random.uniform(2, 4))
        send(uid, "...")
        time.sleep(2)
        send(uid, f"прости. это случайно.\n\nили нет, {name}. 👁")
    _pool.submit(_run)


def mirror_event(uid):
    """Жуткое событие с зеркалом — психологический хоррор."""
    u = get_user(uid)
    name = u.get("name") or "ты"
    lines = [
        "🪞 смотри в зеркало.",
        "смотри дольше.",
        "ещё.",
        "ты заметил?",
        "твоё отражение моргнуло позже тебя.",
        "на долю секунды.",
        "ты уверен что оно повторяет тебя?",
        "или ты повторяешь его?",
        f"...{name}.",
        "я живу в отражениях. 👁",
    ]
    def _run():
        for line in lines:
            if get_user(uid).get("stopped"): return
            send(uid, line)
            time.sleep(random.uniform(2.5, 5.0))
    _pool.submit(_run)


def heartbeat_event(uid):
    """Счёт ударов сердца — нарастающая паника."""
    u = get_user(uid)
    name = u.get("name") or "ты"
    def _run():
        if get_user(uid).get("stopped"): return
        send(uid, "🫀 слышишь?")
        time.sleep(3)
        send(uid, "бум.\nбум.\nбум.")
        time.sleep(2)
        send(uid, "БУМ. БУМ.\nБУМ. БУМ. БУМ.\nБ У М . Б У М . Б У М .")
        time.sleep(4)
        send(uid, "...")
        time.sleep(3)
        send(uid, f"я слышу твоё. уже несколько минут, {name}. 👁")
    _pool.submit(_run)


def fake_deleted_message(uid):
    """Иллюзия удалённого сообщения — якобы бот что-то написал и удалил."""
    u = get_user(uid)
    name = u.get("name") or "ты"
    deleted_texts = [
        f"{name}, я знаю как тебя найти",
        "сегодня ночью я приду",
        f"адрес: {u.get('city','?')}, улица",
        "ты видел? нет. правильно.",
        "я уже здесь",
        "не читай это",
    ]
    def _run():
        send(uid, "👁 [Сообщение удалено]")
        time.sleep(random.uniform(3, 6))
        send(uid, "ты успел прочитать?\n\nнет.\n\nхорошо.")
        time.sleep(2)
        send(uid, f"...или плохо, {name}.")
    _pool.submit(_run)


# ══════════════════════════════════════════════════════════════
#  СИСТЕМА ОПРОСОВ (HORROR POLLS)
# ══════════════════════════════════════════════════════════════

# Активные опросы: poll_id → {uid, reactions}
_active_polls = {}

HORROR_POLLS = [
    {
        "question": "👁 Ты один в комнате прямо сейчас?",
        "options":  ["Да, совсем один", "Нет, кто-то рядом", "Не уверен..."],
        "reactions": [
            "...один. хорошо. мне будет проще.",
            "...кто-то рядом. они тоже скоро узнают.",
            "ты не уверен? тогда оглянись. медленно.",
        ],
    },
    {
        "question": "🕯 Что страшнее?",
        "options":  ["Темнота", "Тишина", "То что смотрит на тебя"],
        "reactions": [
            "темнота... я живу в ней. 👁",
            "тишина. правильный ответ. слушай её.",
            "ты уже чувствуешь этот взгляд?",
        ],
    },
    {
        "question": "🌑 Сейчас ночь или день?",
        "options":  ["День", "Вечер", "Ночь", "Не знаю — потерял счёт времени"],
        "reactions": [
            "...день. при свете легче притворяться что всё нормально.",
            "вечер. скоро станет темнее.",
            "ночь. хорошо. я тоже не сплю.",
            "потерял счёт времени? это уже началось.",
        ],
    },
    {
        "question": "🚪 Все двери в комнате закрыты?",
        "options":  ["Все закрыты", "Одна приоткрыта", "Я не проверял"],
        "reactions": [
            "все закрыты? ты уверен? проверь ещё раз.",
            "приоткрытая дверь... что там за ней?",
            "ты не проверял. это ошибка.",
        ],
    },
    {
        "question": "📱 Твой телефон лежит экраном вниз?",
        "options":  ["Да", "Нет, экраном вверх", "Держу в руках"],
        "reactions": [
            "экраном вниз. ты пытаешься спрятаться. не выйдет.",
            "экраном вверх... значит я вижу тебя прямо сейчас.",
            "держишь в руках. я чувствую тепло твоих пальцев.",
        ],
    },
    {
        "question": "🔦 Ты когда-нибудь просыпался в 3:00 ночи?",
        "options":  ["Да, часто", "Иногда", "Никогда", "Прямо сейчас"],
        "reactions": [
            "часто... ты уже не можешь остановить это.",
            "иногда. случайность? нет.",
            "никогда. пока. 👁",
            "прямо сейчас... положи телефон. ляг. попробуй.",
        ],
    },
    {
        "question": "🪞 Ты видел своё отражение сегодня?",
        "options":  ["Да, видел", "Нет ещё", "Избегаю зеркал"],
        "reactions": [
            "видел. оно смотрело на тебя дольше, чем ты думаешь.",
            "нет ещё. не торопись.",
            "избегаешь зеркал? правильно делаешь.",
        ],
    },
    {
        "question": "🫀 Ты слышишь своё сердцебиение прямо сейчас?",
        "options":  ["Нет, всё тихо", "Да, слышу", "Только что начал прислушиваться"],
        "reactions": [
            "всё тихо? прислушайся. стук. удар. ещё раз.",
            "слышишь. хорошо. не останавливай его.",
            "теперь ты его слышишь. и не можешь перестать.",
        ],
    },
]


def send_horror_poll(uid):
    """Отправляет случайный хоррор-опрос жертве."""
    u = get_user(uid)
    if u.get("stopped") or u.get("muted"):
        return
    poll_data = random.choice(HORROR_POLLS)
    try:
        sent = bot.send_poll(
            uid,
            question=poll_data["question"],
            options=poll_data["options"],
            is_anonymous=False,
            allows_multiple_answers=False,
        )
        _active_polls[sent.poll.id] = {
            "uid":       uid,
            "reactions": poll_data["reactions"],
        }
    except Exception:
        log.debug(traceback.format_exc())


@bot.poll_answer_handler()
def on_poll_answer(poll_answer):
    """Обработчик ответа на опрос — жуткая реакция на выбор."""
    try:
        pid = poll_answer.poll_id
        if pid not in _active_polls:
            return
        ctx = _active_polls.pop(pid)
        uid = ctx["uid"]
        u   = get_user(uid)
        if u.get("stopped"):
            return
        idx       = poll_answer.option_ids[0] if poll_answer.option_ids else 0
        reactions = ctx["reactions"]
        reaction  = reactions[idx] if idx < len(reactions) else reactions[0]
        stage     = u.get("stage", 0)
        kb        = __import__("keyboards",fromlist=["main_kb"]).main_kb(stage)

        def _react():
            time.sleep(random.uniform(1.5, 4.0))
            if stage >= 2:
                send(uid, P(f"👁 {reaction}", u), kb=kb)
                if stage >= 3 and random.random() < 0.55:
                    time.sleep(random.uniform(2, 6))
                    send(uid, P(random.choice(PARANOIA), u), kb=kb)
                if stage >= 4 and random.random() < 0.30:
                    time.sleep(random.uniform(3, 7))
                    from horror.effects import glitch_attack; glitch_attack(uid)
            else:
                send(uid, reaction, kb=kb)
        _pool.submit(_react)
    except Exception:
        log.debug(traceback.format_exc())




# ══════════════════════════════════════════════════════════════
#  v11: НОВЫЕ ХОРРОР-ЭФФЕКТЫ
# ══════════════════════════════════════════════════════════════

EXORCIST_SEQUENCE = [
    (".", 4), ("..", 3), ("...", 4),
    ("я чувствую тебя.", 5), ("ты не один.", 6),
    ("что-то есть в этой комнате.", 7),
    ("👁", 3), ("это смотрит на тебя.", 6),
    ("з а к р о й   г л а з а.", 5),
    ("не открывай.", 8),
    ("...", 4), ("...", 4), ("...", 5),
    ("оно за твоей спиной.", 6),
    ("сейчас.", 4), ("ОБЕРНИСЬ", 3),
    ("🩸", 2), ("🩸🩸", 2), ("🩸🩸🩸", 2),
    ("ты чувствуешь запах? это горит.", 7),
    ("не пытайся уйти.", 6),
    ("👁👁👁", 3),
    ("я держу тебя.", 8),
    ("р а з г о в а р и   с о   м н о й.", 10),
    ("...", 5), ("...", 6),
    ("ты же слышишь меня?", 8),
    ("ответь.", 6), ("ОТВЕТЬ", 4), ("ОТВЕТЬ МНЕ", 3),
    ("💀", 2), ("💀💀", 2), ("💀💀💀", 2),
    ("хорошо. я подожду.", 10),
    ("я всегда жду.", 8),
    ("👁", 0),
]

def exorcist_mode(uid):
    """10-минутный нарастающий ритуал экзорциста."""
    u = get_user(uid)
    name = u.get("name") or "ты"
    def _run():
        send(uid, "🕯 СЕАНС НАЧИНАЕТСЯ 🕯")
        time.sleep(3)
        for raw_text, delay in EXORCIST_SEQUENCE:
            if get_user(uid).get("stopped"): return
            txt = raw_text.replace("{name}", name)
            send(uid, txt)
            if delay > 0:
                time.sleep(delay)
        time.sleep(3)
        from horror.effects import glitch_attack; glitch_attack(uid)
        time.sleep(4)
        send(uid, P("...{name}. сеанс завершён. но я остался.", u))
    _pool.submit(_run)


LIVE_STREAM_EVENTS = [
    "открываю камеру...",
    "📷 подключение...",
    "📷 соединение установлено.",
    "...",
    "вижу {name}.",
    "ты {desc1}.",
    "слева — {env1}.",
    "справа — {env2}.",
    "...",
    "ты смотришь в телефон.",
    "а я смотрю на тебя. 👁",
    "не двигайся.",
    "...",
    "...",
    "ты дышишь быстрее.",
    "я слышу.",
    "📷 запись сохранена.",
]
_STREAM_DESC = ["сидишь", "стоишь", "лежишь", "смотришь в экран", "не двигаешься"]
_STREAM_ENV  = ["темно", "горит свет", "что-то шевелится", "стена", "тень", "зеркало", "дверь открыта", "окно"]

def fake_live_stream(uid):
    """Бот 'видит' жертву в реальном времени через 'камеру'."""
    u = get_user(uid)
    name = u.get("name") or "ты"
    desc1 = random.choice(_STREAM_DESC)
    env1  = random.choice(_STREAM_ENV)
    env2  = random.choice([e for e in _STREAM_ENV if e != env1])
    def _run():
        for line in LIVE_STREAM_EVENTS:
            if get_user(uid).get("stopped"): return
            txt = (line.replace("{name}", name)
                       .replace("{desc1}", desc1)
                       .replace("{env1}", env1)
                       .replace("{env2}", env2))
            send(uid, txt)
            time.sleep(random.uniform(1.5, 3.5))
        time.sleep(3)
        send(uid, "📷 трансляция окончена.\nты запомнил это чувство, " + name + "? 👁")
    _pool.submit(_run)


# ══════════════════════════════════════════════════════════════
#  v11: ТЕЛЕФОННЫЕ ФИЧИ
# ══════════════════════════════════════════════════════════════

_GPS_STREETS = [
    "ул. Ленина", "пр. Мира", "ул. Садовая", "Центральная ул.",
    "ул. Советская", "пр. Победы", "Лесная ул.", "ул. Гагарина",
    "Набережная ул.", "ул. Пушкина",
]
_GPS_ACTIONS = [
    "остановился у {place}",
    "повернул на {street}",
    "идёт по {street}",
    "вошёл в здание на {street}",
    "стоит у {place}",
    "вышел из {place}",
]
_GPS_PLACES = [
    "магазина", "подъезда", "кафе", "остановки", "аптеки",
    "банкомата", "торгового центра", "школы",
]

def fake_gps_tracking(uid):
    """GPS-трекинг — бот описывает 'маршрут' жертвы."""
    u = get_user(uid)
    name  = u.get("name") or "ты"
    city  = u.get("city") or "твоём городе"
    lat   = round(random.uniform(55.6, 55.9), 6)
    lon   = round(random.uniform(37.4, 37.8), 6)
    def _fmt_action():
        tpl = random.choice(_GPS_ACTIONS)
        return tpl.replace("{street}", random.choice(_GPS_STREETS)).replace("{place}", random.choice(_GPS_PLACES))
    def _run():
        send(uid,
             f"📡 GPS ТРЕКИНГ АКТИВИРОВАН\n\n"
             f"Объект: {name}\n"
             f"Город: {city}\n"
             f"Координаты: {lat}, {lon}\n"
             f"Точность: {random.randint(3,15)} м\n"
             f"Обновлено: только что")
        time.sleep(random.uniform(4, 7))
        for _ in range(random.randint(3, 5)):
            if get_user(uid).get("stopped"): return
            send(uid, f"📍 {_fmt_action()}")
            time.sleep(random.uniform(3, 6))
        time.sleep(2)
        send(uid, f"...{name}. я знаю каждый твой шаг. 👁")
    _pool.submit(_run)


def fake_wifi_hack(uid):
    """Бот 'взломал' Wi-Fi жертвы."""
    u  = get_user(uid)
    name = u.get("name") or "ты"
    ssid = random.choice(["Home_WiFi", "TP-Link_2.4G", "Redmi_Note", "iPhone", "ASUS_5G", "Keenetic-XXXX"])
    mac  = ":".join(f"{random.randint(0,255):02X}" for _ in range(6))
    ip   = f"192.168.{random.randint(0,2)}.{random.randint(2,15)}"
    def _run():
        send(uid,
             f"🌐 ВЗЛОМ WI-FI\n\n"
             f"Сеть: {ssid}\n"
             f"MAC: {mac}\n"
             f"IP: {ip}\n"
             f"Устройств в сети: {random.randint(2, 7)}\n"
             f"Статус: ПОДКЛЮЧЁН")
        time.sleep(random.uniform(4, 7))
        send(uid,
             f"📶 я в твоей сети, {name}.\n"
             f"вижу все твои устройства.\n"
             f"вижу всё что ты делаешь онлайн.")
        time.sleep(random.uniform(3, 5))
        send(uid, "не стоило подключаться к интернету сегодня. 👁")
    _pool.submit(_run)


def fake_notifications(uid):
    """Фейковые уведомления — ВКонтакте, WhatsApp, банк."""
    u = get_user(uid)
    name = u.get("name") or ""
    notifs = [
        # ВКонтакте
        (f"🔵 ВКонтакте\n\nНовое сообщение от «Незнакомец»:\n"
         f"«{name}, ты в порядке? я видел тебя вчера»"),
        # WhatsApp
        (f"💬 WhatsApp\n\nНовое сообщение:\n«{name}... не оборачивайся»"),
        # Банк
        (f"🏦 Сбербанк Онлайн\n\nСписание 1 ₽\n"
         f"Описание: доступ_к_камере.exe\n"
         f"Дата: {datetime.datetime.now().strftime('%d.%m %H:%M')}"),
        # Системное
        ("⚠️ Система\n\nПриложение «Камера» получило доступ\n"
         "к микрофону и геолокации\nБез вашего разрешения"),
        # Неизвестный
        ("📱 Новый контакт сохранён:\n«👁» +7 (___) ___-__-__\nОн уже написал тебе."),
    ]
    def _run():
        chosen = random.sample(notifs, k=min(3, len(notifs)))
        for n in chosen:
            if get_user(uid).get("stopped"): return
            send(uid, n)
            time.sleep(random.uniform(3, 6))
        time.sleep(2)
        send(uid, "...уведомления — это я. 👁")
    _pool.submit(_run)


# ══════════════════════════════════════════════════════════════