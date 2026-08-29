"""
backend/user_db.py
StocksSense AI — User Database (SQLite)
Handles Google Login, 30-Day Trial tracking, Pass management.
"""

import os
import sqlite3
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict

# DB file path — store in data/ folder along with the main DB
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "users.db")


def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_user_db():
    """Create users table if not exists."""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                google_id     TEXT UNIQUE NOT NULL,
                email         TEXT UNIQUE NOT NULL,
                name          TEXT,
                picture       TEXT,
                trial_ends_at TEXT NOT NULL,
                active_pass   TEXT DEFAULT 'NONE',
                pass_ends_at  TEXT,
                joined_at     TEXT NOT NULL,
                last_login    TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def upsert_user(google_id: str, email: str, name: str, picture: str = "") -> Dict:
    """
    Create user on first login (trial_ends_at = now + 30 days).
    On subsequent logins, only update last_login.
    Returns the user dict.
    """
    conn = _get_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        trial_ends = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

        # Try to insert (first login)
        conn.execute("""
            INSERT OR IGNORE INTO users
                (google_id, email, name, picture, trial_ends_at, active_pass, joined_at, last_login)
            VALUES (?, ?, ?, ?, ?, 'NONE', ?, ?)
        """, (google_id, email, name, picture, trial_ends, now, now))

        # Always update last_login and name/picture
        conn.execute("""
            UPDATE users SET last_login=?, name=?, picture=?
            WHERE google_id=?
        """, (now, name, picture, google_id))

        conn.commit()

        row = conn.execute(
            "SELECT * FROM users WHERE google_id=?", (google_id,)
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def get_user_by_google_id(google_id: str) -> Optional[Dict]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE google_id=?", (google_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[Dict]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email=?", (email,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_users() -> List[Dict]:
    """Return all users — for admin dashboard only."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY joined_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_trial_status(user: Dict) -> Dict:
    """
    Returns trial status info for a user dict.
    """
    now = datetime.now(timezone.utc)
    trial_end = datetime.fromisoformat(user["trial_ends_at"])

    # Make timezone-aware if naive
    if trial_end.tzinfo is None:
        trial_end = trial_end.replace(tzinfo=timezone.utc)

    days_left = (trial_end - now).days
    is_active = days_left >= 0
    has_pass = user.get("active_pass", "NONE") not in (None, "NONE", "")

    return {
        "trial_active": is_active or has_pass,
        "days_left": max(0, days_left),
        "trial_ends_at": trial_end.strftime("%Y-%m-%d"),
        "active_pass": user.get("active_pass", "NONE"),
        "has_pass": has_pass,
    }


def get_summary_stats() -> Dict:
    """Admin dashboard summary statistics."""
    conn = _get_conn()
    try:
        now = datetime.now(timezone.utc)
        today_str = now.date().isoformat()
        week_ago  = (now - timedelta(days=7)).isoformat()

        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        today_joined = conn.execute(
            "SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{today_str}%",)
        ).fetchone()[0]
        week_joined = conn.execute(
            "SELECT COUNT(*) FROM users WHERE joined_at >= ?", (week_ago,)
        ).fetchone()[0]
        paid = conn.execute(
            "SELECT COUNT(*) FROM users WHERE active_pass NOT IN ('NONE', '')"
        ).fetchone()[0]
        trial_expiring = conn.execute(
            """SELECT COUNT(*) FROM users
               WHERE active_pass IN ('NONE', '')
               AND date(trial_ends_at) BETWEEN date('now') AND date('now', '+5 days')"""
        ).fetchone()[0]

        return {
            "total_users": total,
            "today_joined": today_joined,
            "week_joined": week_joined,
            "paid_users": paid,
            "trial_expiring_soon": trial_expiring,
        }
    finally:
        conn.close()
