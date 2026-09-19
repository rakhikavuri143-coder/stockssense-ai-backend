"""
4-Week Paper Trading Simulator
Tracks virtual trades, portfolio balance, P&L, Target/SL exits dynamically with DB persistence.
"""

# ═══════════════════════════════════════════════════════════
# TARGET 1 PROFIT THRESHOLD (₹ Flat Profit, NOT Price-Based)
# When ANY trade reaches this profit, T1 is triggered.
# ═══════════════════════════════════════════════════════════
T1_PROFIT_THRESHOLD = 150.0  # ₹150 flat profit per trade (3 trades × ₹150 = ₹450/day)

import os
import time
import logging
from datetime import datetime, date
from typing import Optional
from sqlalchemy.orm import Session
from backend.database import PaperTrade, save_paper_trade, get_open_paper_trades

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# GUARD 17: CIRCUIT AND LIQUIDITY GUARD
# ═══════════════════════════════════════════════════════════
def circuit_and_liquidity_guard(market_depth, ltp, lower_circuit):
    """
    Evaluates Circuit Proximity & Order Book Liquidity
    Returns: 'ALLOW', 'EMERGENCY_EXIT', or 'BLOCK_ENTRY'
    """
    # 1. Calculate distance from Lower Circuit
    circuit_distance_pct = ((ltp - lower_circuit) / ltp) * 100
    
    # 2. Extract Top 5 Order Book Totals
    total_buyers_qty = sum([bid['quantity'] for bid in market_depth.get('bids', [])])
    total_sellers_qty = sum([ask['quantity'] for ask in market_depth.get('asks', [])])
    
    # Pre-Entry Filter: Too close to circuit
    if circuit_distance_pct < 3.5:
        return "BLOCK_ENTRY"  # Too risky to trade
    
    # Live Trade Surveillance: Buyers collapsing near lower circuit
    if total_buyers_qty > 0 and (total_sellers_qty / total_buyers_qty) > 5.0 and circuit_distance_pct < 1.2:
        return "EMERGENCY_EXIT"  # Dump position before 0 buyers freeze
        
    return "SAFE"


_circuit_cache = {}

def get_circuit_and_depth_simulator(symbol: str, ltp: float) -> tuple[dict, float]:
    """
    Constructs simulated market depth to support Guard #17 in the paper trading environment.
    Runs instantly (0ms) using a 10% lower circuit limit to ensure fast order execution.
    """
    global _circuit_cache
    if symbol in _circuit_cache:
        lower_circuit = _circuit_cache[symbol]
    else:
        lower_circuit = round(ltp * 0.90, 2)
        _circuit_cache[symbol] = lower_circuit

    # Proximity calculation
    circuit_distance_pct = ((ltp - lower_circuit) / ltp) * 100 if ltp > 0 else 10.0
    
    # Simulate Order Book (Market Depth) based on proximity
    if circuit_distance_pct < 1.2:
        bids = [{"price": lower_circuit, "quantity": 100}]
        asks = [{"price": ltp, "quantity": 600}]
    else:
        bids = [{"price": round(ltp * 0.99, 2), "quantity": 800}]
        asks = [{"price": round(ltp * 1.01, 2), "quantity": 400}]
        
    market_depth = {"bids": bids, "asks": asks}
    return market_depth, lower_circuit


logger = logging.getLogger(__name__)

# Starting capital
_paper_capital = float(os.getenv("PAPER_CAPITAL", "300000"))


def sync_state(db: Session) -> tuple[float, dict]:
    """
    Synchronizes in-memory paper balance and open positions directly from DB.
    Ensures 100% data persistence across server reloads and restarts.
    """
    global _paper_capital

    # 1. Load open positions from DB
    open_trades = db.query(PaperTrade).filter(PaperTrade.status == "OPEN").all()
    open_positions = {}
    for t in open_trades:
        open_positions[t.symbol] = {
            "id":           t.id,
            "symbol":       t.symbol,
            "company_name": t.company_name,
            "action":       t.action,
            "entry_price":  t.entry_price,
            "quantity":     t.quantity,
            "stop_loss":    t.stop_loss,
            "target1":      t.target1,
            "target2":      t.target2,
            "status":       "OPEN",
            "opened_at":    str(t.opened_at),
        }

    # 2. Calculate balance from starting capital + sum of all closed P&Ls
    closed_trades = db.query(PaperTrade).filter(PaperTrade.status != "OPEN").all()
    total_closed_pnl = sum(t.pnl for t in closed_trades if t.pnl is not None)

    # 3. Account for open trade reserved value
    current_balance = round(_paper_capital + total_closed_pnl, 2)
    return current_balance, open_positions


def get_paper_balance(db: Session) -> float:
    balance, _ = sync_state(db)
    return balance


