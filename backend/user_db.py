"""
backend/user_db.py
StocksSense AI — User Database (SQLAlchemy Unified)
Handles Google Login, 30-Day Trial tracking, Pass management.
Works seamlessly with SQLite fallback or cloud PostgreSQL (Supabase) via DATABASE_URL.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
from sqlalchemy import func
from backend.database import SessionLocal, User, init_db

logger = logging.getLogger(__name__)


def to_dict(user_obj: Optional[User]) -> Dict:
    """Helper to convert a SQLAlchemy User object to a dictionary."""
    if not user_obj:
        return {}
    return {
        "id":            user_obj.id,
        "google_id":     user_obj.google_id,
        "email":         user_obj.email,
        "name":          user_obj.name,
        "picture":       user_obj.picture,
        "trial_ends_at": user_obj.trial_ends_at,
        "active_pass":   user_obj.active_pass,
        "pass_ends_at":  user_obj.pass_ends_at,
        "joined_at":     user_obj.joined_at,
        "last_login":    user_obj.last_login
    }


def init_user_db():
    """Create users table if not exists using the unified engine."""
    init_db()


def upsert_user(google_id: str, email: str, name: str, picture: str = "") -> Dict:
    """
    Create user on first login (trial_ends_at = now + 30 days).
    On subsequent logins, only update last_login, name, and picture.
    Returns the user dict.
    """
    db = SessionLocal()
    try:
        now_str = datetime.now(timezone.utc).isoformat()
        trial_ends_str = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

        # Check if user exists
        user = db.query(User).filter(User.google_id == google_id).first()
        if not user:
            # Create user
            user = User(
                google_id=google_id,
                email=email,
                name=name,
                picture=picture,
                trial_ends_at=trial_ends_str,
                active_pass="NONE",
                joined_at=now_str,
                last_login=now_str
            )
            db.add(user)
        else:
            # Update user details on relogin
            user.last_login = now_str
            user.name = name
            user.picture = picture
        
        db.commit()
        db.refresh(user)
        return to_dict(user)
    except Exception as e:
        db.rollback()
        logger.error("Error in upsert_user: %s", e)
        raise e
    finally:
        db.close()


def get_user_by_google_id(google_id: str) -> Optional[Dict]:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.google_id == google_id).first()
        return to_dict(user) if user else None
    finally:
        db.close()


def get_user_by_email(email: str) -> Optional[Dict]:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        return to_dict(user) if user else None
    finally:
        db.close()


def get_all_users() -> List[Dict]:
    """Return all users — for admin dashboard only."""
    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.joined_at.desc()).all()
        return [to_dict(u) for u in users]
    finally:
        db.close()


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
    """Admin dashboard summary statistics using SQL/ORM."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        today_str = now.date().isoformat()
        week_ago_str = (now - timedelta(days=7)).isoformat()
        five_days_ahead_str = (now + timedelta(days=5)).isoformat()

        total = db.query(User).count()
        today_joined = db.query(User).filter(User.joined_at.like(f"{today_str}%")).count()
        week_joined = db.query(User).filter(User.joined_at >= week_ago_str).count()
        paid = db.query(User).filter(User.active_pass != "NONE", User.active_pass != "").count()
        
        trial_expiring = db.query(User).filter(
            User.active_pass.in_(["NONE", ""]),
            User.trial_ends_at >= today_str,
            User.trial_ends_at <= five_days_ahead_str
        ).count()

        return {
            "total_users": total,
            "today_joined": today_joined,
            "week_joined": week_joined,
            "paid_users": paid,
            "trial_expiring_soon": trial_expiring,
        }
    finally:
        db.close()

