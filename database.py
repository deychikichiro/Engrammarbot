import sqlite3
from datetime import date, timedelta
from config import FREE_LIMIT

DB_FILE = "users.db"


def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id        INTEGER PRIMARY KEY,
                username       TEXT,
                first_name     TEXT,
                messages_today INTEGER DEFAULT 0,
                last_reset     TEXT    DEFAULT '',
                plan           TEXT    DEFAULT 'free',
                plan_expiry    TEXT    DEFAULT ''
            )
        """)


def get_user(user_id: int):
    with sqlite3.connect(DB_FILE) as conn:
        return conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()


def create_user(user_id: int, username: str, first_name: str):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
            (user_id, username or "", first_name or "")
        )


def ensure_user(user_id: int, username: str, first_name: str):
    if not get_user(user_id):
        create_user(user_id, username, first_name)


def check_and_increment(user_id: int) -> bool:
    """Returns True if user is allowed to send a message, False if daily limit reached."""
    today = str(date.today())

    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT messages_today, last_reset, plan, plan_expiry FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        if not row:
            return True

        messages_today, last_reset, plan, plan_expiry = row

        # Reset counter on new day
        if last_reset != today:
            messages_today = 0
            conn.execute(
                "UPDATE users SET messages_today = 0, last_reset = ? WHERE user_id = ?",
                (today, user_id)
            )

        # Expire outdated paid plans
        if plan not in ("free", "unlimited") and plan_expiry and plan_expiry < today:
            plan = "free"
            conn.execute(
                "UPDATE users SET plan = 'free', plan_expiry = '' WHERE user_id = ?",
                (user_id,)
            )

        # Paid plans — always allow
        if plan in ("weekly", "monthly", "yearly", "unlimited"):
            conn.execute(
                "UPDATE users SET messages_today = messages_today + 1 WHERE user_id = ?",
                (user_id,)
            )
            return True

        # Free plan — enforce limit
        if messages_today >= FREE_LIMIT:
            return False

        conn.execute(
            "UPDATE users SET messages_today = messages_today + 1 WHERE user_id = ?",
            (user_id,)
        )
        return True


def get_usage(user_id: int):
    """Returns (messages_today, plan, plan_expiry)."""
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT messages_today, last_reset, plan, plan_expiry FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

    if not row:
        return 0, "free", ""

    messages_today, last_reset, plan, plan_expiry = row
    if last_reset != str(date.today()):
        messages_today = 0

    return messages_today, plan, plan_expiry


def set_plan(user_id: int, plan: str):
    today = date.today()
    expiry_map = {
        "weekly":    str(today + timedelta(weeks=1)),
        "monthly":   str(today + timedelta(days=30)),
        "yearly":    str(today + timedelta(days=365)),
        "unlimited": "",
        "free":      "",
    }
    expiry = expiry_map.get(plan, "")

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "UPDATE users SET plan = ?, plan_expiry = ? WHERE user_id = ?",
            (plan, expiry, user_id)
        )