def get_open_positions(db: Session) -> dict:
    _, positions = sync_state(db)
    return positions


def reset_paper_account(db: Session):
    """Reset all paper trades in DB and restore starting capital."""
    db.query(PaperTrade).delete()
    db.commit()
    logger.info("Paper account reset to ₹%.2f", _paper_capital)


def is_market_open_for_trading() -> tuple[bool, str]:
    """Check if Indian Stock Market (NSE) is currently open for new trade entries (09:15 AM to 03:00 PM IST, Mon-Fri)."""
    if os.getenv("ALLOW_OFFMARKET_PAPER_TRADING", "false").lower() == "true":
        return True, "Off-market paper trading override enabled"

    from datetime import datetime, timezone, timedelta, time
    ist_offset = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist_offset)

    if now_ist.weekday() >= 5:
        return False, "Market is closed on weekends! Trading hours are Monday-Friday, 9:15 AM - 3:30 PM IST."

    t = now_ist.time()
    if t < time(9, 15) or t > time(15, 0):
        return False, f"🚫 New intraday trade entries are blocked after 3:00 PM IST! (Current time: {t.strftime('%H:%M:%S')} IST). Market enters EOD square-off mode."

    return True, "Market is OPEN"


def place_paper_order(
    db: Session,
    symbol: str,
    company_name: str,
    action: str,            # "BUY" or "SELL"
    entry_price: float,
    quantity: int,
    stop_loss: float,
    target1: float,
    target2: float,
    signal_id: Optional[int] = None,
) -> dict:
    """
    Place a virtual paper trade and store in DB.
    """
    # 0. Market Hours Guard (9:15 AM - 3:30 PM IST)
    market_open, market_msg = is_market_open_for_trading()
    if not market_open:
        return {
            "success": False,
            "message": f"🚫 Trade Rejected: {market_msg}"
        }

    balance, open_positions = sync_state(db)

    # 0.5. Guard #17: Circuit Proximity Pre-Entry Filter
    try:
        m_depth, low_circuit = get_circuit_and_depth_simulator(symbol, entry_price)
        guard_status = circuit_and_liquidity_guard(m_depth, entry_price, low_circuit)
        if guard_status == "BLOCK_ENTRY":
            return {
                "success": False,
                "message": f"🛡️ Circuit Proximity Guard Active: Stock is too close to its lower circuit limit. Blocked trade entry to prevent trading lockup."
            }
    except Exception as ge:
        logger.warning("Circuit proximity check failed for %s: %s", symbol, ge)


    sym_base = symbol.upper().replace(".NS", "").replace(".BO", "").replace("-EQ", "").replace("-BE", "").strip()
    sym_ns   = f"{sym_base}.NS"
    sym_bo   = f"{sym_base}.BO"
    sym_eq   = f"{sym_base}-EQ"
    sym_be   = f"{sym_base}-BE"
    if any(s in open_positions for s in (symbol, sym_base, sym_ns, sym_bo, sym_eq, sym_be)):
        return {"success": False, "message": f"Already have an open paper position in {sym_base}"}

    # 1. Daily Drawdown Circuit Breaker (-1.5% Max Daily Capital Loss Protection)
    today_trades = db.query(PaperTrade).filter(PaperTrade.trade_date == date.today()).all()

    # 1.1 Category-wise Overtrading Guard (Max 3 Nifty 50 + Max 3 Budget Trades)
    from backend.indian_stocks import BUDGET_LOW_PRICED_STOCKS
    budget_symbols = set(s["symbol"] for s in BUDGET_LOW_PRICED_STOCKS)

    budget_today = [t for t in today_trades if t.symbol in budget_symbols]
    nifty_today  = [t for t in today_trades if t.symbol not in budget_symbols]

    is_budget_trade = symbol in budget_symbols

    if is_budget_trade and len(budget_today) >= 3:
        return {
            "success": False,
            "message": f"🛡️ Overtrading Guard Active: Reached daily limit of 3 Budget Stock trades (Today: {len(budget_today)} budget trades). Paused to enforce discipline."
        }

    if not is_budget_trade and len(nifty_today) >= 3:
        return {
            "success": False,
            "message": f"🛡️ Overtrading Guard Active: Reached daily limit of 3 Nifty 50 trades (Today: {len(nifty_today)} nifty trades). Paused to enforce discipline."
        }

    today_closed_pnl = sum(t.pnl for t in today_trades if t.pnl is not None and t.status != "OPEN")
    max_daily_loss = -(_paper_capital * 0.015)  # -₹4,500 max daily loss
    if today_closed_pnl <= max_daily_loss:
        return {
            "success": False,
            "message": f"🛡️ Daily Drawdown Guard Active: Today's P&L (₹{today_closed_pnl:,.2f}) hit max limit (-₹{abs(max_daily_loss):,.2f}). Trading paused to preserve capital."
        }

    # 1.5. Target & SL Direction Enforcer
    if action == "SELL":
        if target1 >= entry_price or target2 >= entry_price:
            target1 = round(entry_price - (abs(entry_price - stop_loss) * 1.8), 2)
            target2 = round(entry_price - (abs(entry_price - stop_loss) * 3.0), 2)
            logger.info("🔧 Auto-corrected SELL targets for %s: T1=₹%.2f, T2=₹%.2f", symbol, target1, target2)
        if stop_loss <= entry_price:
            stop_loss = round(entry_price * 1.01, 2)
    elif action == "BUY":
        if target1 <= entry_price or target2 <= entry_price:
            target1 = round(entry_price + (abs(entry_price - stop_loss) * 1.8), 2)
            target2 = round(entry_price + (abs(entry_price - stop_loss) * 3.0), 2)
            logger.info("🔧 Auto-corrected BUY targets for %s: T1=₹%.2f, T2=₹%.2f", symbol, target1, target2)
        if stop_loss >= entry_price:
            stop_loss = round(entry_price * 0.99, 2)

    trade_value = round(entry_price * quantity, 2)

    # Risk Control: Cap single trade allocation to max ₹1,00,000 (₹1 Lakh per trade limit)
    max_trade_alloc = min(balance, 100000.0)
    max_affordable_qty = max(1, int(max_trade_alloc / entry_price)) if entry_price > 0 else quantity
    if quantity > max_affordable_qty:
        quantity    = max_affordable_qty
        trade_value = round(entry_price * quantity, 2)
        logger.info("Qty risk-capped to %d (max 15%% capital allocation at ₹%.2f)", quantity, max_trade_alloc)

    # 🛡️ Hard ₹300 Loss Cap Enforcement (Strictly lock SL price to exact ₹300 loss boundary for any quantity)
    if quantity > 0:
        max_price_move = 300.0 / quantity
        if action == "BUY":
            stop_loss = round(entry_price - max_price_move, 2)
        elif action == "SELL":
            stop_loss = round(entry_price + max_price_move, 2)
        logger.info("🛡️ Strictly locked SL for %s to ₹%.2f (Qty: %d -> Exact ₹300.00 Max Loss)", symbol, stop_loss, quantity)

    if trade_value > balance:
        return {
            "success": False,
            "message": f"Insufficient paper balance. Need ₹{trade_value:,.2f}, have ₹{balance:,.2f}"
        }

    trade_data = {
        "signal_id":    signal_id,
        "symbol":       symbol,
        "company_name": company_name,
        "action":       action,
        "entry_price":  entry_price,
        "quantity":     quantity,
        "stop_loss":    stop_loss,
        "target1":      target1,
        "target2":      target2,
        "status":       "OPEN",
        "pnl":          0.0,
        "pnl_percent":  0.0,
        "trade_date":   date.today(),
    }

    db_trade = save_paper_trade(db, trade_data)

    new_balance, new_positions = sync_state(db)

    logger.info(
        "📝 Paper %s %d x %s @ ₹%.2f (SL: ₹%.2f | T1: ₹%.2f | T2: ₹%.2f)",
        action, quantity, symbol, entry_price, stop_loss, target1, target2
    )

    # Send Telegram Alert
    try:
        from backend.telegram_alerts import alert_trade_opened
        alert_trade_opened(symbol, company_name, action, entry_price, quantity, stop_loss, target1, target2)
    except Exception as e:
        logger.warning("Telegram trade open alert failed: %s", e)

    return {
        "success":     True,
        "message":     f"Paper {action} order placed: {quantity} x {symbol} @ ₹{entry_price:.2f}",
        "trade_id":    db_trade.id,
        "trade_value": trade_value,
        "balance":     new_balance,
    }


