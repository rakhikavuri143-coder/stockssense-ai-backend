"""
MySQL Database Engine with SQLite Fallback
Tables: ai_signals, user_trades, daily_performance, paper_trades
"""

import os
import logging
from datetime import date, datetime
from typing import Optional
from sqlalchemy import (
    create_engine, Column, Integer, Float, String, DateTime,
    Date, Text, Boolean, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

Base = declarative_base()

# ─────────────────────────── MODELS ────────────────────────────

class AISignal(Base):
    __tablename__ = "ai_signals"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    symbol          = Column(String(30), nullable=False)
    company_name    = Column(String(100))
    sector          = Column(String(50))
    signal          = Column(String(20))        # BUY / SELL / AVOID
    confidence      = Column(Float)             # e.g. 92.5
    entry_low       = Column(Float)
    entry_high      = Column(Float)
    target1         = Column(Float)
    target2         = Column(Float)
    stop_loss       = Column(Float)
    rr_ratio        = Column(Float)
    sl_hit_prob     = Column(Float)
    news_headline   = Column(Text)
    news_summary    = Column(Text)
    historical_note = Column(Text)
    created_at      = Column(DateTime, default=datetime.utcnow)
    trade_date      = Column(Date, default=date.today)


class PaperTrade(Base):
    __tablename__ = "paper_trades"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    signal_id      = Column(Integer, nullable=True)
    symbol         = Column(String(30), nullable=False)
    company_name   = Column(String(100))
    action         = Column(String(10))         # BUY / SELL
    entry_price    = Column(Float)
    quantity       = Column(Integer)
    exit_price     = Column(Float, nullable=True)
    stop_loss      = Column(Float)
    target1        = Column(Float)
    target2        = Column(Float)
    status         = Column(String(50), default="OPEN")  # OPEN / CLOSED / SL_HIT / T1_HIT / T2_HIT
    pnl            = Column(Float, default=0.0)
    pnl_percent    = Column(Float, default=0.0)
    opened_at      = Column(DateTime, default=datetime.utcnow)
    closed_at      = Column(DateTime, nullable=True)
    trade_date     = Column(Date, default=date.today)


class LiveTrade(Base):
    __tablename__ = "live_trades"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    signal_id      = Column(Integer, nullable=True)
    symbol         = Column(String(30), nullable=False)
    company_name   = Column(String(100))
    action         = Column(String(10))         # BUY / SELL
    entry_price    = Column(Float)
    quantity       = Column(Integer)
    exit_price     = Column(Float, nullable=True)
    stop_loss      = Column(Float)
    target1        = Column(Float)
    target2        = Column(Float)
    status         = Column(String(50), default="OPEN")  # OPEN / CLOSED / SL_HIT / T1_HIT / T2_HIT
    order_id       = Column(String(50), nullable=True)   # Angel One order ID
    pnl            = Column(Float, default=0.0)
    pnl_percent    = Column(Float, default=0.0)
    opened_at      = Column(DateTime, default=datetime.utcnow)
    closed_at      = Column(DateTime, nullable=True)
    trade_date     = Column(Date, default=date.today)



class DailyPerformance(Base):
    __tablename__ = "daily_performance"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    trade_date     = Column(Date, unique=True, nullable=False)
    total_signals  = Column(Integer, default=0)
    total_trades   = Column(Integer, default=0)
    wins           = Column(Integer, default=0)
    losses         = Column(Integer, default=0)
    breakeven      = Column(Integer, default=0)
    net_pnl        = Column(Float, default=0.0)
    win_rate       = Column(Float, default=0.0)
    paper_balance  = Column(Float, default=0.0)
    created_at     = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    google_id     = Column(String(100), unique=True, nullable=False)
    email         = Column(String(100), unique=True, nullable=False)
    name          = Column(String(100))
    picture       = Column(String(200))
    trial_ends_at = Column(String(50), nullable=False)
    active_pass   = Column(String(20), default="NONE")
    pass_ends_at  = Column(String(50))
    joined_at     = Column(String(50), nullable=False)
    last_login    = Column(String(50))


# ─────────────────────────── ENGINE SETUP ────────────────────────────

def _build_engine():
    """Try Database URL (Postgres/MySQL) first, fallback to SQLite."""
    # 1. Try generic DATABASE_URL (for PostgreSQL/Supabase, etc.)
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        # SQLAlchemy requires postgresql:// instead of postgres://
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        try:
            engine = create_engine(
                db_url,
                pool_size=5,
                max_overflow=5,
                pool_timeout=10,
                pool_pre_ping=True,
                pool_recycle=1800
            )
            with engine.connect():
                pass
            logger.info("✅ Connected to database using DATABASE_URL")
            return engine
        except Exception as e:
            logger.warning("⚠️ Database connection via DATABASE_URL failed: %s. Trying MySQL...", e)

    # 2. Try MySQL next
    mysql_user = os.getenv("MYSQL_USER", "root")
    mysql_pass = os.getenv("MYSQL_PASSWORD", "")
    mysql_host = os.getenv("MYSQL_HOST", "localhost")
    mysql_port = os.getenv("MYSQL_PORT", "3306")
    mysql_db   = os.getenv("MYSQL_DB", "stock_agent")

    if mysql_pass:
        try:
            url = f"mysql+pymysql://{mysql_user}:{mysql_pass}@{mysql_host}:{mysql_port}/{mysql_db}"
            engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
            with engine.connect():
                pass
            logger.info("✅ Connected to MySQL database: %s", mysql_db)
            return engine
        except Exception as e:
            logger.warning("⚠️  MySQL connection failed (%s). Falling back to SQLite.", e)

    # 3. Fallback to SQLite
    sqlite_path = os.path.join(os.path.dirname(__file__), "..", "data", "stock_agent.db")
    os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    logger.info("📦 Using SQLite fallback: %s", sqlite_path)
    return engine


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)



