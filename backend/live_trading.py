"""
backend/live_trading.py
StocksSense AI — Live Trading Logic using Angel One SmartAPI
Tracks real money trades, order routing, and auto-exits via DB persistence.
"""

import os
import logging
from datetime import datetime, date
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from backend.database import LiveTrade, save_live_trade
from backend.broker_angelone import (
    login_smartapi,
    place_smartapi_order,
    get_smartapi_positions,
    get_angelone_token_and_symbol
)
from backend.paper_trading import is_market_open_for_trading, circuit_and_liquidity_guard, get_circuit_and_depth_simulator

logger = logging.getLogger(__name__)

# Global session cache to avoid repeating TOTP login requests
_smartapi_session = None

_smartapi_session = None
_last_auth_error = ""

def get_live_auth_data(return_error: bool = False):
    """Retrieve or initialize active Angel One SmartAPI authenticated session."""
    global _smartapi_session, _last_auth_error
    if _smartapi_session:
        return (_smartapi_session, "") if return_error else _smartapi_session

    client_code = os.getenv("ANGELONE_CLIENT_CODE")
    password    = os.getenv("ANGELONE_PASSWORD")
    api_key     = os.getenv("ANGELONE_API_KEY")
    totp_secret = os.getenv("ANGELONE_TOTP_SECRET")

    if not (client_code and password and api_key and totp_secret):
        config_path = os.path.join(os.path.dirname(__file__), "..", "local_config.json")
        if os.path.exists(config_path):
            try:
                import json
                with open(config_path, "r", encoding="utf-8") as cfg:
                    cdata = json.load(cfg)
                    client_code = client_code or cdata.get("client_code")
                    password    = password or cdata.get("password")
                    api_key     = api_key or cdata.get("api_key")
                    totp_secret = totp_secret or cdata.get("totp_secret")
            except Exception:
                pass

        client_code = client_code or "AACL535586"
        password    = password or "7658"
        api_key     = api_key or "GCmlQsKh"
        totp_secret = totp_secret or "EAJXLMJEO5ASGPKQSUIH3I7YYE"

    try:
        session, err = login_smartapi(client_code, password, api_key, totp_secret)
        if session:
            _smartapi_session = session
            _last_auth_error = ""
            return (_smartapi_session, "") if return_error else _smartapi_session
        else:
            _last_auth_error = err or "SmartAPI Authentication failed"
            return (None, _last_auth_error) if return_error else None
    except Exception as e:
        _last_auth_error = str(e)
        logger.error("Failed to authenticate with Angel One SmartAPI: %s", e)
        return (None, _last_auth_error) if return_error else None


