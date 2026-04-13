import sqlite3
from datetime import date, datetime, timedelta

DB_FILE = "users.db"


def init_db():
    """Create database and tables if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            messages_today INTEGER DEFAULT 0,
            last_reset  TEXT DEFAULT '',
            plan        TEXT DEFAULT 'free',
            plan_expiry TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()


def get_user(user_id: int):
    """Get user row, create if not exists."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row


def create_user(user_id: int, username: str, first_name: str):
    """Insert new user."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
        (user_id, username or "", first_name or "")
    )
    conn.commit()
    conn.close()


def check_and_increment(user_id: int) -> bool:
    """
    Check if user can send a message.
    Returns True if allowed, False if daily limit reached.
    Free users: 20/day. Paid users: unlimited.
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT messages_today, last_reset, plan, plan_expiry FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()

    if not row:
        conn.close()
        return True

    messages_today, last_reset, plan, plan_expiry = row
    today = str(date.today())

    # Reset daily counter if it's a new day
    if last_reset != today:
        messages_today = 0
        c.execute("UPDATE users SET messages_today = 0, last_reset = ? WHERE user_id = ?", (today, user_id))
        conn.commit()

    # Check if paid plan is still active
    if plan != "free" and plan != "unlimited":
        if plan_expiry and plan_expiry < today:
            # Plan expired, downgrade to free
            plan = "free"
            c.execute("UPDATE users SET plan = 'free', plan_expiry = '' WHERE user_id = ?", (user_id,))
            conn.commit()

    # Unlimited plan - always allow
    if plan in ("weekly", "monthly", "yearly", "unlimited"):
        c.execute("UPDATE users SET messages_today = messages_today + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True

    # Free plan - check limit
    FREE_LIMIT = 20
    if messages_today >= FREE_LIMIT:
        conn.close()
        return False

    c.execute("UPDATE users SET messages_today = messages_today + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True


def get_usage(user_id: int):
    """Return (messages_today, plan, plan_expiry)."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT messages_today, last_reset, plan, plan_expiry FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return 0, "free", ""

    messages_today, last_reset, plan, plan_expiry = row
    today = str(date.today())
    if last_reset != today:
        messages_today = 0

    return messages_today, plan, plan_expiry


def set_plan(user_id: int, plan: str):
    """Set user plan and calculate expiry date."""
    today = date.today()

    if plan == "weekly":
        expiry = str(today + timedelta(weeks=1))
    elif plan == "monthly":
        expiry = str(today + timedelta(days=30))
    elif plan == "yearly":
        expiry = str(today + timedelta(days=365))
    elif plan == "unlimited":
        expiry = ""
    else:
        expiry = ""
        plan = "free"

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "UPDATE users SET plan = ?, plan_expiry = ? WHERE user_id = ?",
        (plan, expiry, user_id)
    )
    conn.commit()
    conn.close()
