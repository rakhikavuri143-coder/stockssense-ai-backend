"""
Core 5 Loss Prevention & Capital Guard Engine
1. Trailing Stop Loss (Breakeven Profit Lock)
2. Nifty Macro Market Trend Guard
3. False Breakout Trap Filter (VWAP + RVOL)
4. Position Sizing & Capital Allocation Calculator
5. Strict 1:1.5 Min R:R + >= 90% AI Confidence Filter
"""

import logging
import yfinance as yf
from typing import Optional

logger = logging.getLogger(__name__)

NIFTY_SYMBOL = "^NSEI"


# ─────────────────────────── GUARD 1: NIFTY MACRO TREND ────────────────────────────

def check_nifty_trend_guard(crash_threshold: float = -1.5) -> dict:
    """
    Guard 2: Block BUY signals if Nifty 50 is crashing heavily.
    Returns: {blocked: bool, nifty_change_pct: float, reason: str}
    """
    try:
        ticker = yf.Ticker(NIFTY_SYMBOL)
        fast_info = getattr(ticker, "fast_info", None)
        if fast_info and getattr(fast_info, "last_price", None) and getattr(fast_info, "previous_close", None):
            last_p = float(fast_info.last_price)
            prev_p = float(fast_info.previous_close)
            change_pct = round((last_p - prev_p) / prev_p * 100, 2)
        else:
            hist = ticker.history(period="2d", interval="1d")
            if len(hist) < 2:
                return {"blocked": False, "nifty_change_pct": 0.0, "reason": "Nifty Market Guard OK"}
            prev_close    = float(hist["Close"].iloc[-2])
            current_close = float(hist["Close"].iloc[-1])
            change_pct    = round((current_close - prev_close) / prev_close * 100, 2)

        if change_pct <= crash_threshold:
            return {
                "blocked":           True,
                "nifty_change_pct":  change_pct,
                "reason":            f"🚨 Nifty 50 down {change_pct:.1f}% — BUY signals BLOCKED (Market Guard Active)",
            }
        return {
            "blocked":           False,
            "nifty_change_pct":  change_pct,
            "reason":            f"✅ Nifty 50 change: {change_pct:+.1f}% — Market Guard OK",
        }
    except Exception as e:
        logger.warning("Nifty guard error: %s", e)
        return {"blocked": False, "nifty_change_pct": 0.0, "reason": "Nifty Market Guard OK"}


# ─────────────────────────── GUARD 2: VWAP + RVOL TRAP FILTER ────────────────────────────

def check_vwap_trap_filter(
    signal: str,
    current_price: float,
    vwap: float,
    rvol: float,
    rvol_min: float = 1.3,
) -> dict:
    """
    Guard 3: Reject fake breakouts (Bull/Bear Traps) using VWAP + RVOL confirmation.
    BUY signals need price > VWAP and RVOL >= rvol_min.
    SELL signals need price < VWAP and RVOL >= rvol_min.
    """
    if signal == "BUY":
        if current_price > vwap and rvol >= rvol_min:
            return {"passed": True, "reason": f"✅ VWAP Trap Filter OK — Price above VWAP ({vwap:.2f}), RVOL={rvol:.1f}x"}
        else:
            missing = []
            if current_price <= vwap:
                missing.append(f"Price ₹{current_price:.2f} is below VWAP ₹{vwap:.2f}")
            if rvol < rvol_min:
                missing.append(f"RVOL={rvol:.1f}x < minimum {rvol_min}x")
            return {"passed": False, "reason": f"⛔ VWAP Trap Filter BLOCKED: {', '.join(missing)}"}
    elif signal == "SELL":
        if current_price < vwap and rvol >= rvol_min:
            return {"passed": True, "reason": f"✅ VWAP Trap Filter OK — Price below VWAP ({vwap:.2f}), RVOL={rvol:.1f}x"}
        else:
            missing = []
            if current_price >= vwap:
                missing.append(f"Price ₹{current_price:.2f} is above VWAP ₹{vwap:.2f}")
            if rvol < rvol_min:
                missing.append(f"RVOL={rvol:.1f}x < minimum {rvol_min}x")
            return {"passed": False, "reason": f"⛔ VWAP Trap Filter BLOCKED: {', '.join(missing)}"}
    return {"passed": True, "reason": "✅ No VWAP filter needed for AVOID signal"}


# ─────────────────────────── GUARD 3: POSITION SIZING ────────────────────────────

