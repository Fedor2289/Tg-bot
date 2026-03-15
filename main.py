"""
╔══════════════════════════════════════════════════════════════════╗
║              👁  HORROR BOT — main.py  (WEBHOOK)                ║
║  Flask-webhook вместо polling — стабильная работа на Railway     ║
╚══════════════════════════════════════════════════════════════════╝
"""
import threading
import signal
import sys
import time
import traceback
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, request, abort
flask_app = Flask(__name__)

from config import (
    BOT_TOKEN, ADMIN_ID, STAGE_SEC, HORROR_DELAY_SEC,
    VOICE_ENABLED, GIF_DIR, validate, log
)
if not validate():
    sys.exit(1)

from database import init_db, get_admins, add_admin
init_db()
add_admin(ADMIN_ID, added_by=0)
admins: set = get_admins()
admins.add(ADMIN_ID)

_pool_raw = ThreadPoolExecutor(max_workers=32, thread_name_prefix="horror")
_shutdown  = threading.Event()

class _SafePool:
    def submit(self, fn, *args, **kwargs):
        def _wrapped():
            try:
                fn(*args, **kwargs)
            except Exception:
                fn_name = getattr(fn, "__name__", str(fn))
                log.debug(f"pool/{fn_name} crashed:\n{traceback.format_exc()[:400]}")
        return _pool_raw.submit(_wrapped)
    def shutdown(self, **kw):
        return _pool_raw.shutdown(**kw)

pool = _SafePool()

import telebot
from utils import bot

from ai.client import init as ai_init
ai_init()
from horror.engine import set_pool as engine_set_pool
engine_set_pool(pool)
from handlers.admin import set_pool as admin_set_pool
admin_set_pool(pool)
from handlers.dm import init as dm_init
dm_init(pool, admins)
from handlers.group import init as group_init
group_init(pool, admins)
from handlers.callbacks import init as cb_init
cb_init(pool, admins)
from keyboards import main_kb, admin_main_kb

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID or uid in admins

# ════════════════════════════════════════════════════════════════
#  HANDLERS
# ════════════════════════════════════════════════════════════════

@bot.message_handler(commands=["start"])
def on_start(msg):
    uid = msg.from_user.id
    chat_id = msg.chat.id
    if msg.chat.type in ("group", "supergroup"):
        from handlers.group import add_group_user
        add_group_user(chat_id, uid)
        from keyboards import group_main_kb
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
        ik = InlineKeyboardMarkup(row_width=2)
        ik.add(
            InlineKeyboardButton("🎮 Игры",      callback_data=f"gg_bottle_{chat_id}"),
            InlineKeyboardButton("🏆 Рейтинг",   callback_data=f"grp_rating_{chat_id}"),
            InlineKeyboardButton("🌍 Перевести", callback_data=f"grp_translate_{chat_id}"),
            InlineKeyboardButton("🌤 Погода",    callback_data=f"grp_weather_{chat_id}"),
        )
        bot.send_message(chat_id,
            "👁 Horror Bot подключён!\n\n🎮 Игры: Мафия, Бутылочка, Рулетка, RPG!\n🤖 ИИ доступен!\n\nКнопки 👇",
            reply_markup=group_main_kb())
        bot.send_message(chat_id, "⬆️ Или нажми:", reply_markup=ik)
        return
    from handlers.dm import handle_start
    handle_start(msg, uid, admins, pool)

@bot.message_handler(commands=["stop"])
def on_stop(msg):
    uid = msg.from_user.id
    if msg.chat.type != "private":
        return
    from database import update_user_field, cancel_user_attacks
    update_user_field(uid, "stopped", 1)
    update_user_field(uid, "horror_active", 0)
    cancel_user_attacks(uid)
    from telebot.types import ReplyKeyboardRemove
    bot.send_message(uid, "🛑 Бот остановлен. Напиши /start чтобы начать заново.",
                     reply_markup=ReplyKeyboardRemove())

@bot.message_handler(commands=["admingo"])
def on_admingo(msg):
    uid = msg.from_user.id
    if not is_admin(uid):
        return
    bot.send_message(uid, "⚡ БОГ-РЕЖИМ АКТИВИРОВАН ⚡", reply_markup=admin_main_kb())

@bot.message_handler(commands=["gadmin"])
def on_gadmin(msg):
    uid = msg.from_user.id
    chat_id = msg.chat.id
    if not is_admin(uid):
        return
    if msg.chat.type in ("group", "supergroup"):
        from handlers.group import _send_gadm_panel
        _send_gadm_panel(uid, chat_id)