def place_live_order(
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
    Route and execute a real trade in Angel One live market.
    """
    # 0. Safety check: Verify live trading is explicitly enabled (default: true)
    if os.getenv("ENABLE_LIVE_TRADING", "true").lower() == "false":
        return {
            "success": False,
            "message": "🚫 Live Trading is currently DISABLED via ENABLE_LIVE_TRADING=false."
        }

    # 1. Market Hours Guard
    market_open, market_msg = is_market_open_for_trading()
    if not market_open:
        return {
            "success": False,
            "message": f"🚫 Live Trade Rejected: {market_msg}"
        }

    # 2. Translate Yahoo Symbol to Angel One token & tradingsymbol
    token, trading_symbol = get_angelone_token_and_symbol(symbol)
    if not token or not trading_symbol:
        return {
            "success": False,
            "message": f"🚫 Live Trade Rejected: Could not resolve Angel One scrip token for symbol {symbol}."
        }

    # 3. Authenticate with Broker
    auth_data = get_live_auth_data()
    if not auth_data:
        return {
            "success": False,
            "message": "🚫 Broker Login Failed: Unable to authenticate with Angel One SmartAPI. Check your credentials."
        }

    # 4. Check if position is already open in our DB
    existing = db.query(LiveTrade).filter(LiveTrade.symbol == symbol, LiveTrade.status == "OPEN").first()
    if existing:
        return {"success": False, "message": f"Already have an open live position in {symbol}"}

    # 5. Guard #17: Circuit Proximity Pre-Entry Filter
    try:
        m_depth, low_circuit = get_circuit_and_depth_simulator(symbol, entry_price)
        guard_status = circuit_and_liquidity_guard(m_depth, entry_price, low_circuit)
        if guard_status == "BLOCK_ENTRY":
            return {
                "success": False,
                "message": "🛡️ Circuit Proximity Guard Active: Stock is too close to lower circuit. Blocked live entry."
            }
    except Exception as ge:
        logger.warning("Circuit check failed for live order %s: %s", symbol, ge)

    # 5.5. 🛡️ Hard ₹300 Loss Cap Enforcement (Strictly lock SL price to exact ₹300 loss boundary for any quantity)
    if quantity > 0:
        max_price_move = 300.0 / quantity
        if action == "BUY":
            stop_loss = round(entry_price - max_price_move, 2)
        elif action == "SELL":
            stop_loss = round(entry_price + max_price_move, 2)
        logger.info("🛡️ Strictly locked LIVE SL for %s to ₹%.2f (Qty: %d -> Exact ₹300.00 Max Loss)", symbol, stop_loss, quantity)

    # 6. Place order on SmartAPI
    # Target and SL logic mapping
    logger.info("Executing LIVE %s order for %d shares of %s", action, quantity, trading_symbol)
    order_res = place_smartapi_order(
        auth_data=auth_data,
        symbol=trading_symbol,
        symbol_token=token,
        transaction_type=action,
        quantity=quantity,
        price=entry_price,
        order_type="MARKET"  # Default to market order for reliable execution
    )

    if not order_res.get("success"):
        err_msg = order_res.get('message', '')
        resp = {
            "success": False,
            "message": f"❌ Angel One Execution Failed: {err_msg}"
        }
        if "registered IP" in err_msg.lower() or "not a registered ip" in err_msg.lower() or "ab1012" in err_msg.lower():
            resp["browser_fallback"] = True
            resp["jwtToken"] = auth_data.get("jwtToken")
            resp["api_key"] = auth_data.get("api_key")
            resp["trading_symbol"] = trading_symbol
            resp["symbol_token"] = token
            resp["action"] = action
            resp["quantity"] = quantity
            resp["price"] = entry_price
            resp["stop_loss"] = stop_loss
            resp["target1"] = target1
            resp["target2"] = target2
            resp["client_public_ip"] = get_server_public_ip()
        return resp

    order_id = order_res.get("order_id")

    # 7. Save live trade in database
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
        "order_id":      order_id,
        "pnl":          0.0,
        "pnl_percent":  0.0,
        "trade_date":   date.today(),
    }

    db_trade = save_live_trade(db, trade_data)

    # 8. Send Telegram Alert for live trade
    try:
        from backend.telegram_alerts import alert_trade_opened
        # Prepend 🟢 LIVE 🔴 to notify user it is a real trade
        alert_trade_opened(
            f"⚡ LIVE {symbol}", company_name, action, entry_price, quantity,
            stop_loss, target1, target2
        )
    except Exception as e:
        logger.warning("Telegram live open alert failed: %s", e)

    return {
        "success":  True,
        "message":  f"🟢 Live {action} order placed: {quantity} x {symbol} @ ₹{entry_price:.2f}",
        "trade_id": db_trade.id,
        "order_id": order_id,
    }


def close_live_position(
    db: Session,
    symbol: str,
    exit_price: float,
    exit_reason: str = "MANUAL",
) -> dict:
    """
    Close open live position by routing square-off order to Angel One.
    """
    sym_base = symbol.replace(".NS", "").replace(".BO", "").strip()
    sym_ns   = f"{sym_base}.NS"
    sym_bo   = f"{sym_base}.BO"
    trade = db.query(LiveTrade).filter(
        LiveTrade.status == "OPEN",
        LiveTrade.symbol.in_([symbol, sym_base, sym_ns, sym_bo])
    ).first()
    if not trade:
        return {"success": False, "message": f"No open live position found for {symbol}"}

    token, trading_symbol = get_angelone_token_and_symbol(symbol)
    if not token or not trading_symbol:
        return {"success": False, "message": f"Could not resolve Angel One token for squareoff: {symbol}"}

    auth_data = get_live_auth_data()
    if not auth_data:
        return {"success": False, "message": "Failed to login to broker for live position close"}

    # Counter action to square-off
    counter_action = "SELL" if trade.action == "BUY" else "BUY"
    
    logger.info("Executing LIVE Square-off (%s) for %d shares of %s", counter_action, trade.quantity, trading_symbol)
    
    # Place exit order
    exit_res = place_smartapi_order(
        auth_data=auth_data,
        symbol=trading_symbol,
        symbol_token=token,
        transaction_type=counter_action,
        quantity=trade.quantity,
        price=exit_price,
        order_type="MARKET"
    )

    if not exit_res.get("success"):
        return {
            "success": False,
            "message": f"❌ Broker Square-Off Failed: {exit_res.get('message')}"
        }

    # Calculate P&L
    entry_price = trade.entry_price
    quantity    = trade.quantity

    if trade.action == "BUY":
        pnl = round((exit_price - entry_price) * quantity, 2)
        pnl_pct = round(((exit_price - entry_price) / entry_price) * 100, 2) if entry_price > 0 else 0.0
    else:
        pnl = round((entry_price - exit_price) * quantity, 2)
        pnl_pct = round(((entry_price - exit_price) / entry_price) * 100, 2) if entry_price > 0 else 0.0

    if pnl <= -295.0 and exit_reason in ("MANUAL", "SL_HIT"):
        exit_reason = "HARD_SL_BREAKER"

    # Save to DB
    trade.exit_price  = exit_price
    trade.pnl         = pnl
    trade.pnl_percent = pnl_pct
    trade.status      = exit_reason
    trade.closed_at   = datetime.utcnow()
    db.commit()

    emoji = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")
    logger.info(
        "%s LIVE TRADE CLOSED: %s @ ₹%.2f | P&L: ₹%.2f (%.2f%%) | Reason: %s",
        emoji, symbol, exit_price, pnl, pnl_pct, exit_reason
    )

    # Telegram Alert
    try:
        from backend.telegram_alerts import alert_trade_closed
        alert_trade_closed(f"⚡ LIVE {symbol}", trade.action, entry_price, exit_price, quantity, pnl, pnl_pct, exit_reason)
    except Exception as e:
        logger.warning("Telegram live close alert failed: %s", e)

    return {
        "success":     True,
        "symbol":      symbol,
        "exit_price":  exit_price,
        "pnl":         pnl,
        "pnl_percent": pnl_pct,
        "exit_reason": exit_reason,
    }


_live_peak_pnl: dict[int, float] = {}

def check_live_auto_exits(db: Session, live_prices: dict[str, float]) -> List[dict]:
    """
    Check open live positions against live prices and exit on triggers.
    Runs in the 15-second scheduler job.
    """
    global _live_peak_pnl
    open_trades = db.query(LiveTrade).filter(LiveTrade.status == "OPEN").all()
    results = []
    
    # Squareoff times
    from datetime import timezone, timedelta
    ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    current_time_str = ist_now.strftime("%H:%M")
    is_eod_squareoff_time = "15:10" <= current_time_str <= "15:35"

    for trade in open_trades:
        symbol = trade.symbol
        price  = live_prices.get(symbol)
        if price is None:
            continue

        trade_id = trade.id

        # EOD Square-off
        if is_eod_squareoff_time:
            res = close_live_position(db, symbol, price, exit_reason="EOD_AUTO_SQUAREOFF")
            results.append(res)
            _live_peak_pnl.pop(trade_id, None)
            continue

        # 🛡️ Guard #17: Live Emergency Exit check
        try:
            m_depth, low_circuit = get_circuit_and_depth_simulator(symbol, price)
            guard_status = circuit_and_liquidity_guard(m_depth, price, low_circuit)
            if guard_status == "EMERGENCY_EXIT":
                res = close_live_position(db, symbol, price, exit_reason="CIRCUIT_EMERGENCY_EXIT")
                results.append(res)
                _live_peak_pnl.pop(trade_id, None)
                logger.info("🚨 Guard #17 Live: Emergency exit triggered for %s.", symbol)
                continue
        except Exception as ge:
            logger.warning("Live circuit monitor failed: %s", ge)

        # 🚨 Hard Rupee SL Circuit Breaker (Max ₹300 Loss Cap per live trade)
        current_pnl = (price - trade.entry_price) * trade.quantity if trade.action == "BUY" else (trade.entry_price - price) * trade.quantity
        if current_pnl <= -300.0:
            res = close_live_position(db, symbol, price, exit_reason="HARD_SL_BREAKER")
            results.append(res)
            _live_peak_pnl.pop(trade_id, None)
            logger.info("🚨 Hard ₹300 SL Circuit Breaker triggered for LIVE trade %s (PnL: ₹%.2f). Squareoff executed.", symbol, current_pnl)
            continue

        # ══ DYNAMIC TRAILING PROFIT LOCK (+₹400 PEAK ACTIVATION, ₹200 TRAILING FLOOR) ══
        peak_pnl_val = _live_peak_pnl.get(trade_id, 0.0)
        if current_pnl > peak_pnl_val:
            _live_peak_pnl[trade_id] = current_pnl
            peak_pnl_val = current_pnl

        if peak_pnl_val >= 400.0:
            trailing_floor = max(200.0, peak_pnl_val - 200.0)
            if current_pnl <= trailing_floor:
                res = close_live_position(db, symbol, price, exit_reason="DYNAMIC_PROFIT_LOCK")
                results.append(res)
                _live_peak_pnl.pop(trade_id, None)
                logger.info("💰 LIVE Dynamic Profit Lock: %s Peaked at +₹%.0f, Exited at +₹%.0f (Floor: +₹%.0f)", symbol, peak_pnl_val, current_pnl, trailing_floor)
                continue

        # Standard Target/SL logic
        if trade.action == "BUY":
            if price >= trade.target2:
                res = close_live_position(db, symbol, price, exit_reason="T2_HIT")
                results.append(res)
                _live_peak_pnl.pop(trade_id, None)
            elif price >= trade.target1:
                # Notify Telegram when T1 is reached, but DO NOT force-close. Let Dynamic Trailing Engine trail profit!
                logger.info("🎯 LIVE T1 Target Reached for %s (+₹%.2f P&L). Position kept open to trail for T2/Big Gains!", symbol, current_pnl)
            elif price <= trade.stop_loss:
                res = close_live_position(db, symbol, price, exit_reason="SL_HIT")
                results.append(res)
                _live_peak_pnl.pop(trade_id, None)
        elif trade.action == "SELL":
            if price <= trade.target2:
                res = close_live_position(db, symbol, price, exit_reason="T2_HIT")
                results.append(res)
                _live_peak_pnl.pop(trade_id, None)
            elif price <= trade.target1:
                # Notify Telegram when T1 is reached, but DO NOT force-close. Let Dynamic Trailing Engine trail profit!
                logger.info("🎯 LIVE T1 Target Reached for %s (+₹%.2f P&L). Position kept open to trail for T2/Big Gains!", symbol, current_pnl)
            elif price >= trade.stop_loss:
                res = close_live_position(db, symbol, price, exit_reason="SL_HIT")
                results.append(res)
                _live_peak_pnl.pop(trade_id, None)

    return results


def get_live_portfolio_summary(db: Session) -> dict:
    """Fetch live portfolio performance metrics and orders."""
    open_trades = db.query(LiveTrade).filter(LiveTrade.status == "OPEN").all()
    closed_trades = db.query(LiveTrade).filter(LiveTrade.status != "OPEN").all()
    
    total_pnl = sum(t.pnl for t in closed_trades if t.pnl is not None)
    
    # Format open trades list
    positions_list = []
    for t in open_trades:
        positions_list.append({
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
        })

    # Try fetching reality positions and RMS funds from Angel One to compare/verify
    broker_positions = []
    broker_funds = {}
    auth_data = get_live_auth_data()
    if auth_data:
        try:
            from backend.broker_angelone import get_smartapi_positions, get_smartapi_rms
            pos_data = get_smartapi_positions(auth_data)
            if pos_data:
                broker_positions = pos_data
            rms_data = get_smartapi_rms(auth_data)
            if rms_data:
                broker_funds = rms_data
        except Exception as e:
            logger.debug("Could not fetch positions/funds from Angel One API: %s", e)

    return {
        "total_pnl":         round(total_pnl, 2),
        "open_positions":    len(open_trades),
        "positions":         positions_list,
        "broker_positions":  broker_positions,
        "broker_funds":      broker_funds,
        "closed_count":      len(closed_trades)
    }


def record_live_trade(
    db: Session,
    symbol: str,
    company_name: str,
    action: str,
    entry_price: float,
    quantity: int,
    stop_loss: float,
    target1: float,
    target2: float,
    order_id: str,
    signal_id: Optional[int] = None,
    is_scalp: bool = False
) -> dict:
    """Record a live trade in database after browser-direct client-side execution."""
    trade_data = {
        "symbol": symbol,
        "company_name": company_name or symbol,
        "action": action.upper(),
        "entry_price": float(entry_price),
        "quantity": int(quantity),
        "stop_loss": float(stop_loss),
        "target1": float(target1),
        "target2": float(target2),
        "status": "OPEN",
        "order_id": str(order_id),
        "trade_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "signal_id": signal_id,
        "is_scalp": is_scalp
    }
    trade = LiveTrade(**trade_data)
    db.add(trade)
    db.commit()
    db.refresh(trade)

    try:
        telegram_alerts.send_order_alert(trade_data, is_live=True)
    except Exception as te:
        logger.warning("Failed to send Telegram alert for live trade: %s", te)

    return {"success": True, "trade_id": trade.id, "message": f"Recorded live trade for {symbol}"}