def init_db():
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Database tables initialized.")


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────── HELPERS ────────────────────────────

def save_signal(db: Session, signal_data: dict) -> AISignal:
    obj = AISignal(**signal_data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def save_paper_trade(db: Session, trade_data: dict) -> PaperTrade:
    obj = PaperTrade(**trade_data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_open_paper_trades(db: Session):
    return db.query(PaperTrade).filter(PaperTrade.status == "OPEN").all()


def save_live_trade(db: Session, trade_data: dict) -> LiveTrade:
    obj = LiveTrade(**trade_data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_open_live_trades(db: Session):
    return db.query(LiveTrade).filter(LiveTrade.status == "OPEN").all()



def get_weekly_summary(db: Session, mode: str = "paper"):
    from sqlalchemy import text
    dialect = db.bind.dialect.name
    if dialect == "sqlite":
        date_filter = "date('now', '-7 days')"
    else:
        date_filter = "CURRENT_DATE - INTERVAL '7 days'"
        
    table_name = "live_trades" if mode == "live" else "paper_trades"
    result = db.execute(text(f"""
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(pnl), 0) as net_pnl,
            COALESCE(AVG(pnl_percent), 0) as avg_pnl_pct
        FROM {table_name}
        WHERE trade_date >= {date_filter}
    """)).fetchone()
    return dict(result._mapping) if result else {}


def get_monthly_summary(db: Session, mode: str = "paper"):
    from sqlalchemy import text
    dialect = db.bind.dialect.name
    if dialect == "sqlite":
        date_filter = "date('now', '-30 days')"
    else:
        date_filter = "CURRENT_DATE - INTERVAL '30 days'"
        
    table_name = "live_trades" if mode == "live" else "paper_trades"
    result = db.execute(text(f"""
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(pnl), 0) as net_pnl,
            COALESCE(AVG(pnl_percent), 0) as avg_pnl_pct
        FROM {table_name}
        WHERE trade_date >= {date_filter}
    """)).fetchone()
    return dict(result._mapping) if result else {}




def save_daily_performance(db: Session, today: date, paper_balance: float):
    trades = db.query(PaperTrade).filter(PaperTrade.trade_date == today).all()
    wins      = sum(1 for t in trades if t.pnl > 0)
    losses    = sum(1 for t in trades if t.pnl < 0)
    breakeven = sum(1 for t in trades if t.pnl == 0)
    net_pnl   = sum(t.pnl for t in trades)
    total     = len(trades)
    win_rate  = (wins / total * 100) if total > 0 else 0.0

    existing = db.query(DailyPerformance).filter(DailyPerformance.trade_date == today).first()
    if existing:
        existing.total_trades = total
        existing.wins         = wins
        existing.losses       = losses
        existing.breakeven    = breakeven
        existing.net_pnl      = net_pnl
        existing.win_rate     = win_rate
        existing.paper_balance= paper_balance
    else:
        db.add(DailyPerformance(
            trade_date=today, total_trades=total, wins=wins, losses=losses,
            breakeven=breakeven, net_pnl=net_pnl, win_rate=win_rate, paper_balance=paper_balance
        ))
    db.commit()