@bot.message_handler(commands=["score"])
def on_score(msg):
    uid = msg.from_user.id
    if msg.chat.type != "private":
        return
    from database import get_user
    u = get_user(uid)
    bot.send_message(uid, f"🏆 Твой счёт: {u.get('score', 0)} очков\nМесто: #{__import__('database', fromlist=['get_user_rank']).get_user_rank(uid)}")

@bot.message_handler(content_types=["text"])
def on_text(msg):
    try:
        uid = msg.from_user.id
        chat_id = msg.chat.id
        text = (msg.text or "").strip()
        if not text:
            return
        if msg.chat.type in ("group", "supergroup"):
            from handlers.group import handle_group_message, add_group_user
            add_group_user(chat_id, uid)
            handle_group_message(msg, uid, chat_id, text)
            return
        if is_admin(uid):
            from handlers.admin import handle_admin, _adm_state
            adm_buttons = {"⚙️ Выбрать жертву","👥 Жертвы","📊 Статистика","💀 Ужас всем",
                           "🛑 Стоп всем","📤 Рассылка всем","🔇 Тишина всем","🔊 Звук всем",
                           "📋 Список ID","🏆 Лидеры","👑 Со-admin'ы","➕ Добавить admin'а",
                           "➖ Убрать admin'а","🚫 Забанить","✅ Разбанить","🗑 Сбросить всех",
                           "📡 По ID","💬 Чат жертв","🤖 ИИ-настройки","🔙 Выйти из бога",
                           "📝 Текст","🎬 Гифка","⚡ Скример","☠️ Макс-ужас","🌊 Волна паники",
                           "🕯 Ритуал","💬 Диалог-ловушка","😴 Спящий режим","🔇 Заглушить",
                           "🔊 Включить","🔄 Сбросить","📋 Инфо о жертве","👁 ИИ-атака",
                           "🎬 Персональный сценарий","⬆️ Стадия +1","⬇️ Стадия -1",
                           "❄️ Заморозить стадию","🤖 ИИ пишет за меня","📱 Взлом телефона",
                           "📞 Фейк-звонок","💀 Таймер смерти","🪞 Зеркало","🫀 Сердцебиение",
                           "🎙 Голос от него","✏️ Редактировать данные","🔙 Назад"}
            ctx = _adm_state.get(uid, {})
            if text in adm_buttons or ctx.get("step"):
                handle_admin(msg, uid, admins)
                return
            from handlers.dm import handle_dm
            handle_dm(msg, uid)
            return
        from handlers.dm import handle_dm
        handle_dm(msg, uid)
    except Exception:
        log.error(f"on_text crashed:\n{traceback.format_exc()}")

@bot.message_handler(content_types=["new_chat_members"])
def on_new_member(msg):
    chat_id = msg.chat.id
    for member in msg.new_chat_members:
        uid = member.id
        if uid == bot.get_me().id:
            from keyboards import group_main_kb
            bot.send_message(chat_id, "👁 Horror Bot подключился...\n\nЧто-то изменилось.",
                             reply_markup=group_main_kb())
        else:
            from handlers.group import add_group_user
            add_group_user(chat_id, uid)
            from database import get_user
            u = get_user(uid)
            if u.get("stage", 0) >= 3:
                import random
                bot.send_message(chat_id, random.choice([
                    f"👁 {member.first_name}... ты здесь. я знал.",
                    f"...{member.first_name}. давно жду.",
                    f"Ещё один. Добро пожаловать в ловушку, {member.first_name}.",
                ]))

@bot.message_handler(content_types=["photo","animation","video","audio","voice","sticker"])
def on_media(msg):
    uid = msg.from_user.id
    if msg.chat.type != "private":
        return
    from database import get_user
    u = get_user(uid)
    if u.get("stage", 0) >= 3:
        import random
        from utils import send
        send(uid, random.choice([
            "...я вижу что ты отправил. 👁",
            "...интересно. я запомнил.",
            "...файл получен. изучаю.",
        ]))

@bot.callback_query_handler(func=lambda call: True)
def on_callback(call):
    try:
        uid = call.from_user.id
        data = call.data or ""
        from handlers.callbacks import handle_callback
        handle_callback(call, uid, data)
    except Exception:
        log.error(f"on_callback crashed:\n{traceback.format_exc()}")
        try:
            bot.answer_callback_query(call.id, "⚠️ Ошибка")
        except Exception:
            pass

