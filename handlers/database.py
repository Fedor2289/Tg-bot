"""
database.py — SQLite хранилище. Все данные сохраняются между перезапусками.
"""
import sqlite3
import json
import threading
import time
import logging
from config import DB_PATH

log = logging.getLogger("horror.db")
_lock = threading.Lock()

# ── Подключение ───────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

_conn = get_conn()

def init_db():
    """Создаёт все таблицы если их нет."""
    with _lock:
        c = _conn
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            uid         INTEGER PRIMARY KEY,
            username    TEXT,
            name        TEXT,
            age         TEXT,
            city        TEXT,
            job         TEXT,
            fear        TEXT,
            pet         TEXT,
            sleep_time  TEXT,
            phone_model TEXT,
            color       TEXT,
            food        TEXT,
            music       TEXT,
            interests   TEXT DEFAULT '[]',
            lang_pair   TEXT DEFAULT 'ru|en',
            stage       INTEGER DEFAULT 0,
            score       INTEGER DEFAULT 0,
            msg_count   INTEGER DEFAULT 0,
            horror_active INTEGER DEFAULT 0,
            stopped     INTEGER DEFAULT 0,
            muted       INTEGER DEFAULT 0,
            banned      INTEGER DEFAULT 0,
            spy         INTEGER DEFAULT 1,
            ai_mode     INTEGER DEFAULT 0,
            ai_msg_count INTEGER DEFAULT 0,
            achievements TEXT DEFAULT '[]',
            msg_history  TEXT DEFAULT '[]',
            translate_mode INTEGER DEFAULT 0,
            created_at  REAL DEFAULT (unixepoch()),
            updated_at  REAL DEFAULT (unixepoch()),
            last_seen   REAL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS admins (
            uid         INTEGER PRIMARY KEY,
            added_by    INTEGER,
            added_at    REAL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS horror_queue (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uid         INTEGER NOT NULL,
            func_name   TEXT NOT NULL,
            fire_at     REAL NOT NULL,
            data        TEXT DEFAULT '{}',
            done        INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS ai_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id     INTEGER NOT NULL,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            created_at  REAL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS daily_quests (
            uid         INTEGER PRIMARY KEY,
            last_date   TEXT,
            streak      INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS anonymous_chat (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uid         INTEGER NOT NULL,
            text        TEXT NOT NULL,
            created_at  REAL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS friend_invites (
            code        TEXT PRIMARY KEY,
            inviter_uid INTEGER NOT NULL,
            invitee_uid INTEGER,
            created_at  REAL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS shop_items (
            uid         INTEGER NOT NULL,
            item_id     TEXT NOT NULL,
            expires_at  REAL,
            PRIMARY KEY (uid, item_id)
        );

        CREATE TABLE IF NOT EXISTS stage_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uid         INTEGER NOT NULL,
            stage       INTEGER NOT NULL,
            created_at  REAL DEFAULT (unixepoch())
        );

        CREATE INDEX IF NOT EXISTS idx_ai_history_chat ON ai_history(chat_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_horror_queue_fire ON horror_queue(fire_at, done);
        CREATE INDEX IF NOT EXISTS idx_stage_history_uid ON stage_history(uid, created_at);
        """)
        _conn.commit()
    # Миграция: добавляем msg_history если нет
    try:
        _conn.execute("ALTER TABLE users ADD COLUMN msg_history TEXT DEFAULT '[]'")
        _conn.commit()
    except Exception:
        pass  # колонка уже есть
    log.info("✅ База данных инициализирована")


# ── Пользователи ─────────────────────────────────────────────────
def get_user(uid: int) -> dict:
    """Возвращает профиль пользователя. Создаёт если нет."""
    with _lock:
        row = _conn.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
        if not row:
            _conn.execute("INSERT OR IGNORE INTO users (uid) VALUES (?)", (uid,))
            _conn.commit()
            row = _conn.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
        d = dict(row)
        d["interests"] = json.loads(d.get("interests") or "[]")
        d["achievements"] = json.loads(d.get("achievements") or "[]")
        return d

def save_user(uid: int, data: dict):
    """Сохраняет изменённые поля профиля."""
    with _lock:
        d = dict(data)
        if "interests" in d and isinstance(d["interests"], list):
            d["interests"] = json.dumps(d["interests"], ensure_ascii=False)
        if "achievements" in d and isinstance(d["achievements"], list):
            d["achievements"] = json.dumps(d["achievements"], ensure_ascii=False)
        d["updated_at"] = time.time()
        d["uid"] = uid
        fields = [k for k in d if k != "uid"]
        sql = f"UPDATE users SET {', '.join(f'{f}=?' for f in fields)}, updated_at=? WHERE uid=?"
        vals = [d[f] for f in fields] + [time.time(), uid]
        _conn.execute(sql, vals)
        _conn.commit()

def update_user_field(uid: int, field: str, value):
    """Быстрое обновление одного поля."""
    with _lock:
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        _conn.execute(
            f"UPDATE users SET {field}=?, updated_at=? WHERE uid=?",
            (value, time.time(), uid)
        )
        _conn.commit()

def touch_user(uid: int):
    with _lock:
        _conn.execute("UPDATE users SET last_seen=? WHERE uid=?", (time.time(), uid))
        _conn.commit()

def get_all_users() -> list:
    with _lock:
        rows = _conn.execute("SELECT * FROM users").fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["interests"] = json.loads(d.get("interests") or "[]")
            d["achievements"] = json.loads(d.get("achievements") or "[]")
            result.append(d)
        return result

def get_active_users(min_stage: int = 0) -> list:
    """Активные жертвы (не stopped, не muted)."""
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM users WHERE stopped=0 AND muted=0 AND horror_active=1 AND stage>=?",
            (min_stage,)
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["interests"] = json.loads(d.get("interests") or "[]")
            d["achievements"] = json.loads(d.get("achievements") or "[]")
            result.append(d)
        return result

def count_users() -> int:
    with _lock:
        return _conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


# ── Admins ───────────────────────────────────────────────────────
def get_admins() -> set:
    with _lock:
        rows = _conn.execute("SELECT uid FROM admins").fetchall()
        return {row[0] for row in rows}

def add_admin(uid: int, added_by: int = 0):
    with _lock:
        _conn.execute(
            "INSERT OR IGNORE INTO admins (uid, added_by) VALUES (?,?)",
            (uid, added_by)
        )
        _conn.commit()

def remove_admin(uid: int):
    with _lock:
        _conn.execute("DELETE FROM admins WHERE uid=?", (uid,))
        _conn.commit()


# ── AI История ───────────────────────────────────────────────────
AI_HIST_MAX = 20
AI_HIST_TTL = 3600 * 24 * 7  # 7 дней

def get_ai_history(chat_id: int, limit: int = AI_HIST_MAX) -> list:
    with _lock:
        cutoff = time.time() - AI_HIST_TTL
        rows = _conn.execute(
            "SELECT role, content FROM ai_history WHERE chat_id=? AND created_at>? ORDER BY created_at DESC LIMIT ?",
            (chat_id, cutoff, limit)
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

def add_ai_message(chat_id: int, role: str, content: str):
    with _lock:
        _conn.execute(
            "INSERT INTO ai_history (chat_id, role, content) VALUES (?,?,?)",
            (chat_id, role, content)
        )
        # Чистим старые (>TTL или >MAX*2)
        cutoff = time.time() - AI_HIST_TTL
        _conn.execute(
            "DELETE FROM ai_history WHERE chat_id=? AND created_at<?",
            (chat_id, cutoff)
        )
        _conn.commit()

def clear_ai_history(chat_id: int):
    with _lock:
        _conn.execute("DELETE FROM ai_history WHERE chat_id=?", (chat_id,))
        _conn.commit()


# ── Horror Queue (очередь атак) ──────────────────────────────────
def schedule_attack(uid: int, func_name: str, fire_at: float, data: dict = None):
    with _lock:
        _conn.execute(
            "INSERT INTO horror_queue (uid, func_name, fire_at, data) VALUES (?,?,?,?)",
            (uid, func_name, fire_at, json.dumps(data or {}))
        )
        _conn.commit()

def get_pending_attacks(now: float = None) -> list:
    if now is None:
        now = time.time()
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM horror_queue WHERE fire_at<=? AND done=0 ORDER BY fire_at",
            (now,)
        ).fetchall()
        return [dict(r) for r in rows]

def mark_attack_done(attack_id: int):
    with _lock:
        _conn.execute("UPDATE horror_queue SET done=1 WHERE id=?", (attack_id,))
        _conn.commit()

def cancel_user_attacks(uid: int):
    with _lock:
        _conn.execute("DELETE FROM horror_queue WHERE uid=? AND done=0", (uid,))
        _conn.commit()


# ── Daily quests ─────────────────────────────────────────────────
def get_daily_info(uid: int) -> dict:
    with _lock:
        row = _conn.execute("SELECT * FROM daily_quests WHERE uid=?", (uid,)).fetchone()
        return dict(row) if row else {"uid": uid, "last_date": None, "streak": 0}

def set_daily_done(uid: int, date_str: str, streak: int):
    with _lock:
        _conn.execute(
            "INSERT OR REPLACE INTO daily_quests (uid, last_date, streak) VALUES (?,?,?)",
            (uid, date_str, streak)
        )
        _conn.commit()


# ── Leaderboard ──────────────────────────────────────────────────
def get_leaderboard(limit: int = 10, city: str = None) -> list:
    with _lock:
        if city:
            rows = _conn.execute(
                "SELECT uid, name, username, score, stage, city FROM users "
                "WHERE LOWER(city)=LOWER(?) AND banned=0 ORDER BY score DESC LIMIT ?",
                (city, limit)
            ).fetchall()
        else:
            rows = _conn.execute(
                "SELECT uid, name, username, score, stage, city FROM users "
                "WHERE banned=0 ORDER BY score DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

def get_user_rank(uid: int) -> int:
    with _lock:
        score = _conn.execute("SELECT score FROM users WHERE uid=?", (uid,)).fetchone()
        if not score:
            return 0
        rank = _conn.execute(
            "SELECT COUNT(*)+1 FROM users WHERE score>? AND banned=0",
            (score[0],)
        ).fetchone()[0]
        return rank


# ── Shop ─────────────────────────────────────────────────────────
def get_shop_item(uid: int, item_id: str) -> dict | None:
    with _lock:
        row = _conn.execute(
            "SELECT * FROM shop_items WHERE uid=? AND item_id=?",
            (uid, item_id)
        ).fetchone()
        return dict(row) if row else None

def set_shop_item(uid: int, item_id: str, expires_at: float = None):
    with _lock:
        _conn.execute(
            "INSERT OR REPLACE INTO shop_items (uid, item_id, expires_at) VALUES (?,?,?)",
            (uid, item_id, expires_at)
        )
        _conn.commit()

def remove_shop_item(uid: int, item_id: str):
    with _lock:
        _conn.execute(
            "DELETE FROM shop_items WHERE uid=? AND item_id=?",
            (uid, item_id)
        )
        _conn.commit()

def cleanup_expired_shop():
    with _lock:
        _conn.execute(
            "DELETE FROM shop_items WHERE expires_at IS NOT NULL AND expires_at<?",
            (time.time(),)
        )
        _conn.commit()


# ── Stage history ────────────────────────────────────────────────
def log_stage_change(uid: int, stage: int):
    with _lock:
        _conn.execute(
            "INSERT INTO stage_history (uid, stage) VALUES (?,?)",
            (uid, stage)
        )
        _conn.commit()

def get_stage_history(uid: int, limit: int = 50) -> list:
    with _lock:
        rows = _conn.execute(
            "SELECT stage, created_at FROM stage_history WHERE uid=? ORDER BY created_at DESC LIMIT ?",
            (uid, limit)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Anonymous chat ────────────────────────────────────────────────
def add_anon_message(uid: int, text: str):
    with _lock:
        _conn.execute(
            "INSERT INTO anonymous_chat (uid, text) VALUES (?,?)",
            (uid, text[:500])
        )
        _conn.commit()

def get_anon_messages(limit: int = 20) -> list:
    with _lock:
        rows = _conn.execute(
            "SELECT uid, text, created_at FROM anonymous_chat ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Friend invites ────────────────────────────────────────────────
def create_invite(code: str, inviter_uid: int):
    with _lock:
        _conn.execute(
            "INSERT OR IGNORE INTO friend_invites (code, inviter_uid) VALUES (?,?)",
            (code, inviter_uid)
        )
        _conn.commit()

def use_invite(code: str, invitee_uid: int) -> int | None:
    """Возвращает inviter_uid если код валиден."""
    with _lock:
        row = _conn.execute(
            "SELECT inviter_uid FROM friend_invites WHERE code=? AND invitee_uid IS NULL",
            (code,)
        ).fetchone()
        if not row:
            return None
        _conn.execute(
            "UPDATE friend_invites SET invitee_uid=? WHERE code=?",
            (invitee_uid, code)
        )
        _conn.commit()
        return row[0]