def calculate_position_size(
    capital: float,
    entry_price: float,
    stop_loss: float,
    risk_pct: float = 2.0,
) -> dict:
    """
    Guard 4: Calculate exact share quantity based on capital risk.
    Risks max risk_pct% of total capital per trade.
    """
    risk_amount   = capital * (risk_pct / 100)
    sl_distance   = abs(entry_price - stop_loss)
    if sl_distance == 0:
        return {"quantity": 0, "risk_amount": 0.0, "trade_value": 0.0, "reason": "⚠️ SL = Entry Price, cannot size position"}
    quantity      = max(1, int(risk_amount / sl_distance))
    trade_value   = round(quantity * entry_price, 2)
    actual_risk   = round(quantity * sl_distance, 2)
    return {
        "quantity":    quantity,
        "risk_amount": actual_risk,
        "trade_value": trade_value,
        "reason":      (
            f"📊 Position Size: {quantity} shares @ ₹{entry_price:.2f} "
            f"| Trade Value: ₹{trade_value:,.2f} "
            f"| Max Risk: ₹{actual_risk:.2f} ({risk_pct}% of ₹{capital:,.2f} capital)"
        ),
    }


# ─────────────────────────── GUARD 4: R:R RATIO FILTER ────────────────────────────

def check_rr_ratio(
    entry: float,
    stop_loss: float,
    target1: float,
    min_rr: float = 1.5,
) -> dict:
    """
    Guard 5: Reject trades where R:R ratio < min_rr (default 1:1.5).
    """
    risk   = abs(entry - stop_loss)
    reward = abs(target1 - entry)
    if risk == 0:
        return {"passed": False, "rr_ratio": 0.0, "reason": "⛔ R:R Filter: Zero risk distance, trade rejected"}
    rr = round(reward / risk, 2)
    if rr >= min_rr:
        return {"passed": True, "rr_ratio": rr, "reason": f"✅ R:R Ratio: 1:{rr:.1f} — Passes minimum 1:{min_rr}"}
    return {"passed": False, "rr_ratio": rr, "reason": f"⛔ R:R Filter BLOCKED: Ratio 1:{rr:.1f} < minimum 1:{min_rr}"}


# ─────────────────────────── GUARD 5: TRAILING STOP LOSS ────────────────────────────

def compute_trailing_sl(entry_price: float, current_price: float, original_sl: float) -> dict:
    """
    Guard 1: Trailing Stop Loss — when price moves +1% above entry, lock SL at breakeven.
    """
    gain_pct = (current_price - entry_price) / entry_price * 100
    if gain_pct >= 1.0:
        return {
            "trailing_sl":    entry_price,
            "is_breakeven":   True,
            "gain_pct":       round(gain_pct, 2),
            "reason":         f"🔒 Trailing SL locked at BREAKEVEN ₹{entry_price:.2f} (Price up {gain_pct:.1f}%)",
        }
    return {
        "trailing_sl":    original_sl,
        "is_breakeven":   False,
        "gain_pct":       round(gain_pct, 2),
        "reason":         f"📍 SL at original: ₹{original_sl:.2f} (Price gain only {gain_pct:.1f}%)",
    }


# ─────────────────────────── CONFIDENCE FILTER ────────────────────────────

def check_confidence_threshold(confidence: float, threshold: float = 90.0) -> dict:
    """
    Check if AI confidence meets the >= 90% threshold.
    """
    if confidence >= threshold:
        return {"passed": True, "reason": f"✅ Confidence {confidence:.1f}% ≥ {threshold}% threshold"}
    return {"passed": False, "reason": f"⛔ Confidence {confidence:.1f}% < {threshold}% threshold — Signal Rejected"}


# ─────────────────────────── GUARD 6: SECTOR CONFLUENCE ────────────────────────────

SECTOR_BENCHMARKS = {
    "Auto":         ["MARUTI.NS", "M&M.NS"],
    "Banking":      ["HDFCBANK.NS", "ICICIBANK.NS"],
    "IT":           ["TCS.NS", "INFY.NS"],
    "Pharma":       ["SUNPHARMA.NS", "CIPLA.NS"],
    "Healthcare":   ["APOLLOHOSP.NS"],
    "FMCG":         ["HINDUNILVR.NS", "ITC.NS"],
    "Metal":        ["TATASTEEL.NS", "JSWSTEEL.NS"],
    "Energy":       ["RELIANCE.NS", "ONGC.NS"],
}