# ════════════════════════════════════════════════════════════════
#  FLASK ROUTES
# ════════════════════════════════════════════════════════════════

WEBHOOK_SECRET = BOT_TOKEN.split(":")[0]  # числовой ID бота как секрет

@flask_app.route("/", methods=["GET"])
def health():
    return "👁 Horror Bot — OK", 200

@flask_app.route(f"/webhook/<secret>", methods=["POST"])
def webhook(secret):
    if secret != WEBHOOK_SECRET:
        abort(403)
    if request.headers.get("content-type") != "application/json":
        abort(403)
    try:
        update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
        bot.process_new_updates([update])
    except Exception:
        log.error(f"webhook error:\n{traceback.format_exc()}")
    return "OK", 200

# ════════════════════════════════════════════════════════════════
#  ФОНОВЫЕ ПОТОКИ
# ════════════════════════════════════════════════════════════════

def _stage_loop():
    while not _shutdown.is_set():
        _shutdown.wait(STAGE_SEC)
        try:
            from database import get_active_users
            from horror.engine import advance_stage, is_stage_frozen
            for u in get_active_users(min_stage=0):
                uid = u["uid"]
                if not is_stage_frozen(uid) and u.get("stage", 0) < 5:
                    advance_stage(uid)
        except Exception:
            log.debug(f"Stage loop:\n{traceback.format_exc()[:200]}")

def _scheduler():
    while not _shutdown.is_set():
        try:
            from database import get_pending_attacks, mark_attack_done, get_user
            from horror import effects as eff
            for attack in get_pending_attacks():
                mark_attack_done(attack["id"])
                uid = attack["uid"]
                u = get_user(uid)
                if u.get("stopped") or u.get("muted") or u.get("banned"):
                    continue
                fn = getattr(eff, attack["func_name"], None)
                if fn:
                    pool.submit(fn, uid)
        except Exception:
            log.debug(f"Scheduler:\n{traceback.format_exc()[:200]}")
        _shutdown.wait(30)

def _random_events():
    _shutdown.wait(600)
    while not _shutdown.is_set():
        try:
            import random
            from database import get_active_users
            from horror.engine import horror_tick
            active = get_active_users(min_stage=2)
            if active:
                pool.submit(horror_tick, random.choice(active)["uid"])
        except Exception:
            log.debug(f"Random events:\n{traceback.format_exc()[:200]}")
        _shutdown.wait(7200)

def _shop_cleanup():
    while not _shutdown.is_set():
        _shutdown.wait(3600)
        try:
            from database import cleanup_expired_shop
            cleanup_expired_shop()
        except Exception:
            pass

# ════════════════════════════════════════════════════════════════
#  ЗАПУСК
# ════════════════════════════════════════════════════════════════

def graceful_shutdown(sig, frame):
    log.info("Получен сигнал остановки...")
    _shutdown.set()
    try:
        bot.remove_webhook()
    except Exception:
        pass
    pool.shutdown(wait=False)
    sys.exit(0)

if __name__ == "__main__":
    for target, name in [
        (_stage_loop,    "stage_loop"),
        (_scheduler,     "scheduler"),
        (_random_events, "random_events"),
        (_shop_cleanup,  "shop_cleanup"),
    ]:
        threading.Thread(target=target, daemon=True, name=name).start()

    signal.signal(signal.SIGINT,  graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
    if not domain:
        log.critical("❌ RAILWAY_PUBLIC_DOMAIN не задан!")
        sys.exit(1)

    webhook_url = f"https://{domain}/webhook/{WEBHOOK_SECRET}"
    log.info(f"Setting webhook: {webhook_url}")
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=webhook_url)
    log.info("✅ Webhook set!")

    gif_count = len([f for f in os.listdir(GIF_DIR) if f.lower().endswith(".gif")]) if os.path.isdir(GIF_DIR) else 0
    from ai.client import is_enabled
    print("╔══════════════════════════════════════════════════════╗")
    print("║        👁  HORROR BOT — WEBHOOK MODE  👁             ║")
    print("╠══════════════════════════════════════════════════════╣")
    print(f"║  Admin ID : {ADMIN_ID}")
    print(f"║  Domain   : {domain}")
    print(f"║  AI       : {'✅' if is_enabled() else '❌'}")
    print(f"║  Гифки    : {gif_count} файлов")
    print("╚══════════════════════════════════════════════════════╝")

    PORT = int(os.environ.get("PORT", 8080))
    log.info(f"Flask on port {PORT}")
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