def close_paper_position(
    db: Session,
    symbol: str,
    exit_price: float,
    exit_reason: str = "MANUAL",   # "MANUAL" | "T1_HIT" | "T2_HIT" | "SL_HIT"
) -> dict:
    """
    Close an open paper position at exit_price and save P&L into DB.
    """
    # Flexible symbol matching (supports ONGC, ONGC.NS, ONGC-EQ, ONGC.BO, etc.)
    sym_base = symbol.upper().replace(".NS", "").replace(".BO", "").replace("-EQ", "").replace("-BE", "").strip()
    sym_variants = list(set([
        symbol, symbol.upper(), symbol.lower(),
        sym_base, sym_base.upper(),
        f"{sym_base}.NS", f"{sym_base}.BO", f"{sym_base}-EQ", f"{sym_base}-BE"
    ]))
    trade = db.query(PaperTrade).filter(
        PaperTrade.status == "OPEN",
        PaperTrade.symbol.in_(sym_variants)
    ).first()

    if not trade:
        # Fallback search if exact variant matching misses due to unusual formatting
        trade = db.query(PaperTrade).filter(
            PaperTrade.status == "OPEN",
            PaperTrade.symbol.like(f"%{sym_base}%")
        ).first()

    if not trade:
        return {"success": False, "message": f"No open paper position found for {symbol}"}

    entry_price = trade.entry_price
    quantity    = trade.quantity
    action      = trade.action

    if action == "BUY":
        pnl = round((exit_price - entry_price) * quantity, 2)
    else:
        pnl = round((entry_price - exit_price) * quantity, 2)

    # pnl_percent = % price move, not % of position size
    # e.g. entry 1580 → exit 1555 = -1.58% (as the stock moved)
    if entry_price > 0:
        if action == "BUY":
            pnl_pct = round(((exit_price - entry_price) / entry_price) * 100, 2)
        else:
            pnl_pct = round(((entry_price - exit_price) / entry_price) * 100, 2)
    else:
        pnl_pct = 0.0

    # 🛡️ Hard ₹300 Loss Cap Guard: Ensure no loss EVER exceeds -₹300.00
    if pnl < -300.0:
        pnl = -300.0
        exit_reason = "HARD_SL_BREAKER"
        if action == "BUY":
            exit_price = round(entry_price - (300.0 / quantity), 2)
            pnl_pct = round(((exit_price - entry_price) / entry_price) * 100, 2) if entry_price > 0 else 0.0
        else:
            exit_price = round(entry_price + (300.0 / quantity), 2)
            pnl_pct = round(((entry_price - exit_price) / entry_price) * 100, 2) if entry_price > 0 else 0.0
    elif pnl <= -295.0 and exit_reason in ("MANUAL", "SL_HIT"):
        exit_reason = "HARD_SL_BREAKER"

    # Save to DB
    trade.exit_price  = exit_price
    trade.pnl         = pnl
    trade.pnl_percent = pnl_pct
    trade.status      = exit_reason
    trade.closed_at   = datetime.utcnow()
    db.commit()
    
    # Clean up internal trade notification & peak caches
    _t1_notified_trades.discard(trade.id)
    _peak_prices.pop(trade.id, None)
    _peak_pnl.pop(trade.id, None)
    _paper_reversal_notified.discard(trade.id)
    _paper_last_reversal_check_ts.pop(trade.id, None)

    new_balance, _ = sync_state(db)

    emoji = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")
    logger.info(
        "%s Paper trade CLOSED: %s @ ₹%.2f | P&L: ₹%.2f (%.2f%%) | Reason: %s",
        emoji, symbol, exit_price, pnl, pnl_pct, exit_reason
    )

    # Send Telegram Alert
    try:
        from backend.telegram_alerts import alert_trade_closed
        alert_trade_closed(symbol, action, entry_price, exit_price, quantity, pnl, pnl_pct, exit_reason)
    except Exception as e:
        logger.warning("Telegram trade close alert failed: %s", e)

    return {
        "success":     True,
        "symbol":      symbol,
        "exit_price":  exit_price,
        "pnl":         pnl,
        "pnl_percent": pnl_pct,
        "exit_reason": exit_reason,
        "balance":     new_balance,
    }