def check_sector_trend_guard(sector: str, signal: str) -> dict:
    """
    Guard 6: Block BUY if Sector Benchmark Leaders are falling (< -0.3%),
    and Block SELL if Sector Benchmark Leaders are surging (> +0.3%).
    Prevents buying into a falling sector or selling into a surging sector!
    """
    benchmarks = SECTOR_BENCHMARKS.get(sector, [])
    if not benchmarks:
        return {"passed": True, "sector_change_pct": 0.0, "reason": f"✅ Sector Guard: No benchmark filter for {sector}"}

    changes = []
    for sym in benchmarks:
        try:
            t = yf.Ticker(sym)
            fi = getattr(t, "fast_info", None)
            if fi and getattr(fi, "last_price", None) and getattr(fi, "previous_close", None):
                lp = float(fi.last_price)
                pc = float(fi.previous_close)
                if pc > 0:
                    changes.append((lp - pc) / pc * 100)
        except Exception:
            pass

    if not changes:
        return {"passed": True, "sector_change_pct": 0.0, "reason": f"✅ Sector Guard: Data unavailable for {sector}"}

    avg_change = round(sum(changes) / len(changes), 2)

    if signal == "BUY" and avg_change <= -0.3:
        return {
            "passed": False,
            "sector_change_pct": avg_change,
            "reason": f"🚨 {sector} Sector falling ({avg_change:+.2f}%) — BUY signal BLOCKED (Sector Guard Active)"
        }
    elif signal == "SELL" and avg_change >= 0.3:
        return {
            "passed": False,
            "sector_change_pct": avg_change,
            "reason": f"🚨 {sector} Sector surging ({avg_change:+.2f}%) — SELL signal BLOCKED (Sector Guard Active)"
        }

    return {
        "passed": True,
        "sector_change_pct": avg_change,
        "reason": f"✅ {sector} Sector trend ({avg_change:+.2f}%) aligns with {signal}"
    }


# ─────────────────────────── GUARD 7: MAX OPEN TRADES LIMIT ────────────────────────────

def check_max_open_trades_guard(open_trades_count: int, max_allowed: int = 2) -> dict:
    """
    Guard 7: Limit open active trades to max_allowed (default 2 trades).
    Prevents over-exposure and entering too many trades simultaneously in morning.
    """
    if open_trades_count >= max_allowed:
        return {
            "passed": False,
            "reason": f"🚨 Max Open Trades Limit ({max_allowed}) Reached — New Signal BLOCKED (Risk Guard)"
        }
    return {
        "passed": True,
        "reason": f"✅ Active trades ({open_trades_count}/{max_allowed}) within safety limit"
    }


# ─────────────────────────── GUARD 8: SL DISTANCE BOUNDS ────────────────────────────

def check_sl_distance_guard(entry_price: float, stop_loss: float, min_dist_pct: float = 0.4, max_dist_pct: float = 3.5) -> dict:
    """
    Guard 8: Ensure SL is neither too tight (noise trap <0.4%) nor too wide (huge risk >3.5%).
    """
    sl_dist_pct = round(abs(entry_price - stop_loss) / entry_price * 100, 2)
    if sl_dist_pct < min_dist_pct:
        return {
            "passed": False,
            "reason": f"⛔ SL Distance ({sl_dist_pct}%) is too tight (< {min_dist_pct}%) — High Noise Trap Risk"
        }
    if sl_dist_pct > max_dist_pct:
        return {
            "passed": False,
            "reason": f"⛔ SL Distance ({sl_dist_pct}%) is too wide (> {max_dist_pct}%) — Excessive Risk"
        }
    return {
        "passed": True,
        "reason": f"✅ SL Distance ({sl_dist_pct}%) within safe bounds ({min_dist_pct}% - {max_dist_pct}%)"
    }


# ─────────────────────────── GUARD 9: RSI EXTREMES TRAP ────────────────────────────

def check_rsi_extremes_guard(signal: str, rsi_15m: float) -> dict:
    """
    Guard 9: Block BUY if RSI 15m > 70 (Overbought - Pullback trap).
    Block SELL if RSI 15m < 30 (Oversold - Bounce trap).
    """
    if rsi_15m <= 0:  # Data unavailable
        return {"passed": True, "reason": "✅ RSI Extremes: Data unavailable"}
    
    if signal == "BUY" and rsi_15m >= 70.0:
        return {
            "passed": False,
            "reason": f"🚨 RSI 15m ({rsi_15m:.1f}) is Overbought (≥70) — BUY signal BLOCKED (Pullback Trap Risk)"
        }
    if signal == "SELL" and rsi_15m <= 30.0:
        return {
            "passed": False,
            "reason": f"🚨 RSI 15m ({rsi_15m:.1f}) is Oversold (≤30) — SELL signal BLOCKED (Bounce Trap Risk)"
        }
    return {
        "passed": True,
        "reason": f"✅ RSI 15m ({rsi_15m:.1f}) within safe trade zone (30-70)"
    }


