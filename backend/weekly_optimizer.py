"""
Saturday Auto-Quant Optimizer & Dynamic Strategy Self-Tuning Engine
Evaluates trading journal data from the preceding week (past 7 days),
identifies strategy drift / sector performance / win-rate trends,
atomically updates strategy parameters in backend/strategy_config.json,
and dispatches an EOW Quant Audit Telegram card.
"""

import os
import sys
import gc
import json
import logging
from datetime import datetime, timedelta, date, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategy_config.json")
TMP_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategy_config.json.tmp")

DEFAULT_CONFIG: Dict[str, Any] = {
    "confidence_threshold": 80.0,
    "atr_stoploss_multiplier": 1.5,
    "max_daily_trades": 5,
    "risk_per_trade_percent": 2.0,
    "sector_weights": {
        "IT": 1.0,
        "BANKING": 1.0,
        "AUTO": 1.0,
        "PHARMA": 1.0,
        "METALS": 1.0,
        "ENERGY": 1.0,
        "CONSUMER": 1.0
    },
    "last_audit_timestamp": None,
    "last_audit_summary": "Initial default configuration loaded."
}


def get_strategy_config() -> Dict[str, Any]:
    """Read the current strategy_config.json safely."""
    if not os.path.exists(CONFIG_PATH):
        save_strategy_config_atomic(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Merge with default keys in case new keys were added
            merged = DEFAULT_CONFIG.copy()
            merged.update(data)
            return merged
    except Exception as e:
        logger.error("Failed to read strategy_config.json: %s. Using default.", e)
        return DEFAULT_CONFIG.copy()


def save_strategy_config_atomic(config_dict: Dict[str, Any]) -> bool:
    """
    Atomically save strategy configuration to prevent file corruption during unexpected crashes.
    1. Write to strategy_config.json.tmp
    2. Flush and fsync
    3. Atomic replace strategy_config.json.tmp -> strategy_config.json
    """
    try:
        with open(TMP_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(TMP_CONFIG_PATH, CONFIG_PATH)
        logger.info("✅ Strategy config atomically updated: %s", CONFIG_PATH)
        return True
    except Exception as e:
        logger.error("❌ Atomic write failed for strategy_config.json: %s", e)
        if os.path.exists(TMP_CONFIG_PATH):
            try:
                os.remove(TMP_CONFIG_PATH)
            except Exception:
                pass
        return False


def run_weekly_quant_audit(db_session) -> Dict[str, Any]:
    """
    Execute Saturday Quant Audit.
    1. Fetch paper trades from past 7 days.
    2. Compute performance metrics (Win Rate, Total PnL, Win/Loss Count).
    3. Determine parameter adjustments (Self-Tuning Engine).
    4. Save updated parameters atomically to strategy_config.json.
    5. Clean up memory with explicit gc.collect().
    6. Send Telegram audit report.
    """
    logger.info("🤖 Starting Saturday Weekly Quant Audit & Auto-Optimization...")

    config = get_strategy_config()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    trades = []
    try:
        from backend.database import PaperTrade, LiveTrade
        # Fetch both paper trades and live trades in the last 7 days
        raw_paper = db_session.query(PaperTrade).filter(
            PaperTrade.trade_date >= start_date.date()
        ).all()
        raw_live = db_session.query(LiveTrade).filter(
            LiveTrade.trade_date >= start_date.date()
        ).all()
        raw_trades = raw_paper + raw_live

        # Extract primitive values into lightweight dicts to keep memory <100KB
        for t in raw_trades:
            trades.append({
                "symbol": t.symbol,
                "status": t.status,
                "pnl": float(t.pnl or 0.0),
                "pnl_percent": float(t.pnl_percent or 0.0),
                "action": getattr(t, "action", "BUY"),
                "exit_reason": t.status or "UNKNOWN",
                "trade_date": str(t.trade_date)
            })
        del raw_paper, raw_live, raw_trades
    except Exception as e:
        logger.error("Error querying paper/live trades for weekly audit: %s", e)

    total_trades = len(trades)
    closed_trades = [t for t in trades if t["status"] != "OPEN"]
    closed_count = len(closed_trades)

    wins = [t for t in closed_trades if t["pnl"] > 0]
    losses = [t for t in closed_trades if t["pnl"] < 0]
    breakevens = [t for t in closed_trades if t["pnl"] == 0]

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / closed_count * 100.0) if closed_count > 0 else 0.0

    total_pnl = sum(t["pnl"] for t in closed_trades)

    # ─── SELF-TUNING DECISION LOGIC ───
    old_confidence = config.get("confidence_threshold", 80.0)
    old_atr_mult = config.get("atr_stoploss_multiplier", 1.5)
    
    new_confidence = old_confidence
    new_atr_mult = old_atr_mult
    tuning_reasons = []

    if closed_count >= 5:
        if win_rate < 45.0:
            # Low win rate -> Tighten screening, increase confidence threshold by +2% (max 90%)
            new_confidence = min(90.0, round(old_confidence + 2.0, 1))
            tuning_reasons.append(f"Win rate fell to {win_rate:.1f}%. Increased Confidence Gate to {new_confidence}%.")
        elif win_rate >= 75.0:
            # High win rate -> Slightly relax confidence threshold by -1% (min 80%) to allow more entries
            new_confidence = max(80.0, round(old_confidence - 1.0, 1))
            tuning_reasons.append(f"High Win rate ({win_rate:.1f}%). Dynamic Confidence Gate tuned to {new_confidence}%.")

        # Volatility & SL hit analysis
        sl_hits = sum(1 for t in losses if "SL" in t["exit_reason"].upper() or "STOP" in t["exit_reason"].upper())
        if loss_count > 0 and (sl_hits / loss_count) > 0.6:
            # Frequent stop loss hits -> Expand ATR multiplier slightly by +0.1x (max 2.2x)
            new_atr_mult = min(2.2, round(old_atr_mult + 0.1, 2))
            tuning_reasons.append(f"Frequent SL hits ({sl_hits}/{loss_count}). Adjusted ATR SL multiplier to {new_atr_mult}x.")
    else:
        tuning_reasons.append("Insufficient trade volume this week (<5 trades). Preserved baseline parameters.")

    # Update config dict
    ist_now_str = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %I:%M %p IST")
    config["confidence_threshold"] = new_confidence
    config["atr_stoploss_multiplier"] = new_atr_mult
    config["last_audit_timestamp"] = ist_now_str
    config["last_audit_summary"] = " | ".join(tuning_reasons) if tuning_reasons else "Audit completed cleanly."

    # Save configuration atomically
    save_strategy_config_atomic(config)

    report_payload = {
        "period": f"{start_date.strftime('%b %d')} – {end_date.strftime('%b %d, %Y')}",
        "total_trades": total_trades,
        "closed_trades": closed_count,
        "wins": win_count,
        "losses": loss_count,
        "win_rate": round(win_rate, 1),
        "net_pnl": round(total_pnl, 2),
        "old_confidence": old_confidence,
        "new_confidence": new_confidence,
        "old_atr_mult": old_atr_mult,
        "new_atr_mult": new_atr_mult,
        "reasons": tuning_reasons,
        "timestamp": ist_now_str
    }

    # Clean up memory explicitly
    del trades, closed_trades, wins, losses
    gc.collect()
    logger.info("🧹 Memory cleanup complete after weekly audit.")

    # Send Telegram Notification
    try:
        from backend.telegram_alerts import alert_weekly_audit
        alert_weekly_audit(report_payload)
    except Exception as e:
        logger.warning("Telegram weekly audit notification failed: %s", e)

    return report_payload