_peak_prices: dict[int, float] = {}
_peak_pnl:    dict[int, float] = {}   # Tracks peak P&L (₹) per trade for Nifty trailing stop
_t1_notified_trades: set[int] = set() # Track trade IDs that sent Telegram T1 alert
_paper_reversal_notified: set[int] = set()
_paper_last_reversal_check_ts: dict[int, float] = {}

def check_auto_exits(db: Session, live_prices: dict[str, float]):
    """
    Auto-check open positions against live prices.
    Triggers Target 1, Target 2, Stop Loss exits, EOD 3:25 PM Auto-Squareoff, or Trailing Peak Profit Lock automatically.
    """
    global _peak_prices, _peak_pnl, _t1_notified_trades, _paper_reversal_notified, _paper_last_reversal_check_ts
    _, open_positions = sync_state(db)
    results = []
    from datetime import timezone, timedelta
    from backend.indian_stocks import NIFTY50_STOCKS, BUDGET_LOW_PRICED_STOCKS
    nifty50_symbols = set(s["symbol"] for s in NIFTY50_STOCKS)
    budget_symbols  = set(s["symbol"] for s in BUDGET_LOW_PRICED_STOCKS)
    ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    current_time_str = ist_now.strftime("%H:%M")
    is_eod_squareoff_time = "15:10" <= current_time_str <= "15:35"



    for symbol, pos in list(open_positions.items()):
        price = live_prices.get(symbol)
        if price is None:
            continue
        action = pos["action"]
        trade_id = pos["id"]

        # ⏱️ 1-Hour Scalp Timeout Check
        if pos.get("company_name") and "(Scalp)" in pos["company_name"]:
            opened_at_str = pos.get("opened_at")
            if opened_at_str:
                opened_at = None
                try:
                    opened_at = datetime.strptime(opened_at_str, "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    try:
                        opened_at = datetime.strptime(opened_at_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        pass
                if opened_at:
                    age_seconds = (datetime.utcnow() - opened_at).total_seconds()
                    if age_seconds >= 3600:  # 1 hour
                        res = close_paper_position(db, symbol, price, exit_reason="SCALP_TIMEOUT")
                        results.append(res)
                        _peak_prices.pop(trade_id, None)
                        _peak_pnl.pop(trade_id, None)
                        logger.info("⏱️ Scalp 1-Hour Timeout reached for %s. Closed position.", symbol)
                        continue

        # EOD Auto-Squareoff at 3:10 PM IST
        if is_eod_squareoff_time:

            res = close_paper_position(db, symbol, price, exit_reason="EOD_SQUAREOFF")
            results.append(res)
            _peak_prices.pop(trade_id, None)
            continue

        # 🛡️ Guard #17: Circuit Emergency Exit Surveillance Check
        try:
            m_depth, low_circuit = get_circuit_and_depth_simulator(symbol, price)
            guard_status = circuit_and_liquidity_guard(m_depth, price, low_circuit)
            if guard_status == "EMERGENCY_EXIT":
                res = close_paper_position(db, symbol, price, exit_reason="CIRCUIT_EXIT")
                results.append(res)
                _peak_prices.pop(trade_id, None)
                _peak_pnl.pop(trade_id, None)
                logger.info("🚨 Guard #17 Active: Circuit Emergency Exit triggered for %s. Buyers collapsed near circuit freeze.", symbol)
                continue
        except Exception as ge:
            logger.warning("Circuit emergency monitoring failed for %s: %s", symbol, ge)

        # 🚨 Hard Rupee SL Circuit Breaker (Max ₹300 Loss Cap per trade)
        qty = pos.get("quantity", 1)
        entry_p = pos.get("entry_price", price)
        sl_p = pos.get("stop_loss", 0.0)
        current_pnl = (price - entry_p) * qty if action == "BUY" else (entry_p - price) * qty
        is_sl_breached = (action == "BUY" and price <= sl_p) or (action == "SELL" and price >= sl_p) if sl_p > 0 else False
        if current_pnl <= -290.0 or is_sl_breached:
            res = close_paper_position(db, symbol, price, exit_reason="HARD_SL_BREAKER" if current_pnl <= -290.0 else "SL_HIT")
            results.append(res)
            _peak_prices.pop(trade_id, None)
            _peak_pnl.pop(trade_id, None)
            logger.info("🚨 Hard SL / Loss Breaker triggered for %s (PnL: ₹%.2f, CMP: ₹%.2f, SL: ₹%.2f). Auto-closed immediately.", symbol, current_pnl, price, sl_p)
            continue


        if action == "BUY":
            entry_p = pos["entry_price"]
            t1_p    = pos["target1"]

            # Update Peak Price
            peak = _peak_prices.get(trade_id, price)
            if price > peak:
                peak = price
                _peak_prices[trade_id] = peak

            # Current P&L
            current_pnl_buy = round((price - entry_p) * pos["quantity"], 2)

            # ══ NIFTY 50 FLAT LOSS GUARD ══════════════════════════════════
            if symbol in nifty50_symbols:
                trade_value = entry_p * pos["quantity"]
                if trade_value <= 10500.0:  # Only for trades ~₹10k or below
                    if current_pnl_buy <= -100.0:
                        res = close_paper_position(db, symbol, price, exit_reason="SL_HIT")
                        results.append(res)
                        _peak_prices.pop(trade_id, None)
                        _peak_pnl.pop(trade_id, None)
                        logger.info("❌ Nifty Max Loss Hit (-₹100) for %s! P&L: ₹%.2f (Trade Value: ₹%.2f)", symbol, current_pnl_buy, trade_value)
                        continue

            # ══ FILTER 2: DYNAMIC 20% TRAILING PEAK PROFIT LOCK (Noise Protected) ══
            # Rule: "Green trade ni eppatiki Red avvanivvakoodadhu!"
            # Peak ₹150 -> 20% pullback (₹30) -> Locks +₹120
            # Peak ₹300 -> 20% pullback (₹60) -> Locks +₹240
            # Peak ₹500 -> 20% pullback (₹100) -> Locks +₹400
            peak_pnl_val = _peak_pnl.get(trade_id, 0.0)
            if current_pnl_buy > peak_pnl_val:
                _peak_pnl[trade_id] = current_pnl_buy
                peak_pnl_val = current_pnl_buy

            price_drop = peak - price
            pullback_allowed = max(30.0, peak_pnl_val * 0.20)
            min_price_buffer = max(0.20, entry_p * 0.002)

            if peak_pnl_val >= 120.0 and (peak_pnl_val - current_pnl_buy) >= pullback_allowed and current_pnl_buy > 0 and price_drop >= min_price_buffer:
                res = close_paper_position(db, symbol, price, exit_reason="DYNAMIC_PROFIT_LOCK")
                results.append(res)
                _peak_prices.pop(trade_id, None)
                _peak_pnl.pop(trade_id, None)
                _paper_reversal_notified.discard(trade_id)
                _paper_last_reversal_check_ts.pop(trade_id, None)
                logger.info("💰 Dynamic 20% Peak Profit Lock: %s Peaked at +₹%.2f, Dropped to +₹%.2f (Locked +₹%.2f)", symbol, peak_pnl_val, current_pnl_buy, current_pnl_buy)
                continue

            # ══ FILTER 3: 5-MINUTE TECHNICAL REVERSAL DETECTOR (Telegram Alert Only) ══
            # Does NOT close trade. Checks 5m candle & RSI every 45s, alerts user if momentum fades.
            now_ts = time.time()
            last_check = _paper_last_reversal_check_ts.get(trade_id, 0.0)
            if trade_id not in _paper_reversal_notified and (now_ts - last_check >= 45.0):
                _paper_last_reversal_check_ts[trade_id] = now_ts
                try:
                    from backend.loss_guard import check_5m_momentum_reversal
                    from backend.telegram_alerts import alert_momentum_reversal
                    rev_info = check_5m_momentum_reversal(symbol, action)
                    if rev_info.get("reversal_detected"):
                        _paper_reversal_notified.add(trade_id)
                        logger.info("⚠️ [FILTER 3 PAPER ALERT] Momentum reversal for %s: %s", symbol, rev_info.get("details"))
                        alert_momentum_reversal(symbol, action, price, current_pnl_buy, peak_pnl_val, rev_info.get("details", ""))
                except Exception as _re:
                    logger.warning("Paper 5m reversal check failed for %s: %s", symbol, _re)

            # ══ BUDGET STOCKS SPECIAL RULES ═══════════════════════════════
            if symbol in budget_symbols:
                # Track peak P&L (₹) for this trade
                peak_pnl = _peak_pnl.get(trade_id, 0.0)
                if current_pnl_buy > peak_pnl:
                    _peak_pnl[trade_id] = current_pnl_buy
                    peak_pnl = current_pnl_buy

                # Trailing P&L stop: if peak reached >= ₹20 and dropped by ₹20 → close to lock profit
                if peak_pnl >= 20.0 and (peak_pnl - current_pnl_buy) >= 20.0:
                    res = close_paper_position(db, symbol, price, exit_reason="PROFIT_RETREAT_LOCK")
                    results.append(res)
                    _peak_prices.pop(trade_id, None)
                    _peak_pnl.pop(trade_id, None)
                    logger.info("🔒 Budget Trailing Stop: %s Peak=₹%.0f Now=₹%.0f → Locked!", symbol, peak_pnl, current_pnl_buy)
                    continue

            # ══ STANDARD TARGETS & TRAILING LOGIC ════════════════════════
            t1_threshold = 80.0 if symbol in budget_symbols else 600.0
            max_gain  = t1_p - entry_p
            peak_gain = peak - entry_p

            # 1. Trailing Peak Profit Lock (price-based) - Non-budget stocks only
            if symbol not in budget_symbols and max_gain > 0 and peak_gain >= (max_gain * 0.5):
                retreat_trigger = peak - (peak_gain * 0.25)
                if price <= retreat_trigger:
                    res = close_paper_position(db, symbol, price, exit_reason="PROFIT_RETREAT_LOCK")
                    results.append(res)
                    _peak_prices.pop(trade_id, None)
                    _peak_pnl.pop(trade_id, None)
                    logger.info("💰 Trailing Profit Lock for %s @ ₹%.2f", symbol, price)
                    continue

            # 2. Trail SL to Break-Even once 35% of T1 reached
            trigger_progress = entry_p + (max_gain * 0.35) if max_gain > 0 else entry_p
            if price >= trigger_progress and pos["stop_loss"] < entry_p:
                pos["stop_loss"] = entry_p
                t_obj = db.query(PaperTrade).filter(PaperTrade.id == trade_id).first()
                if t_obj:
                    t_obj.stop_loss = entry_p
                    db.commit()
                logger.info("🛡️ Trailing SL → Break-Even for %s (₹%.2f)", symbol, entry_p)

            if price >= pos["target2"]:
                res = close_paper_position(db, symbol, price, exit_reason="T2_HIT")
                results.append(res)
                _peak_prices.pop(trade_id, None)
                _peak_pnl.pop(trade_id, None)
            elif price >= pos["target1"] or current_pnl_buy >= t1_threshold:
                # Notify Telegram ONCE per trade when T1 is reached (persisted via _t1_notified_trades set)
                if trade_id not in _t1_notified_trades:
                    _t1_notified_trades.add(trade_id)
                    try:
                        from backend.telegram_alerts import alert_profit_target_approaching
                        alert_profit_target_approaching(symbol, pos["action"], entry_p, price, pos["quantity"], current_pnl_buy, t1_threshold)
                    except Exception as e:
                        logger.warning("Telegram T1 alert failed: %s", e)
                    logger.info("🎯 T1 Target Reached for %s (+₹%.2f P&L). Position kept open to trail for T2/Big Gains!", symbol, current_pnl_buy)
            elif price <= pos["stop_loss"]:
                res = close_paper_position(db, symbol, price, exit_reason="SL_HIT")
                results.append(res)
                _peak_prices.pop(trade_id, None)
                _peak_pnl.pop(trade_id, None)

        elif action == "SELL":
            entry_p = pos["entry_price"]
            t1_p    = pos["target1"]

            # Update Peak Price (lower is better for SELL)
            peak = _peak_prices.get(trade_id, price)
            if price < peak:
                peak = price
                _peak_prices[trade_id] = peak

            # Current P&L for SELL
            current_pnl_sell = round((entry_p - price) * pos["quantity"], 2)

            # ══ NIFTY 50 FLAT LOSS GUARD ══════════════════════════════════
            if symbol in nifty50_symbols:
                trade_value = entry_p * pos["quantity"]
                if trade_value <= 10500.0:  # Only for trades ~₹10k or below
                    if current_pnl_sell <= -100.0:
                        res = close_paper_position(db, symbol, price, exit_reason="SL_HIT")
                        results.append(res)
                        _peak_prices.pop(trade_id, None)
                        _peak_pnl.pop(trade_id, None)
                        logger.info("❌ Nifty Max Loss Hit (-₹100) for %s! P&L: ₹%.2f (Trade Value: ₹%.2f)", symbol, current_pnl_sell, trade_value)
                        continue

            # ══ FILTER 2: TRAILING PEAK PROFIT LOCK (+₹120 PEAK, ₹30 TRAIL PULLBACK) ══
            # Rule: "Green trade ni eppatiki Red avvanivvakoodadhu!"
            peak_pnl_val = _peak_pnl.get(trade_id, 0.0)
            if current_pnl_sell > peak_pnl_val:
                _peak_pnl[trade_id] = current_pnl_sell
                peak_pnl_val = current_pnl_sell

            price_drop = price - peak
            pullback_allowed = max(30.0, peak_pnl_val * 0.20)
            min_price_buffer = max(0.20, entry_p * 0.002)

            if peak_pnl_val >= 120.0 and (peak_pnl_val - current_pnl_sell) >= pullback_allowed and current_pnl_sell > 0 and price_drop >= min_price_buffer:
                res = close_paper_position(db, symbol, price, exit_reason="DYNAMIC_PROFIT_LOCK")
                results.append(res)
                _peak_prices.pop(trade_id, None)
                _peak_pnl.pop(trade_id, None)
                _paper_reversal_notified.discard(trade_id)
                _paper_last_reversal_check_ts.pop(trade_id, None)
                logger.info("💰 Dynamic 20% Peak Profit Lock: %s Peaked at +₹%.2f, Dropped to +₹%.2f (Locked +₹%.2f)", symbol, peak_pnl_val, current_pnl_sell, current_pnl_sell)
                continue

            # ══ FILTER 3: 5-MINUTE TECHNICAL REVERSAL DETECTOR (Telegram Alert Only) ══
            # Does NOT close trade. Checks 5m candle & RSI every 45s, alerts user if momentum fades.
            now_ts = time.time()
            last_check = _paper_last_reversal_check_ts.get(trade_id, 0.0)
            if trade_id not in _paper_reversal_notified and (now_ts - last_check >= 45.0):
                _paper_last_reversal_check_ts[trade_id] = now_ts
                try:
                    from backend.loss_guard import check_5m_momentum_reversal
                    from backend.telegram_alerts import alert_momentum_reversal
                    rev_info = check_5m_momentum_reversal(symbol, action)
                    if rev_info.get("reversal_detected"):
                        _paper_reversal_notified.add(trade_id)
                        logger.info("⚠️ [FILTER 3 PAPER ALERT] Momentum reversal for %s: %s", symbol, rev_info.get("details"))
                        alert_momentum_reversal(symbol, action, price, current_pnl_sell, peak_pnl_val, rev_info.get("details", ""))
                except Exception as _re:
                    logger.warning("Paper 5m reversal check failed for %s: %s", symbol, _re)

            # ══ BUDGET STOCKS SPECIAL RULES ═══════════════════════════════
            if symbol in budget_symbols:
                # Track peak P&L (₹) for this trade
                peak_pnl = _peak_pnl.get(trade_id, 0.0)
                if current_pnl_sell > peak_pnl:
                    _peak_pnl[trade_id] = current_pnl_sell
                    peak_pnl = current_pnl_sell

                # Trailing P&L stop: if peak reached >= ₹20 and dropped by ₹20 → close to lock profit
                if peak_pnl >= 20.0 and (peak_pnl - current_pnl_sell) >= 20.0:
                    res = close_paper_position(db, symbol, price, exit_reason="PROFIT_RETREAT_LOCK")
                    results.append(res)
                    _peak_prices.pop(trade_id, None)
                    _peak_pnl.pop(trade_id, None)
                    logger.info("🔒 Budget Trailing Stop: %s Peak=₹%.0f Now=₹%.0f → Locked!", symbol, peak_pnl, current_pnl_sell)
                    continue

            # ══ STANDARD TARGETS & TRAILING LOGIC ════════════════════════
            t1_threshold = 80.0 if symbol in budget_symbols else 600.0
            max_gain  = entry_p - t1_p
            peak_gain = entry_p - peak

            # 1. Trailing Peak Profit Lock for SELL (price-based) - Non-budget stocks only
            if symbol not in budget_symbols and max_gain > 0 and peak_gain >= (max_gain * 0.5):
                retreat_trigger = peak + (peak_gain * 0.25)
                if price >= retreat_trigger:
                    res = close_paper_position(db, symbol, price, exit_reason="PROFIT_RETREAT_LOCK")
                    results.append(res)
                    _peak_prices.pop(trade_id, None)
                    _peak_pnl.pop(trade_id, None)
                    logger.info("💰 Trailing Profit Lock for %s @ ₹%.2f", symbol, price)
                    continue

            # 2. Trail SL to Break-Even once 35% of T1 reached
            trigger_progress = entry_p - (max_gain * 0.35) if max_gain > 0 else entry_p
            if price <= trigger_progress and pos["stop_loss"] > entry_p:
                pos["stop_loss"] = entry_p
                t_obj = db.query(PaperTrade).filter(PaperTrade.id == trade_id).first()
                if t_obj:
                    t_obj.stop_loss = entry_p
                    db.commit()
                logger.info("🛡️ Trailing SL → Break-Even for %s (₹%.2f)", symbol, entry_p)

            if price <= pos["target2"]:
                res = close_paper_position(db, symbol, price, exit_reason="T2_HIT")
                results.append(res)
                _peak_prices.pop(trade_id, None)
                _peak_pnl.pop(trade_id, None)
            elif price <= pos["target1"] or current_pnl_sell >= t1_threshold:
                # Notify Telegram ONCE per trade when T1 is reached (persisted via _t1_notified_trades set)
                if trade_id not in _t1_notified_trades:
                    _t1_notified_trades.add(trade_id)
                    try:
                        from backend.telegram_alerts import alert_profit_target_approaching
                        alert_profit_target_approaching(symbol, pos["action"], entry_p, price, pos["quantity"], current_pnl_sell, t1_threshold)
                    except Exception as e:
                        logger.warning("Telegram T1 alert failed: %s", e)
                    logger.info("🎯 T1 Target Reached for %s (+₹%.2f P&L). Position kept open to trail for T2/Big Gains!", symbol, current_pnl_sell)
            elif price >= pos["stop_loss"]:
                res = close_paper_position(db, symbol, price, exit_reason="SL_HIT")
                results.append(res)
                _peak_prices.pop(trade_id, None)
                _peak_pnl.pop(trade_id, None)

    return results


def get_paper_portfolio_summary(db: Session) -> dict:
    from backend.database import get_weekly_summary, get_monthly_summary
    balance, open_positions = sync_state(db)
    weekly  = get_weekly_summary(db)
    monthly = get_monthly_summary(db)
    open_count = len(open_positions)
    return {
        "paper_balance":       balance,
        "starting_capital":    _paper_capital,
        "total_pnl":           round(balance - _paper_capital, 2),
        "total_pnl_pct":       round((balance - _paper_capital) / _paper_capital * 100, 2),
        "open_positions":      open_count,
        "positions":           list(open_positions.values()),
        "weekly_summary":      weekly,
        "monthly_summary":     monthly,
    }