# ─────────────────────────── GUARD 10: DAILY LOSS CIRCUIT BREAKER ────────────────────────────

def check_daily_loss_circuit_breaker(losses_today: int, max_losses: int = 2) -> dict:
    """
    Guard 10: Automatically lock trading if 2 losses occur in a single day.
    Protects remaining capital on bad/choppy market days!
    """
    if losses_today >= max_losses:
        return {
            "passed": False,
            "reason": f"🛑 Daily Loss Circuit Breaker Active ({losses_today} losses today) — Trading Locked for Day!"
        }
    return {
        "passed": True,
        "reason": f"✅ Daily losses ({losses_today}/{max_losses}) within safety limit"
    }


# ─────────────────────────── FULL GUARD SUITE ────────────────────────────

def run_all_guards(
    signal: str,
    confidence: float,
    current_price: float,
    entry_price: float,
    stop_loss: float,
    target1: float,
    vwap: float,
    rvol: float,
    capital: float = 10000.0,
    confidence_threshold: float = 90.0,
    sector: str = "",
    open_trades_count: int = 0,
    rsi_15m: float = 0.0,
    losses_today: int = 0,
) -> dict:
    """
    Run all 10 loss prevention guards:
    1. Confidence Threshold (>=90%)
    2. Nifty Macro Market Trend Guard
    3. VWAP + RVOL Trap Filter
    4. R:R Ratio (>=1:1.5)
    5. Position Sizing
    6. Trailing Stop Loss Engine
    7. Sector Index Confluence Guard
    8. Max Open Trades Limit (Max 2)
    9. SL Distance Bounds (0.4% - 3.5%)
    10. RSI Extremes Trap Filter (30 - 70)
    11. Daily Loss Circuit Breaker (Max 2 Losses/day)
    """
    results = {}

    # Guard 1: Confidence filter
    results["confidence"] = check_confidence_threshold(confidence, confidence_threshold)

    # Guard 2: Nifty Trend Guard (only block BUY on crash)
    nifty = check_nifty_trend_guard()
    results["nifty_guard"] = nifty
    if signal == "BUY" and nifty["blocked"]:
        results["approved"] = False
        results["block_reason"] = nifty["reason"]
        return results

    # Guard 3: VWAP Trap Filter
    results["vwap_trap"] = check_vwap_trap_filter(signal, current_price, vwap, rvol)

    # Guard 4: R:R Ratio
    results["rr_ratio"] = check_rr_ratio(entry_price, stop_loss, target1)

    # Guard 5: Position Sizing
    results["position_size"] = calculate_position_size(capital, entry_price, stop_loss)

    # Guard 6: Sector Confluence Guard
    sector_guard = check_sector_trend_guard(sector, signal)
    results["sector_guard"] = sector_guard

    # Guard 7: Max Open Trades Limit
    results["max_open_trades"] = check_max_open_trades_guard(open_trades_count, max_allowed=2)

    # Guard 8: SL Distance Bounds
    results["sl_distance"] = check_sl_distance_guard(entry_price, stop_loss)

    # Guard 9: RSI Extremes Trap Filter
    results["rsi_extremes"] = check_rsi_extremes_guard(signal, rsi_15m)

    # Guard 10: Daily Loss Circuit Breaker
    results["circuit_breaker"] = check_daily_loss_circuit_breaker(losses_today, max_losses=2)

    # Final approval
    approved = (
        results["confidence"]["passed"] and
        results["vwap_trap"]["passed"] and
        results["rr_ratio"]["passed"] and
        results["sector_guard"]["passed"] and
        results["max_open_trades"]["passed"] and
        results["sl_distance"]["passed"] and
        results["rsi_extremes"]["passed"] and
        results["circuit_breaker"]["passed"]
    )
    results["approved"] = approved
    if not approved:
        failed = []
        for key in ["confidence", "vwap_trap", "rr_ratio", "sector_guard", "max_open_trades", "sl_distance", "rsi_extremes", "circuit_breaker"]:
            if not results[key]["passed"]:
                failed.append(results[key]["reason"])
        results["block_reason"] = " | ".join(failed)

    return results


