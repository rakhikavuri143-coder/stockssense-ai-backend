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
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_BOT_TOKEN = "8613233140:AAEfeblJ0e5vK9iJe5CWgao_yjiGRsBuvMk"
DEFAULT_CHAT_ID   = "7327907687"

def _get_credentials() -> tuple[str, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN") or DEFAULT_BOT_TOKEN
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or DEFAULT_CHAT_ID
    return token.strip(), chat_id.strip()

BOT_TOKEN, CHAT_ID = _get_credentials()

IST = timezone(timedelta(hours=5, minutes=30))


def _ist_now() -> str:
    return datetime.now(IST).strftime("%I:%M %p IST")


import threading

def _send_telegram_sync(text: str, parse_mode: str = "HTML") -> bool:
    """Internal synchronous sender run inside a background thread."""
    bot_token, chat_id = _get_credentials()
    if not bot_token or not chat_id:
        return False

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id":    chat_id,
            "text":       text,
            "parse_mode": parse_mode,
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req  = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
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


def send_telegram_message(text: str, parse_mode: str = "HTML") -> bool:
    """Send a message via Telegram Bot API asynchronously (0ms blocking, fire-and-forget)."""
    try:
        thread = threading.Thread(target=_send_telegram_sync, args=(text, parse_mode), daemon=True)
        thread.start()
        return True
    except Exception as e:
        logger.error("Failed to spawn Telegram alert thread: %s", e)
        return False


# ─────────────────────── SIGNAL ALERTS ───────────────────────

def alert_scan_signals(signals: list):
    """Send Telegram alert for Top 3 Nifty 50 + Top 3 Budget Stock BUY/SELL signals."""
    if not signals:
        return

    from backend.indian_stocks import BUDGET_LOW_PRICED_STOCKS
    budget_symbols = set(s["symbol"] for s in BUDGET_LOW_PRICED_STOCKS)

    buy_sell = [s for s in signals if s.get("signal") in ("BUY", "SELL") and s.get("confidence", 0) >= 80]
    if not buy_sell:
        return

    nifty_signals  = [s for s in buy_sell if s.get("symbol") not in budget_symbols][:3]
    budget_signals = [s for s in buy_sell if s.get("symbol") in budget_symbols][:3]

    header = f"<b>📊 StockSense AI — Signal Alert</b>\n<i>{_ist_now()}</i>\n{'=' * 30}\n"
    cards = []

    if nifty_signals:
        cards.append("<b>🏆 TOP 3 NIFTY 50 SIGNALS:</b>")
        for idx, s in enumerate(nifty_signals, 1):
            signal_emoji = "🟢 BUY" if s["signal"] == "BUY" else "🔴 SELL"
            approved_tag = "✅ APPROVED" if s.get("approved") else "⚠️ REVIEW"
            card = (
                f"<b>#{idx} {s['symbol'].replace('.NS', '')}</b> — {s.get('company_name', '')}\n"
                f"Signal: <b>{signal_emoji}</b> | Confidence: <b>{s.get('confidence', 0):.1f}%</b>\n"
                f"Guard: {approved_tag}\n"
                f"Price: ₹{s.get('current_price', 0):,.2f} | SL: ₹{s.get('stop_loss', 0):,.2f} | T1: ₹{s.get('target1', 0):,.2f}"
            )
            cards.append(card)

    if budget_signals:
        if nifty_signals:
            cards.append("\n" + "=" * 30)
        cards.append("<b>⚡ TOP 3 BUDGET STOCK SIGNALS (Under ₹200):</b>")
        for idx, s in enumerate(budget_signals, 1):
            signal_emoji = "🟢 BUY" if s["signal"] == "BUY" else "🔴 SELL"
            approved_tag = "✅ APPROVED" if s.get("approved") else "⚠️ REVIEW"
            card = (
                f"<b>#{idx} {s['symbol'].replace('.NS', '')}</b> — {s.get('company_name', '')}\n"
                f"Signal: <b>{signal_emoji}</b> | Confidence: <b>{s.get('confidence', 0):.1f}%</b>\n"
                f"Guard: {approved_tag}\n"
                f"Price: ₹{s.get('current_price', 0):,.2f} | SL: ₹{s.get('stop_loss', 0):,.2f} | T1: ₹{s.get('target1', 0):,.2f}"
            )
            cards.append(card)

    msg = header + "\n\n".join(cards)
    msg += f"\n\n💡 <i>Open StockSense AI dashboard to trade.</i>"

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
        "T1_HIT":             "🎯 ₹150 Profit Target Hit!",
        "T2_HIT":             "🎯🎯 Target 2 Hit!",
        "MANUAL":             "✋ Manual Exit",
        "EOD_AUTO_SQUAREOFF": "⏰ EOD 3:10 PM Auto Close",

        "PROFIT_RETREAT_LOCK":"💰 Trailing Profit Lock",
        "CIRCUIT_EMERGENCY_EXIT": "🚨 Circuit Emergency Exit (Guard #17)",
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


# ─────────────────────── PROFIT TARGET HIT ALERT ───────────────────────

def alert_profit_target_approaching(symbol: str, action: str, entry_price: float,
                                     current_price: float, quantity: int,
                                     current_pnl: float, threshold: float):
    """Alert BEFORE trade is closed when flat profit target (₹600) is reached.
    This fires BEFORE close_paper_position so user sees the notification first."""
    pnl_emoji = "🟢" if current_pnl > 0 else "🔴"

    msg = (
        f"<b>🎯💰 PROFIT TARGET HIT!</b>\n"
        f"<i>{_ist_now()}</i>\n"
        f"{'=' * 30}\n"
        f"<b>{symbol.replace('.NS', '')}</b>\n"
        f"Action: {'🟢 BUY' if action == 'BUY' else '🔴 SELL'}\n"
        f"Entry: ₹{entry_price:,.2f} → Current: ₹{current_price:,.2f}\n"
        f"Qty: {quantity}\n"
        f"<b>{pnl_emoji} Profit: ₹{current_pnl:+,.2f}</b>\n"
        f"Target: ₹{threshold:,.0f} ✅ REACHED!\n"
        f"{'=' * 30}\n"
        f"⚡ <i>Auto-closing trade now...</i>"
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


# ─────────────────────── WEEKLY QUANT AUDIT REPORT ───────────────────────

def alert_weekly_audit(report: dict):
    """Send Saturday Weekly Quant Audit Card to Telegram."""
    pnl_emoji = "🟢" if report.get("net_pnl", 0) >= 0 else "🔴"
    reasons = report.get("reasons", [])
    clean_reasons = [r.replace("<", "&lt;").replace(">", "&gt;") for r in reasons]
    reasons_str = "\n".join([f"• {r}" for r in clean_reasons]) if clean_reasons else "• Baseline parameters maintained."

    msg = (
        f"<b>📊 StocksSense AI — Weekly Quant Audit Card</b>\n"
        f"<i>{report.get('timestamp', _ist_now())}</i>\n"
        f"🗓️ <b>Period:</b> {report.get('period', 'Past 7 Days')}\n"
        f"{'=' * 32}\n"
        f"📈 <b>Total Trades:</b> {report.get('total_trades', 0)}\n"
        f"🟢 <b>Wins:</b> {report.get('wins', 0)} | 🔴 <b>Losses:</b> {report.get('losses', 0)}\n"
        f"🎯 <b>Win Rate:</b> {report.get('win_rate', 0.0)}%\n"
        f"💰 <b>Weekly Net P&L:</b> <b>{pnl_emoji} ₹{report.get('net_pnl', 0.0):+,.2f}</b>\n"
        f"{'=' * 32}\n"
        f"⚙️ <b>Auto-Tuning Parameter Adjustments:</b>\n"
        f"• <b>Confidence Gate:</b> {report.get('old_confidence')}% → <b>{report.get('new_confidence')}%</b>\n"
        f"• <b>ATR SL Multiplier:</b> {report.get('old_atr_mult')}x → <b>{report.get('new_atr_mult')}x</b>\n"
        f"\n<b>💡 AI Quant Audit Notes:</b>\n"
        f"{reasons_str}\n"
        f"\n🚀 <i>System auto-tuned & ready for Monday Market Open!</i>"
    )
    send_telegram_message(msg)

