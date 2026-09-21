"""Small SQLite store. Everything lives in data/brief.db on this computer."""
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "brief.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    due TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    created TEXT NOT NULL,
    done_at TEXT,
    event_id TEXT
);
CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    source TEXT,
    saved TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mail_state (
    id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS focus_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    minutes INTEGER NOT NULL,
    label TEXT,
    finished TEXT NOT NULL
);
"""


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    with closing(_connect()) as conn, conn:
        conn.executescript(SCHEMA)
        
        # Safely attempt to add the event_id column to existing databases
        try:
            conn.execute("ALTER TABLE tasks ADD COLUMN event_id TEXT")
        except sqlite3.OperationalError:
            pass # The column already exists, safe to ignore
            
        # Forget mail states older than 30 days so the table stays small.
        conn.execute("DELETE FROM mail_state WHERE date(updated) < date('now', 'localtime', '-30 day')")


# ---------- tasks ----------

def list_tasks():
    with closing(_connect()) as conn:
        rows = conn.execute(
            """SELECT id, title, due, done, event_id FROM tasks
               WHERE done = 0 OR date(done_at) = date('now', 'localtime')
               ORDER BY done, (due IS NULL), due, id"""
        ).fetchall()
    return [dict(r, done=bool(r["done"])) for r in rows]


def add_task(title, due):
    with closing(_connect()) as conn, conn:
        cur = conn.execute("INSERT INTO tasks (title, due, created) VALUES (?, ?, ?)", (title, due, _now()))
        task_id = cur.lastrowid
    return {"id": task_id, "title": title, "due": due, "done": False, "event_id": None}


def set_task_done(task_id, done):
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "UPDATE tasks SET done = ?, done_at = ? WHERE id = ?",
            (1 if done else 0, _now() if done else None, task_id),
        )
        return cur.rowcount > 0


def delete_task(task_id):
    with closing(_connect()) as conn, conn:
        return conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,)).rowcount > 0


def clear_done_tasks():
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM tasks WHERE done = 1")


def set_task_event_id(task_id, event_id):
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "UPDATE tasks SET event_id = ? WHERE id = ?",
            (event_id, task_id),
        )
        return cur.rowcount > 0


# ---------- bookmarks ----------

def list_bookmarks():
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT id, kind, title, url, source, saved FROM bookmarks ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def add_bookmark(kind, title, url, source):
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT OR IGNORE INTO bookmarks (kind, title, url, source, saved) VALUES (?, ?, ?, ?, ?)",
            (kind, title, url, source, _now()),
        )


def delete_bookmark(bookmark_id):
    with closing(_connect()) as conn, conn:
        return conn.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,)).rowcount > 0


# ---------- mail state (pinned / done are stored here, never written back to Gmail) ----------

def mail_states():
    with closing(_connect()) as conn:
        return {r["id"]: r["state"] for r in conn.execute("SELECT id, state FROM mail_state")}


def set_mail_state(mail_id, state):
    with closing(_connect()) as conn, conn:
        if state is None:
            conn.execute("DELETE FROM mail_state WHERE id = ?", (mail_id,))
        else:
            conn.execute(
                "INSERT OR REPLACE INTO mail_state (id, state, updated) VALUES (?, ?, ?)",
                (mail_id, state, _now()),
            )


def reset_done_mail():
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM mail_state WHERE state = 'done'")


# ---------- focus sessions ----------

def log_focus(minutes, label):
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT INTO focus_sessions (day, minutes, label, finished) VALUES (?, ?, ?, ?)",
            (date.today().isoformat(), minutes, label, _now()),
        )


def focus_today():
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(minutes), 0) AS m FROM focus_sessions WHERE day = ?",
            (date.today().isoformat(),),
        ).fetchone()
    return {"sessions": row["n"], "minutes": row["m"]}