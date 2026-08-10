"""
Telegram Bot Alert Engine for StockSense AI
Sends real-time BUY/SELL signals, trade executions, SL/Target exits, and EOD reports to Telegram.
"""

import os
import logging
import urllib.request
import urllib.parse
import json
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

IST = timezone(timedelta(hours=5, minutes=30))


def _ist_now() -> str:
    return datetime.now(IST).strftime("%I:%M %p IST")


def send_telegram_message(text: str, parse_mode: str = "HTML") -> bool:
    """Send a message via Telegram Bot API (non-blocking, fire-and-forget)."""
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("Telegram credentials not set. Skipping alert.")
        return False

    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id":    CHAT_ID,
            "text":       text,
            "parse_mode": parse_mode,
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req  = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                logger.info("Telegram alert sent successfully.")
                return True
            else:
                logger.warning("Telegram API error: %s", result)
                return False
    except Exception as e:
        logger.error("Telegram send failed: %s", e)
        return False


# ─────────────────────── SIGNAL ALERTS ───────────────────────

def alert_scan_signals(signals: list):
    """Send Telegram alert for BUY/SELL signals found after a scan."""
    if not signals:
        return

    buy_sell = [s for s in signals if s.get("signal") in ("BUY", "SELL") and s.get("confidence", 0) >= 85]
    if not buy_sell:
        return

    header = f"<b>StockSense AI Signal Alert</b>\n<i>{_ist_now()}</i>\n{'=' * 30}\n"
    cards = []

    for s in buy_sell[:5]:  # Max 5 alerts per scan
        signal_emoji = "🟢 BUY" if s["signal"] == "BUY" else "🔴 SELL"
        approved_tag = "✅ APPROVED" if s.get("approved") else "⚠️ REVIEW"
        rank_tag     = f"🏆 TOP #{s['rank']} " if s.get("rank") else ""

        card = (
            f"{rank_tag}<b>{s['symbol'].replace('.NS', '')}</b> — {s.get('company_name', '')}\n"
            f"Signal: <b>{signal_emoji}</b> | Confidence: <b>{s.get('confidence', 0):.1f}%</b>\n"
            f"Guard: {approved_tag}\n"
            f"Entry: ₹{s.get('current_price', 0):,.2f}\n"
            f"Target 1: ₹{s.get('target1', 0):,.2f}\n"
            f"Target 2: ₹{s.get('target2', 0):,.2f}\n"
            f"Stop Loss: ₹{s.get('stop_loss', 0):,.2f}\n"
            f"R:R Ratio: 1:{s.get('rr_ratio', 0):.1f}\n"
            f"Sector: {s.get('sector', 'N/A')}"
        )
        cards.append(card)

    msg = header + "\n\n".join(cards)
    msg += f"\n\n💡 <i>Total {len(buy_sell)} signal(s) found. Open StockSense AI dashboard to trade.</i>"

    send_telegram_message(msg)


# ─────────────────────── TRADE EXECUTION ALERTS ───────────────────────

def alert_trade_opened(symbol: str, company_name: str, action: str,
                       entry_price: float, quantity: int,
                       stop_loss: float, target1: float, target2: float):
    """Alert when a new paper trade is placed."""
    action_emoji = "🟢 BUY" if action == "BUY" else "🔴 SELL"
    trade_value  = entry_price * quantity

    msg = (
        f"<b>📝 Paper Trade Placed!</b>\n"
        f"<i>{_ist_now()}</i>\n"
        f"{'=' * 30}\n"
        f"<b>{symbol.replace('.NS', '')}</b> — {company_name}\n"
        f"Action: <b>{action_emoji}</b>\n"
        f"Entry: ₹{entry_price:,.2f} x {quantity} shares\n"
        f"Trade Value: ₹{trade_value:,.0f}\n"
        f"Stop Loss: ₹{stop_loss:,.2f}\n"
        f"Target 1: ₹{target1:,.2f}\n"
        f"Target 2: ₹{target2:,.2f}\n"
        f"\n⚡ <i>Auto-monitoring active (15 sec intervals)</i>"
    )
    send_telegram_message(msg)


def alert_trade_closed(symbol: str, action: str, entry_price: float,
                       exit_price: float, quantity: int,
                       pnl: float, pnl_pct: float, exit_reason: str):
    """Alert when a paper trade is closed (SL/Target/Manual/EOD)."""
    pnl_emoji = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")

    reason_map = {
        "SL_HIT":             "🛑 Stop Loss Hit",
        "T1_HIT":             "🎯 Target 1 Hit!",
        "T2_HIT":             "🎯🎯 Target 2 Hit!",
        "MANUAL":             "✋ Manual Exit",
        "EOD_AUTO_SQUAREOFF": "⏰ EOD 3:25 PM Auto Close",
        "PROFIT_RETREAT_LOCK":"💰 Trailing Profit Lock",
    }
    reason_text = reason_map.get(exit_reason, exit_reason)

    msg = (
        f"<b>{pnl_emoji} Trade Closed!</b>\n"
        f"<i>{_ist_now()}</i>\n"
        f"{'=' * 30}\n"
        f"<b>{symbol.replace('.NS', '')}</b>\n"
        f"Action: {'BUY' if action == 'BUY' else 'SELL'}\n"
        f"Entry: ₹{entry_price:,.2f} → Exit: ₹{exit_price:,.2f}\n"
        f"Qty: {quantity}\n"
        f"P&L: <b>{pnl_emoji} ₹{pnl:+,.2f} ({pnl_pct:+.2f}%)</b>\n"
        f"Reason: {reason_text}"
    )
    send_telegram_message(msg)


# ─────────────────────── EOD DAILY REPORT ───────────────────────

def alert_daily_report(balance: float, starting_capital: float,
                       today_trades: int, today_wins: int,
                       today_losses: int, today_pnl: float):
    """Send end-of-day performance summary to Telegram."""
    pnl_emoji   = "🟢" if today_pnl >= 0 else "🔴"
    total_pnl   = balance - starting_capital
    total_emoji = "📈" if total_pnl >= 0 else "📉"
    win_rate    = round((today_wins / today_trades * 100), 1) if today_trades > 0 else 0

    msg = (
        f"<b>📊 StockSense AI — Day End Report</b>\n"
        f"<i>{_ist_now()}</i>\n"
        f"{'=' * 30}\n"
        f"Today's Trades: {today_trades}\n"
        f"Wins: {today_wins} | Losses: {today_losses}\n"
        f"Win Rate: {win_rate}%\n"
        f"Today P&L: <b>{pnl_emoji} ₹{today_pnl:+,.2f}</b>\n"
        f"{'=' * 30}\n"
        f"Paper Balance: <b>₹{balance:,.2f}</b>\n"
        f"Total P&L: {total_emoji} ₹{total_pnl:+,.2f} ({total_pnl/starting_capital*100:+.2f}%)\n"
        f"\n💤 <i>Market closed. See you tomorrow 9:15 AM!</i>"
    )
    send_telegram_message(msg)


# ─────────────────────── GUARD BLOCK ALERT ───────────────────────

def alert_guard_blocked(symbol: str, guard_name: str, reason: str):
    """Alert when a trade is blocked by a protection guard."""
    msg = (
        f"<b>🛡️ Guard BLOCKED Trade!</b>\n"
        f"<i>{_ist_now()}</i>\n"
        f"{'=' * 30}\n"
        f"Stock: <b>{symbol.replace('.NS', '')}</b>\n"
        f"Guard: {guard_name}\n"
        f"Reason: {reason}\n"
        f"\n💡 <i>Trade rejected to protect your capital.</i>"
    )
    send_telegram_message(msg)
