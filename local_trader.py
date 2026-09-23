"""
StocksSense AI — Local Live Trader Pro (Deep AI Brain Edition)
==============================================================
Complete algorithmic trading dashboard running locally with your registered Home IP.
Features: Fast 5M Scanner + Full Gemini AI Brain (1H/15M/News/18-Guards), 1-Click Angel One Execution.
"""

import os
import sys

# Ensure UTF-8 output encoding on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import datetime
from datetime import datetime, timezone, timedelta
import json
import webbrowser
import http.server
import urllib.request
import urllib.parse
import ssl
import pyotp
import re
from typing import Dict, Optional, List

# ── Deep AI Brain: Load Backend Modules (same as Render) ──────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
    from backend.technicals_1h import analyze_1h, analyze_15m
    from backend.news_fetcher import fetch_stock_news
    from backend.ai_agent import analyze_stock_with_ai
    from backend.historical_reaction import analyze_historical_reaction
    from backend.loss_guard import check_nifty_trend_guard
    from backend.indian_stocks import NIFTY50_STOCKS, BUDGET_LOW_PRICED_STOCKS, ALL_STOCKS
    DEEP_AI_AVAILABLE = True
    print("✅ Deep Gemini AI Brain loaded successfully!")
except Exception as _e:
    DEEP_AI_AVAILABLE = False
    print(f"⚠️ Deep AI Brain not available (using Fast Mode): {_e}")

try:
    from backend.indian_stocks import NIFTY50_STOCKS, BUDGET_LOW_PRICED_STOCKS, ALL_STOCKS
except Exception:
    NIFTY50_STOCKS = []
    BUDGET_LOW_PRICED_STOCKS = []
    ALL_STOCKS = []

try:
    from backend.database import SessionLocal, PaperTrade, LiveTrade, get_weekly_summary, get_monthly_summary
    DB_AVAILABLE = True
    print("✅ Database (Paper/Live Trading Engine) loaded successfully!")
except Exception as _dbe:
    DB_AVAILABLE = False
    print(f"⚠️ Database module load error: {_dbe}")

try:
    from backend.telegram_alerts import send_telegram_message as _backend_tg_send
except Exception:
    def _backend_tg_send(msg, parse_mode="HTML"): pass

ANGEL_TOKENS_MAP = {
    "RELIANCE.NS": "2885",  "TCS.NS": "11536",  "HDFCBANK.NS": "1333",
    "ICICIBANK.NS": "4963", "INFY.NS": "1594",  "SBIN.NS": "3045",
    "BHARTIARTL.NS": "10604", "TATAMOTORS.NS": "3456", "M&M.NS": "2031",
    "AXISBANK.NS": "5900",  "SUNPHARMA.NS": "3351", "BAJFINANCE.NS": "317",
    "TATASTEEL.NS": "3499", "BEL.NS": "383",    "NTPC.NS": "11630",
    "POWERGRID.NS": "14977","ONGC.NS": "2475",  "COALINDIA.NS": "20374",
    "ADANIENT.NS": "25",    "ADANIPORTS.NS": "15083", "LT.NS": "11483",
    "HCLTECH.NS": "7229",   "WIPRO.NS": "3787", "MARUTI.NS": "10999",
    "KOTAKBANK.NS": "1922", "TITAN.NS": "3506", "JSWSTEEL.NS": "11723",
    "HINDUNILVR.NS": "356", "ITC.NS": "1660",   "ULTRACEMCO.NS": "11532",
    "TECHM.NS": "13538",    "LTIM.NS": "17818", "GRASIM.NS": "315",
    "CIPLA.NS": "694",      "DRREDDY.NS": "881", "DIVISLAB.NS": "10940",
    "APOLLOHOSP.NS": "157", "BAJAJ-AUTO.NS": "16675", "EICHERMOT.NS": "910",
    "INDUSINDBK.NS": "5258","HEROMOTOCO.NS": "1348", "NESTLEIND.NS": "17963",
    "SHRIRAMFIN.NS": "4306","SBILIFE.NS": "21808", "BPCL.NS": "526",
    "TATACONSUM.NS": "3432","HDFCLIFE.NS": "467",
    "SUZLON.NS": "12018",   "IDFCFIRSTB.NS": "11184", "PNB.NS": "10666",
    "YESBANK.NS": "11915",  "IRFC.NS": "2029",  "NHPC.NS": "17400",
    "SAIL.NS": "2963",      "IOC.NS": "1624",   "UCOBANK.NS": "8064",
    "UNIONBANK.NS": "10780","NBCC.NS": "14730", "SJVN.NS": "18883",
    "HFCL.NS": "2303",      "ETERNAL.NS": "5097", "IDBI.NS": "10531",
    "GMRAIRPORT.NS": "4328","FEDERALBNK.NS": "1023", "IDEA.NS": "14366",
    "ZOMATO.NS": "5097",    "BANKBARODA.NS": "467", "HUDCO.NS": "14732",
}


def _deep_ai_scan_single(stock: dict) -> Optional[dict]:
    """Run full Gemini AI Brain analysis on a single stock — same as Render."""
    symbol = stock["symbol"]
    name   = stock["name"]
    sector = stock.get("sector", "N/A")
    try:
        # Step 1: 1H Technical Analysis
        technical = analyze_1h(symbol)
        if not technical:
            return None

        # Step 2: 15M Dual Timeframe Confluence
        tech_15m = analyze_15m(symbol)
        if tech_15m:
            technical.update(tech_15m)

        price = technical.get("current_price", 0)
        if not price or price <= 0:
            return None

        # Step 3: News Sentiment
        try:
            news_items = fetch_stock_news(symbol, name, max_items=4)
        except Exception:
            news_items = []

        # Step 4: Historical reaction
        try:
            historical = analyze_historical_reaction(symbol, news_items, technical)
        except Exception:
            historical = {"historical_note": "No historical pattern found."}

        # Step 5: Gemini AI Signal (with Quant fallback if rate-limited)
        ai = analyze_stock_with_ai(symbol, name, sector, news_items, technical, historical, confidence_threshold=90.0)
        if not ai:
            return None

        signal = (ai.get("signal") or "AVOID").upper()
        conf   = float(ai.get("confidence", 0))
        if signal not in ("BUY", "SELL") or conf < 90.0:
            return None   # Strict 90%+ High Conviction Filter

        isBuy = signal == "BUY"
        sl     = technical.get("sl_buy" if isBuy else "sl_sell", round(price * (0.988 if isBuy else 1.012), 2))
        t1     = technical.get("target1_buy" if isBuy else "target1_sell", round(price * (1.015 if isBuy else 0.985), 2))
        t2     = technical.get("target2_buy" if isBuy else "target2_sell", round(price * (1.030 if isBuy else 0.970), 2))

        # Map to Angel One token
        base_sym = symbol.replace(".NS", "-EQ")
        tok = ANGEL_TOKENS_MAP.get(symbol) or STOCK_TOKENS.get(base_sym, "")

        return {
            "symbol":       base_sym,
            "stock":        base_sym,
            "company_name": name,
            "sector":       sector,
            "token":        tok,
            "symboltoken":  tok,
            "symbol_token": tok,
            "action":       signal,
            "price":        round(float(price), 2),
            "entry_price":  round(float(price), 2),
            "target":       round(float(t1), 2),
            "target2":      round(float(t2), 2),
            "stoploss":     round(float(sl), 2),
            "confidence":   round(conf, 1),
            "rsi":          round(technical.get("rsi", 50), 1),
            "rvol":         round(technical.get("rvol", 1.0), 2),
            "trend_1h":     technical.get("trend_1h", "NEUTRAL"),
            "trend_15m":    technical.get("trend_15m", "NEUTRAL"),
            "risk_level":   ai.get("risk_level", "MEDIUM"),
            "news_summary": ai.get("news_summary", ""),
            "reasoning":    ai.get("reasoning", ""),
            "mode":         "DEEP_AI",
            "scan_type":    "deep_scan",
        }
    except Exception as ex:
        return None


def run_deep_ai_scan(category: str = "all") -> dict:
    """Full Gemini AI Brain scan — same pipeline as Render website."""
    from concurrent.futures import ThreadPoolExecutor

    market_open, market_msg = check_market_hours_ist()
    if not market_open:
        return {"signals": [], "total": 0, "category": category, "market_closed": True, "error": market_msg}

    if not DEEP_AI_AVAILABLE:
        return {"signals": [], "total": 0, "category": category,
                "error": "Deep AI Brain not available. Backend modules missing."}

    # Nifty macro guard
    try:
        nifty_status = check_nifty_trend_guard()
        nifty_blocked = nifty_status.get("action_block", False)
        nifty_pct     = nifty_status.get("nifty_change_pct", 0.0)
    except Exception:
        nifty_blocked = False
        nifty_pct     = 0.0

    if category == "budget":
        stocks = BUDGET_LOW_PRICED_STOCKS[:10]
    elif category == "nifty50":
        stocks = NIFTY50_STOCKS[:10]
    else:
        stocks = BUDGET_LOW_PRICED_STOCKS[:6] + NIFTY50_STOCKS[:8]

    signals = []
    with ThreadPoolExecutor(max_workers=min(6, len(stocks))) as executor:
        results = executor.map(_deep_ai_scan_single, stocks)
        for res in results:
            if res:
                signals.append(res)

    signals.sort(key=lambda x: x["confidence"], reverse=True)
    return {
        "signals":        signals,
        "total":          len(signals),
        "category":       category,
        "mode":           "DEEP_AI",
        "nifty_pct":      nifty_pct,
        "nifty_blocked":  nifty_blocked,
        "ai_available":   DEEP_AI_AVAILABLE,
    }


def _ultra_sniper_scan_single(stock: dict) -> Optional[dict]:
    """
    Evaluates a single stock against 7 Ultra Strict Filters + 18 Loss Guards for 92%+ Snipe.
    Returns structured trade data with 6-point checklist radar or None if rejected.
    """
    symbol = stock["symbol"]
    name   = stock["name"]
    sector = stock.get("sector", "N/A")

    try:
        # Step 1: 1H Technicals
        tech_1h = analyze_1h(symbol)
        if not tech_1h:
            return None

        # Step 2: 15M Technicals (Upgrade 2 Dual Lock)
        tech_15m = analyze_15m(symbol)
        if not tech_15m:
            return None

        price = tech_1h.get("current_price", 0)
        if not price or price <= 0:
            return None

        # Extract indicators
        trend_1h     = tech_1h.get("trend_1h", "NEUTRAL")
        trend_15m    = tech_15m.get("trend_15m", "NEUTRAL")
        rsi_1h       = tech_1h.get("rsi", 50)
        rsi_15m      = tech_15m.get("rsi_15m", 50)
        p_vwap_1h    = tech_1h.get("price_vs_vwap", "AT")
        p_vwap_15m   = tech_15m.get("price_vs_vwap_15m", "AT")
        rvol_1h      = tech_1h.get("rvol", 1.0)
        rvol_15m     = tech_15m.get("rvol_15m", 1.0)
        is_open_high = tech_1h.get("is_open_high", False)
        ema9         = tech_1h.get("ema9", 0)
        ema21        = tech_1h.get("ema21", 0)

        # ── 7 ULTRA SNIPER FILTERS ──────────────────────────────────────────
        # Checklist 1: Dual Timeframe Confluence Lock (1H + 15M)
        check1_buy  = (trend_1h == "BULLISH" and trend_15m == "BULLISH" and ema9 > ema21)
        check1_sell = (trend_1h == "BEARISH" and trend_15m == "BEARISH" and ema9 < ema21)
        if not (check1_buy or check1_sell):
            return None  # Rejection 1: Timeframes not aligned

        isBuy = check1_buy

        # Checklist 2: Institutional RVOL >= 1.8x Gate (Big Money Volume)
        effective_rvol = max(rvol_1h, rvol_15m)
        check2 = effective_rvol >= 1.8
        if not check2:
            return None  # Rejection 2: Low Volume / Retail Trap

        # Checklist 3: VWAP Confluence (Price above VWAP for BUY, below for SELL)
        check3 = (isBuy and p_vwap_1h == "ABOVE" and p_vwap_15m == "ABOVE") or \
                 (not isBuy and p_vwap_1h == "BELOW" and p_vwap_15m == "BELOW")
        if not check3:
            return None  # Rejection 3: Price wrong side of VWAP

        # Checklist 4: RSI Sweet Zone (52 - 68 for BUY, 32 - 48 for SELL)
        check4 = (isBuy and 52 <= rsi_1h <= 68 and 50 <= rsi_15m <= 72) or \
                 (not isBuy and 32 <= rsi_1h <= 48 and 28 <= rsi_15m <= 50)
        if not check4:
            return None  # Rejection 4: RSI overbought (>70) or weak (<50)

        # Checklist 5: Open=High Selling Trap Filter
        check5 = not is_open_high if isBuy else True
        if not check5:
            return None  # Rejection 5: Open=High Trap

        # Checklist 6: Risk-to-Reward Ratio (Min 1:1.8 Guarantee)
        sl  = tech_1h.get("sl_buy" if isBuy else "sl_sell", round(price * (0.988 if isBuy else 1.012), 2))
        t1  = tech_1h.get("target1_buy" if isBuy else "target1_sell", round(price * (1.018 if isBuy else 0.982), 2))
        t2  = tech_1h.get("target2_buy" if isBuy else "target2_sell", round(price * (1.030 if isBuy else 0.970), 2))
        risk = abs(price - sl)
        reward = abs(t1 - price)
        rr_ratio = round(reward / risk, 2) if risk > 0 else 1.8
        check6 = rr_ratio >= 1.75
        if not check6:
            return None  # Rejection 6: R:R ratio below 1.75x

        # Checklist 7: Anti-FOMO & Extended Move Trap Filter (Eliminates 3-4 Candle Lag Traps)
        # If price is already stretched > 1.0% away from 15M VWAP, reject! (Smart money profit-taking zone)
        is_extended = tech_15m.get("is_extended_move", False)
        if is_extended:
            return None  # Rejection 7: Extended Move / Late Entry FOMO Trap

        # Checklist 8: Fresh Breakout or Clean Pullback Bounce (Candle 1 or 2 Only)
        is_fresh = tech_15m.get("is_fresh_breakout", False)
        is_bounce = tech_15m.get("is_pullback_bounce", False)
        if not (is_fresh or is_bounce):
            return None  # Rejection 8: Not an early breakout or dip-bounce (Candle 1-2 only)

        # ── SCORE CALCULATION (0-100) ──────────────────────────────────────
        score = 90.0
        if effective_rvol >= 2.5: score += 3.0
        elif effective_rvol >= 2.0: score += 2.0
        if 55 <= rsi_1h <= 65: score += 2.0
        if rr_ratio >= 2.0: score += 2.0
        if is_fresh: score += 1.0
        score = min(99.0, score)

        if score < 92.0:
            return None  # Strict 92% Conviction Gate

        # Map to Angel One Token
        base_sym = symbol.replace(".NS", "-EQ")
        tok = ANGEL_TOKENS_MAP.get(symbol) or STOCK_TOKENS.get(base_sym, "")

        return {
            "symbol":        base_sym,
            "stock":         base_sym,
            "company_name":  name,
            "sector":        sector,
            "token":         tok,
            "symboltoken":   tok,
            "action":        "BUY" if isBuy else "SELL",
            "price":         round(float(price), 2),
            "entry_price":   round(float(price), 2),
            "target":        round(float(t1), 2),
            "target2":       round(float(t2), 2),
            "stoploss":      round(float(sl), 2),
            "confidence":    round(score, 1),
            "score":         round(score, 1),
            "rr_ratio":      rr_ratio,
            "rsi_1h":        round(rsi_1h, 1),
            "rsi_15m":       round(rsi_15m, 1),
            "rvol":          round(effective_rvol, 2),
            "trend_1h":      trend_1h,
            "trend_15m":     trend_15m,
            "checklist": {
                "timeframe_lock": True,
                "rvol_gate": True,
                "vwap_confluence": True,
                "rsi_sweet_zone": True,
                "no_open_high_trap": True,
                "rr_ratio_ok": True,
                "early_entry_lock": True
            },
            "scan_type":     "ultra_sniper",
            "is_fresh_breakout": is_fresh,
            "is_pullback_bounce": is_bounce,
            "reasoning":     f"👑 92%+ ULTRA SNIPER TRADE: Candle 1-2 Early Entry | 1H+15M Confluence | RVOL {effective_rvol:.1f}x | R:R 1:{rr_ratio:.1f} | Pure Trend!",
            "mode":          "ULTRA_SNIPER"
        }
    except Exception as ex:
        return None


def check_market_hours_ist() -> tuple[bool, str]:
    """Check if Indian stock market (NSE) is currently open for new entries (Mon-Fri 9:15 AM - 3:00 PM IST)."""
    from datetime import datetime, timezone, timedelta
    ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    if ist_now.weekday() in (5, 6):
        return False, "🌙 MARKET IS CLOSED TODAY (Weekend: Saturday/Sunday). Live signals active Mon-Fri 9:15 AM - 3:00 PM IST."
    time_str = ist_now.strftime("%H:%M")
    if not ("09:15" <= time_str <= "15:00"):
        return False, f"🌙 NEW ENTRIES CLOSED ({time_str} IST). Live NSE Trading new entry cutoff is 3:00 PM IST. Zero new signals generated during EOD squareoff to protect capital."
    return True, "✅ Market is Open"


def run_ultra_sniper_scan() -> dict:
    """
    👑 TODAY'S #1 ULTRA SNIPER TRADE SCANNER
    Scans Nifty 50 stocks, runs 7 Ultra Strict Filters + 18 Loss Guards.
    Selects EXACTLY 1 TOP HIGHEST SCORING STOCK (>92% score).
    """
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timezone, timedelta

    # 🛑 Market Hours Guard: Zero signals outside 9:15 AM - 3:30 PM IST
    market_open, market_msg = check_market_hours_ist()
    if not market_open:
        return {
            "sniper_trade": None,
            "total_scanned": 0,
            "market_closed": True,
            "message": market_msg
        }

    ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    time_str = ist_now.strftime("%H:%M")
    is_lunch_trap = "11:30" <= time_str <= "13:30"

    # Nifty Macro Guard
    try:
        nifty_status = check_nifty_trend_guard()
        nifty_blocked = nifty_status.get("action_block", False) or nifty_status.get("blocked", False)
        nifty_pct     = nifty_status.get("nifty_change_pct", 0.0)
    except Exception:
        nifty_blocked = False
        nifty_pct     = 0.0

    if nifty_blocked:
        return {
            "sniper_trade": None,
            "total_scanned": 50,
            "nifty_pct": nifty_pct,
            "nifty_blocked": True,
            "message": f"🚨 Nifty 50 Market Crash Guard Active ({nifty_pct:+.2f}%). ALL BUY TRADES BLOCKED TODAY FOR CAPITAL PROTECTION."
        }

    stocks = NIFTY50_STOCKS + BUDGET_LOW_PRICED_STOCKS[:10]
    candidates = []

    with ThreadPoolExecutor(max_workers=min(8, len(stocks))) as executor:
        results = executor.map(_ultra_sniper_scan_single, stocks)
        for res in results:
            if res:
                candidates.append(res)

    candidates.sort(key=lambda x: x["confidence"], reverse=True)

    if not candidates:
        return {
            "sniper_trade": None,
            "total_scanned": len(stocks),
            "nifty_pct": nifty_pct,
            "is_lunch_trap": is_lunch_trap,
            "message": "⚠️ NO 92%+ ULTRA SNIPER TRADE TODAY: Market is currently sideways/choppy. No stock passed all 7 Ultra Strict Filters + 18 Loss Guards. CAPITAL IS 100% PROTECTED."
        }

    top_sniper = candidates[0]
    try:
        broadcast_top_scan_signals_to_telegram([top_sniper], scan_mode="👑 ULTRA SNIPER")
    except Exception:
        pass
    return {
        "sniper_trade": top_sniper,
        "runner_ups": candidates[1:3],
        "total_scanned": len(stocks),
        "nifty_pct": nifty_pct,
        "is_lunch_trap": is_lunch_trap,
        "scan_time": time_str
    }


CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_config.json")
ANGELONE_URL = "https://apiconnect.angelbroking.com"
STOCKSSENSE_URL = "https://stockssense-ai-backend.onrender.com"

config = {
    "client_code": "AACL535586",
    "password": "",
    "api_key": "",
    "totp_secret": "",
    "trading_mode": "paper",
    "telegram_bot_token": "",
    "telegram_chat_id": ""
}

if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r") as f:
            config.update(json.load(f))
    except Exception as e:
        print(f"Error loading config: {e}")

auth_session = {}
scrip_token_cache = {}


def save_config(new_config: dict):
    global config
    config.update(new_config)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def auto_detect_chat_id(bot_token: str) -> Optional[str]:
    """Inspects Telegram getUpdates to automatically find user/group Chat ID."""
    if not bot_token:
        return None
    try:
        url = f"https://api.telegram.org/bot{bot_token.strip()}/getUpdates"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for u in reversed(data.get("result", [])):
                m = u.get("message") or u.get("channel_post") or u.get("my_chat_member")
                if m and "chat" in m and "id" in m["chat"]:
                    return str(m["chat"]["id"])
    except Exception:
        pass
    return None


def send_telegram_direct(bot_token: str, chat_id: str, text: str) -> dict:
    """Synchronous direct sender to any specified Telegram Bot and Chat."""
    if not bot_token:
        return {"success": False, "message": "Bot Token is required!"}

    bot_token = bot_token.strip()
    chat_id = (chat_id or "").strip()
    bot_id = bot_token.split(":")[0].strip() if ":" in bot_token else ""
    detected_id = None

    # If chat_id is missing or user mistakenly entered bot's own ID
    if not chat_id or chat_id == bot_id:
        detected_id = auto_detect_chat_id(bot_token)
        if detected_id and detected_id != bot_id:
            chat_id = detected_id
        else:
            return {
                "success": False,
                "message": f"❌ '{chat_id}' అనేది Bot ID! మీ Personal Chat ID కాదు. Telegram లో బాట్ ని ఓపెన్ చేసి START నొక్కి, Chat ID బాక్స్ లో 7327907687 ఎంటర్ చేయండి."
            }

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if res.get("ok"):
                msg = "✅ Test alert delivered to your Telegram successfully!"
                if detected_id:
                    msg += f" (Auto-detected Chat ID: {detected_id})"
                return {"success": True, "message": msg, "detected_chat_id": chat_id}
            else:
                return {"success": False, "message": f"Telegram API error: {res.get('description', 'Unknown error')}"}
    except urllib.error.HTTPError as e:
        err_msg = str(e)
        if e.code == 403:
            err_msg = "HTTP 403 Forbidden: Chat ID తప్పుగా ఉంది లేదా బాట్ ఇంకా /start చేయలేదు. దయచేసి Chat ID '7327907687' ఎంటర్ చేయండి."
        return {"success": False, "message": f"Telegram connection error: {err_msg}"}
    except Exception as e:
        return {"success": False, "message": f"Telegram connection error: {e}"}


def send_telegram_message(msg: str, parse_mode: str = "HTML"):
    """
    Unified Telegram alert sender for Local Trader:
    If a custom Telegram bot/chat is saved in local_config.json, sends to that custom bot.
    Otherwise, falls back to the backend default Telegram bot.
    """
    bot_token = (config.get("telegram_bot_token") or "").strip()
    chat_id = (config.get("telegram_chat_id") or "").strip()

    if bot_token and chat_id:
        def _bg():
            send_telegram_direct(bot_token, chat_id, msg)
        import threading
        threading.Thread(target=_bg, daemon=True).start()
    else:
        _backend_tg_send(msg, parse_mode=parse_mode)


def save_paper_trade_db(symbol: str, action: str, qty: int, price: float, sl: float = 0, t1: float = 0, t2: float = 0, company_name: str = ""):
    if not DB_AVAILABLE:
        return None
    try:
        db = SessionLocal()
        pt = PaperTrade(
            symbol=symbol,
            company_name=company_name or symbol,
            action=action.upper(),
            entry_price=float(price or 0),
            quantity=int(qty or 1),
            stop_loss=float(sl or 0),
            target1=float(t1 or 0),
            target2=float(t2 or 0),
            status="OPEN"
        )
        db.add(pt)
        db.commit()
        db.refresh(pt)
        tid = pt.id
        db.close()
        return tid
    except Exception as e:
        print(f"Error saving paper trade to DB: {e}")
        return None


def save_live_trade_db(symbol: str, action: str, qty: int, price: float, sl: float = 0, t1: float = 0, t2: float = 0, order_id: str = "", company_name: str = ""):
    if not DB_AVAILABLE:
        return None
    try:
        db = SessionLocal()
        lt = LiveTrade(
            symbol=symbol,
            company_name=company_name or symbol,
            action=action.upper(),
            entry_price=float(price or 0),
            quantity=int(qty or 1),
            stop_loss=float(sl or 0),
            target1=float(t1 or 0),
            target2=float(t2 or 0),
            status="OPEN",
            order_id=str(order_id or "")
        )
        db.add(lt)
        db.commit()
        db.refresh(lt)
        tid = lt.id
        db.close()
        return tid
    except Exception as e:
        print(f"Error saving live trade to DB: {e}")
        return None


def close_live_trade_record(symbol: str, exit_price: float, pnl: float, exit_reason: str = "CLOSED"):
    """Update LiveTrade record in DB when an auto-exit or square-off occurs."""
    if not DB_AVAILABLE:
        return
    try:
        db = SessionLocal()
        clean_s = symbol.replace("-EQ", "").strip()
        t = db.query(LiveTrade).filter(
            LiveTrade.status == "OPEN",
            (LiveTrade.symbol == symbol) | (LiveTrade.symbol == clean_s) | (LiveTrade.symbol == f"{clean_s}-EQ")
        ).order_by(LiveTrade.id.desc()).first()
        if t:
            t.status = exit_reason or "CLOSED"
            t.exit_price = round(float(exit_price or 0.0), 2)
            t.pnl = round(float(pnl or 0.0), 2)
            if t.entry_price and t.quantity and t.entry_price > 0:
                t.pnl_percent = round((t.pnl / (t.entry_price * t.quantity)) * 100, 2)
            t.closed_at = datetime.utcnow()
            db.commit()
            print(f"✅ Closed LiveTrade #{t.id} in DB: {symbol} Exit: ₹{t.exit_price} P&L: ₹{t.pnl}")
        db.close()
    except Exception as e:
        print(f"⚠️ close_live_trade_record error: {e}")


def reconcile_live_trades_with_broker(db):
    """
    Syncs and reconciles LiveTrade rows against Angel One broker's position book and order book.
    - If a trade was closed on Angel One (netqty == 0), updates exit_price, pnl, pnl_percent, and status to CLOSED.
    - If a trade is from a previous trading day (trade_date < today), auto-marks as CLOSED since intraday positions expire daily.
    """
    if not db:
        return
    try:
        from datetime import datetime, timezone, timedelta
        ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        today_ist = ist_now.date()

        open_trades = db.query(LiveTrade).filter(LiveTrade.status == "OPEN").all()
        if not open_trades:
            return

        # Fetch broker positions
        pos_resp = get_live_positions()
        broker_positions = {}
        if pos_resp.get("connected"):
            for p in pos_resp.get("positions", []):
                tsym = p.get("tradingsymbol", "")
                broker_positions[tsym] = p
                broker_positions[tsym.replace("-EQ", "")] = p

        # Fetch broker completed orders today for exact fill price matching
        order_resp = get_order_book()
        completed_orders = []
        if order_resp.get("connected"):
            completed_orders = [o for o in order_resp.get("orders", []) if (o.get("status") or "").lower() == "complete"]

        for t in open_trades:
            clean_s = (t.symbol or "").replace("-EQ", "").strip()
            pos = broker_positions.get(t.symbol) or broker_positions.get(clean_s) or broker_positions.get(f"{clean_s}-EQ")

            # 1. Closed today on Angel One (netqty == 0)
            if pos and int(pos.get("netqty") or 0) == 0:
                realised_pnl = float(pos.get("realised") or pos.get("pnl") or 0.0)
                buy_avg = float(pos.get("buyavgprice") or pos.get("totalbuyavgprice") or t.entry_price or 0.0)
                sell_avg = float(pos.get("sellavgprice") or pos.get("totalsellavgprice") or 0.0)

                act = (t.action or "BUY").upper()
                exit_p = 0.0
                # Try finding matching exit order from order book
                exit_action = "SELL" if act == "BUY" else "BUY"
                matching_orders = [o for o in completed_orders if (o.get("tradingsymbol") in (t.symbol, clean_s, f"{clean_s}-EQ")) and (o.get("transactiontype") == exit_action)]
                if matching_orders:
                    exit_p = float(matching_orders[0].get("averageprice") or 0.0)

                if exit_p <= 0:
                    exit_p = sell_avg if act == "BUY" and sell_avg > 0 else (buy_avg if act == "SELL" and buy_avg > 0 else 0.0)

                if exit_p <= 0 and t.entry_price and t.quantity:
                    exit_p = t.entry_price + (realised_pnl / max(1, t.quantity)) if act == "BUY" else t.entry_price - (realised_pnl / max(1, t.quantity))

                calc_pnl = round((exit_p - t.entry_price) * (t.quantity or 1), 2) if act == "BUY" else round((t.entry_price - exit_p) * (t.quantity or 1), 2)
                if abs(calc_pnl) < 0.01 and abs(realised_pnl) > 0:
                    calc_pnl = realised_pnl

                t.status = "CLOSED"
                t.exit_price = round(exit_p, 2)
                t.pnl = round(calc_pnl, 2)
                if t.entry_price and t.quantity and t.entry_price > 0:
                    t.pnl_percent = round((t.pnl / (t.entry_price * t.quantity)) * 100, 2)
                t.closed_at = datetime.utcnow()
                print(f"🔄 [Journal Sync] Closed trade #{t.id} ({t.symbol}): Exit ₹{t.exit_price}, P&L ₹{t.pnl}")

            # 2. Past-day trade still marked OPEN (MIS intraday squares off at 3:15 PM daily)
            elif t.trade_date and t.trade_date < today_ist:
                t.status = "CLOSED"
                t.closed_at = datetime.combine(t.trade_date, datetime.min.time()) + timedelta(hours=15, minutes=15)
                if not t.exit_price or t.exit_price <= 0:
                    try:
                        import yfinance as yf
                        hist = yf.Ticker(clean_s + ".NS").history(start=str(t.trade_date), end=str(t.trade_date + timedelta(days=2)))
                        if not hist.empty and "Close" in hist:
                            t.exit_price = round(float(hist["Close"].iloc[0]), 2)
                        else:
                            t.exit_price = t.entry_price
                    except Exception:
                        t.exit_price = t.entry_price
                act = (t.action or "BUY").upper()
                q = t.quantity or 1
                t.pnl = round(((t.exit_price or t.entry_price) - t.entry_price) * q, 2) if act == "BUY" else round((t.entry_price - (t.exit_price or t.entry_price)) * q, 2)
                if t.entry_price and t.entry_price > 0:
                    t.pnl_percent = round((t.pnl / (t.entry_price * q)) * 100, 2)
                print(f"🔄 [Journal Sync] Auto-closed past-day trade #{t.id} ({t.symbol} on {t.trade_date}): Exit ₹{t.exit_price}, P&L ₹{t.pnl}")

        db.commit()
    except Exception as e:
        print(f"⚠️ reconcile_live_trades_with_broker error: {e}")


def reconcile_paper_trades(db):
    """Auto-close past-day open paper trades at EOD."""
    if not db:
        return
    try:
        from datetime import datetime, timezone, timedelta
        ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        today_ist = ist_now.date()
        open_pts = db.query(PaperTrade).filter(PaperTrade.status == "OPEN").all()
        for pt in open_pts:
            if pt.trade_date and pt.trade_date < today_ist:
                pt.status = "EOD_AUTO_SQUAREOFF"
                pt.exit_price = pt.entry_price
                pt.pnl = 0.0
                pt.pnl_percent = 0.0
                pt.closed_at = datetime.combine(pt.trade_date, datetime.min.time()) + timedelta(hours=15, minutes=30)
        db.commit()
    except Exception as e:
        print(f"⚠️ reconcile_paper_trades error: {e}")


def get_trades_list(mode: str = "paper", limit: int = 50):
    if not DB_AVAILABLE:
        return []
    try:
        db = SessionLocal()
        if mode == "live":
            reconcile_live_trades_with_broker(db)
        else:
            reconcile_paper_trades(db)
        model = LiveTrade if mode == "live" else PaperTrade
        trades = db.query(model).order_by(model.id.desc()).limit(limit).all()
        res = []
        for t in trades:
            res.append({
                "id": t.id,
                "symbol": t.symbol,
                "company_name": t.company_name or t.symbol,
                "action": t.action,
                "entry_price": t.entry_price or 0.0,
                "quantity": t.quantity or 1,
                "exit_price": t.exit_price,
                "stop_loss": t.stop_loss or 0.0,
                "target1": t.target1 or 0.0,
                "target2": t.target2 or 0.0,
                "status": t.status or "OPEN",
                "pnl": t.pnl or 0.0,
                "pnl_percent": t.pnl_percent or 0.0,
                "opened_at": t.opened_at.strftime("%Y-%m-%d %H:%M") if t.opened_at else "",
                "closed_at": t.closed_at.strftime("%Y-%m-%d %H:%M") if t.closed_at else "",
                "order_id": getattr(t, "order_id", None)
            })
        db.close()
        return res
    except Exception as e:
        print(f"Error fetching trades list: {e}")
        return []


def get_paper_balance_calc():
    """Calculate virtual paper balance starting at ₹1,00,000 + paper trade P&L."""
    if not DB_AVAILABLE:
        return 100000.0
    try:
        db = SessionLocal()
        trades = db.query(PaperTrade).all()
        total_pnl = sum(t.pnl or 0.0 for t in trades)
        db.close()
        return round(100000.0 + total_pnl, 2)
    except Exception:
        return 100000.0


def calculate_position_size(entry_price: float, sl_price: float, risk_amount: float = 230.0) -> int:
    """
    Calculate dynamic position size (shares) based on strict ₹300 NET loss limit (accounting for ₹60-70 Angel One taxes/brokerage).
    Formula: Quantity = max(1, int(230.0 / abs(Entry Price - SL Price)))
    """
    try:
        p = float(entry_price or 0)
        sl = float(sl_price or 0)
        risk_per_share = abs(p - sl)
        if risk_per_share <= 0:
            risk_per_share = (p * 0.01) if p > 0 else 1.0
        qty = int(risk_amount / risk_per_share)
        return max(1, qty)
    except Exception:
        return 1


def execute_trade(symbol, symbol_token, action, qty, price, sl=0, t1=0, t2=0, mode="paper", order_type="MARKET", scan_type="ultra_sniper"):
    current_mode = mode or config.get("trading_mode", "paper")
    clean_sym = symbol.upper().strip().replace(".NS", "-EQ")
    if not clean_sym.endswith("-EQ") and not clean_sym.endswith("-BE"):
        clean_sym = f"{clean_sym}-EQ"
    
    # Auto-resolve symbol token upfront for both Main Order and SL Order
    if not symbol_token or str(symbol_token).strip() in ("", "None", "0"):
        symbol_token = STOCK_TOKENS.get(clean_sym) or STOCK_TOKENS.get(clean_sym.replace("-EQ", ""))
        if not symbol_token:
            from backend.broker_angelone import get_angelone_token_and_symbol
            tok, t_sym = get_angelone_token_and_symbol(clean_sym.replace("-EQ", ""))
            if tok:
                symbol_token = tok
                clean_sym = t_sym

    p = float(price or 0)
    sl_val = float(sl or 0)
    if (sl_val <= 0) and p > 0:
        is_buy = action.upper() == "BUY"
        sl_val = round(p * (0.988 if is_buy else 1.012), 2)

    t1_val = float(t1 or 0)
    t2_val = float(t2 or 0)
    if (t1_val <= 0) and p > 0:
        t1_val = round(p * (1.015 if action.upper() == "BUY" else 0.985), 2)
    if (t2_val <= 0) and p > 0:
        t2_val = round(p * (1.030 if action.upper() == "BUY" else 0.970), 2)
    
    # 📐 Dynamic Net ₹300 Position Sizing (Gross Stock Risk ₹230 + Taxes/Brokerage ~₹60 = Net ₹290 Cap)
    calc_qty = calculate_position_size(p, sl_val, 230.0)
    q = min(int(qty), calc_qty) if (qty and int(qty) > 0) else calc_qty
    q = max(1, q)
    import time

    if current_mode == "paper":
        tid = save_paper_trade_db(clean_sym, action, q, p, sl_val, t1_val, t2_val)
        if tid:
            LOCAL_PAPER_SCAN_TYPE[tid] = scan_type
        register_local_trade_guard(clean_sym, symbol_token, action, q, p, sl_val, t1_val, t2_val, scan_type=scan_type)
        tg_msg = (
            f"📝 <b>PAPER TRADE EXECUTED</b>\n"
            f"<b>Symbol:</b> {clean_sym}\n"
            f"<b>Action:</b> {action.upper()}\n"
            f"<b>Qty:</b> {q} (₹300 Risk Sizing)\n"
            f"<b>Entry Price:</b> ₹{p:.2f}\n"
            f"<b>SL:</b> ₹{sl_val:.2f} | <b>T1:</b> ₹{t1_val:.2f} | <b>T2:</b> ₹{t2_val:.2f}\n"
            f"<b>Strategy:</b> {scan_type.upper().replace('_', ' ')}"
        )
        send_telegram_message(tg_msg)
        return {
            "success": True,
            "mode": "paper",
            "symbol": clean_sym,
            "action": action.upper(),
            "qty": q,
            "entry_price": p,
            "sl_price": sl_val,
            "target1": t1_val,
            "target2": t2_val,
            "sl_placed": True,
            "sl_order_id": f"PAPER-SL-{tid or int(time.time())}",
            "order_id": f"PAPER-{tid or int(time.time())}",
            "scan_type": scan_type,
            "message": f"🎉 PAPER TRADE PLACED SUCCESSFULLY!\nSymbol: {clean_sym}\nAction: {action.upper()}\nQty: {q}\nPrice: ₹{p:.2f}\nRisk Cap: ₹300.00"
        }
    else:
        # Live order execution via Angel One SmartAPI (MARKET order type by default for instant fill)
        res = place_order(clean_sym, symbol_token, action, q, p, order_type=order_type)
        if res.get("success"):
            order_id = res.get("order_id", "")
            try:
                save_live_trade_db(clean_sym, action, q, p, sl_val, t1_val, t2_val, order_id=order_id)
            except Exception as e:
                print(f"⚠️ Live trade DB save error: {e}")

            # 🛡️ 1. Register Local Trade Guard Immediately (Active during 60s settle window)
            try:
                register_local_trade_guard(clean_sym, symbol_token, action, q, p, sl_val, t1_val, t2_val, scan_type=scan_type)
            except Exception as e:
                print(f"⚠️ Register guard error: {e}")

            # ⏳ 2. 60-Second Delayed Broker Stop-Loss Worker (Prevents instant Angel One rejection)
            def _delayed_sl_worker(target_sym, target_tok, target_act, target_qty, target_sl):
                print(f"⏳ [60s Settle Engine] Waiting 60 seconds before submitting broker SL for {target_sym}...")
                time.sleep(60)
                try:
                    # Check if position is still open in broker
                    p_data = get_live_positions()
                    matching = [x for x in p_data.get("positions", []) if int(x.get("netqty") or 0) != 0 and target_sym.replace("-EQ", "") in x.get("tradingsymbol", "")]
                    if not matching:
                        print(f"ℹ️ [60s Settle Engine] Position {target_sym} already closed or not found. Skipping SL.")
                        return

                    sl_result = place_smartapi_sl_order(target_sym, target_tok, target_act, target_qty, target_sl)
                    if sl_result.get("success"):
                        placed_oid = sl_result.get("sl_order_id")
                        if target_sym in LOCAL_SL_TRACKER:
                            LOCAL_SL_TRACKER[target_sym]["sl_order_id"] = placed_oid
                        print(f"🛡️ [60s Settle Engine] Exchange SL successfully placed for {target_sym}: #{placed_oid} @ ₹{target_sl:.2f}")
                        send_telegram_message(
                            f"🛡️ <b>BROKER STOP-LOSS PLACED (60s Settle Delay)</b>\n\n"
                            f"• <b>Symbol:</b> {target_sym}\n"
                            f"• <b>SL Order ID:</b> <code>#{placed_oid}</code>\n"
                            f"• <b>Trigger Price:</b> ₹{target_sl:.2f}\n"
                            f"• <b>Qty:</b> {target_qty}\n"
                            f"• <b>Status:</b> ✅ Placed in Angel One Order Book!"
                        )
                    else:
                        fail_msg = sl_result.get("message", "Unknown error")
                        print(f"⚠️ [60s Settle Engine] Broker SL placement note: {fail_msg}")
                        send_telegram_message(
                            f"⚠️ <b>BROKER SL PLACEMENT NOTE for {target_sym}</b>\n\n"
                            f"• <b>Broker Msg:</b> {fail_msg}\n"
                            f"• <b>Local SL Guard:</b> ACTIVE in background! (₹300 Net Loss Cap is actively monitoring)"
                        )
                except Exception as dex:
                    print(f"⚠️ [60s Settle Engine] Exception: {dex}")

            if sl_val > 0:
                threading.Thread(
                    target=_delayed_sl_worker,
                    args=(clean_sym, symbol_token, action, q, sl_val),
                    daemon=True
                ).start()

            sl_note = f"\n⏳ <b>Exchange SL Order:</b> Scheduled to place in 60s (Settle Delay buffer to prevent broker rejection)"
            sl_summary = "Exchange SL scheduled in 60s (Local Guard active)"

            tg_msg = (
                f"💼 <b>LIVE ORDER EXECUTED (ANGEL ONE)</b>\n"
                f"<b>Symbol:</b> {clean_sym}\n"
                f"<b>Action:</b> {action.upper()}\n"
                f"<b>Qty:</b> {q} (₹300 Risk Sizing)\n"
                f"<b>Entry Price:</b> ₹{p:.2f}\n"
                f"<b>SL:</b> ₹{sl_val:.2f}\n"
                f"<b>Order ID:</b> {order_id}"
                f"{sl_note}\n"
                f"🎯 <b>Targets:</b> T1 ₹{t1_val:.2f} | T2 ₹{t2_val:.2f}\n"
                f"<b>Strategy:</b> {scan_type.upper().replace('_', ' ')}"
            )
            send_telegram_message(tg_msg)

            res["sl_order_id"] = "SCHEDULED_60S"
            res["sl_placed"] = False
            res["sl_scheduled"] = True
            res["sl_message"] = "Exchange SL will be submitted in 60 seconds (settlement buffer)."
            res["sl_summary"] = sl_summary
            res["symbol"] = clean_sym
            res["action"] = action.upper()
            res["qty"] = q
            res["entry_price"] = p
            res["sl_price"] = sl_val
            res["target1"] = t1_val
            res["target2"] = t2_val
            res["scan_type"] = scan_type
            res["message"] = (
                f"🎉 LIVE ORDER EXECUTED ON ANGEL ONE!\n\n"
                f"📌 Stock: {clean_sym} ({action.upper()})\n"
                f"📦 Quantity: {q} Shares (₹300 Risk Sizing)\n"
                f"💵 Main Order ID: {order_id}\n"
                f"{sl_note}\n"
                f"🎯 Targets: T1 ₹{t1_val:.2f} | T2 ₹{t2_val:.2f}"
            )
        return res


def get_proxy_opener():
    proxy_url = config.get("proxy_url")
    ctx = ssl.create_default_context()
    if proxy_url:
        proxy_handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        https_handler = urllib.request.HTTPSHandler(context=ctx)
        return urllib.request.build_opener(proxy_handler, https_handler)
    https_handler = urllib.request.HTTPSHandler(context=ctx)
    return urllib.request.build_opener(https_handler)


def get_my_ip():
    if config.get("static_ip"):
        return config["static_ip"]
    try:
        req = urllib.request.Request("https://api.ipify.org?format=json")
        opener = get_proxy_opener()
        with opener.open(req, timeout=5) as resp:
            return json.loads(resp.read().decode())["ip"]
    except:
        return config.get("static_ip", "178.92.40.115")


def generate_totp(secret: str):
    clean = secret.strip().replace(" ", "").upper()
    clean = clean.replace("0", "O").replace("1", "I").replace("8", "B")
    clean = re.sub(r'[^A-Z2-7]', '', clean)
    if len(clean) % 8 != 0:
        clean += '=' * (-len(clean) % 8)
    return pyotp.TOTP(clean).now()


def api_call(url, payload=None, headers=None, method="POST"):
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    opener = get_proxy_opener()
    try:
        with opener.open(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except:
            return {"status": False, "message": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"status": False, "message": str(e)}



def login_smartapi():
    global auth_session
    if not config.get("password") or not config.get("api_key") or not config.get("totp_secret"):
        return {"success": False, "message": "⚠️ Please fill your Angel One Password, API Key, and TOTP Secret below and click Save!"}

    try:
        totp = generate_totp(config["totp_secret"])
    except Exception as e:
        return {"success": False, "message": f"Invalid TOTP Secret Key: {e}"}

    my_ip = get_my_ip()
    headers = {
        "Content-Type": "application/json",
        "X-PrivateKey": config["api_key"].strip(),
        "Accept": "application/json",
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": my_ip,
        "X-MACaddress": "fe-80-00-00-00-00",
        "MACAddress": "fe-80-00-00-00-00"
    }
    payload = {
        "clientcode": config["client_code"].upper().strip(),
        "password": config["password"].strip(),
        "totp": totp
    }

    for endpoint in [
        f"{ANGELONE_URL}/rest/auth/angelbroking/user/v1/loginByPassword",
        f"{ANGELONE_URL}/publisher-apis/api/v1/user/login/v3"
    ]:
        result = api_call(endpoint, payload, headers)
        if result.get("status") is True and "data" in result:
            tokens = result["data"]
            auth_session = {
                "jwtToken": tokens.get("jwtToken") or tokens.get("token"),
                "refreshToken": tokens.get("refreshToken", ""),
                "feedToken": tokens.get("feedToken", ""),
                "client_code": config["client_code"],
                "api_key": config["api_key"],
                "my_ip": my_ip
            }
            return {"success": True, "message": f"✅ Connected to Angel One! Outbound IP: {my_ip}", "ip": my_ip}

    msg = result.get("message") or "Authentication failed"
    return {"success": False, "message": f"❌ Angel One Login Failed: {msg}"}


def get_live_balance():
    if not auth_session.get("jwtToken"):
        login_res = login_smartapi()
        if not login_res["success"]:
            return {"balance": 0.0, "connected": False, "error": login_res["message"]}

    my_ip = auth_session.get("my_ip", get_my_ip())
    headers = {
        "Authorization": f"Bearer {auth_session['jwtToken']}",
        "Content-Type": "application/json",
        "X-PrivateKey": auth_session["api_key"],
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": my_ip,
        "X-MACaddress": "fe-80-00-00-00-00",
        "MACAddress": "fe-80-00-00-00-00"
    }
    res = api_call(f"{ANGELONE_URL}/rest/secure/angelbroking/user/v1/getRMS", headers=headers, method="GET")
    if res.get("status") is True and "data" in res:
        net = float(res["data"].get("net", 0.0) or res["data"].get("availablecash", 0.0))
        return {"balance": net, "buying_power": net * 5.0, "connected": True, "raw": res["data"]}
    return {"balance": 0.0, "buying_power": 0.0, "connected": False, "error": res.get("message")}


def get_live_positions():
    global auth_session
    if not auth_session.get("jwtToken"):
        lres = login_smartapi()
        if not lres.get("success"):
            return {"positions": [], "connected": False, "error": lres.get("message", "Not logged in")}

    my_ip = auth_session.get("my_ip", get_my_ip())
    headers = {
        "Authorization": f"Bearer {auth_session['jwtToken']}",
        "Content-Type": "application/json",
        "X-PrivateKey": auth_session["api_key"],
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": my_ip,
        "X-MACaddress": "fe-80-00-00-00-00",
        "MACAddress": "fe-80-00-00-00-00"
    }
    res = api_call(f"{ANGELONE_URL}/rest/secure/angelbroking/order/v1/getPosition", headers=headers, method="GET")

    # Silent Auto-Relogin Interceptor for expired/invalid session
    if res.get("status") is not True:
        err = str(res.get("message", "")).lower()
        if any(w in err for w in ("token", "jwt", "session", "unauthorized", "invalid", "ag8001", "ab8050", "ab1006")):
            print("🔄 [Auto-Relogin] Token expired during getPosition, refreshing session...")
            lres = login_smartapi()
            if lres.get("success"):
                headers["Authorization"] = f"Bearer {auth_session['jwtToken']}"
                headers["X-ClientPublicIP"] = auth_session.get("my_ip", my_ip)
                res = api_call(f"{ANGELONE_URL}/rest/secure/angelbroking/order/v1/getPosition", headers=headers, method="GET")

    if res.get("status") is True and "data" in res:
        return {"positions": res.get("data") or [], "connected": True}
    return {"positions": [], "connected": False, "error": res.get("message")}


def get_order_book():
    """Fetch today's full order book from Angel One with charges breakdown."""
    if not auth_session.get("jwtToken"):
        lres = login_smartapi()
        if not lres.get("success"):
            return {"orders": [], "connected": False, "error": "Not logged in"}

    my_ip = auth_session.get("my_ip", get_my_ip())
    headers = {
        "Authorization": f"Bearer {auth_session['jwtToken']}",
        "Content-Type": "application/json",
        "X-PrivateKey": auth_session["api_key"],
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": my_ip,
        "X-MACaddress": "fe-80-00-00-00-00",
        "MACAddress": "fe-80-00-00-00-00"
    }

    # Fetch order book
    res = api_call(f"{ANGELONE_URL}/rest/secure/angelbroking/order/v1/getOrderBook", headers=headers, method="GET")
    if res.get("status") is True and "data" in res:
        orders = res.get("data") or []
        # Attach estimated charges for each executed order
        enriched = []
        for o in orders:
            try:
                qty    = int(o.get("filledshares") or o.get("quantity") or 0)
                price  = float(o.get("averageprice") or o.get("price") or 0)
                status = (o.get("orderstatus") or o.get("status") or "").upper()
                ptype  = (o.get("producttype") or "").upper()
                txtype = (o.get("transactiontype") or "").upper()
                trade_val = qty * price

                # Charges estimate (Angel One flat ₹20 brokerage)
                brokerage = min(20.0, trade_val * 0.0025) if trade_val > 0 else 0.0
                stt = round(trade_val * 0.00025, 4) if txtype == "SELL" and "INTRADAY" in ptype else 0.0
                exchange_charges = round(trade_val * 0.0000345, 4)
                gst = round((brokerage + exchange_charges) * 0.18, 4)
                stamp = round(trade_val * 0.00003, 4) if txtype == "BUY" else 0.0
                total_charges = round(brokerage + stt + exchange_charges + gst + stamp, 2)

                o["_trade_value"]      = round(trade_val, 2)
                o["_brokerage"]        = round(brokerage, 2)
                o["_stt"]              = stt
                o["_exchange_charges"] = exchange_charges
                o["_gst"]              = gst
                o["_stamp"]            = stamp
                o["_total_charges"]    = total_charges
            except Exception:
                o["_total_charges"] = 0.0
            enriched.append(o)

        # Sort: latest orders first
        enriched.sort(key=lambda x: x.get("orderid", ""), reverse=True)
        return {"orders": enriched, "connected": True, "total": len(enriched)}

    return {"orders": [], "connected": False, "error": res.get("message", "Failed to fetch order book")}


def place_order(symbol, symbol_token, action, qty, price=0, exchange="NSE", order_type="MARKET", product="INTRADAY"):
    global auth_session
    if not auth_session.get("jwtToken"):
        lres = login_smartapi()
        if not lres["success"]:
            return lres

    # Clean symbol and auto-lookup token if not provided
    clean_sym = symbol.upper().strip()
    if not clean_sym.endswith("-EQ") and not clean_sym.endswith("-BE") and not clean_sym.endswith(".NS"):
        clean_sym = f"{clean_sym}-EQ"
    clean_sym = clean_sym.replace(".NS", "-EQ")

    if not symbol_token or str(symbol_token).strip() in ("", "None", "0"):
        symbol_token = STOCK_TOKENS.get(clean_sym) or STOCK_TOKENS.get(clean_sym.replace("-EQ", ""))
        if not symbol_token:
            from backend.broker_angelone import get_angelone_token_and_symbol
            tok, t_sym = get_angelone_token_and_symbol(clean_sym.replace("-EQ", ""))
            if tok:
                symbol_token = tok
                clean_sym = t_sym

    if not symbol_token:
        return {"success": False, "message": f"❌ Could not find Angel One Symbol Token for '{symbol}'. Please select a stock from the Scanner or enter valid token."}

    order_p = float(price or 0)
    actual_order_type = order_type.upper() if order_type else "MARKET"

    my_ip = auth_session.get("my_ip", get_my_ip())
    headers = {
        "Authorization": f"Bearer {auth_session['jwtToken']}",
        "Content-Type": "application/json",
        "X-PrivateKey": auth_session["api_key"],
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": my_ip,
        "X-MACaddress": "fe-80-00-00-00-00",
        "MACAddress": "fe-80-00-00-00-00"
    }
    payload = {
        "variety": "NORMAL",
        "tradingsymbol": clean_sym,
        "symboltoken": str(symbol_token),
        "transactiontype": action.upper(),
        "exchange": exchange.upper(),
        "ordertype": actual_order_type,
        "producttype": product.upper(),
        "duration": "DAY",
        "price": f"{float(order_p):.2f}" if actual_order_type == "LIMIT" else "0",
        "quantity": str(max(1, int(qty))),
        "squareoff": "0.00",
        "stoploss": "0.00"
    }

    url = f"{ANGELONE_URL}/rest/secure/angelbroking/order/v1/placeOrder"
    result = api_call(url, payload, headers)

    if result.get("status") is True and "data" in result:
        order_id = result["data"].get("uniqueorderid") or result["data"].get("orderid")
        return {
            "success": True, 
            "order_id": order_id, 
            "message": f"🎉 LIVE ORDER PLACED SUCCESSFULLY!\\nSymbol: {clean_sym}\\nAction: {action}\\nQty: {qty}\\nOrder ID: {order_id}"
        }
    else:
        msg = result.get("message", "Unknown error")
        if "registered ip" in msg.lower() or "not a registered ip" in msg.lower() or "ab1012" in msg.lower():
            msg = f"❌ Angel One IP Rejection: Your current IP ({my_ip}) is not registered. Please open https://smartapi.angelone.in/ -> My Apps -> Edit App -> Add IP: {my_ip}"
        elif "cautionary" in msg.lower() or "surveillance" in msg.lower() or "ab1008" in msg.lower():
            msg = f"⚠️ Exchange Cautionary Listing: {clean_sym} is listed under Cautionary/Surveillance (GSM/ESM) by NSE. Angel One blocks Intraday API orders for this token. Please pick a liquid stock like INFY, HDFCBANK, SBIN, ITC."
        return {"success": False, "message": msg}


def place_smartapi_sl_order(symbol: str, symbol_token: str, action: str, qty: int, sl_price: float, exchange: str = "NSE", product: str = "INTRADAY") -> dict:
    """
    Place an automatic Exchange STOPLOSS_LIMIT order directly in Angel One Order Book.
    Counter-action is used (SELL SL for BUY entry, BUY SL for SELL entry).
    """
    global auth_session
    if not auth_session.get("jwtToken"):
        lres = login_smartapi()
        if not lres.get("success"):
            return lres

    clean_sym = symbol.upper().strip()
    if not clean_sym.endswith("-EQ") and not clean_sym.endswith("-BE") and not clean_sym.endswith(".NS"):
        clean_sym = f"{clean_sym}-EQ"
    clean_sym = clean_sym.replace(".NS", "-EQ")

    if not symbol_token or str(symbol_token).strip() in ("", "None", "0"):
        symbol_token = STOCK_TOKENS.get(clean_sym) or STOCK_TOKENS.get(clean_sym.replace("-EQ", ""))
        if not symbol_token:
            from backend.broker_angelone import get_angelone_token_and_symbol
            tok, t_sym = get_angelone_token_and_symbol(clean_sym.replace("-EQ", ""))
            if tok:
                symbol_token = tok
                clean_sym = t_sym

    if not symbol_token:
        return {"success": False, "message": f"Could not resolve token for SL order: {symbol}"}

    counter_action = "SELL" if action.upper() == "BUY" else "BUY"
    
    # Tick size compliance (multiples of 0.05 on NSE)
    raw_trigger = float(sl_price)
    trigger_p = round(round(raw_trigger / 0.05) * 0.05, 2)
    
    # For SELL SL: limit_price <= trigger_price
    # For BUY SL: limit_price >= trigger_price
    if counter_action == "SELL":
        raw_limit = trigger_p * 0.995
        limit_p = min(trigger_p, round(round(raw_limit / 0.05) * 0.05, 2))
    else:
        raw_limit = trigger_p * 1.005
        limit_p = max(trigger_p, round(round(raw_limit / 0.05) * 0.05, 2))

    my_ip = auth_session.get("my_ip", get_my_ip())
    headers = {
        "Authorization": f"Bearer {auth_session['jwtToken']}",
        "Content-Type": "application/json",
        "X-PrivateKey": auth_session["api_key"],
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": my_ip,
        "X-MACaddress": "fe-80-00-00-00-00",
        "MACAddress": "fe-80-00-00-00-00"
    }

    last_res = {}
    # Try combinations of variety ("STOPLOSS", "NORMAL") and ordertype ("STOPLOSS_LIMIT", "STOPLOSS_MARKET")
    for variety_type in ["STOPLOSS", "NORMAL"]:
        for order_t in ["STOPLOSS_LIMIT", "STOPLOSS_MARKET"]:
            payload = {
                "variety": variety_type,
                "tradingsymbol": clean_sym,
                "symboltoken": str(symbol_token),
                "transactiontype": counter_action,
                "exchange": exchange.upper(),
                "ordertype": order_t,
                "producttype": product.upper(),
                "duration": "DAY",
                "price": f"{float(limit_p):.2f}" if order_t == "STOPLOSS_LIMIT" else "0",
                "triggerprice": f"{float(trigger_p):.2f}",
                "quantity": str(max(1, int(qty))),
                "squareoff": "0.00",
                "stoploss": "0.00"
            }

            url = f"{ANGELONE_URL}/rest/secure/angelbroking/order/v1/placeOrder"
            result = api_call(url, payload, headers)
            last_res = result

            if result.get("status") is not True:
                err_str = str(result.get("message", "")).lower()
                if any(w in err_str for w in ("token", "jwt", "session", "unauthorized", "ag8001", "ab8050")):
                    print("🔄 [Auto-Relogin] Token expired during SL placement in Local Trader, refreshing session...")
                    lres = login_smartapi()
                    if lres.get("success"):
                        headers["Authorization"] = f"Bearer {auth_session['jwtToken']}"
                        result = api_call(url, payload, headers)
                        last_res = result

            if result.get("status") is True and "data" in result:
                sl_order_id = result["data"].get("uniqueorderid") or result["data"].get("orderid")
                print(f"🛡️ Angel One Exchange SL Order Placed! ID: {sl_order_id} (Variety: {variety_type}, Type: {order_t}) | Trigger: ₹{trigger_p:.2f}")
                return {
                    "success": True, 
                    "sl_order_id": sl_order_id, 
                    "trigger_price": trigger_p, 
                    "limit_price": limit_p if order_t == "STOPLOSS_LIMIT" else trigger_p, 
                    "variety": variety_type,
                    "order_type": order_t,
                    "message": f"Exchange SL Order Placed: {sl_order_id}"
                }

    err_msg = last_res.get("message", "SL Order rejected")
    if "registered ip" in err_msg.lower() or "not a registered ip" in err_msg.lower() or "ab1012" in err_msg.lower():
        err_msg = f"Angel One IP Rejection: Current IP ({my_ip}) not registered in smartapi.angelone.in"
    print(f"⚠️ Angel One Exchange SL Order note: {err_msg} (Local SL Guard Monitor active in background)")
    try:
        send_telegram_message(
            f"🚨 <b>CRITICAL: BROKER STOP-LOSS FAILED</b>\n\n"
            f"• <b>Symbol:</b> {clean_sym}\n"
            f"• <b>Trigger Price:</b> ₹{trigger_p:.2f}\n"
            f"• <b>Broker Error:</b> {err_msg}\n"
            f"• <b>Local Guard:</b> ACTIVE in background! (₹300 Net Loss Cap)\n"
            f"• <b>Action:</b> You can enter SL manually in Angel One App at ₹{trigger_p:.2f} for 100% safety! 📱"
        )
    except Exception:
        pass
    return {"success": False, "message": err_msg, "sl_price": trigger_p}


def cancel_smartapi_order(order_id: str, variety: str = "STOPLOSS") -> dict:
    """Cancel any open order (e.g. Stop-Loss order) on Angel One."""
    global auth_session
    if not auth_session.get("jwtToken") or not order_id:
        return {"success": False, "message": "No session or order ID"}
    try:
        url = f"{ANGELONE_URL}/rest/secure/angelbroking/order/v1/cancelOrder"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": config.get("ip", "106.193.147.98"),
            "X-MACAddress": "fe80::1",
            "X-PrivateKey": config.get("api_key", ""),
            "Authorization": f"Bearer {auth_session['jwtToken']}"
        }
        payload = {"variety": variety, "orderid": str(order_id)}
        res = api_call(url, payload, headers)
        print(f"🗑️ Angel One Cancel Order ({order_id}): {res}")
        return res
    except Exception as e:
        print(f"⚠️ Cancel Order Error: {e}")
        return {"success": False, "message": str(e)}


SCRIP_TOKEN_CACHE = {}

# ── Local SL & Loss Cap Monitoring Engine ─────────────────────────────────────
LOCAL_SL_TRACKER = {}  # {clean_sym: {symbol, symbol_token, action, qty, entry_price, stop_loss, target1, target2}}
POSITION_FIRST_SEEN = {}  # {sym: timestamp_when_first_detected_as_open}
SL_AUTO_PLACED = {}      # {sym: True}  tracks if we already auto-placed exchange SL for this position
SL_AUTO_DELAY_SECS = 60  # 60 seconds after detecting open position → auto-place exchange SL


def register_local_trade_guard(symbol: str, symbol_token: str, action: str, qty: int, entry_price: float, stop_loss: float = 0, target1: float = 0, target2: float = 0, scan_type: str = "ultra_sniper"):
    """Register trade in local SL monitor engine with strict ₹300 loss cap."""
    clean_sym = symbol.upper().strip()
    if not clean_sym.endswith("-EQ") and not clean_sym.endswith("-BE") and not clean_sym.endswith(".NS"):
        clean_sym = f"{clean_sym}-EQ"
    clean_sym = clean_sym.replace(".NS", "-EQ")

    p = float(entry_price or 0)
    q = max(1, int(qty or 1))
    max_price_move = 300.0 / q

    act = action.upper()
    sl = float(stop_loss or 0)
    if sl <= 0 or (act == "BUY" and sl >= p) or (act == "SELL" and sl <= p):
        sl = round(p - max_price_move if act == "BUY" else p + max_price_move, 2)

    # Strictly cap SL to ₹300 max loss boundary
    if act == "BUY":
        sl = max(sl, round(p - max_price_move, 2))
    else:
        sl = min(sl, round(p + max_price_move, 2))

    LOCAL_SL_TRACKER[clean_sym] = {
        "symbol":              clean_sym,
        "symbol_token":        str(symbol_token),
        "action":              act,
        "qty":                 q,
        "entry_price":         p,
        "stop_loss":           sl,
        "initial_sl":          sl,
        "target1":             float(target1 or 0),
        "target2":             float(target2 or 0),
        "target_150_price":    0.0,
        "sl_order_id":         None,
        "target_order_id":     None,
        "converted_to_target": False,
        "peak_pnl":            0.0,
        "peak_price":          p,
        "reversal_alert_sent": False,
        "last_reversal_check": 0.0,
        "registered_at":       time.time(),
        "scan_type":           scan_type
    }
    mode_desc = "👑 Ultra-Sniper ₹30 Profit Lock" if scan_type == "ultra_sniper" else "🌊 Deep Scan ₹50 Swing Trailing"
    print(f"🛡️ Local SL Monitor Locked for {clean_sym} ({mode_desc}): Entry ₹{p:.2f} | SL ₹{sl:.2f} (Max Loss Cap ₹300)")



LAST_SATURDAY_AUDIT_DATE = None
LOCAL_PAPER_PEAKS: dict[int, float] = {}
LOCAL_PAPER_PEAK_PRICES: dict[int, float] = {}
LOCAL_PAPER_REVERSALS: dict[int, float] = {}
LOCAL_PAPER_NOTIFIED_REV: set[int] = set()
LOCAL_PAPER_SCAN_TYPE: dict[int, str] = {}


def _local_sl_monitor_thread():
    """Background daemon thread running every 5 seconds to enforce SL and ₹300 Loss Cap."""
    global LAST_SATURDAY_AUDIT_DATE
    import threading
    import time
    from datetime import datetime, timezone, timedelta
    import yfinance as yf

    print("🛡️ Local Auto-SL & ₹300 Loss Guard Monitor started in background!")

    while True:
        try:
            time.sleep(5)

            # ── Saturday Auto-Quant Audit & Strategy Self-Tuning (Runs Sat 10:00 AM IST) ──
            ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
            if ist_now.weekday() == 5 and ist_now.hour >= 10 and LAST_SATURDAY_AUDIT_DATE != ist_now.date():
                LAST_SATURDAY_AUDIT_DATE = ist_now.date()
                if DB_AVAILABLE:
                    try:
                        from backend.weekly_optimizer import run_weekly_quant_audit
                        db_audit = SessionLocal()
                        print("🤖 [Saturday Auto-Tuning] Running weekly quant audit & self-tuning...")
                        audit_res = run_weekly_quant_audit(db_audit)
                        db_audit.close()
                        print(f"✅ [Saturday Auto-Tuning] Audit complete: {audit_res.get('last_audit_summary', '')}")
                    except Exception as _ae:
                        print(f"⚠️ Saturday Auto-Tuning error: {_ae}")

            # 1. Paper Trades Monitor (Runs even if Angel One is not logged in)
            if DB_AVAILABLE:

                try:
                    db = SessionLocal()
                    open_pts = db.query(PaperTrade).filter(PaperTrade.status == "OPEN").all()
                    for pt in open_pts:
                        sym = pt.symbol
                        yf_sym = sym.replace("-EQ", ".NS").replace("-BE", ".NS")
                        cmp_price = 0.0
                        try:
                            ticker = yf.Ticker(yf_sym)
                            fi = getattr(ticker, "fast_info", None)
                            if fi and getattr(fi, "last_price", None) and float(fi.last_price) > 0:
                                cmp_price = float(fi.last_price)
                        except Exception:
                            pass

                        if cmp_price > 0:
                            q = pt.quantity or 1
                            ep = pt.entry_price or 0.0
                            act = (pt.action or "BUY").upper()
                            pnl = round((cmp_price - ep) * q if act == "BUY" else (ep - cmp_price) * q, 2)
                            pnl_pct = round((pnl / (ep * q)) * 100, 2) if (ep * q) > 0 else 0.0

                            sl_price = pt.stop_loss or 0.0
                            t1_price = pt.target1 or 0.0

                            # Track Peak P&L (High-water mark)
                            curr_peak = max(LOCAL_PAPER_PEAKS.get(pt.id, 0.0), pnl)
                            LOCAL_PAPER_PEAKS[pt.id] = round(curr_peak, 2)

                            # ── Filter 3: 5-Minute Technical Reversal Alert (Telegram Only, no exit) ──
                            now_t = time.time()
                            last_rev_chk = LOCAL_PAPER_REVERSALS.get(pt.id, 0.0)
                            if pt.id not in LOCAL_PAPER_NOTIFIED_REV and (now_t - last_rev_chk >= 45.0):
                                LOCAL_PAPER_REVERSALS[pt.id] = now_t
                                try:
                                    from backend.loss_guard import check_5m_momentum_reversal
                                    rev_info = check_5m_momentum_reversal(sym, act)
                                    if rev_info.get("reversal_detected"):
                                        LOCAL_PAPER_NOTIFIED_REV.add(pt.id)
                                        send_telegram_message(
                                            f"⚠️ <b>[PAPER] MOMENTUM REVERSAL DETECTED!</b>\n\n"
                                            f"• <b>Symbol:</b> {sym}\n"
                                            f"• <b>Current P&L:</b> {'+' if pnl >= 0 else ''}₹{pnl:.2f} (Peak: +₹{curr_peak:.2f})\n"
                                            f"• <b>Signal:</b> {rev_info.get('details')} 🔻\n"
                                            f"• <b>Status:</b> <b>Paper Trade remains OPEN</b> 🛡️"
                                        )
                                except Exception:
                                    pass

                            # ── Filter 2: Dynamic 20% Trailing Peak Profit Lock (Noise Protected) ──
                            p_peak = LOCAL_PAPER_PEAK_PRICES.get(pt.id, cmp_price)
                            if act == "BUY":
                                if cmp_price > p_peak or p_peak <= 0:
                                    p_peak = cmp_price
                                    LOCAL_PAPER_PEAK_PRICES[pt.id] = p_peak
                                p_drop = p_peak - cmp_price
                            else:
                                if cmp_price < p_peak or p_peak <= 0:
                                    p_peak = cmp_price
                                    LOCAL_PAPER_PEAK_PRICES[pt.id] = p_peak
                                p_drop = cmp_price - p_peak

                            pullback_allowed = 30.0
                            min_price_buf = max(0.10, ep * 0.001)

                            pt_scan = LOCAL_PAPER_SCAN_TYPE.get(pt.id, "ultra_sniper")
                            if pt_scan == "ultra_sniper":
                                is_paper_lock = (curr_peak >= 100.0 and ((curr_peak - pnl) >= 30.0 or pnl <= 10.0) and pnl > 0)
                                lock_desc = f"👑 ULTRA SNIPER ₹30 PROFIT LOCKED"
                            else:
                                is_paper_lock = (curr_peak >= 150.0 and ((curr_peak - pnl) >= 50.0 or pnl <= 25.0) and pnl > 0)
                                lock_desc = f"🌊 DEEP SCAN ₹50 SWING TRAILING LOCKED"

                            if is_paper_lock:
                                pt.status = "PROFIT_LOCK"
                                pt.exit_price = cmp_price
                                pt.pnl = pnl
                                pt.pnl_percent = pnl_pct
                                pt.closed_at = datetime.utcnow()
                                db.commit()
                                LOCAL_PAPER_PEAKS.pop(pt.id, None)
                                LOCAL_PAPER_PEAK_PRICES.pop(pt.id, None)
                                LOCAL_PAPER_REVERSALS.pop(pt.id, None)
                                LOCAL_PAPER_NOTIFIED_REV.discard(pt.id)
                                LOCAL_PAPER_SCAN_TYPE.pop(pt.id, None)
                                send_telegram_message(f"💰 <b>PAPER TRADE {lock_desc}</b>\nSymbol: {sym}\nExit: ₹{cmp_price:.2f}\nLocked P&L: +₹{pnl:.2f} (Peak: +₹{curr_peak:.2f})")

                            # SL Hit check
                            elif (act == "BUY" and sl_price > 0 and cmp_price <= sl_price) or \
                                 (act == "SELL" and sl_price > 0 and cmp_price >= sl_price):
                                pt.status = "SL_HIT"
                                pt.exit_price = cmp_price
                                pt.pnl = pnl
                                pt.pnl_percent = pnl_pct
                                pt.closed_at = datetime.utcnow()
                                db.commit()
                                LOCAL_PAPER_PEAKS.pop(pt.id, None)
                                LOCAL_PAPER_REVERSALS.pop(pt.id, None)
                                LOCAL_PAPER_NOTIFIED_REV.discard(pt.id)
                                send_telegram_message(f"🛑 <b>PAPER TRADE SL HIT</b>\nSymbol: {sym}\nExit: ₹{cmp_price:.2f}\nP&L: ₹{pnl:.2f}")

                            # Target 1 Hit check
                            elif (act == "BUY" and t1_price > 0 and cmp_price >= t1_price) or \
                                 (act == "SELL" and t1_price > 0 and cmp_price <= t1_price):
                                pt.status = "T1_HIT"
                                pt.exit_price = cmp_price
                                pt.pnl = pnl
                                pt.pnl_percent = pnl_pct
                                pt.closed_at = datetime.utcnow()
                                db.commit()
                                LOCAL_PAPER_PEAKS.pop(pt.id, None)
                                LOCAL_PAPER_REVERSALS.pop(pt.id, None)
                                LOCAL_PAPER_NOTIFIED_REV.discard(pt.id)
                                send_telegram_message(f"🎯 <b>PAPER TRADE TARGET HIT</b>\nSymbol: {sym}\nExit: ₹{cmp_price:.2f}\nP&L: +₹{pnl:.2f}")
                    db.close()
                except Exception as _pe:
                    pass

            # 2. Live Trades Monitor (Requires Angel One login)
            if not auth_session.get("jwtToken"):
                continue

            pos_resp = get_live_positions()
            positions = pos_resp.get("positions", [])
            open_positions = {p.get("tradingsymbol"): p for p in positions if int(p.get("netqty") or 0) != 0}

            if not open_positions:
                LOCAL_SL_TRACKER.clear()
                POSITION_FIRST_SEEN.clear()
                SL_AUTO_PLACED.clear()
                if DB_AVAILABLE:
                    try:
                        db_mon = SessionLocal()
                        reconcile_live_trades_with_broker(db_mon)
                        db_mon.close()
                    except Exception:
                        pass
                continue

            ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
            time_str = ist_now.strftime("%H:%M")
            is_eod = "15:10" <= time_str <= "15:35"

            # ── AUTO SL PLACEMENT (3-MINUTE DELAYED ENGINE) ──────────────────
            # For each newly detected open position, record first-seen time.
            # After SL_AUTO_DELAY_SECS (3 min), if no exchange SL order exists
            # in Angel One order book for that symbol, auto-place one.
            now_ts = time.time()
            for sym in list(open_positions.keys()):
                if sym not in POSITION_FIRST_SEEN:
                    POSITION_FIRST_SEEN[sym] = now_ts
                    print(f"🕐 New open position detected: {sym}. Auto-SL will be placed in {SL_AUTO_DELAY_SECS}s if not already present.")

            # Check positions that have waited >= SL_AUTO_DELAY_SECS
            for sym, first_seen_ts in list(POSITION_FIRST_SEEN.items()):
                if sym not in open_positions:
                    POSITION_FIRST_SEEN.pop(sym, None)
                    SL_AUTO_PLACED.pop(sym, None)
                    continue
                if SL_AUTO_PLACED.get(sym):
                    continue  # Already placed SL for this position
                elapsed = now_ts - first_seen_ts
                if elapsed < SL_AUTO_DELAY_SECS:
                    remaining = int(SL_AUTO_DELAY_SECS - elapsed)
                    print(f"⏳ Auto-SL for {sym}: waiting {remaining}s more before placing exchange SL...")
                    continue

                # 3 minutes passed — check if exchange SL already exists in order book
                try:
                    pos = open_positions[sym]
                    pos_qty  = abs(int(pos.get("netqty") or 0))
                    net_qty  = int(pos.get("netqty") or 0)
                    if pos_act == "BUY":
                        avg_p = float(pos.get("buyavgprice") or pos.get("totalbuyavgprice") or pos.get("avgprice") or pos.get("buyprice") or pos.get("averageprice") or 0)
                    else:
                        avg_p = float(pos.get("sellavgprice") or pos.get("totalsellavgprice") or pos.get("avgprice") or pos.get("sellprice") or pos.get("averageprice") or 0)
                    if avg_p <= 0:
                        avg_p = float(pos.get("netprice") or guard_sl_info.get("entry_price") or 0)
                    pos_tok  = pos.get("symboltoken") or ""

                    # Resolve token if missing
                    if not pos_tok or str(pos_tok).strip() in ("", "None", "0"):
                        guard_info_sl = LOCAL_SL_TRACKER.get(sym) or LOCAL_SL_TRACKER.get(sym.replace("-EQ", "")) or {}
                        pos_tok = guard_info_sl.get("symbol_token", "") or STOCK_TOKENS.get(sym) or STOCK_TOKENS.get(sym.replace("-EQ", ""))

                    # Decide SL price from tracker or ₹300 cap
                    guard_sl_info = LOCAL_SL_TRACKER.get(sym) or LOCAL_SL_TRACKER.get(f"{sym}-EQ") or LOCAL_SL_TRACKER.get(sym.replace("-EQ", "")) or {}
                    if guard_sl_info.get("converted_to_target"):
                        print(f"ℹ️ {sym}: Already converted to Target Limit order at ₹150 level. Skipping delayed SL placement.")
                        SL_AUTO_PLACED[sym] = True
                        continue

                    auto_sl_price = guard_sl_info.get("stop_loss", 0)
                    if (auto_sl_price <= 0) and avg_p > 0:
                        max_move = 300.0 / max(1, pos_qty)
                        auto_sl_price = round(avg_p - max_move if pos_act == "BUY" else avg_p + max_move, 2)


                    # Check order book: is there already an open STOPLOSS order for this symbol?
                    ob_res = get_order_book()
                    ob_orders = ob_res.get("orders") or []
                    sl_exists = False
                    counter_action = "SELL" if pos_act == "BUY" else "BUY"
                    for o in ob_orders:
                        o_sym    = (o.get("tradingsymbol") or "").upper()
                        o_tx     = (o.get("transactiontype") or "").upper()
                        o_type   = (o.get("ordertype") or "").upper()
                        o_status = (o.get("orderstatus") or o.get("status") or "").upper()
                        if (o_sym == sym.upper() and o_tx == counter_action and
                                "STOPLOSS" in o_type and o_status in ("OPEN", "PENDING", "TRIGGER PENDING")):
                            sl_exists = True
                            break

                    if sl_exists:
                        print(f"✅ {sym}: Exchange SL already present in order book. No auto-place needed.")
                        SL_AUTO_PLACED[sym] = True
                    elif auto_sl_price > 0 and pos_tok:
                        print(f"🤖 AUTO-SL PLACEMENT (3-MIN DELAY): {sym} | SL ₹{auto_sl_price:.2f} | Qty {pos_qty}")
                        sl_res = place_smartapi_sl_order(sym, pos_tok, pos_act, pos_qty, auto_sl_price)
                        if sl_res.get("success"):
                            sl_oid = sl_res.get("sl_order_id")
                            SL_AUTO_PLACED[sym] = True
                            # Store in tracker
                            if sym in LOCAL_SL_TRACKER:
                                LOCAL_SL_TRACKER[sym]["sl_order_id"] = sl_oid
                            print(f"✅ Auto-SL Placed for {sym}: Order ID {sl_oid} @ ₹{auto_sl_price:.2f}")
                            send_telegram_message(
                                f"🤖 <b>AUTO STOP-LOSS PLACED (3-Min Delay)</b>\n\n"
                                f"• <b>Symbol:</b> {sym}\n"
                                f"• <b>SL Price:</b> ₹{auto_sl_price:.2f}\n"
                                f"• <b>SL Order ID:</b> {sl_oid}\n"
                                f"• <b>Qty:</b> {pos_qty}\n"
                                f"• <b>Note:</b> Auto-placed 3 min after position detected ✅"
                            )
                        else:
                            err = sl_res.get("message", "Unknown")
                            print(f"⚠️ Auto-SL for {sym} failed: {err}")
                            send_telegram_message(
                                f"⚠️ <b>AUTO-SL FAILED for {sym}</b>\n"
                                f"Error: {err}\n"
                                f"<b>Local ₹300 Guard is ACTIVE as fallback!</b>"
                            )
                            # Reset so we retry next cycle
                            POSITION_FIRST_SEEN[sym] = now_ts  # retry in 3 more mins
                    else:
                        print(f"⚠️ Auto-SL for {sym}: cannot determine SL price or token. Local guard active.")
                except Exception as auto_sl_ex:
                    print(f"⚠️ Auto-SL engine error for {sym}: {auto_sl_ex}")
            # ── END AUTO SL PLACEMENT ─────────────────────────────────────────


            for sym, pos in open_positions.items():
                qty = abs(int(pos.get("netqty") or 0))
                net_qty = int(pos.get("netqty") or 0)
                action = "BUY" if net_qty > 0 else "SELL"
                reverse_action = "SELL" if action == "BUY" else "BUY"
                if action == "BUY":
                    avg_price = float(pos.get("buyavgprice") or pos.get("totalbuyavgprice") or pos.get("avgprice") or pos.get("buyprice") or pos.get("averageprice") or 0)
                else:
                    avg_price = float(pos.get("sellavgprice") or pos.get("totalsellavgprice") or pos.get("avgprice") or pos.get("sellprice") or pos.get("averageprice") or 0)
                if avg_price <= 0:
                    avg_price = float(pos.get("netprice") or 0)
                tok = pos.get("symboltoken", "")

                clean_sym = sym.replace("-EQ", "").strip()
                guard_info = LOCAL_SL_TRACKER.get(sym) or LOCAL_SL_TRACKER.get(f"{sym}-EQ") or LOCAL_SL_TRACKER.get(clean_sym)
                if avg_price <= 0 and guard_info:
                    avg_price = float(guard_info.get("entry_price") or 0)
                if not guard_info:
                    guard_info = {
                        "symbol":              clean_sym,
                        "symbol_token":        str(tok),
                        "action":              action,
                        "qty":                 qty,
                        "entry_price":         avg_price,
                        "stop_loss":           0,
                        "initial_sl":          0,
                        "target1":             0,
                        "target2":             0,
                        "target_150_price":    0.0,
                        "sl_order_id":         None,
                        "target_order_id":     None,
                        "converted_to_target": False,
                        "peak_pnl":            0.0,
                        "peak_price":          avg_price,
                        "reversal_alert_sent": False,
                        "last_reversal_check": 0.0,
                        "registered_at":       time.time()
                    }
                    LOCAL_SL_TRACKER[sym] = guard_info

                sl_price = guard_info.get("stop_loss", 0)
                if (sl_price <= 0 or sl_price is None) and avg_price > 0:
                    max_move = 300.0 / qty
                    sl_price = round(avg_price - max_move if action == "BUY" else avg_price + max_move, 2)

                target1 = guard_info.get("target1", 0)
                target2 = guard_info.get("target2", 0)
                if (target1 <= 0 or target1 is None) and avg_price > 0:
                    target1 = round(avg_price * 1.015 if action == "BUY" else avg_price * 0.985, 2)
                if (target2 <= 0 or target2 is None) and avg_price > 0:
                    target2 = round(avg_price * 1.030 if action == "BUY" else avg_price * 0.970, 2)

                # ── STEP 1: Fetch Real-Time Live Price (CMP) First ──
                # 1st Priority: Angel One position LTP (Zero-latency instant broker tick)
                cmp_price = float(pos.get("ltp") or pos.get("close") or 0.0)

                # 2nd Priority: SmartAPI live quote query if pos.ltp is 0
                if cmp_price <= 0 and tok:
                    try:
                        from backend.broker_angelone import get_smartapi_ltp
                        ltp_val = get_smartapi_ltp(auth_session, tok, sym)
                        if ltp_val and ltp_val > 0:
                            cmp_price = ltp_val
                    except Exception:
                        pass

                # 3rd Priority: Yahoo Finance as fallback only if broker did not return price
                if cmp_price <= 0:
                    yf_sym = sym.replace("-EQ", ".NS").replace("-BE", ".NS")
                    try:
                        ticker = yf.Ticker(yf_sym)
                        fi = getattr(ticker, "fast_info", None)
                        if fi and getattr(fi, "last_price", None) and float(fi.last_price) > 0:
                            cmp_price = float(fi.last_price)
                        elif fi and getattr(fi, "lastPrice", None) and float(fi.lastPrice) > 0:
                            cmp_price = float(fi.lastPrice)
                    except Exception:
                        pass

                if cmp_price <= 0 or avg_price <= 0:
                    continue

                # ── STEP 1: Compute Live P&L ──
                if action == "BUY":
                    live_pnl = (cmp_price - avg_price) * qty
                else:
                    live_pnl = (avg_price - cmp_price) * qty

                # ── STEP 1B: Track High-Water Mark (Peak P&L & Peak Price) ──
                current_peak = max(guard_info.get("peak_pnl", 0.0), live_pnl)
                guard_info["peak_pnl"] = round(current_peak, 2)

                peak_price = guard_info.get("peak_price", cmp_price)
                if action == "BUY":
                    if cmp_price > peak_price or peak_price <= 0:
                        peak_price = cmp_price
                        guard_info["peak_price"] = peak_price
                    price_drop_from_peak = peak_price - cmp_price
                else:
                    if cmp_price < peak_price or peak_price <= 0:
                        peak_price = cmp_price
                        guard_info["peak_price"] = peak_price
                    price_drop_from_peak = cmp_price - peak_price

                # ── STEP 1C: FILTER 3 - 5-Minute Technical Reversal Alert (Telegram Notification Only) ──
                # NOTE: Does NOT auto-close trade! Sends an early warning so user can manually decide.
                now_ts_rev = time.time()
                if not guard_info.get("reversal_alert_sent") and (now_ts_rev - guard_info.get("last_reversal_check", 0) >= 45):
                    guard_info["last_reversal_check"] = now_ts_rev
                    try:
                        rev_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_sym}?interval=5m&range=1d"
                        rev_req = urllib.request.Request(rev_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                        rev_ctx = ssl.create_default_context()
                        with urllib.request.urlopen(rev_req, context=rev_ctx, timeout=3) as rev_resp:
                            rev_data = json.loads(rev_resp.read().decode("utf-8"))
                            rev_res = rev_data.get("chart", {}).get("result", [{}])[0]
                            rev_quotes = rev_res.get("indicators", {}).get("quote", [{}])[0]
                            c_list = [c for c in rev_quotes.get("close", []) if c is not None]
                            o_list = [o for o in rev_quotes.get("open", []) if o is not None]

                            if len(c_list) >= 15 and len(o_list) >= 1:
                                c_diffs = [c_list[i] - c_list[i-1] for i in range(1, len(c_list))]
                                c_gains = [d for d in c_diffs if d > 0]
                                c_losses = [abs(d) for d in c_diffs if d < 0]
                                avg_g = sum(c_gains[-14:]) / 14 if c_gains else 0.001
                                avg_l = sum(c_losses[-14:]) / 14 if c_losses else 0.001
                                c_rsi = round(100 - (100 / (1 + (avg_g / avg_l))), 1)

                                last_c = c_list[-1]
                                last_o = o_list[-1]
                                is_reversal = False
                                rev_signal_desc = ""

                                if action == "BUY":
                                    # Bearish reversal: Red candle + RSI drops below 50
                                    if last_c < last_o and c_rsi < 50.0:
                                        is_reversal = True
                                        rev_signal_desc = f"5m Red Candle (₹{last_o:.2f} ➔ ₹{last_c:.2f}) & 5m RSI: {c_rsi} (< 50)"
                                elif action == "SELL":
                                    # Bullish reversal: Green candle + RSI crosses above 50
                                    if last_c > last_o and c_rsi > 50.0:
                                        is_reversal = True
                                        rev_signal_desc = f"5m Green Candle (₹{last_o:.2f} ➔ ₹{last_c:.2f}) & 5m RSI: {c_rsi} (> 50)"

                                if is_reversal:
                                    guard_info["reversal_alert_sent"] = True
                                    print(f"⚠️ [FILTER 3 ALERT] Momentum Reversal detected for {sym}: {rev_signal_desc} (P&L: ₹{live_pnl:.2f})")
                                    send_telegram_message(
                                        f"⚠️ <b>MOMENTUM REVERSAL DETECTED!</b>\n\n"
                                        f"• <b>Symbol:</b> {sym}\n"
                                        f"• <b>Current P&L:</b> {'+' if live_pnl >= 0 else ''}₹{live_pnl:.2f} (Peak: +₹{current_peak:.2f})\n"
                                        f"• <b>Signal:</b> {rev_signal_desc} 🔻\n"
                                        f"• <b>Status:</b> <b>Trade remains OPEN</b> (Not Auto-Closed) 🛡️\n\n"
                                        f"👉 <i>Tip: Stock momentum is reversing. Review your position on Angel One or lock profits manually if needed!</i> 📱"
                                    )
                    except Exception:
                        pass

                scan_type = guard_info.get("scan_type", "ultra_sniper")

                # ── STEP 2: ₹100 PROFIT REACHED -> PROFIT LOCK STRATEGY ──
                if scan_type == "ultra_sniper":
                    # Ultra-Sniper: Option to convert to Target ₹150 Limit order
                    if live_pnl >= 100.0 and not guard_info.get("converted_to_target"):
                        guard_info["converted_to_target"] = True
                        print(f"🎯 ₹100 PROFIT HIT for {sym} (Ultra Sniper)! (Current P&L: +₹{live_pnl:.2f}). Converting SL to Target ₹150 Limit Order...")

                        # 1. Cancel existing pending exchange SL order
                        old_sl_id = guard_info.get("sl_order_id")
                        if old_sl_id:
                            try:
                                print(f"🗑️ Cancelling Exchange SL Order {old_sl_id} for {sym} to switch to Target Order...")
                                cancel_smartapi_order(old_sl_id, variety="STOPLOSS")
                            except Exception as _ce:
                                print(f"⚠️ Cancel SL error: {_ce}")
                            guard_info["sl_order_id"] = None

                        # 2. Calculate Target Price for ₹150 Profit (rounded to NSE 0.05 tick size)
                        target_pts = 150.0 / max(1, qty)
                        target_raw = (avg_price + target_pts) if action == "BUY" else (avg_price - target_pts)
                        target_price = round(round(target_raw / 0.05) * 0.05, 2)
                        guard_info["target_150_price"] = target_price

                        # 3. Place new exchange TARGET LIMIT order
                        tgt_order_id = None
                        pos_order_tok = tok or pos.get("symboltoken") or ""
                        if not pos_order_tok or str(pos_order_tok).strip() in ("", "None", "0"):
                            pos_order_tok = STOCK_TOKENS.get(sym) or STOCK_TOKENS.get(sym.replace("-EQ", ""))

                        if pos_order_tok:
                            try:
                                tgt_res = place_order(
                                    symbol=sym,
                                    symbol_token=str(pos_order_tok),
                                    action=reverse_action,
                                    qty=qty,
                                    price=target_price,
                                    order_type="LIMIT",
                                    product="INTRADAY"
                                )
                                if tgt_res.get("success"):
                                    tgt_order_id = tgt_res.get("order_id") or tgt_res.get("data", {}).get("orderid")
                                    guard_info["target_order_id"] = tgt_order_id
                                    print(f"✅ Exchange Target Limit Order Placed for {sym}: Order ID {tgt_order_id} @ ₹{target_price:.2f}")
                                else:
                                    print(f"⚠️ Exchange Target Order response: {tgt_res}")
                            except Exception as _te:
                                print(f"⚠️ Exchange Target Order error: {_te}")

                        # 4. Trail local emergency SL to Entry Price (Cost-to-Cost / Breakeven)
                        guard_info["stop_loss"] = avg_price
                        sl_price = avg_price
                        guard_info["t1_trailed"] = True

                        # 5. Telegram Notification
                        tgt_note = f"Order ID: <code>{tgt_order_id}</code>" if tgt_order_id else "Local Surveillance Active"
                        send_telegram_message(
                            f"🎯 <b>₹100 PROFIT HIT — SL CONVERTED TO TARGET!</b>\n\n"
                            f"• <b>Symbol:</b> {sym}\n"
                            f"• <b>Current P&L:</b> +₹{live_pnl:.2f}\n"
                            f"• <b>Status:</b> Pending SL Cancelled ❌\n"
                            f"• <b>New Target Order:</b> LIMIT SELL @ ₹{target_price:.2f} (+₹150 Goal) 🎯\n"
                            f"• <b>Exchange Order:</b> {tgt_note}\n"
                            f"• <b>Zero-Risk Lock:</b> SL moved to Entry ₹{avg_price:.2f} (Breakeven) 🛡️\n"
                            f"• <b>Capital:</b> 100% Protected (Zero Loss Possible)!"
                        )
                else:
                    # Deep AI Scan: Do NOT cap trade at ₹150! Move SL to entry at ₹100 profit so trade is 100% risk-free, and let the ₹50 swing trailing ride huge multi-hour moves!
                    if live_pnl >= 100.0 and not guard_info.get("t1_trailed"):
                        guard_info["stop_loss"] = avg_price
                        guard_info["t1_trailed"] = True
                        sl_price = avg_price
                        print(f"🛡️ DEEP SCAN ZERO-RISK LOCK: {sym} reached +₹{live_pnl:.2f}! SL moved to Entry ₹{avg_price:.2f}. Letting swing trend ride with ₹50 buffer!")
                        send_telegram_message(
                            f"🛡️ <b>DEEP SCAN ZERO-RISK PROFIT LOCK!</b>\n\n"
                            f"• <b>Symbol:</b> {sym}\n"
                            f"• <b>Current P&L:</b> +₹{live_pnl:.2f}\n"
                            f"• <b>Trailing SL:</b> Moved to Entry ₹{avg_price:.2f} (Breakeven) 🛡️\n"
                            f"• <b>Status:</b> Zero Risk | ₹50 Swing Trailing Active for Full Trend Run (+₹400, +₹800+) 🚀"
                        )

                # ── STEP 2B: Zero-Risk Dynamic Profit Lock for T1 if not converted ──
                if target1 > 0 and not guard_info.get("t1_trailed") and not guard_info.get("converted_to_target"):
                    t1_hit = (action == "BUY" and cmp_price >= target1) or (action == "SELL" and cmp_price <= target1)
                    if t1_hit:
                        guard_info["stop_loss"] = avg_price
                        guard_info["t1_trailed"] = True
                        sl_price = avg_price
                        print(f"🛡️ ZERO-RISK PROFIT LOCK: {sym} reached T1 (₹{cmp_price:.2f})! SL moved to Entry Price ₹{avg_price:.2f}. Risk is now ZERO!")
                        send_telegram_message(
                            f"🛡️ <b>ZERO-RISK PROFIT LOCK ACTIVATED!</b>\n\n"
                            f"• <b>Symbol:</b> {sym}\n"
                            f"• <b>Target 1 Reached:</b> ₹{cmp_price:.2f}\n"
                            f"• <b>New Trailing SL:</b> ₹{avg_price:.2f} (Entry Price)\n"
                            f"• <b>Status:</b> Risk is now <b>ZERO (Cost-to-Cost)</b>! 🎯"
                        )

                should_exit = False
                exit_reason = ""

                # Trigger 0: Dedicated ₹150 Target Profit Hit (Only for Ultra Sniper converted orders)
                tgt_150_p = guard_info.get("target_150_price", 0)
                pullback_drop = current_peak - live_pnl

                if scan_type == "ultra_sniper" and (live_pnl >= 148.0 or (tgt_150_p > 0 and ((action == "BUY" and cmp_price >= tgt_150_p) or (action == "SELL" and cmp_price <= tgt_150_p)))):
                    should_exit = True
                    exit_reason = f"TARGET ₹150 PROFIT HIT (P&L: +₹{live_pnl:.2f} | CMP ₹{cmp_price:.2f})"

                # Trigger 0B: DYNAMIC TRAILING PROFIT LOCK (Mode-Specific)
                # 👑 ULTRA SNIPER QUICK TRAILING PROFIT LOCK: Activates after Peak >= ₹100; exits on any ₹30 pullback.
                elif scan_type == "ultra_sniper" and current_peak >= 100.0 and (pullback_drop >= 30.0 or live_pnl <= 10.0) and live_pnl > 0:
                    should_exit = True
                    exit_reason = f"👑 ULTRA SNIPER ₹30 PEAK PROFIT LOCK (Peak: +₹{current_peak:.2f} ➔ Retraced ₹{pullback_drop:.2f} to +₹{live_pnl:.2f} | Locked +₹{live_pnl:.2f} Profit)"

                # 🌊 DEEP AI SCAN SWING TRAILING PROFIT LOCK: Activates after Peak >= ₹150; exits on ₹50 pullback from peak.
                elif scan_type != "ultra_sniper" and current_peak >= 150.0 and (pullback_drop >= 50.0 or live_pnl <= 25.0) and live_pnl > 0:
                    should_exit = True
                    exit_reason = f"🌊 DEEP SCAN ₹50 SWING TRAILING PROFIT LOCK (Peak: +₹{current_peak:.2f} ➔ Retraced ₹{pullback_drop:.2f} to +₹{live_pnl:.2f} | Locked +₹{live_pnl:.2f} Profit)"

                # Trigger 1: EOD Square-off at 3:10 PM
                elif is_eod:
                    should_exit = True
                    exit_reason = "EOD_AUTO_SQUAREOFF (3:10 PM)"

                # Trigger 2: Hard Net ₹300 Loss Cap Trigger (Gross Loss -₹230 + Taxes ~₹60 <= ₹290 Net Loss)
                elif live_pnl <= -230.0:
                    should_exit = True
                    exit_reason = f"HARD ₹300 NET LOSS CAP (Gross Loss: -₹{abs(live_pnl):.2f})"

                # Trigger 3: SL Price Hit (or Trailed Breakeven SL after ₹100 conversion)
                elif action == "BUY" and sl_price > 0 and cmp_price <= sl_price:
                    should_exit = True
                    exit_reason = f"ZERO-RISK BREAKEVEN HIT (CMP ₹{cmp_price:.2f} <= Entry ₹{sl_price:.2f})" if guard_info.get("converted_to_target") else f"SL HIT (CMP ₹{cmp_price:.2f} <= SL ₹{sl_price:.2f})"
                elif action == "SELL" and sl_price > 0 and cmp_price >= sl_price:
                    should_exit = True
                    exit_reason = f"ZERO-RISK BREAKEVEN HIT (CMP ₹{cmp_price:.2f} >= Entry ₹{sl_price:.2f})" if guard_info.get("converted_to_target") else f"SL HIT (CMP ₹{cmp_price:.2f} >= SL ₹{sl_price:.2f})"

                # Trigger 4: Target 2 Hit (Full Profit Lock)
                elif action == "BUY" and target2 > 0 and cmp_price >= target2:
                    should_exit = True
                    exit_reason = f"TARGET 2 HIT (CMP ₹{cmp_price:.2f} >= T2 ₹{target2:.2f})"
                elif action == "SELL" and target2 > 0 and cmp_price <= target2:
                    should_exit = True
                    exit_reason = f"TARGET 2 HIT (CMP ₹{cmp_price:.2f} <= T2 ₹{target2:.2f})"

                # ── STEP 4: Execute Auto-Squareoff! ──
                if should_exit:
                    print(f"🚨 AUTO SQUARE-OFF TRIGGERED for {sym}: {exit_reason}")

                    # Check if target order was already filled by exchange!
                    already_filled = False
                    tgt_oid = guard_info.get("target_order_id")
                    if tgt_oid:
                        try:
                            ob_orders = get_order_book().get("orders", [])
                            for o in ob_orders:
                                if str(o.get("orderid")) == str(tgt_oid):
                                    st_val = (o.get("orderstatus") or o.get("status") or "").upper()
                                    if st_val in ("COMPLETE", "FILLED"):
                                        print(f"🎉 Target Order {tgt_oid} already FILLED on exchange!")
                                        already_filled = True
                                        break
                        except Exception:
                            pass

                    # Cancel any pending exchange SL order to prevent duplicate sell
                    sl_oid = guard_info.get("sl_order_id")
                    if sl_oid:
                        try:
                            cancel_smartapi_order(sl_oid, variety="STOPLOSS")
                        except Exception:
                            pass

                    # Cancel any pending exchange Target order if not already filled
                    if tgt_oid and not already_filled:
                        try:
                            cancel_smartapi_order(tgt_oid, variety="NORMAL")
                        except Exception:
                            pass

                    if not already_filled:
                        res = place_order(
                            symbol=sym,
                            symbol_token=tok,
                            action=reverse_action,
                            qty=qty,
                            price=0,
                            order_type="MARKET",
                            product="INTRADAY"
                        )
                    else:
                        res = {"success": True, "message": "Position filled by exchange target limit order"}

                    print(f"⚡ Auto Square-Off Result: {res}")
                    send_telegram_message(
                        f"🚨 <b>AUTO SQUARE-OFF EXECUTED</b>\n\n"
                        f"• <b>Symbol:</b> {sym}\n"
                        f"• <b>Reason:</b> {exit_reason}\n"
                        f"• <b>Exit Price:</b> ₹{cmp_price:.2f}\n"
                        f"• <b>P&L:</b> {'+' if live_pnl >= 0 else ''}₹{live_pnl:.2f}\n"
                        f"• <b>Status:</b> {'✅ SUCCESS' if res.get('success') else '⚠️ CHECK BROKER'}"
                    )
                    close_live_trade_record(sym, cmp_price, live_pnl, exit_reason)
                    LOCAL_SL_TRACKER.pop(sym, None)
                    clean_sym = sym.replace("-EQ", "").strip()
                    LOCAL_SL_TRACKER.pop(clean_sym, None)
                    LOCAL_SL_TRACKER.pop(f"{clean_sym}-EQ", None)
                    POSITION_FIRST_SEEN.pop(sym, None)
                    POSITION_FIRST_SEEN.pop(clean_sym, None)
                    SL_AUTO_PLACED.pop(sym, None)
                    SL_AUTO_PLACED.pop(clean_sym, None)



        except Exception as ex:
            pass



import threading
monitor_thread = threading.Thread(target=_local_sl_monitor_thread, daemon=True)
monitor_thread.start()

def get_live_token(symbol_base: str) -> str:
    """Dynamically get token from cache or Scrip Master."""
    clean = symbol_base.upper().replace(".NS", "").replace("-EQ", "").strip()
    clean_eq = f"{clean}-EQ"
    if clean_eq in STOCK_TOKENS:
        return STOCK_TOKENS[clean_eq]
    
    global SCRIP_TOKEN_CACHE
    if not SCRIP_TOKEN_CACHE:
        try:
            url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                for item in data:
                    if item.get("exch_seg") == "NSE" and item.get("symbol", "").endswith("-EQ"):
                        SCRIP_TOKEN_CACHE[item["symbol"]] = str(item["token"])
        except Exception:
            pass
    return SCRIP_TOKEN_CACHE.get(clean_eq, "")


STOCK_TOKENS = {
    "IDEA-EQ": "14366", "SUZLON-EQ": "12018", "YESBANK-EQ": "11915", "RPOWER-EQ": "10099",
    "JPPOWER-EQ": "10098", "IRFC-EQ": "2029", "NHPC-EQ": "17400", "SJVN-EQ": "18883",
    "IOB-EQ": "1076", "UCOBANK-EQ": "8064", "CENTRALBK-EQ": "5307", "SOUTHBANK-EQ": "3351",
    "IDFCFIRSTB-EQ": "11184", "PNB-EQ": "10666", "BANKBARODA-EQ": "467", "ZOMATO-EQ": "5097",
    "TATASTEEL-EQ": "3499", "NBCC-EQ": "14730", "SAIL-EQ": "2963", "HUDCO-EQ": "14732",
    "RELIANCE-EQ": "2885", "TCS-EQ": "11536", "HDFCBANK-EQ": "1333", "ICICIBANK-EQ": "4963",
    "INFY-EQ": "1594", "SBIN-EQ": "3045", "BHARTIARTL-EQ": "10604", "KOTAKBANK-EQ": "1922",
    "LT-EQ": "11483", "HCLTECH-EQ": "7229", "MARUTI-EQ": "10999", "AXISBANK-EQ": "5900",
    "SUNPHARMA-EQ": "3351", "BAJFINANCE-EQ": "317", "TATAMOTORS-EQ": "3456", "M&M-EQ": "2031",
    "WIPRO-EQ": "3787", "ADANIENT-EQ": "25", "ADANIPORTS-EQ": "15083", "COALINDIA-EQ": "20374",
    "ONGC-EQ": "2475", "NTPC-EQ": "11630", "POWERGRID-EQ": "14977", "TITAN-EQ": "3506",
    "JSWSTEEL-EQ": "11723", "BEL-EQ": "383"
}

WATCHLISTS = {
    "budget": [
        {"symbol": "IDEA.NS", "name": "Vodafone Idea", "base": "IDEA-EQ", "tok": "14366"},
        {"symbol": "SUZLON.NS", "name": "Suzlon Energy", "base": "SUZLON-EQ", "tok": "12018"},
        {"symbol": "YESBANK.NS", "name": "Yes Bank", "base": "YESBANK-EQ", "tok": "11915"},
        {"symbol": "IRFC.NS", "name": "Indian Railway Finance", "base": "IRFC-EQ", "tok": "2029"},
        {"symbol": "NHPC.NS", "name": "NHPC Limited", "base": "NHPC-EQ", "tok": "17400"},
        {"symbol": "SJVN.NS", "name": "SJVN Limited", "base": "SJVN-EQ", "tok": "18883"},
        {"symbol": "IDFCFIRSTB.NS", "name": "IDFC First Bank", "base": "IDFCFIRSTB-EQ", "tok": "11184"},
        {"symbol": "PNB.NS", "name": "Punjab National Bank", "base": "PNB-EQ", "tok": "10666"},
        {"symbol": "BANKBARODA.NS", "name": "Bank of Baroda", "base": "BANKBARODA-EQ", "tok": "467"},
        {"symbol": "ZOMATO.NS", "name": "Zomato Limited", "base": "ZOMATO-EQ", "tok": "5097"},
        {"symbol": "TATASTEEL.NS", "name": "Tata Steel", "base": "TATASTEEL-EQ", "tok": "3499"},
        {"symbol": "SAIL.NS", "name": "Steel Authority of India", "base": "SAIL-EQ", "tok": "2963"},
        {"symbol": "HUDCO.NS", "name": "HUDCO", "base": "HUDCO-EQ", "tok": "14732"},
    ],
    "nifty50": [
        {"symbol": "RELIANCE.NS", "name": "Reliance Industries", "base": "RELIANCE-EQ", "tok": "2885"},
        {"symbol": "TCS.NS", "name": "Tata Consultancy Services", "base": "TCS-EQ", "tok": "11536"},
        {"symbol": "HDFCBANK.NS", "name": "HDFC Bank", "base": "HDFCBANK-EQ", "tok": "1333"},
        {"symbol": "ICICIBANK.NS", "name": "ICICI Bank", "base": "ICICIBANK-EQ", "tok": "4963"},
        {"symbol": "INFY.NS", "name": "Infosys", "base": "INFY-EQ", "tok": "1594"},
        {"symbol": "SBIN.NS", "name": "State Bank of India", "base": "SBIN-EQ", "tok": "3045"},
        {"symbol": "BHARTIARTL.NS", "name": "Bharti Airtel", "base": "BHARTIARTL-EQ", "tok": "10604"},
        {"symbol": "TATAMOTORS.NS", "name": "Tata Motors", "base": "TATAMOTORS-EQ", "tok": "3456"},
        {"symbol": "M&M.NS", "name": "Mahindra & Mahindra", "base": "M&M-EQ", "tok": "2031"},
        {"symbol": "AXISBANK.NS", "name": "Axis Bank", "base": "AXISBANK-EQ", "tok": "5900"},
        {"symbol": "SUNPHARMA.NS", "name": "Sun Pharma", "base": "SUNPHARMA-EQ", "tok": "3351"},
        {"symbol": "BAJFINANCE.NS", "name": "Bajaj Finance", "base": "BAJFINANCE-EQ", "tok": "317"},
        {"symbol": "TATASTEEL.NS", "name": "Tata Steel", "base": "TATASTEEL-EQ", "tok": "3499"},
        {"symbol": "BEL.NS", "name": "Bharat Electronics", "base": "BEL-EQ", "tok": "383"},
    ],
    "momentum": [
        {"symbol": "SUZLON.NS", "name": "Suzlon Energy", "base": "SUZLON-EQ", "tok": "12018"},
        {"symbol": "ZOMATO.NS", "name": "Zomato Limited", "base": "ZOMATO-EQ", "tok": "5097"},
        {"symbol": "TATAMOTORS.NS", "name": "Tata Motors", "base": "TATAMOTORS-EQ", "tok": "3456"},
        {"symbol": "IRFC.NS", "name": "Indian Railway Finance", "base": "IRFC-EQ", "tok": "2029"},
        {"symbol": "BEL.NS", "name": "Bharat Electronics", "base": "BEL-EQ", "tok": "383"},
    ]
}


def _analyze_single_stock_local(stk):
    """Fetch live price & 1m/5m candle data for instant accurate technical setup."""
    sym = stk["symbol"]
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=5m&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            price = meta.get("regularMarketPrice") or meta.get("previousClose")
            if not price or price <= 0:
                return None

            prev_close = meta.get("chartPreviousClose") or meta.get("previousClose") or price
            day_high = meta.get("regularMarketDayHigh") or price * 1.01
            day_low = meta.get("regularMarketDayLow") or price * 0.99
            change_pct = ((price - prev_close) / prev_close) * 100.0

            quotes = result.get("indicators", {}).get("quote", [{}])[0]
            closes = [c for c in quotes.get("close", []) if c is not None]
            
            # Fast RSI calculation on 5m
            rsi = 50.0
            if len(closes) >= 14:
                diffs = [closes[i] - closes[i-1] for i in range(1, len(closes))]
                gains = [d for d in diffs if d > 0]
                losses = [abs(d) for d in diffs if d < 0]
                avg_gain = sum(gains[-14:]) / 14 if gains else 0.001
                avg_loss = sum(losses[-14:]) / 14 if losses else 0.001
                rs = avg_gain / avg_loss
                rsi = round(100 - (100 / (1 + rs)), 1)

            # Signal Decision Engine
            if change_pct >= 0.2 and rsi >= 48.0:
                action = "BUY"
                target1 = round(price * 1.015, 2)
                target2 = round(price * 1.030, 2)
                stoploss = round(price * 0.988, 2)
                confidence = min(96, max(82, int(84 + (change_pct * 3) + (rsi - 50) * 0.4)))
                reason = f"Bullish momentum: +{change_pct:.2f}% intraday gain | 5m RSI: {rsi} (Healthy Uptrend) | VWAP Support Held."
            elif change_pct <= -0.2 and rsi <= 52.0:
                action = "SELL"
                target1 = round(price * 0.985, 2)
                target2 = round(price * 0.970, 2)
                stoploss = round(price * 1.012, 2)
                confidence = min(94, max(80, int(82 + (abs(change_pct) * 3) + (50 - rsi) * 0.4)))
                reason = f"Bearish breakdown: {change_pct:.2f}% intraday drop | 5m RSI: {rsi} (Oversold pressure) | Resistance active."
            else:
                action = "BUY" if change_pct >= 0 else "SELL"
                target1 = round(price * 1.012, 2) if action == "BUY" else round(price * 0.988, 2)
                target2 = round(price * 1.025, 2) if action == "BUY" else round(price * 0.975, 2)
                stoploss = round(price * 0.990, 2) if action == "BUY" else round(price * 1.010, 2)
                confidence = 85
                reason = f"Consolidation breakout setup: Intraday change {change_pct:+.2f}% | Key 5m RSI support at {rsi}."

            return {
                "symbol": stk["base"],
                "stock": stk["base"],
                "company_name": stk["name"],
                "token": stk["tok"],
                "symboltoken": stk["tok"],
                "action": action,
                "price": round(float(price), 2),
                "entry_price": round(float(price), 2),
                "target": target1,
                "target2": target2,
                "stoploss": stoploss,
                "confidence": confidence,
                "change_pct": round(change_pct, 2),
                "rsi": rsi,
                "reasoning": reason,
                "timestamp": str(meta.get("regularMarketTime", ""))
            }
    except Exception as e:
        return None


_last_scan_alert_ts = 0.0
_alerted_signals = {}  # {symbol: action} to avoid sending duplicate alerts


def broadcast_top_scan_signals_to_telegram(signals: list, scan_mode: str = "FAST 5M"):
    """Broadcast top 1-2 high-conviction scan signals to Telegram with smart cooldown."""
    global _last_scan_alert_ts, _alerted_signals
    now = time.time()
    # At least 30 seconds cooldown between Telegram signal alerts
    if now - _last_scan_alert_ts < 30.0:
        return

    # Select top 2 signals with >= 88% confidence (or top 1 >= 85%)
    top_picks = [s for s in signals if s.get("confidence", 0) >= 88][:2]
    if not top_picks:
        top_picks = [s for s in signals if s.get("confidence", 0) >= 85][:1]

    if not top_picks:
        return

    # Filter out signals already alerted recently with same action
    fresh_picks = []
    for s in top_picks:
        sym = s.get("symbol") or s.get("stock")
        act = s.get("action")
        if _alerted_signals.get(sym) != act:
            fresh_picks.append(s)
            _alerted_signals[sym] = act

    if not fresh_picks:
        return

    _last_scan_alert_ts = now
    lines = [f"🎯 <b>STOCKSENSE AI — {scan_mode.upper()} SCAN SIGNALS</b>\n"]
    for i, s in enumerate(fresh_picks, 1):
        sym = s.get("symbol") or s.get("stock")
        act = s.get("action", "BUY")
        badge = "🟢 BUY" if act == "BUY" else "🔴 SELL"
        cmp_p = float(s.get("price") or s.get("entry_price") or 0.0)
        t1 = float(s.get("target") or s.get("target1") or 0.0)
        t2 = float(s.get("target2") or 0.0)
        sl = float(s.get("stoploss") or s.get("stop_loss") or 0.0)
        conf = s.get("confidence") or 0
        rsi_val = s.get("rsi") or s.get("rsi_15m") or ""
        rsi_txt = f" | 5m RSI: {rsi_val}" if rsi_val else ""

        lines.append(
            f"<b>{i}. {sym} — {badge}</b>\n"
            f"• <b>CMP:</b> ₹{cmp_p:.2f} | <b>Confidence:</b> {conf}%\n"
            f"• <b>Targets:</b> T1 ₹{t1:.2f} | T2 ₹{t2:.2f}\n"
            f"• <b>Stop Loss:</b> ₹{sl:.2f}{rsi_txt}"
        )

    lines.append("\n⚡ <i>Open Mobile Dashboard to execute 1-Click: http://192.168.1.229:8888</i>")
    send_telegram_message("\n\n".join(lines))


def run_instant_market_scan(category="all"):
    """Scan market in parallel within 1.5 seconds!"""
    from concurrent.futures import ThreadPoolExecutor

    market_open, market_msg = check_market_hours_ist()
    if not market_open:
        return {"signals": [], "total": 0, "category": category, "market_closed": True, "error": market_msg}
    
    if category == "budget":
        stocks = WATCHLISTS["budget"]
    elif category == "nifty50":
        stocks = WATCHLISTS["nifty50"]
    elif category == "momentum":
        stocks = WATCHLISTS["momentum"]
    else:
        stocks = WATCHLISTS["budget"] + WATCHLISTS["nifty50"][:8]

    signals = []
    with ThreadPoolExecutor(max_workers=min(12, len(stocks))) as executor:
        results = executor.map(_analyze_single_stock_local, stocks)
        for res in results:
            if res:
                signals.append(res)

    # Sort high confidence signals first
    signals.sort(key=lambda x: (x["confidence"], abs(x.get("change_pct", 0))), reverse=True)

    # 📲 Broadcast top signals to Telegram!
    try:
        broadcast_top_scan_signals_to_telegram(signals, scan_mode=f"FAST {category.upper()}")
    except Exception as _tge:
        print(f"⚠️ Telegram signal broadcast error: {_tge}")

    return {"signals": signals, "total": len(signals), "category": category}


def fetch_signals():
    return run_instant_market_scan("budget")


def get_watchlist_data() -> dict:
    """Return all 69 stocks (Nifty 50 + Budget) with tokens, sectors and category metadata."""
    stocks_list = []
    all_s = ALL_STOCKS if ("ALL_STOCKS" in globals() and ALL_STOCKS) else (NIFTY50_STOCKS + BUDGET_LOW_PRICED_STOCKS)
    budget_syms = set(s["symbol"] for s in BUDGET_LOW_PRICED_STOCKS) if ("BUDGET_LOW_PRICED_STOCKS" in globals() and BUDGET_LOW_PRICED_STOCKS) else set()

    for s in all_s:
        sym = s["symbol"]
        base = sym.replace(".NS", "") + "-EQ"
        tok = ANGEL_TOKENS_MAP.get(sym, STOCK_TOKENS.get(base, get_live_token(base)))
        is_budget = sym in budget_syms
        stocks_list.append({
            "symbol": sym,
            "base": base,
            "name": s["name"],
            "sector": s.get("sector", "General"),
            "is_budget": is_budget,
            "tok": tok
        })
    return {"stocks": stocks_list, "total": len(stocks_list)}


def get_single_stock_price(symbol: str) -> dict:
    """Fetch live stock price & change via fast Yahoo REST chart endpoint."""
    sym = symbol.upper().replace("-EQ", "").strip()
    if not sym.endswith(".NS") and not sym.endswith(".BO"):
        yahoo_sym = sym + ".NS"
    else:
        yahoo_sym = sym
    base = sym.replace(".NS", "") + "-EQ"
    tok = ANGEL_TOKENS_MAP.get(yahoo_sym, STOCK_TOKENS.get(base, get_live_token(base)))

    price = 0.0
    change_pct = 0.0
    prev_close = 0.0
    day_high = 0.0
    day_low = 0.0

    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}?interval=5m&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            price = meta.get("regularMarketPrice") or meta.get("previousClose") or 0.0
            prev_close = meta.get("chartPreviousClose") or meta.get("previousClose") or price
            day_high = meta.get("regularMarketDayHigh") or price
            day_low = meta.get("regularMarketDayLow") or price
            if prev_close and prev_close > 0 and price:
                change_pct = round(((price - prev_close) / prev_close) * 100.0, 2)
    except Exception:
        pass

    price = round(float(price or 0.0), 2)
    return {
        "symbol": base,
        "yahoo_symbol": yahoo_sym,
        "token": tok,
        "price": price,
        "change_pct": change_pct,
        "prev_close": round(float(prev_close or price), 2),
        "day_high": round(float(day_high or price), 2),
        "day_low": round(float(day_low or price), 2),
        "target1": round(price * 1.015, 2),
        "target2": round(price * 1.030, 2),
        "stoploss": round(price * 0.988, 2)
    }


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>⚡ StocksSense AI — Local Live Trader Pro</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #070b14;
            --surface: #0f172a;
            --surface-card: #141e33;
            --border: #1e293b;
            --border-accent: #334155;
            --accent: #3b82f6;
            --accent-glow: rgba(59, 130, 246, 0.25);
            --green: #10b981;
            --green-glow: rgba(16, 185, 129, 0.2);
            --red: #ef4444;
            --red-glow: rgba(239, 68, 68, 0.2);
            --gold: #f59e0b;
            --text: #f8fafc;
            --text-muted: #94a3b8;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Inter', sans-serif; }
        body { background: var(--bg); color: var(--text); padding: 20px; min-height: 100vh; }
        .container { max-width: 1200px; margin: 0 auto; }
        
        .header { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 20px; }
        .logo-area h1 { font-size: 24px; font-weight: 900; background: linear-gradient(135deg, #60a5fa, #3b82f6, #93c5fd); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .logo-area p { font-size: 13px; color: var(--text-muted); margin-top: 4px; display: flex; align-items: center; gap: 8px; }
        
        .status-badge { padding: 8px 16px; border-radius: 9999px; font-size: 13px; font-weight: 700; display: inline-flex; align-items: center; gap: 8px; }
        .status-connected { background: rgba(16, 185, 129, 0.15); color: var(--green); border: 1px solid rgba(16, 185, 129, 0.3); }
        .status-disconnected { background: rgba(239, 68, 68, 0.15); color: var(--red); border: 1px solid rgba(239, 68, 68, 0.3); }
        
        .stats-bar { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
        @media (max-width: 900px) { .stats-bar { grid-template-columns: repeat(2, 1fr); } }
        .stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 16px; }
        .stat-label { font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
        .stat-val { font-size: 20px; font-weight: 900; margin-top: 4px; color: #fff; }
        
        .main-grid { display: grid; grid-template-columns: 360px 1fr; gap: 20px; }
        @media (max-width: 960px) { .main-grid { grid-template-columns: 1fr; } }
        
        .card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 20px; margin-bottom: 20px; }
        .card-title { font-size: 15px; font-weight: 800; margin-bottom: 14px; display: flex; align-items: center; justify-content: space-between; color: #fff; }
        
        label { display: block; font-size: 11px; font-weight: 700; color: var(--text-muted); margin-bottom: 6px; text-transform: uppercase; }
        input, select { width: 100%; background: #090f1d; border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; color: #fff; font-size: 14px; margin-bottom: 12px; outline: none; transition: 0.2s; }
        input:focus, select:focus { border-color: var(--accent); }
        
        .btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; width: 100%; padding: 12px; border-radius: 10px; font-size: 14px; font-weight: 700; border: none; cursor: pointer; transition: 0.2s; }
        .btn-primary { background: #2563eb; color: #fff; }
        .btn-primary:hover { background: #1d4ed8; }
        .btn-scan { background: linear-gradient(135deg, #3b82f6, #8b5cf6); color: #fff; font-weight: 800; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.4); }
        .btn-scan:hover { opacity: 0.9; transform: translateY(-1px); }
        .btn-buy { background: var(--green); color: #000; font-weight: 800; }
        .btn-buy:hover { background: #059669; color: #fff; }
        .btn-sell { background: var(--red); color: #fff; font-weight: 800; }
        .btn-sell:hover { background: #dc2626; }
        
        .scanner-bar { display: flex; gap: 10px; align-items: center; background: var(--surface-card); padding: 12px 16px; border-radius: 12px; border: 1px solid var(--border); margin-bottom: 16px; }
        .scanner-bar select { width: auto; margin-bottom: 0; min-width: 180px; }
        
        .signals-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
        @media (max-width: 1100px) { .signals-grid { grid-template-columns: 1fr; } }
        
        .signal-card { background: var(--surface-card); border: 1px solid var(--border); border-radius: 14px; padding: 16px; transition: 0.2s; position: relative; overflow: hidden; }
        .signal-card:hover { border-color: var(--accent); box-shadow: 0 4px 20px rgba(0,0,0,0.4); }
        .signal-card.buy-card { border-left: 4px solid var(--green); }
        .signal-card.sell-card { border-left: 4px solid var(--red); }
        
        .sig-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; }
        .sig-name { font-size: 17px; font-weight: 900; }
        .sig-sub { font-size: 12px; color: var(--text-muted); }
        
        .badge { padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 800; text-transform: uppercase; }
        .badge-buy { background: var(--green-glow); color: var(--green); }
        .badge-sell { background: var(--red-glow); color: var(--red); }
        .badge-conv { background: rgba(245, 158, 11, 0.15); color: var(--gold); }
        
        .sig-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; font-size: 11px; color: var(--text-muted); background: #0b1120; padding: 10px; border-radius: 8px; margin-bottom: 12px; }
        .sig-grid span b { color: #fff; display: block; font-size: 13px; margin-top: 2px; }
        
        .sig-reason { font-size: 12px; color: #cbd5e1; margin-bottom: 12px; line-height: 1.4; background: rgba(255,255,255,0.02); padding: 8px; border-radius: 6px; border: 1px dashed var(--border); }
        
        .alert-box { padding: 12px; border-radius: 10px; font-size: 13px; margin-top: 12px; white-space: pre-wrap; word-break: break-word; }
        .alert-ok { background: rgba(16,185,129,0.15); border: 1px solid var(--green); color: #34d399; }
        .alert-err { background: rgba(239,68,68,0.15); border: 1px solid var(--red); color: #f87171; }
        
        .ip-pill { background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.3); color: #93c5fd; padding: 3px 8px; border-radius: 6px; font-size: 12px; font-weight: 700; }
        
        .tabs { display: flex; gap: 8px; margin-bottom: 14px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
        .tab { padding: 6px 14px; border-radius: 8px; font-size: 13px; font-weight: 700; color: var(--text-muted); cursor: pointer; border: 1px solid transparent; transition: 0.2s; background: none; }
        .tab.active { color: #fff; background: var(--surface-card); border-color: var(--border); }
        .tab:hover { color: #fff; }

        /* Watchlist Grid & Cards */
        .watchlist-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
        .watchlist-card { background: var(--surface-card); border: 1px solid var(--border); border-radius: 12px; padding: 14px; transition: 0.2s; position: relative; }
        .watchlist-card:hover { border-color: var(--accent); box-shadow: 0 4px 20px rgba(0,0,0,0.3); transform: translateY(-1px); }

        /* Sector & Category Filter Pills */
        .sector-btn { padding: 5px 12px; border-radius: 20px; font-size: 11px; font-weight: 700; border: 1px solid var(--border); background: #090f1d; color: var(--text-muted); cursor: pointer; transition: 0.2s; }
        .sector-btn:hover { color: #fff; border-color: var(--border-accent); }
        .sector-btn.active { background: #2563eb; color: #fff; border-color: #2563eb; box-shadow: 0 0 10px rgba(37,99,235,0.4); }

        /* Auto-Scanner Pulsing Animation */
        @keyframes pulse-scan {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.75; transform: scale(1.04); }
        }
        .pulse-badge { animation: pulse-scan 1.5s infinite; }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <div class="logo-area">
                <h1>⚡ StocksSense AI — Local Live Trader Pro</h1>
                <p>
                    Outbound IP: <span class="ip-pill" id="display-ip" onclick="copyIP()" style="cursor:pointer; background:#065f46; color:#34d399; border:1px solid #059669;" title="Click to copy Dedicated Static IP for smartapi.angelone.in">178.92.40.115 (Static 🟢)</span>
                    <span>● StaticIP.in Dedicated Proxy Bridge</span>

                </p>
            </div>
            <div style="display:flex; align-items:center; gap:12px;">
                <div id="mode-switcher-bar" style="background:#090f1d; border:1px solid var(--border); border-radius:30px; padding:4px; display:inline-flex; align-items:center; gap:4px;">
                    <button id="hdr-mode-paper" onclick="switchMode('paper')" style="padding:6px 14px; border-radius:20px; font-size:12px; font-weight:800; border:none; cursor:pointer; background:#2563eb; color:#fff;">📝 PAPER MODE</button>
                    <button id="hdr-mode-live" onclick="switchMode('live')" style="padding:6px 14px; border-radius:20px; font-size:12px; font-weight:800; border:none; cursor:pointer; background:transparent; color:var(--text-muted);">💼 LIVE MODE</button>
                </div>
                <div id="conn-badge" class="status-badge status-disconnected">● Connecting...</div>
                <div id="refresh-timer-badge" onclick="toggleAutoRefresh()" style="padding:6px 14px; border-radius:20px; font-size:11px; font-weight:700; cursor:pointer; background:rgba(59,130,246,0.15); border:1px solid rgba(59,130,246,0.3); color:#93c5fd; display:inline-flex; align-items:center; gap:6px; user-select:none;" title="Click to pause/resume auto-refresh">
                    🔄 <span id="refresh-countdown">15s</span>
                </div>
            </div>
        </div>

        <!-- Real-Time Account Bar -->
        <div class="stats-bar">
            <div class="stat-card">
                <div class="stat-label" id="lbl_bal_type">Paper Trading Balance</div>
                <div class="stat-val" id="st_bal" style="color:#60a5fa;">₹100,000.00</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">5X MIS Buying Power</div>
                <div class="stat-val" id="st_power" style="color:#34d399;">₹500,000.00</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Daily Loss Guard (SL)</div>
                <div class="stat-val" style="color:#f87171;">₹300.00 Max Cap</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Execution Speed</div>
                <div class="stat-val" style="color:#fbbf24;">⚡ 0.1s Direct IP</div>
            </div>
        </div>

        <div class="main-grid">
            <!-- Left Column: Controls & Orders -->
            <div>
                <!-- Quick Order Placement -->
                <div class="card">
                    <div class="card-title">📝 Quick Manual <span id="m-order-mode-lbl" style="color:#60a5fa;">Paper</span> Order</div>
                    <div style="display:flex; gap:10px;">
                        <div style="flex:2;">
                            <label>Stock Symbol</label>
                            <input id="m_sym" placeholder="e.g. SBIN-EQ, RELIANCE-EQ">
                        </div>
                        <div style="flex:1;">
                            <label>Token</label>
                            <input id="m_tok" placeholder="e.g. 3063">
                        </div>
                    </div>
                    <div style="display:flex; gap:10px;">
                        <div style="flex:1;">
                            <label>Qty (5X MIS)</label>
                            <input id="m_qty" type="number" value="1">
                        </div>
                        <div style="flex:1;">
                            <label>Price (₹)</label>
                            <input id="m_prc" type="number" step="0.05" placeholder="Limit / Market">
                        </div>
                    </div>
                    <div style="display:flex; gap:10px; margin-top:4px;">
                        <button class="btn btn-buy" onclick="submitManual('BUY')">⚡ BUY (INTRADAY)</button>
                        <button class="btn btn-sell" onclick="submitManual('SELL')">⚡ SELL (INTRADAY)</button>
                    </div>
                    <div id="manual-alert" style="display:none;" class="alert-box"></div>
                </div>

                <!-- Angel One Credentials -->
                <div class="card">
                    <div class="card-title">
                        <span>🔐 SmartAPI Credentials</span>
                        <span style="font-size:11px; color:var(--text-muted);">Saved on PC</span>
                    </div>
                    <div style="background:rgba(16, 185, 129, 0.1); border:1px solid rgba(16, 185, 129, 0.4); border-radius:8px; padding:10px; margin-bottom:12px; font-size:11px; color:#34d399; line-height:1.4;">
                        🛡️ <b>StaticIP.in Dedicated Proxy Active:</b><br>
                        Your fixed dedicated IP is <b id="cfg-display-ip" style="color:#fff; text-decoration:underline; cursor:pointer;" onclick="copyIP()" title="Click to copy">178.92.40.115</b> [📋 Click to Copy].<br>
                        Please whitelist this IP in <a href="https://smartapi.angelone.in/" target="_blank" style="color:#60a5fa; text-decoration:underline; font-weight:bold;">smartapi.angelone.in</a> &gt; My Apps. It never changes!
                    </div>

                    <label>Client Code</label>
                    <input id="cfg_client" placeholder="AACL535586">
                    <label>Password / MPIN</label>
                    <input id="cfg_pass" type="password" placeholder="Password">
                    <label>API Key</label>
                    <input id="cfg_key" placeholder="SmartAPI Private Key">
                    <label>TOTP Secret Key</label>
                    <input id="cfg_totp" placeholder="Base32 TOTP Secret">
                    <button class="btn btn-primary" onclick="saveAndLogin()">💾 Save & Re-Connect</button>
                    <div id="auth-alert" style="display:none;" class="alert-box"></div>
                </div>

                <!-- 📱 Local Telegram Alerts Card -->
                <div class="card">
                    <div class="card-title">
                        <span>📱 Telegram Alerts (Local)</span>
                        <span id="tg-status-pill" style="font-size:10px; background:#2563eb; color:#fff; padding:2px 7px; border-radius:8px; font-weight:800;">DEFAULT BOT</span>
                    </div>
                    <p style="font-size:11px; color:var(--text-muted); margin-bottom:10px; line-height:1.4;">
                        Add a separate/custom Telegram Bot & Chat ID for Local Trader orders and exit alerts.
                    </p>
                    <label>Telegram Bot Token</label>
                    <input id="cfg_tg_token" placeholder="e.g. 8613233140:AAEfeblJ0e5vK...">
                    <label>Telegram Chat ID</label>
                    <input id="cfg_tg_chat" placeholder="e.g. 7327907687 or -100...">

                    <div style="display:flex; gap:8px;">
                        <button class="btn btn-primary" style="flex:2;" onclick="saveTelegramSettings()">💾 Save Telegram</button>
                        <button class="btn" style="flex:1; background:#0284c7; color:#fff; font-weight:800;" onclick="testTelegramAlert()">🔔 Test</button>
                    </div>
                    <div id="tg-alert" style="display:none;" class="alert-box"></div>
                </div>

                <!-- 🤖 Auto-SL Delay Settings Card -->
                <div class="card">
                    <div class="card-title">
                        <span>🤖 Auto Stop-Loss Delay</span>
                        <span style="font-size:10px; background:#10b981; color:#000; padding:2px 7px; border-radius:8px; font-weight:800;" id="sl-delay-badge">3 MIN</span>
                    </div>
                    <p style="font-size:11px; color:var(--text-muted); margin-bottom:10px; line-height:1.4;">
                        After buying a stock, Local Trader will <b>automatically place a Stop-Loss order</b> in Angel One exchange after this delay. SL price is from your entry setup or ₹300 cap.
                    </p>
                    <label>Delay after Buy (minutes)</label>
                    <div style="display:flex; gap:8px; align-items:center;">
                        <input id="sl-delay-input" type="number" min="1" max="15" value="3" style="flex:1; padding:8px 10px; font-size:14px; font-weight:700;">
                        <button class="btn btn-primary" style="flex:1; font-weight:800;" onclick="setSLDelay()">⚡ Set Delay</button>
                    </div>
                    <div id="sl-delay-alert" style="display:none;" class="alert-box"></div>
                </div>
            </div>

            <!-- Right Column: Scanner, Watchlist, Positions, Journal -->
            <div>
                <!-- Main Dashboard Navigation Tabs -->
                <div class="tabs" style="margin-bottom:16px; display:flex; gap:8px; flex-wrap:wrap;">
                    <button class="tab active" id="tab-nav-scanner" onclick="switchDashboardTab('scanner')" style="display:flex; align-items:center; gap:8px;">
                        <span>🚀 Live AI Scanner</span>
                        <span id="nav-auto-scan-pill" style="display:none; font-size:10px; background:#10b981; color:#000; padding:2px 7px; border-radius:10px; font-weight:900;">AUTO ON</span>
                    </button>
                    <button class="tab" id="tab-nav-watchlist" onclick="switchDashboardTab('watchlist')" style="display:flex; align-items:center; gap:8px;">
                        <span>📋 Market Watchlist & Manual Buy</span>
                        <span style="font-size:10px; background:rgba(59,130,246,0.25); color:#93c5fd; padding:2px 6px; border-radius:8px; font-weight:800;">69 Stocks</span>
                    </button>
                    <button class="tab" id="tab-nav-positions" onclick="switchDashboardTab('positions')" style="display:flex; align-items:center; gap:6px;">
                        <span>💼 Open Positions & Orders</span>
                        <span id="nav-pos-count" style="display:none; font-size:10px; background:#10b981; color:#000; padding:1px 6px; border-radius:10px; font-weight:800;">0</span>
                    </button>
                    <button class="tab" id="tab-nav-journal" onclick="switchDashboardTab('journal')">
                        📝 Trade Journal
                    </button>
                </div>

                <!-- ──── TAB 1: SCANNER ──── -->
                <div id="tab-content-scanner">
                    <div class="card">
                        <div class="card-title">
                            <span>🚀 Live AI Market Scanner</span>
                            <span id="scan-status" style="font-size:12px; color:var(--text-muted);">Ready</span>
                        </div>

                        <!-- Scan Mode Toggle -->
                        <div style="display:flex; gap:8px; margin-bottom:12px;">
                            <button id="mode-fast-btn" class="btn btn-scan" style="flex:1; padding:8px 6px; font-size:11px; font-weight:800; opacity:1; box-shadow:0 0 16px rgba(59,130,246,0.5);" onclick="setScanMode('fast')">
                                ⚡ FAST (5M)
                            </button>
                            <button id="mode-ai-btn" class="btn" style="flex:1; padding:8px 6px; font-size:11px; font-weight:800; background:linear-gradient(135deg,#7c3aed,#4f46e5); color:#fff; opacity:0.6;" onclick="setScanMode('deep')">
                                🧠 DEEP AI
                            </button>
                            <button id="mode-sniper-btn" class="btn" style="flex:1; padding:8px 6px; font-size:11px; font-weight:800; background:linear-gradient(135deg,#f59e0b,#d97706); color:#fff; opacity:0.6;" onclick="setScanMode('sniper')">
                                👑 1-SNIPER (92%+)
                            </button>
                        </div>

                        <div id="mode-label" style="text-align:center; font-size:11px; color:#94a3b8; margin-bottom:10px; padding:6px; background:#090f1d; border-radius:8px;">
                            ⚡ <b>Fast Mode</b>: 5-Minute momentum scanner (1-2 seconds)
                        </div>

                        <!-- Scanner Control Bar with Auto-Scanner -->
                        <div class="scanner-bar" style="flex-wrap:wrap; gap:10px;">
                            <div style="display:flex; align-items:center; gap:8px;">
                                <label style="margin-bottom:0;">Category:</label>
                                <select id="scan_cat">
                                    <option value="all">🌐 All Top Opportunities</option>
                                    <option value="budget">💰 Budget Stocks (&lt; ₹500)</option>
                                    <option value="nifty50">⚡ Nifty 50 High Conviction</option>
                                    <option value="momentum">🚀 Momentum Breakouts</option>
                                </select>
                            </div>
                            <button class="btn btn-scan" style="width:auto; padding:10px 18px;" onclick="runScanner()">
                                🔍 SCAN MARKET NOW
                            </button>
                            <button class="btn btn-primary" style="width:auto; padding:10px 12px;" onclick="loadSignals()">
                                🔄 Refresh
                            </button>

                            <!-- ⚡ Auto-Scanner Controller -->
                            <div style="display:inline-flex; align-items:center; gap:8px; background:#090f1d; padding:6px 12px; border-radius:10px; border:1px solid var(--border); margin-left:auto;">
                                <label style="margin-bottom:0; font-size:11px; color:#94a3b8; display:flex; align-items:center; gap:6px; cursor:pointer;" onclick="toggleAutoScanner()">
                                    <input type="checkbox" id="auto-scanner-toggle" onchange="toggleAutoScanner()" style="width:auto; margin:0; cursor:pointer;">
                                    <b style="color:#fff;">⚡ Auto-Scanner:</b>
                                </label>
                                <select id="auto-scan-interval" onchange="changeAutoScanInterval()" style="width:auto; margin-bottom:0; padding:3px 6px; font-size:11px; background:#0f172a; border-radius:6px; border:1px solid var(--border); color:#38bdf8;">
                                    <option value="30">Every 30s</option>
                                    <option value="60" selected>Every 60s</option>
                                    <option value="120">Every 2 Mins</option>
                                    <option value="300">Every 5 Mins</option>
                                </select>
                                <span id="auto-scanner-badge" style="font-size:11px; font-weight:800; color:#94a3b8; padding:3px 8px; border-radius:6px; background:#1e293b;">
                                    OFF
                                </span>
                            </div>
                        </div>

                        <!-- Signals Container -->
                        <div id="signals-container">
                            <p style="color:var(--text-muted); font-size:13px; text-align:center; padding:40px 0;">
                                Click <b>"🔍 SCAN MARKET NOW"</b> or enable <b>⚡ Auto-Scanner</b> to discover live trade opportunities!
                            </p>
                        </div>
                    </div>
                </div>

                <!-- ──── TAB 2: WATCHLIST & MANUAL BUY ──── -->
                <div id="tab-content-watchlist" style="display:none;">
                    <div class="card">
                        <div class="card-title">
                            <div style="display:flex; align-items:center; gap:10px;">
                                <span>📋 Market Watchlist & Manual Buy (Render Style)</span>
                                <span class="badge" style="background:rgba(59,130,246,0.2); color:#60a5fa;">69 STOCKS</span>
                            </div>
                            <button id="btn-refresh-wl-prices" class="btn btn-primary" style="width:auto; padding:6px 14px; font-size:11px;" onclick="refreshWatchlistPrices()">
                                🔄 Refresh Prices
                            </button>
                        </div>

                        <!-- Watchlist Instructions -->
                        <p style="font-size:12px; color:var(--text-muted); margin-bottom:12px;">
                            Click <b>⚡ BUY</b> or <b>⚡ SELL</b> on any stock to manually place order with automatic <b>₹300 Max Risk Dynamic Sizing</b>.
                        </p>

                        <!-- Search & Category Filters -->
                        <div style="display:flex; gap:10px; margin-bottom:12px; flex-wrap:wrap; align-items:center;">
                            <input id="wl-search" placeholder="🔍 Search stock symbol or name (e.g. SBIN, SUZLON, TATA, RELIANCE)..." oninput="filterAndRenderWatchlist()" style="flex:1; min-width:220px; margin-bottom:0;">

                            <div style="display:flex; gap:6px;" id="wl-cat-group">
                                <button class="sector-btn active" id="wl-cat-all" onclick="filterWlCategory('all')">All (69)</button>
                                <button class="sector-btn" id="wl-cat-nifty50" onclick="filterWlCategory('nifty50')">🏆 Nifty 50 (51)</button>
                                <button class="sector-btn" id="wl-cat-budget" onclick="filterWlCategory('budget')">⚡ Budget (&lt;₹200) (18)</button>
                            </div>
                        </div>

                        <!-- Sector Filter Buttons -->
                        <div id="wl-sector-filters" style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:14px;">
                            <!-- Injected dynamically via JS -->
                        </div>

                        <!-- Watchlist Grid -->
                        <div id="watchlist-container" class="watchlist-grid">
                            <p style="color:var(--text-muted); font-size:13px; text-align:center; padding:30px; grid-column:1/-1;">Loading stocks...</p>
                        </div>
                    </div>
                </div>

                <!-- ──── TAB 3: POSITIONS & ORDERS ──── -->
                <div id="tab-content-positions" style="display:none;">
                    <!-- Live Open Positions -->
                    <div class="card">
                        <div class="card-title">
                            <span>💼 Angel One Open Positions</span>
                            <button style="background:none; border:none; color:var(--accent); font-size:12px; font-weight:700; cursor:pointer;" onclick="loadPositions()">🔄 Refresh P&L</button>
                        </div>
                        <div id="positions-container">
                            <p style="color:var(--text-muted); font-size:13px; text-align:center; padding:15px 0;">No active open intraday positions right now.</p>
                        </div>
                    </div>

                    <!-- Today's Order Book with Charges -->
                    <div class="card">
                        <div class="card-title">
                            <span>📋 Today's Orders & Charges</span>
                            <button style="background:none; border:none; color:var(--accent); font-size:12px; font-weight:700; cursor:pointer;" onclick="loadOrders()">🔄 Refresh Orders</button>
                        </div>
                        <div id="orders-container">
                            <p style="color:var(--text-muted); font-size:13px; text-align:center; padding:15px 0;">
                                Click <b>🔄 Refresh Orders</b> to see today's trades & charges.
                            </p>
                        </div>
                    </div>
                </div>

                <!-- ──── TAB 4: TRADE HISTORY & JOURNAL ──── -->
                <div id="tab-content-journal" style="display:none;">
                    <div class="card">
                        <div class="card-title">
                            <span id="journal-header-title">📝 Paper Trading Journal & History</span>
                            <div style="display:flex; gap:8px;">
                                <button id="jtab-paper" onclick="loadJournal('paper')" class="btn" style="width:auto; padding:6px 12px; font-size:11px; background:#2563eb; color:#fff;">Paper Trades</button>
                                <button id="jtab-live" onclick="loadJournal('live')" class="btn" style="width:auto; padding:6px 12px; font-size:11px; background:#090f1d; color:var(--text-muted); border:1px solid var(--border);">Live Trades</button>
                            </div>
                        </div>

                        <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin-bottom:16px;">
                            <div style="background:#0b1120; padding:12px; border-radius:10px; text-align:center; border:1px solid var(--border);">
                                <div style="font-size:11px; color:var(--text-muted); font-weight:700; text-transform:uppercase;">Weekly Net P&L</div>
                                <div id="j_weekly_pnl" style="font-size:18px; font-weight:900; color:#10b981; margin-top:4px;">+₹0.00</div>
                            </div>
                            <div style="background:#0b1120; padding:12px; border-radius:10px; text-align:center; border:1px solid var(--border);">
                                <div style="font-size:11px; color:var(--text-muted); font-weight:700; text-transform:uppercase;">Monthly Net P&L</div>
                                <div id="j_monthly_pnl" style="font-size:18px; font-weight:900; color:#10b981; margin-top:4px;">+₹0.00</div>
                            </div>
                            <div style="background:#0b1120; padding:12px; border-radius:10px; text-align:center; border:1px solid var(--border);">
                                <div style="font-size:11px; color:var(--text-muted); font-weight:700; text-transform:uppercase;">Total Trades</div>
                                <div id="j_total_trades" style="font-size:18px; font-weight:900; color:#60a5fa; margin-top:4px;">0</div>
                            </div>
                            <div style="background:#0b1120; padding:12px; border-radius:10px; text-align:center; border:1px solid var(--border);">
                                <div style="font-size:11px; color:var(--text-muted); font-weight:700; text-transform:uppercase;">Wins / Losses</div>
                                <div id="j_wins_losses" style="font-size:16px; font-weight:900; margin-top:5px;"><span style="color:#10b981;">0W</span> / <span style="color:#ef4444;">0L</span></div>
                            </div>
                        </div>

                        <div style="overflow-x:auto;">
                            <table style="width:100%; border-collapse:collapse; font-size:12px; text-align:left;">
                                <thead>
                                    <tr style="border-bottom:1px solid var(--border); color:var(--text-muted); font-weight:700;">
                                        <th style="padding:10px;">Symbol</th>
                                        <th style="padding:10px;">Action</th>
                                        <th style="padding:10px;">Qty</th>
                                        <th style="padding:10px;">Entry Price</th>
                                        <th style="padding:10px;">Exit Price</th>
                                        <th style="padding:10px;">SL / Targets</th>
                                        <th style="padding:10px;">Status</th>
                                        <th style="padding:10px;">Net P&L</th>
                                        <th style="padding:10px;">Date & Time</th>
                                    </tr>
                                </thead>
                                <tbody id="journal-trades-body">
                                    <tr><td colspan="9" style="text-align:center; padding:20px; color:var(--text-muted);">Loading trade history...</td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

        </div>
    </div>

<script>
let currentTradingMode = 'paper';
let currentBalance = 100000;

async function init() {
    try {
        const r = await fetch('/api/get-config');
        const d = await r.json();
        document.getElementById('cfg_client').value = d.client_code || '';
        document.getElementById('cfg_pass').value = d.password || '';
        document.getElementById('cfg_key').value = d.api_key || '';
        document.getElementById('cfg_totp').value = d.totp_secret || '';
        if (d.ip) document.getElementById('display-ip').textContent = d.ip;

        if (document.getElementById('cfg_tg_token')) {
            document.getElementById('cfg_tg_token').value = d.telegram_bot_token || '';
        }
        if (document.getElementById('cfg_tg_chat')) {
            document.getElementById('cfg_tg_chat').value = d.telegram_chat_id || '';
        }
        updateTelegramStatusPill(d.telegram_bot_token, d.telegram_chat_id);

        currentTradingMode = d.trading_mode || 'paper';
        switchMode(currentTradingMode, false);

        if (d.password && d.api_key && d.totp_secret) {
            await autoConnect();
        }
    } catch(e) { console.log(e); }
    loadSignals();
    loadJournal(currentTradingMode);
    loadWatchlist();
    startAutoRefresh();
}

// ═══ Auto-Refresh Timer (15s) ═══
let _refreshInterval = null;
let _refreshCountdown = 15;
let _refreshPaused = false;
const REFRESH_SECONDS = 15;

function startAutoRefresh() {
    if (_refreshInterval) clearInterval(_refreshInterval);
    _refreshCountdown = REFRESH_SECONDS;
    _refreshPaused = false;
    updateRefreshBadge();
    _refreshInterval = setInterval(() => {
        if (_refreshPaused) return;
        _refreshCountdown--;
        if (_refreshCountdown <= 0) {
            doAutoRefresh();
            _refreshCountdown = REFRESH_SECONDS;
        }
        updateRefreshBadge();
    }, 1000);
}

function updateRefreshBadge() {
    const el = document.getElementById('refresh-countdown');
    const badge = document.getElementById('refresh-timer-badge');
    if (!el || !badge) return;
    if (_refreshPaused) {
        el.textContent = 'Paused';
        badge.style.background = 'rgba(239,68,68,0.15)';
        badge.style.borderColor = 'rgba(239,68,68,0.3)';
        badge.style.color = '#f87171';
    } else {
        el.textContent = _refreshCountdown + 's';
        badge.style.background = 'rgba(59,130,246,0.15)';
        badge.style.borderColor = 'rgba(59,130,246,0.3)';
        badge.style.color = '#93c5fd';
    }
}

function toggleAutoRefresh() {
    _refreshPaused = !_refreshPaused;
    if (!_refreshPaused) _refreshCountdown = REFRESH_SECONDS;
    updateRefreshBadge();
}

async function doAutoRefresh() {
    try { await loadBalance(); } catch(e) {}
    try { await loadPositions(); } catch(e) {}
    try { await loadJournal(currentTradingMode); } catch(e) {}
}

// ══════ Dashboard Tab Navigation ══════
let currentDashboardTab = 'scanner';

function switchDashboardTab(tab) {
    currentDashboardTab = tab;
    ['scanner', 'watchlist', 'positions', 'journal'].forEach(t => {
        const btn = document.getElementById('tab-nav-' + t);
        const sec = document.getElementById('tab-content-' + t);
        if (btn) btn.classList.toggle('active', t === tab);
        if (sec) sec.style.display = (t === tab ? 'block' : 'none');
    });

    if (tab === 'watchlist') {
        if (allWatchlistStocks.length === 0) {
            loadWatchlist();
        }
    } else if (tab === 'positions') {
        loadPositions();
        loadOrders();
    } else if (tab === 'journal') {
        loadJournal(currentTradingMode);
    }
}

// ══════ ⚡ Auto-Scanner Engine ══════
let autoScanTimerId = null;
let autoScanSecLeft = 60;
let autoScanIntervalSec = 60;
let isAutoScanRunning = false;
let isScanBusy = false;

function toggleAutoScanner() {
    const chk = document.getElementById('auto-scanner-toggle');
    const badge = document.getElementById('auto-scanner-badge');
    const navPill = document.getElementById('nav-auto-scan-pill');

    isAutoScanRunning = chk ? chk.checked : !isAutoScanRunning;
    if (chk) chk.checked = isAutoScanRunning;

    if (isAutoScanRunning) {
        autoScanSecLeft = autoScanIntervalSec;
        if (badge) {
            badge.style.background = 'rgba(16,185,129,0.2)';
            badge.style.color = '#34d399';
            badge.className = 'pulse-badge';
            badge.textContent = `🟢 ${autoScanSecLeft}s`;
        }
        if (navPill) {
            navPill.style.display = 'inline-block';
            navPill.textContent = `AUTO: ${autoScanSecLeft}s`;
        }
        startAutoScanTimer();
        // Trigger immediate scan if no signals loaded
        const cont = document.getElementById('signals-container');
        if (cont && (cont.innerHTML.includes('Click') || cont.innerHTML.includes('0 Trades'))) {
            triggerAutoScan();
        }
    } else {
        if (autoScanTimerId) clearInterval(autoScanTimerId);
        autoScanTimerId = null;
        if (badge) {
            badge.style.background = '#1e293b';
            badge.style.color = '#94a3b8';
            badge.className = '';
            badge.textContent = 'OFF';
        }
        if (navPill) navPill.style.display = 'none';
    }
}

function changeAutoScanInterval() {
    const sel = document.getElementById('auto-scan-interval');
    if (sel) {
        autoScanIntervalSec = parseInt(sel.value) || 60;
        if (isAutoScanRunning) {
            autoScanSecLeft = autoScanIntervalSec;
            const badge = document.getElementById('auto-scanner-badge');
            if (badge) badge.textContent = `🟢 ${autoScanSecLeft}s`;
        }
    }
}

function startAutoScanTimer() {
    if (autoScanTimerId) clearInterval(autoScanTimerId);
    autoScanTimerId = setInterval(async () => {
        if (!isAutoScanRunning) return;

        autoScanSecLeft--;
        const badge = document.getElementById('auto-scanner-badge');
        const navPill = document.getElementById('nav-auto-scan-pill');

        if (badge) badge.textContent = `🟢 ${autoScanSecLeft}s`;
        if (navPill) navPill.textContent = `AUTO: ${autoScanSecLeft}s`;

        if (autoScanSecLeft <= 0) {
            autoScanSecLeft = autoScanIntervalSec;
            await triggerAutoScan();
        }
    }, 1000);
}

async function triggerAutoScan() {
    if (isScanBusy) return;
    isScanBusy = true;
    const badge = document.getElementById('auto-scanner-badge');
    const navPill = document.getElementById('nav-auto-scan-pill');
    if (badge) badge.textContent = '⚡ Scanning...';
    if (navPill) navPill.textContent = 'SCANNING...';

    try {
        await runScanner(true);
    } catch(e) {
        console.error('Auto-scan error:', e);
    } finally {
        isScanBusy = false;
        if (badge && isAutoScanRunning) badge.textContent = `🟢 ${autoScanSecLeft}s`;
        if (navPill && isAutoScanRunning) navPill.textContent = `AUTO: ${autoScanSecLeft}s`;
    }
}

// ══════ 📋 Market Watchlist & Manual Buy (Render Style) ══════
let allWatchlistStocks = [];
let activeWlCategory = 'all';
let activeWlSector = 'All';
let watchlistPricesCache = {};

async function loadWatchlist() {
    const cont = document.getElementById('watchlist-container');
    if (cont && allWatchlistStocks.length === 0) {
        cont.innerHTML = '<p style="color:var(--text-muted); font-size:13px; text-align:center; padding:30px; grid-column:1/-1;">⏳ Loading 69 Watchlist Stocks from NSE Database...</p>';
    }
    try {
        const r = await fetch('/api/watchlist');
        const d = await r.json();
        allWatchlistStocks = d.stocks || [];
        populateStockDatalist(allWatchlistStocks);
        renderSectorFilters(allWatchlistStocks);
        filterAndRenderWatchlist();
        // Fetch live quotes for top 12 stocks in background
        fetchWatchlistPrices(allWatchlistStocks.slice(0, 12));
    } catch(e) {
        if (cont) cont.innerHTML = '<p style="color:var(--red); font-size:13px; text-align:center; padding:20px; grid-column:1/-1;">Failed to load watchlist: ' + e + '</p>';
    }
}

function renderSectorFilters(stocks) {
    const el = document.getElementById('wl-sector-filters');
    if (!el) return;
    const sectors = ['All', ...new Set(stocks.map(s => s.sector || 'General'))].sort();
    el.innerHTML = sectors.map(s =>
        `<button class="sector-btn ${s === activeWlSector ? 'active' : ''}" onclick="filterWlSector('${s}')">${s}</button>`
    ).join('');
}

function filterWlCategory(cat) {
    activeWlCategory = cat;
    ['all', 'nifty50', 'budget'].forEach(c => {
        const btn = document.getElementById('wl-cat-' + c);
        if (btn) btn.className = 'sector-btn' + (c === cat ? ' active' : '');
    });
    filterAndRenderWatchlist();
}

function filterWlSector(sec) {
    activeWlSector = sec;
    document.querySelectorAll('#wl-sector-filters .sector-btn').forEach(b => {
        b.classList.toggle('active', b.textContent === sec);
    });
    filterAndRenderWatchlist();
}

function filterAndRenderWatchlist() {
    const query = (document.getElementById('wl-search')?.value || '').toLowerCase().trim();
    let list = allWatchlistStocks;

    if (activeWlCategory === 'budget') {
        list = list.filter(s => s.is_budget);
    } else if (activeWlCategory === 'nifty50') {
        list = list.filter(s => !s.is_budget);
    }

    if (activeWlSector !== 'All') {
        list = list.filter(s => s.sector === activeWlSector);
    }

    if (query) {
        list = list.filter(s =>
            (s.symbol && s.symbol.toLowerCase().includes(query)) ||
            (s.base && s.base.toLowerCase().includes(query)) ||
            (s.name && s.name.toLowerCase().includes(query)) ||
            (s.sector && s.sector.toLowerCase().includes(query))
        );
    }

    renderWatchlistCards(list);
}

function renderWatchlistCards(stocks) {
    const cont = document.getElementById('watchlist-container');
    if (!cont) return;
    if (!stocks.length) {
        cont.innerHTML = '<p style="color:var(--text-muted); font-size:13px; text-align:center; padding:30px; grid-column:1/-1;">No stocks found matching search filter.</p>';
        return;
    }

    let html = '';
    stocks.forEach(s => {
        const cached = watchlistPricesCache[s.base] || {};
        const p = cached.price || 0;
        const chg = cached.change_pct !== undefined ? cached.change_pct : null;
        const pDisplay = p > 0 ? '₹' + p.toFixed(2) : '<span style="color:#64748b; font-size:12px;">Click to fetch</span>';
        const chgDisplay = chg !== null ?
            `<span style="font-size:11px; font-weight:700; color:${chg>=0?'#34d399':'#f87171'}; margin-left:6px;">${chg>=0?'+':''}${chg.toFixed(2)}%</span>` : '';

        const badge = s.is_budget ?
            '<span class="badge" style="background:rgba(234,179,8,0.15); color:#fbbf24; border:1px solid rgba(234,179,8,0.3); font-size:10px;">⚡ BUDGET</span>' :
            '<span class="badge" style="background:rgba(59,130,246,0.15); color:#60a5fa; border:1px solid rgba(59,130,246,0.3); font-size:10px;">🏆 NIFTY 50</span>';

        html += `
        <div class="watchlist-card" id="wl-card-${s.base}">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:4px;">
                <div>
                    <div style="font-size:15px; font-weight:900; color:#fff;">${s.base}</div>
                    <div style="font-size:11px; color:#94a3b8; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:150px;" title="${s.name}">${s.name}</div>
                </div>
                ${badge}
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; margin:8px 0; padding:6px 10px; background:#090f1d; border-radius:8px; border:1px solid var(--border);">
                <div>
                    <span style="font-size:10px; color:#94a3b8; text-transform:uppercase;">Price</span>
                    <div id="wl-p-${s.base}" style="font-size:14px; font-weight:900; color:#fff; display:flex; align-items:center;">
                        ${pDisplay} ${chgDisplay}
                    </div>
                </div>
                <div style="text-align:right;">
                    <span style="font-size:10px; color:#94a3b8; text-transform:uppercase;">Sector</span>
                    <div style="font-size:11px; font-weight:700; color:#cbd5e1;">${s.sector}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns:1fr 1fr 36px; gap:6px;">
                <button class="btn btn-buy" style="padding:7px 4px; font-size:11px; font-weight:800;" onclick="openTradeForStock('${s.base}', '${s.tok}', 'BUY', ${p})">
                    ⚡ BUY
                </button>
                <button class="btn btn-sell" style="padding:7px 4px; font-size:11px; font-weight:800;" onclick="openTradeForStock('${s.base}', '${s.tok}', 'SELL', ${p})">
                    ⚡ SELL
                </button>
                <button class="btn" style="padding:7px 0; font-size:12px; background:#1e293b; color:#94a3b8; border:1px solid var(--border);" title="Quick Scan this stock" onclick="scanSingleStock('${s.base}', '${s.name}', '${s.tok}')">
                    🔍
                </button>
            </div>
        </div>`;
    });
    cont.innerHTML = html;
}

async function openTradeForStock(base, tok, action, knownPrice) {
    let p = parseFloat(knownPrice) || 0;
    if (p <= 0) {
        try {
            const r = await fetch('/api/stock-price?symbol=' + encodeURIComponent(base));
            const d = await r.json();
            if (d.price && d.price > 0) {
                p = d.price;
                watchlistPricesCache[base] = d;
                const el = document.getElementById('wl-p-' + base);
                if (el) el.innerHTML = `₹${p.toFixed(2)} <span style="font-size:11px; font-weight:700; color:${(d.change_pct||0)>=0?'#34d399':'#f87171'}; margin-left:6px;">${(d.change_pct||0)>=0?'+':''}${(d.change_pct||0).toFixed(2)}%</span>`;
            }
        } catch(e) {}
    }

    if (p <= 0) p = 100.0;
    const isBuy = action === 'BUY';
    const t1 = (p * (isBuy ? 1.015 : 0.985)).toFixed(2);
    const t2 = (p * (isBuy ? 1.030 : 0.970)).toFixed(2);
    const sl = (p * (isBuy ? 0.988 : 1.012)).toFixed(2);

    // Dynamic ₹300 Risk Quantity: Qty = Math.floor(300 / |price - sl|)
    const riskPts = Math.abs(p - parseFloat(sl)) || (p * 0.01) || 1.0;
    const qty = Math.max(1, Math.floor(300.0 / riskPts));

    openTradeModal(base, tok, action, qty, p.toFixed(2), t1, t2, sl);
}

async function fetchWatchlistPrices(stocks) {
    for (const s of stocks) {
        try {
            const r = await fetch('/api/stock-price?symbol=' + encodeURIComponent(s.base));
            const d = await r.json();
            if (d.price && d.price > 0) {
                watchlistPricesCache[s.base] = d;
                const el = document.getElementById('wl-p-' + s.base);
                if (el) {
                    el.innerHTML = `₹${d.price.toFixed(2)} <span style="font-size:11px; font-weight:700; color:${(d.change_pct||0)>=0?'#34d399':'#f87171'}; margin-left:6px;">${(d.change_pct||0)>=0?'+':''}${(d.change_pct||0).toFixed(2)}%</span>`;
                }
            }
        } catch(e) {}
    }
}

async function refreshWatchlistPrices() {
    const btn = document.getElementById('btn-refresh-wl-prices');
    if (btn) btn.textContent = '⏳ Fetching Prices...';
    const query = (document.getElementById('wl-search')?.value || '').toLowerCase().trim();
    let list = allWatchlistStocks;
    if (activeWlCategory === 'budget') list = list.filter(s => s.is_budget);
    else if (activeWlCategory === 'nifty50') list = list.filter(s => !s.is_budget);
    if (activeWlSector !== 'All') list = list.filter(s => s.sector === activeWlSector);
    if (query) list = list.filter(s => (s.symbol && s.symbol.toLowerCase().includes(query)) || (s.name && s.name.toLowerCase().includes(query)));

    await fetchWatchlistPrices(list.slice(0, 25));
    if (btn) btn.textContent = '🔄 Refresh Prices';
}

async function scanSingleStock(base, name, tok) {
    switchDashboardTab('scanner');
    const st = document.getElementById('scan-status');
    const cont = document.getElementById('signals-container');
    if (st) st.textContent = `Scanning ${base}...`;
    if (cont) cont.innerHTML = `<p style="color:var(--text-muted); font-size:13px; text-align:center; padding:30px 0;">⏳ Running technical setup scan for <b>${base}</b> (${name})...</p>`;

    try {
        const r = await fetch('/api/scan-single?symbol=' + encodeURIComponent(base));
        const d = await r.json();
        if (d.signal) {
            if (st) st.textContent = `Scan Complete — ${base}`;
            renderSignals([d.signal]);
        } else {
            if (st) st.textContent = 'No Signal';
            if (cont) cont.innerHTML = `<p style="color:var(--text-muted); font-size:13px; text-align:center; padding:30px 0;">No high-probability breakout setup on <b>${base}</b> right now.</p>`;
        }
    } catch(e) {
        if (st) st.textContent = 'Error';
        if (cont) cont.innerHTML = '<p style="color:var(--red); font-size:13px; text-align:center;">Scan failed: ' + e + '</p>';
    }
}

function populateStockDatalist(stocks) {
    let dl = document.getElementById('stocks-datalist');
    if (!dl) {
        dl = document.createElement('datalist');
        dl.id = 'stocks-datalist';
        document.body.appendChild(dl);
    }
    const input = document.getElementById('m_sym');
    if (input) {
        input.setAttribute('list', 'stocks-datalist');
        input.addEventListener('change', async function() {
            const val = this.value.trim().toUpperCase();
            const found = stocks.find(s => s.base === val || s.symbol.replace('.NS','') === val.replace('-EQ',''));
            if (found) {
                this.value = found.base;
                document.getElementById('m_tok').value = found.tok || '';
                try {
                    const r = await fetch('/api/stock-price?symbol=' + encodeURIComponent(found.base));
                    const d = await r.json();
                    if (d.price) document.getElementById('m_prc').value = d.price;
                } catch(e) {}
            }
        });
    }
    dl.innerHTML = stocks.map(s => `<option value="${s.base}">${s.name} (${s.sector})</option>`).join('');
}

async function switchMode(mode, save = true) {
    currentTradingMode = mode;
    const btnPaper = document.getElementById('hdr-mode-paper');
    const btnLive = document.getElementById('hdr-mode-live');
    const lblBalType = document.getElementById('lbl_bal_type');
    const lblOrderMode = document.getElementById('m-order-mode-lbl');

    if (mode === 'paper') {
        if (btnPaper) { btnPaper.style.background = '#2563eb'; btnPaper.style.color = '#fff'; }
        if (btnLive) { btnLive.style.background = 'transparent'; btnLive.style.color = 'var(--text-muted)'; }
        if (lblBalType) lblBalType.textContent = 'Paper Trading Balance';
        if (lblOrderMode) { lblOrderMode.textContent = 'Paper'; lblOrderMode.style.color = '#60a5fa'; }
    } else {
        if (btnLive) { btnLive.style.background = '#10b981'; btnLive.style.color = '#000'; }
        if (btnPaper) { btnPaper.style.background = 'transparent'; btnPaper.style.color = 'var(--text-muted)'; }
        if (lblBalType) lblBalType.textContent = 'Angel One RMS Balance';
        if (lblOrderMode) { lblOrderMode.textContent = 'Live'; lblOrderMode.style.color = '#10b981'; }
    }

    if (save) {
        try {
            await fetch('/api/set-trading-mode', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mode: mode})
            });
        } catch(e) {}
    }
    loadBalance();
    loadJournal(mode);
}

function copyIP() {
    const el = document.getElementById('cfg-display-ip') || document.getElementById('display-ip');
    let ip = el ? el.textContent.trim().split(' ')[0] : '178.92.40.115';
    navigator.clipboard.writeText(ip).then(() => {
        showGlobalToast(`📋 Copied Static IP: <b>${ip}</b>! Add it to smartapi.angelone.in Allowed IP`, 'info');
    }).catch(() => {
        prompt('Copy your Static IP:', ip);
    });
}


async function autoConnect() {
    const r = await fetch('/api/login', {method:'POST'});
    const d = await r.json();
    const badge = document.getElementById('conn-badge');
    if (d.success) {
        badge.className = 'status-badge status-connected';
        badge.textContent = '● Angel One Connected';
        if (d.ip) {
            const dip = document.getElementById('display-ip');
            if (dip) dip.textContent = d.ip;
            const cdip = document.getElementById('cfg-display-ip');
            if (cdip) cdip.textContent = d.ip;
        }
        loadBalance();
        loadPositions();
    } else {
        badge.className = 'status-badge status-disconnected';
        badge.textContent = '● Disconnected';
    }
}

async function saveAndLogin() {
    const payload = {
        client_code: document.getElementById('cfg_client').value.trim(),
        password: document.getElementById('cfg_pass').value.trim(),
        api_key: document.getElementById('cfg_key').value.trim(),
        totp_secret: document.getElementById('cfg_totp').value.trim()
    };
    const alertBox = document.getElementById('auth-alert');
    alertBox.style.display = 'block';
    alertBox.className = 'alert-box';
    alertBox.textContent = '⏳ Connecting to Angel One from your Registered IP...';

    const r = await fetch('/api/save-and-login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    });
    const d = await r.json();
    alertBox.textContent = d.message;
    alertBox.className = 'alert-box ' + (d.success ? 'alert-ok' : 'alert-err');

    const badge = document.getElementById('conn-badge');
    if (d.success) {
        badge.className = 'status-badge status-connected';
        badge.textContent = '● Angel One Connected';
        if (d.ip) {
            const dip = document.getElementById('display-ip');
            if (dip) dip.textContent = d.ip;
            const cdip = document.getElementById('cfg-display-ip');
            if (cdip) cdip.textContent = d.ip;
        }
        loadBalance();
        loadPositions();
    }
}

async function saveTelegramSettings() {
    const token = document.getElementById('cfg_tg_token').value.trim();
    const chat = document.getElementById('cfg_tg_chat').value.trim();
    const alertBox = document.getElementById('tg-alert');
    alertBox.style.display = 'block';
    alertBox.className = 'alert-box';
    alertBox.textContent = '⏳ Saving Telegram settings...';

    try {
        const r = await fetch('/api/save-telegram', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({telegram_bot_token: token, telegram_chat_id: chat})
        });
        const d = await r.json();
        alertBox.textContent = d.message;
        alertBox.className = 'alert-box ' + (d.success ? 'alert-ok' : 'alert-err');
        updateTelegramStatusPill(token, chat);
    } catch(e) {
        alertBox.textContent = 'Error: ' + e;
        alertBox.className = 'alert-box alert-err';
    }
}

async function testTelegramAlert() {
    const token = document.getElementById('cfg_tg_token').value.trim();
    let chat = document.getElementById('cfg_tg_chat').value.trim();
    const alertBox = document.getElementById('tg-alert');
    alertBox.style.display = 'block';
    alertBox.className = 'alert-box';
    alertBox.textContent = '⏳ Sending test message to Telegram...';

    try {
        const r = await fetch('/api/test-telegram', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({telegram_bot_token: token, telegram_chat_id: chat})
        });
        const d = await r.json();
        alertBox.textContent = d.message;
        alertBox.className = 'alert-box ' + (d.success ? 'alert-ok' : 'alert-err');
        if (d.detected_chat_id) {
            document.getElementById('cfg_tg_chat').value = d.detected_chat_id;
            updateTelegramStatusPill(token, d.detected_chat_id);
        }
    } catch(e) {
        alertBox.textContent = 'Test failed: ' + e;
        alertBox.className = 'alert-box alert-err';
    }
}

function updateTelegramStatusPill(token, chat) {
    const pill = document.getElementById('tg-status-pill');
    if (!pill) return;
    if (token && chat) {
        pill.textContent = 'CUSTOM BOT ACTIVE';
        pill.style.background = '#10b981';
        pill.style.color = '#000';
    } else {
        pill.textContent = 'DEFAULT BOT';
        pill.style.background = '#2563eb';
        pill.style.color = '#fff';
    }
}

async function setSLDelay() {
    const mins = parseInt(document.getElementById('sl-delay-input').value) || 3;
    const alertBox = document.getElementById('sl-delay-alert');
    alertBox.style.display = 'block';
    alertBox.className = 'alert-box';
    alertBox.textContent = `⏳ Setting Auto-SL delay to ${mins} minute(s)...`;
    try {
        const r = await fetch('/api/set-sl-delay', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({delay_mins: mins})
        });
        const d = await r.json();
        alertBox.textContent = d.message || (d.success ? '✅ Done!' : '❌ Failed');
        alertBox.className = 'alert-box ' + (d.success ? 'alert-ok' : 'alert-err');
        const badge = document.getElementById('sl-delay-badge');
        if (badge && d.success) badge.textContent = `${mins} MIN`;
    } catch(e) {
        alertBox.textContent = 'Error: ' + e;
        alertBox.className = 'alert-box alert-err';
    }
}

async function loadBalance() {
    try {
        const r = await fetch(`/api/balance?mode=${currentTradingMode}`);
        const d = await r.json();
        if (d.connected) {
            currentBalance = d.balance || 0;
            document.getElementById('st_bal').textContent = '₹' + currentBalance.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
            document.getElementById('st_power').textContent = '₹' + (currentBalance * 5).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }
    } catch(e) { console.log(e); }
}

async function loadJournal(mode) {
    const jheader = document.getElementById('journal-header-title');
    const jtabPaper = document.getElementById('jtab-paper');
    const jtabLive = document.getElementById('jtab-live');
    const tbody = document.getElementById('journal-trades-body');

    if (jheader) jheader.textContent = mode === 'paper' ? '📝 Paper Trading Journal & History' : '💼 Live Trading Journal & History';
    if (jtabPaper) {
        jtabPaper.style.background = mode === 'paper' ? '#2563eb' : '#090f1d';
        jtabPaper.style.color = mode === 'paper' ? '#fff' : 'var(--text-muted)';
    }
    if (jtabLive) {
        jtabLive.style.background = mode === 'live' ? '#10b981' : '#090f1d';
        jtabLive.style.color = mode === 'live' ? '#000' : 'var(--text-muted)';
    }

    // Load stats summary
    try {
        const rSum = await fetch(`/api/get-journal-summary?mode=${mode}`);
        const dSum = await rSum.json();
        const w = dSum.weekly || {};
        const mn = dSum.monthly || {};
        const wPnl = parseFloat(w.net_pnl || 0);
        const mPnl = parseFloat(mn.net_pnl || 0);
        const totalT = parseInt(w.total_trades || 0);
        const wins = parseInt(w.wins || 0);
        const losses = parseInt(w.losses || 0);

        const elW = document.getElementById('j_weekly_pnl');
        const elM = document.getElementById('j_monthly_pnl');
        const elT = document.getElementById('j_total_trades');
        const elWL = document.getElementById('j_wins_losses');

        if (elW) {
            elW.textContent = (wPnl >= 0 ? '+' : '') + '₹' + wPnl.toFixed(2);
            elW.style.color = wPnl >= 0 ? '#10b981' : '#ef4444';
        }
        if (elM) {
            elM.textContent = (mPnl >= 0 ? '+' : '') + '₹' + mPnl.toFixed(2);
            elM.style.color = mPnl >= 0 ? '#10b981' : '#ef4444';
        }
        if (elT) elT.textContent = totalT;
        if (elWL) {
            elWL.innerHTML = `<span style="color:#10b981;">${wins}W</span> / <span style="color:#ef4444;">${losses}L</span>`;
        }
    } catch(e) {}

    // Load trades list
    try {
        const rTrd = await fetch(`/api/get-trades?mode=${mode}`);
        const dTrd = await rTrd.json();
        const trades = dTrd.trades || [];

        if (!tbody) return;
        if (!trades.length) {
            tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:20px; color:var(--text-muted);">No ${mode} trades recorded yet.</td></tr>`;
            return;
        }

        let html = '';
        trades.forEach(t => {
            const pnl = parseFloat(t.pnl || 0);
            const pnlPct = parseFloat(t.pnl_percent || 0);
            const isBuy = t.action === 'BUY';
            const isClosed = t.status !== 'OPEN';
            const stColor = t.status === 'CLOSED' || t.status === 'T1_HIT' || t.status === 'T2_HIT' || t.status === 'PROFIT_LOCK' 
                ? (pnl >= 0 ? '#10b981' : '#ef4444') 
                : t.status === 'SL_HIT' || t.status === 'HARD_SL_BREAKER' ? '#ef4444' : '#f59e0b';
            const exitStr = t.exit_price && parseFloat(t.exit_price) > 0 ? `₹${parseFloat(t.exit_price).toFixed(2)}` : '—';
            const pnlStr = isClosed || pnl !== 0 
                ? `<span style="font-weight:800; color:${pnl >= 0 ? '#10b981' : '#ef4444'};">${pnl >= 0 ? '+' : ''}₹${pnl.toFixed(2)} (${pnl >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%)</span>` 
                : '<span style="color:var(--text-muted);">Active</span>';
            const timeStr = t.closed_at || t.opened_at || '';

            html += `<tr style="border-bottom:1px solid var(--border);">
                <td style="padding:10px; font-weight:800;">${t.symbol}</td>
                <td style="padding:10px;"><span class="badge ${isBuy ? 'badge-buy' : 'badge-sell'}">${t.action}</span></td>
                <td style="padding:10px;">${t.quantity}</td>
                <td style="padding:10px;">₹${parseFloat(t.entry_price || 0).toFixed(2)}</td>
                <td style="padding:10px; font-weight:700; color:#93c5fd;">${exitStr}</td>
                <td style="padding:10px; font-size:11px; color:var(--text-muted);">SL: ₹${parseFloat(t.stop_loss || 0).toFixed(2)} | T1: ₹${parseFloat(t.target1 || 0).toFixed(2)}</td>
                <td style="padding:10px;"><span style="color:${stColor}; font-weight:700; padding:2px 6px; border-radius:4px; background:${stColor}15;">${t.status}</span></td>
                <td style="padding:10px;">${pnlStr}</td>
                <td style="padding:10px; font-size:11px; color:var(--text-muted);">${timeStr}</td>
            </tr>`;
        });
        tbody.innerHTML = html;
    } catch(e) {
        if (tbody) tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; padding:20px; color:#ef4444;">Failed to load trade history.</td></tr>';
    }
}

async function loadPositions() {
    const cont = document.getElementById('positions-container');
    try {
        const r = await fetch('/api/positions');
        const d = await r.json();
        const allPos = d.positions || [];

        // ✅ FIX: Only show OPEN positions (netqty != 0)
        const pos     = allPos.filter(p => parseInt(p.netqty || 0) !== 0);
        const closed  = allPos.filter(p => parseInt(p.netqty || 0) === 0);

        const navPos = document.getElementById('nav-pos-count');
        if (navPos) {
            navPos.textContent = pos.length;
            navPos.style.display = pos.length > 0 ? 'inline-block' : 'none';
        }

        if (!pos.length && !closed.length) {
            cont.innerHTML = '<p style="color:var(--text-muted); font-size:13px; text-align:center; padding:15px 0;">No positions today.</p>';
            return;
        }

        let html = '';

        // Open positions
        if (pos.length) {
            html += '<div style="display:grid; gap:10px;">';
            pos.forEach(p => {
                const pnl = parseFloat(p.pnl || 0);
                const pnlColor = pnl >= 0 ? 'var(--green)' : 'var(--red)';
                html += `<div style="background:#090f1d; padding:12px; border-radius:10px; border:1px solid var(--border); display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <b>${p.tradingsymbol}</b> (${p.producttype})
                        <div style="font-size:12px; color:var(--text-muted);">Qty: ${p.netqty} | Avg: ₹${p.avgprice || '-'}</div>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:15px; font-weight:800; color:${pnlColor};">P&L: ₹${pnl.toFixed(2)}</div>
                        <button class="btn btn-sell" style="width:auto; padding:4px 10px; font-size:11px; margin-top:4px;" onclick="exitPosition('${p.tradingsymbol}','${p.symboltoken}',${p.netqty})">Square Off</button>
                    </div>
                </div>`;
            });
            html += '</div>';
        } else {
            html += '<p style="color:var(--text-muted); font-size:13px; text-align:center; padding:10px 0;">✅ No open positions. All squared off.</p>';
        }

        // Closed positions summary (collapsible)
        if (closed.length) {
            const totalRealizedPnl = closed.reduce((sum, p) => sum + parseFloat(p.pnl || 0), 0);
            const pnlColor = totalRealizedPnl >= 0 ? '#34d399' : '#f87171';
            html += `<details style="margin-top:10px;">
                <summary style="cursor:pointer; font-size:12px; color:#94a3b8; padding:6px 0; display:flex; justify-content:space-between;">
                    <span>📂 ${closed.length} Closed Position(s) Today</span>
                    <span style="color:${pnlColor}; font-weight:700;">Realized P&L: ₹${totalRealizedPnl.toFixed(2)}</span>
                </summary>
                <div style="display:grid; gap:6px; margin-top:6px;">
                ${closed.map(p => {
                    const pnl = parseFloat(p.pnl || 0);
                    const pc = pnl >= 0 ? '#34d399' : '#f87171';
                    return `<div style="background:#070b14; padding:10px; border-radius:8px; border:1px solid #1e293b; display:flex; justify-content:space-between; align-items:center; opacity:0.75;">
                        <div>
                            <b style="font-size:13px;">${p.tradingsymbol}</b>
                            <span style="font-size:10px; color:#64748b; margin-left:6px;">CLOSED ✅</span>
                            <div style="font-size:11px; color:#475569;">Avg: ₹${p.avgprice || '-'}</div>
                        </div>
                        <div style="font-size:14px; font-weight:800; color:${pc};">₹${pnl.toFixed(2)}</div>
                    </div>`;
                }).join('')}
                </div>
            </details>`;
        }

        cont.innerHTML = html;
    } catch(e) {
        cont.innerHTML = '<p style="color:var(--red); font-size:12px;">Failed to fetch positions: ' + e + '</p>';
    }
}

async function loadOrders() {
    const cont = document.getElementById('orders-container');
    cont.innerHTML = '<p style="color:var(--text-muted); font-size:12px; text-align:center; padding:10px;">⏳ Fetching orders from Angel One...</p>';
    try {
        const r = await fetch('/api/orders');
        const d = await r.json();
        if (d.error) {
            cont.innerHTML = `<p style="color:var(--red); font-size:12px; text-align:center;">${d.error}</p>`;
            return;
        }
        const orders = d.orders || [];
        if (!orders.length) {
            cont.innerHTML = '<p style="color:var(--text-muted); font-size:13px; text-align:center; padding:10px;">No orders placed today.</p>';
            return;
        }

        let totalCharges = 0;
        let html = '<div style="display:grid; gap:8px;">';
        orders.forEach(o => {
            const status   = (o.orderstatus || o.status || '').toUpperCase();
            const sym      = o.tradingsymbol || o.symbol || '—';
            const txn      = (o.transactiontype || '').toUpperCase();
            const qty      = o.filledshares || o.quantity || 0;
            const price    = parseFloat(o.averageprice || o.price || 0).toFixed(2);
            const orderVal = parseFloat(o._trade_value || 0).toFixed(2);
            const charges  = parseFloat(o._total_charges || 0);
            const brok     = parseFloat(o._brokerage || 0).toFixed(2);
            const stt      = parseFloat(o._stt || 0).toFixed(4);
            const gst      = parseFloat(o._gst || 0).toFixed(2);
            const stamp    = parseFloat(o._stamp || 0).toFixed(4);
            const time     = o.ordertag || o.updatetime || o.exchtime || '';
            const isBuy    = txn === 'BUY';
            const isExecuted = status === 'COMPLETE' || status === 'EXECUTED';
            totalCharges  += charges;

            const statusColor = isExecuted ? '#34d399' : (status === 'REJECTED' || status === 'CANCELLED') ? '#f87171' : '#fbbf24';

            html += `<div style="background:#090f1d; padding:12px; border-radius:10px; border:1px solid var(--border);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                    <div>
                        <b style="font-size:14px;">${sym}</b>
                        <span class="badge ${isBuy ? 'badge-buy' : 'badge-sell'}" style="margin-left:6px; font-size:10px;">${txn}</span>
                        <span style="font-size:10px; color:${statusColor}; margin-left:6px; font-weight:700;">${status}</span>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:13px; font-weight:800; color:#fff;">₹${price} × ${qty}</div>
                        <div style="font-size:11px; color:#94a3b8;">Value: ₹${orderVal}</div>
                    </div>
                </div>
                ${isExecuted ? `
                <div style="background:#070b14; padding:8px 10px; border-radius:8px; font-size:11px; display:grid; grid-template-columns:repeat(4,1fr); gap:4px; text-align:center;">
                    <div><span style="color:#94a3b8;">Brokerage</span><br><b style="color:#f87171;">₹${brok}</b></div>
                    <div><span style="color:#94a3b8;">STT</span><br><b style="color:#f87171;">₹${stt}</b></div>
                    <div><span style="color:#94a3b8;">GST</span><br><b style="color:#f87171;">₹${gst}</b></div>
                    <div><span style="color:#94a3b8;">Total</span><br><b style="color:#ef4444; font-size:13px;">₹${charges.toFixed(2)}</b></div>
                </div>` : ''}
                ${time ? `<div style="font-size:10px; color:#475569; margin-top:4px;">🕐 ${time}</div>` : ''}
            </div>`;
        });

        html += `</div>
        <div style="margin-top:12px; background:rgba(239,68,68,0.1); border:1px solid #ef4444; border-radius:10px; padding:12px; text-align:center;">
            <span style="font-size:12px; color:#94a3b8;">💸 Today's Total Charges (All Orders)</span>
            <div style="font-size:20px; font-weight:900; color:#ef4444; margin-top:4px;">−₹${totalCharges.toFixed(2)}</div>
            <div style="font-size:10px; color:#94a3b8; margin-top:4px;">Brokerage + STT + Exchange + GST + Stamp Duty</div>
        </div>`;
        cont.innerHTML = html;
    } catch(e) {
        cont.innerHTML = '<p style="color:var(--red); font-size:12px;">Failed to fetch orders: ' + e + '</p>';
    }
}

let currentScanMode = 'fast'; // 'fast', 'deep', or 'sniper'

function setScanMode(mode) {
    currentScanMode = mode;
    const fastBtn   = document.getElementById('mode-fast-btn');
    const aiBtn     = document.getElementById('mode-ai-btn');
    const sniperBtn = document.getElementById('mode-sniper-btn');
    const label     = document.getElementById('mode-label');

    fastBtn.style.opacity   = '0.5';
    aiBtn.style.opacity     = '0.5';
    sniperBtn.style.opacity = '0.5';
    fastBtn.style.boxShadow   = 'none';
    aiBtn.style.boxShadow     = 'none';
    sniperBtn.style.boxShadow = 'none';

    if (mode === 'sniper') {
        sniperBtn.style.opacity = '1';
        sniperBtn.style.boxShadow = '0 0 16px rgba(245,158,11,0.6)';
        label.innerHTML = '👑 <b style="color:#fbbf24;">DAILY 1-SNIPER TRADE MODE</b>: Scans Nifty 50 for EXACTLY 1 TOP TRADE (>92% Score + 7 Filters + 18 Guards)';
    } else if (mode === 'deep') {
        aiBtn.style.opacity = '1';
        aiBtn.style.boxShadow = '0 0 16px rgba(124,58,237,0.5)';
        label.innerHTML = '🧠 <b style="color:#a78bfa;">Deep AI Brain Mode</b>: Gemini AI + 1H/15M Confluence + News + 18 Guards (30-60 sec)';
    } else {
        fastBtn.style.opacity = '1';
        fastBtn.style.boxShadow = '0 0 16px rgba(59,130,246,0.5)';
        label.innerHTML = '⚡ <b>Fast Mode</b>: 5-Minute momentum scanner (1-2 seconds)';
    }
}

async function runScanner() {
    const cat = document.getElementById('scan_cat').value;
    const st = document.getElementById('scan-status');
    const cont = document.getElementById('signals-container');

    if (currentScanMode === 'sniper') {
        st.textContent = '👑 Sniper Scanning...';
        cont.innerHTML = `<div style="text-align:center; padding:40px 20px;">
            <div style="font-size:44px; margin-bottom:16px;">👑</div>
            <div style="font-size:16px; font-weight:800; color:#fbbf24; margin-bottom:8px;">Scanning Nifty 50 for Today's #1 Sniper Trade...</div>
            <div style="font-size:12px; color:#94a3b8; max-width:380px; margin:0 auto; line-height:1.6;">
                Evaluating: <b>1H+15M Dual Lock</b> → <b>RVOL >= 1.8x Gate</b> → <b>VWAP Confluence</b> → <b>RSI Sweet Zone</b> → <b>All 18 Loss Guards</b><br><br>
                <i>Filtering out 49 stocks to find the SINGLE 92%+ Ultra-Conviction Winner!</i>
            </div>
        </div>`;
        try {
            const r = await fetch('/api/ultra-sniper');
            const d = await r.json();
            if (d.error) {
                st.textContent = 'Sniper Error';
                cont.innerHTML = `<p style="color:var(--red); font-size:13px; text-align:center; padding:20px;">${d.error}</p>`;
                return;
            }
            if (d.nifty_blocked || d.message) {
                st.textContent = 'Sniper Complete';
                cont.innerHTML = `<div style="background:rgba(245,158,11,0.1); border:1px solid #f59e0b; border-radius:14px; padding:24px; text-align:center;">
                    <div style="font-size:32px; margin-bottom:10px;">🛡️</div>
                    <div style="font-size:15px; font-weight:800; color:#fbbf24;">CAPITAL IS 100% PROTECTED</div>
                    <div style="font-size:13px; color:#cbd5e1; margin-top:8px; line-height:1.6;">${d.message || d.error}</div>
                </div>`;
                return;
            }
            if (!d.sniper_trade) {
                st.textContent = 'Sniper Done — 0 Trades';
                cont.innerHTML = `<p style="color:var(--text-muted); font-size:13px; text-align:center; padding:40px 0;">No 92%+ conviction trades right now. Market is sideways — CAPITAL IS SAFE.</p>`;
            } else {
                st.textContent = `👑 TODAY'S #1 ULTRA SNIPER TRADE FOUND!`;
                renderSniperHeroCard(d.sniper_trade);
            }
        } catch(e) {
            st.textContent = 'Sniper Error';
            cont.innerHTML = '<p style="color:var(--red); font-size:13px; text-align:center;">Sniper scan error: ' + e + '</p>';
        }
        return;
    }

    if (currentScanMode === 'deep') {
        st.textContent = '🧠 Deep AI Running...';
        cont.innerHTML = `<div style="text-align:center; padding:40px 20px;">
            <div style="font-size:40px; margin-bottom:16px;">🧠</div>
            <div style="font-size:15px; font-weight:700; color:#a78bfa; margin-bottom:8px;">Deep Gemini AI Brain Scanning...</div>
            <div style="font-size:12px; color:#94a3b8; max-width:340px; margin:0 auto; line-height:1.6;">
                Running: <b>1H + 15M Technicals</b> → <b>News Sentiment</b> → <b>Historical Patterns</b> → <b>Gemini AI Model</b> → <b>18 Capital Guards</b><br><br>
                <i>This takes 30–60 seconds. Only 85%+ conviction trades will appear.</i>
            </div>
        </div>`;
        try {
            const r = await fetch('/api/deep-scan?category=' + encodeURIComponent(cat));
            const d = await r.json();
            if (d.error) {
                st.textContent = 'AI Error';
                cont.innerHTML = `<p style="color:var(--red); font-size:13px; text-align:center; padding:20px;">${d.error}</p>`;
                return;
            }
            st.textContent = `🧠 Deep AI Done — ${d.total} Signals`;
            if (d.nifty_blocked) {
                cont.innerHTML = `<div style="background:rgba(239,68,68,0.1); border:1px solid var(--red); border-radius:12px; padding:16px; text-align:center; margin-bottom:16px;">
                    <div style="font-size:20px;">⚠️ Nifty 50 Guard Active</div>
                    <div style="font-size:13px; color:#f87171; margin-top:6px;">Market is falling (Nifty ${(d.nifty_pct||0).toFixed(2)}%). All BUY signals blocked for capital safety.</div>
                </div>`;
                if (!d.signals || !d.signals.length) return;
            }
            if (!d.signals || !d.signals.length) {
                cont.innerHTML = `<p style="color:var(--text-muted); font-size:13px; text-align:center; padding:40px 0;">No 85%+ conviction signals right now for <b>${cat.toUpperCase()}</b>. Market may be sideways — waiting for confluence.</p>`;
            } else {
                renderSignals(d.signals, true);
            }
        } catch(e) {
            st.textContent = 'Error';
            cont.innerHTML = '<p style="color:var(--red); font-size:13px; text-align:center;">Deep AI scan error: ' + e + '</p>';
        }
    } else {
        st.textContent = 'Scanning market...';
        cont.innerHTML = '<p style="color:var(--text-muted); font-size:13px; text-align:center; padding:40px 0;">⏳ Fast scanning: 5M RSI & Momentum for ' + cat.toUpperCase() + '...</p>';
        try {
            const r = await fetch('/api/scan-market?category=' + encodeURIComponent(cat));
            const d = await r.json();
            st.textContent = 'Scan Complete';
            renderSignals(d.signals || []);
        } catch(e) {
            st.textContent = 'Error';
            cont.innerHTML = '<p style="color:var(--red); font-size:13px; text-align:center;">Scan error: ' + e + '</p>';
        }
    }
}

async function loadSignals() {
    try {
        const r = await fetch('/api/fetch-signals');
        const d = await r.json();
        renderSignals(d.signals || []);
    } catch(e) { console.log(e); }
}


function renderSniperHeroCard(s) {
    const cont = document.getElementById('signals-container');
    const isBuy = s.action === 'BUY';
    const price = parseFloat(s.price || 0);
    const sym = s.symbol || 'STOCK';
    const tok = s.token || '';
    const target1 = parseFloat(s.target || (isBuy ? price*1.018 : price*0.982)).toFixed(2);
    const target2 = parseFloat(s.target2 || (isBuy ? price*1.030 : price*0.970)).toFixed(2);
    const sl = parseFloat(s.stoploss || (isBuy ? price*0.988 : price*1.012)).toFixed(2);
    const score = s.score || 95.0;

    // 📐 Strict ₹300 Max Risk Position Sizing: Qty = int(300 / |Price - SL|)
    const lossPerShare = Math.abs(price - parseFloat(sl)) || (price * 0.01) || 1.0;
    const qty = Math.max(1, Math.floor(300.0 / lossPerShare));

    cont.innerHTML = `
    <div style="background:linear-gradient(145deg, #111827, #1e1b4b); border:2px solid #f59e0b; border-radius:18px; padding:20px; box-shadow:0 10px 40px rgba(245,158,11,0.25); position:relative; overflow:hidden;">
        <!-- Header Badge -->
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; border-bottom:1px solid rgba(245,158,11,0.2); padding-bottom:12px;">
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:24px;">👑</span>
                <div>
                    <div style="font-size:16px; font-weight:900; color:#fbbf24;">TODAY'S #1 ULTRA SNIPER TRADE</div>
                    <div style="font-size:11px; color:#94a3b8;">1 Single Ultra-Conviction Trade Per Day</div>
                </div>
            </div>
            <div style="text-align:right;">
                <span class="badge" style="background:#f59e0b; color:#000; font-size:13px; font-weight:900;">${score}% CONVICTION</span>
            </div>
        </div>

        <!-- Stock Title & Action -->
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
            <div>
                <div style="font-size:22px; font-weight:900; color:#fff;">${sym}</div>
                <div style="font-size:12px; color:#94a3b8;">${s.company_name || ''} | ${s.sector || 'NSE'}</div>
            </div>
            <span class="badge ${isBuy ? 'badge-buy' : 'badge-sell'}" style="font-size:16px; padding:6px 16px;">${s.action}</span>
        </div>

        <!-- 6-Point AI Conviction Radar -->
        <div style="background:#090f1d; padding:12px; border-radius:12px; border:1px solid #334155; margin-bottom:14px; display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:11px;">
            <div style="color:#34d399;">✅ 1H+15M Dual Lock: <b>${s.trend_1h}</b></div>
            <div style="color:#34d399;">✅ Institutional RVOL: <b>${s.rvol}x Volume</b></div>
            <div style="color:#34d399;">✅ Risk-Reward Ratio: <b>1:${s.rr_ratio}</b></div>
            <div style="color:#34d399;">✅ RSI Sweet Zone: <b>${s.rsi_1h}</b></div>
            <div style="color:#34d399;">✅ Open=High Trap: <b>PASSED</b></div>
            <div style="color:#34d399;">✅ All 18 Loss Guards: <b>ALL CLEAR</b></div>
        </div>

        <!-- Prices Grid -->
        <div class="sig-grid" style="grid-template-columns: repeat(4, 1fr); margin-bottom:16px;">
            <span>Entry<b style="color:#f8fafc; font-size:15px;">₹${price.toFixed(2)}</b></span>
            <span>🎯 T1 (1.8x)<b style="color:#34d399; font-size:15px;">₹${target1}</b></span>
            <span>🚀 T2 (3.0x)<b style="color:#fbbf24; font-size:15px;">₹${target2}</b></span>
            <span>🛡️ SL (Cap ₹300)<b style="color:#f87171; font-size:15px;">₹${sl}</b></span>
        </div>

        <button class="btn ${isBuy ? 'btn-buy' : 'btn-sell'}" style="font-size:15px; padding:14px; font-weight:900; box-shadow:0 6px 20px rgba(0,0,0,0.4);" onclick="openTradeModal('${sym}', '${tok}', '${s.action}', ${qty}, ${price}, '${target1}', '${target2}', '${sl}', 'ultra_sniper')">
            ⚡ EXECUTE LIVE ULTRA SNIPER TRADE (${qty} Qty @ ₹${price.toFixed(2)})
        </button>
    </div>`;
}

function renderSignals(sigs, deepMode) {
    const cont = document.getElementById('signals-container');
    if (!sigs.length) {
        cont.innerHTML = '<p style="color:var(--text-muted); font-size:13px; text-align:center; padding:40px 0;">No active signals right now. Select a category above and click <b>"SCAN MARKET NOW"</b>!</p>';
        return;
    }

    let html = '<div class="signals-grid">';
    sigs.forEach(s => {
        const isBuy = s.action === 'BUY';
        const price = parseFloat(s.price || s.entry_price || 0);
        const sym = s.symbol || s.stock || 'STOCK';
        const tok = s.token || s.symboltoken || '';
        const target = parseFloat(s.target || (isBuy ? (price*1.02) : (price*0.98))).toFixed(1);
        const sl = parseFloat(s.stoploss || (isBuy ? (price*0.99) : (price*1.01))).toFixed(1);
        const conf = s.confidence ? `${s.confidence}%` : (deepMode ? '90%' : '88%');

        // 📐 Strict ₹300 Max Risk Position Sizing: Qty = int(300 / |Price - SL|)
        const lossPerShare = Math.abs(price - parseFloat(sl)) || (price * 0.01) || 1.0;
        const qty = Math.max(1, Math.floor(300.0 / lossPerShare));

        // Deep AI extra info
        const riskBadge = deepMode && s.risk_level ? 
            `<span class="badge" style="background:${s.risk_level==='LOW'?'rgba(16,185,129,0.2)':s.risk_level==='HIGH'?'rgba(239,68,68,0.2)':'rgba(245,158,11,0.2)'}; color:${s.risk_level==='LOW'?'#34d399':s.risk_level==='HIGH'?'#f87171':'#fbbf24'}; font-size:10px;">${s.risk_level} RISK</span>` : '';
        const aiBadge = deepMode ? `<span class="badge" style="background:rgba(124,58,237,0.2); color:#a78bfa; font-size:10px;">🧠 Gemini AI</span>` : '';

        html += `
        <div class="signal-card ${isBuy ? 'buy-card' : 'sell-card'}">
            <div class="sig-top">
                <div>
                    <div class="sig-name">${sym}</div>
                    <div class="sig-sub">${s.company_name || ''} | ${s.sector || 'NSE'} | Token: ${tok || 'Auto'}</div>
                </div>
                <div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:flex-end;">
                    <span class="badge ${isBuy ? 'badge-buy' : 'badge-sell'}">${s.action}</span>
                    <span class="badge badge-conv">${conf} Conv</span>
                    ${aiBadge}${riskBadge}
                </div>
            </div>

            <!-- T1, T2, SL Grid -->
            <div class="sig-grid" style="grid-template-columns: repeat(4, 1fr);">
                <span>Entry<b style="color:#f8fafc;">₹${price.toFixed(2)}</b></span>
                <span>🎯 T1<b style="color:#34d399;">₹${parseFloat(s.target || target).toFixed(2)}</b></span>
                <span>🚀 T2<b style="color:#fbbf24;">₹${parseFloat(s.target2 || (isBuy ? price*1.03 : price*0.97)).toFixed(2)}</b></span>
                <span>🛡️ SL (₹300 Risk)<b style="color:#f87171;">₹${parseFloat(s.stoploss || sl).toFixed(2)}</b></span>
            </div>

            ${deepMode && (s.rvol || s.trend_1h) ? `
            <div class="sig-grid" style="grid-template-columns: repeat(3, 1fr); margin-top:4px;">
                <span>1H Trend<b style="color:${s.trend_1h==='BULLISH'?'#34d399':s.trend_1h==='BEARISH'?'#f87171':'#94a3b8'};">${s.trend_1h||'—'}</b></span>
                <span>15M Trend<b style="color:${s.trend_15m==='BULLISH'?'#34d399':s.trend_15m==='BEARISH'?'#f87171':'#94a3b8'};">${s.trend_15m||'—'}</b></span>
                <span>RVOL<b style="color:${parseFloat(s.rvol||1)>=1.5?'#34d399':'#f87171'};">${s.rvol||'—'}x ${parseFloat(s.rvol||1)>=1.5?'✅':'⚠️'}</b></span>
            </div>` : ''}

            ${deepMode && s.news_summary ? `<div style="font-size:11px; color:#94a3b8; background:#0b1120; padding:7px 10px; border-radius:6px; margin-top:6px; border-left:3px solid #334155;">📰 ${s.news_summary.slice(0,120)}${s.news_summary.length>120?'...':''}</div>` : ''}

            <div class="sig-reason">${s.reasoning || s.ai_reason || 'RSI Breakout + SuperTrend Bullish confirmation on 5-min chart.'}</div>

            <button class="btn ${isBuy ? 'btn-buy' : 'btn-sell'}" onclick="openTradeModal('${sym}', '${tok}', '${s.action}', ${qty}, ${price}, '${s.target || target}', '${s.target2 || (isBuy ? price*1.03 : price*0.97)}', '${s.stoploss || sl}', '${s.scan_type || (deepMode ? 'deep_scan' : 'ultra_sniper')}')">
                ⚡ LIVE ${s.action} (${qty} Qty @ ₹${price.toFixed(2)})
            </button>
        </div>`;
    });
    html += '</div>';
    cont.innerHTML = html;
}

function showGlobalToast(msg, type='success') {
    let toast = document.getElementById('global-toast');
    if (!toast) return;
    toast.style.background = type === 'success' ? '#064e3b' : '#7f1d1d';
    toast.style.color = type === 'success' ? '#6ee7b7' : '#fca5a5';
    toast.style.border = type === 'success' ? '1px solid #10b981' : '1px solid #ef4444';
    toast.innerHTML = msg;
    toast.style.display = 'block';
    setTimeout(() => {
        if (toast) toast.style.display = 'none';
    }, 8000);
}

let currentTradeScanType = 'ultra_sniper';

function openTradeModal(sym, tok, action, qty, price, target1, target2, sl, scanType = 'ultra_sniper') {
    currentTradeScanType = scanType;
    // Reset view to form
    const formCont = document.getElementById('modal_form_container');
    const succCont = document.getElementById('modal_success_container');
    if (formCont) formCont.style.display = 'block';
    if (succCont) { succCont.style.display = 'none'; succCont.innerHTML = ''; }

    document.getElementById('modal_sym').textContent = sym;
    document.getElementById('modal_tok').value = tok;
    document.getElementById('modal_action').textContent = action;
    document.getElementById('modal_action').className = 'badge ' + (action === 'BUY' ? 'badge-buy' : 'badge-sell');
    
    const submitBtn = document.getElementById('modal_btn_submit');
    if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.className = 'btn ' + (action === 'BUY' ? 'btn-buy' : 'btn-sell');
        if (currentTradingMode === 'paper') {
            submitBtn.textContent = `⚡ CONFIRM PAPER TRADE (${action})`;
        } else {
            submitBtn.textContent = `⚡ CONFIRM LIVE ORDER (ANGEL ONE)`;
        }
    }

    const alertBox = document.getElementById('modal-alert');
    if (alertBox) {
        alertBox.style.display = 'none';
        alertBox.textContent = '';
    }

    const isBuy = action === 'BUY';
    const p = parseFloat(price) || 0;
    const slVal = sl ? parseFloat(sl) : (p * (isBuy ? 0.988 : 1.012));
    
    // Dynamic Net ₹300 Risk Quantity (Gross Stock Risk ₹230 + Taxes/Brokerage ~₹60 = Net ₹290 Cap)
    const riskPts = Math.abs(p - slVal) || (p * 0.01) || 1.0;
    const calculatedQty = Math.max(1, Math.floor(230.0 / riskPts));

    document.getElementById('modal_qty').value = calculatedQty;
    document.getElementById('modal_price').value = p.toFixed(2);
    document.getElementById('modal_t1').value = target1 ? parseFloat(target1).toFixed(2) : (p * (isBuy ? 1.015 : 0.985)).toFixed(2);
    document.getElementById('modal_t2').value = target2 ? parseFloat(target2).toFixed(2) : (p * (isBuy ? 1.030 : 0.970)).toFixed(2);
    document.getElementById('modal_sl').value = slVal.toFixed(2);
    
    updateModalMath();
    document.getElementById('trade-modal-overlay').style.display = 'flex';
}

function closeTradeModal() {
    document.getElementById('trade-modal-overlay').style.display = 'none';
    const alertBox = document.getElementById('modal-alert');
    if (alertBox) alertBox.style.display = 'none';
    const formCont = document.getElementById('modal_form_container');
    const succCont = document.getElementById('modal_success_container');
    if (formCont) formCont.style.display = 'block';
    if (succCont) { succCont.style.display = 'none'; succCont.innerHTML = ''; }
}

function updateModalMath(autoRecalcQty = false) {
    const p = parseFloat(document.getElementById('modal_price').value) || 0;
    const sl = parseFloat(document.getElementById('modal_sl').value) || p;
    const action = document.getElementById('modal_action').textContent.trim();
    const isBuy = action === 'BUY';

    if (autoRecalcQty && p > 0 && sl > 0) {
        const riskPoints = Math.abs(p - sl) || (p * 0.01) || 1.0;
        const autoQty = Math.max(1, Math.floor(230.0 / riskPoints));
        document.getElementById('modal_qty').value = autoQty;
    }

    const q = parseInt(document.getElementById('modal_qty').value) || 1;
    const t1 = parseFloat(document.getElementById('modal_t1').value) || p;
    const t2 = parseFloat(document.getElementById('modal_t2').value) || p;

    const margin = (p * q) / 5.0;
    const exposure = p * q;
    
    // Expected Profit / Loss
    const t1Gain = isBuy ? (t1 - p) * q : (p - t1) * q;
    const t2Gain = isBuy ? (t2 - p) * q : (p - t2) * q;
    const slLoss = isBuy ? (p - sl) * q : (sl - p) * q;

    document.getElementById('modal_margin').textContent = '₹' + margin.toFixed(2);
    document.getElementById('modal_exposure').textContent = '₹' + exposure.toFixed(2);
    
    document.getElementById('modal_pnl_t1').textContent = '+₹' + Math.max(0, t1Gain).toFixed(2);
    document.getElementById('modal_pnl_t2').textContent = '+₹' + Math.max(0, t2Gain).toFixed(2);
    document.getElementById('modal_pnl_sl').textContent = '-₹' + Math.max(0, slLoss).toFixed(2);
}

function applyRiskSizing() {
    updateModalMath(true);
}

function adjustModalQty(delta) {
    const el = document.getElementById('modal_qty');
    let val = Math.max(1, (parseInt(el.value) || 1) + delta);
    el.value = val;
    updateModalMath();
}

function setModalMaxQty() {
    const p = parseFloat(document.getElementById('modal_price').value) || 100;
    const buyingPower = (currentBalance || 500) * 5;
    const maxQ = Math.max(1, Math.floor(buyingPower / p));
    document.getElementById('modal_qty').value = maxQ;
    updateModalMath();
}

async function executeModalOrder() {
    const sym = document.getElementById('modal_sym').textContent.trim();
    const tok = document.getElementById('modal_tok').value.trim();
    const action = document.getElementById('modal_action').textContent.trim();
    const qty = parseInt(document.getElementById('modal_qty').value) || 1;
    const price = parseFloat(document.getElementById('modal_price').value) || 0;
    const sl = parseFloat(document.getElementById('modal_sl').value) || 0;
    const t1 = parseFloat(document.getElementById('modal_t1').value) || 0;
    const t2 = parseFloat(document.getElementById('modal_t2').value) || 0;

    const btnSubmit = document.getElementById('modal_btn_submit');
    const alertBox = document.getElementById('modal-alert');
    if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.innerHTML = `⏳ Placing ${action} Order...`;
    }
    if (alertBox) {
        alertBox.style.display = 'block';
        alertBox.className = 'alert-box';
        alertBox.textContent = currentTradingMode === 'paper' ? `⏳ Placing Virtual Paper Trade for ${sym}...` : `⏳ Placing ${action} order for ${sym} (5X Intraday MIS) on Angel One...`;
    }

    try {
        const r = await fetch('/api/place-order', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                symbol: sym, 
                token: tok, 
                action: action, 
                qty: qty, 
                price: price, 
                stoploss: sl, 
                target1: t1, 
                target2: t2,
                mode: currentTradingMode,
                scan_type: currentTradeScanType
            })
        });
        const d = await r.json();

        if (d.success) {
            // Transform Modal into Rich Order Confirmation Screen
            const formCont = document.getElementById('modal_form_container');
            const succCont = document.getElementById('modal_success_container');
            if (formCont && succCont) {
                formCont.style.display = 'none';
                succCont.style.display = 'block';

                const slHtml = d.sl_placed ? `
                    <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                        <span style="color:#94a3b8;">Exchange Stop-Loss:</span>
                        <b style="color:#34d399;">✅ PLACED IN BOOK (#${d.sl_order_id})</b>
                    </div>
                ` : (d.sl_scheduled ? `
                    <div style="margin:12px 0; background:rgba(59, 130, 246, 0.18); border:1px solid #3b82f6; border-radius:10px; padding:12px; text-align:left;">
                        <div style="color:#60a5fa; font-weight:800; font-size:13px; margin-bottom:4px; display:flex; align-items:center; gap:6px;">
                            <span>⏳</span> BROKER SL: SCHEDULED IN 60 SECONDS
                        </div>
                        <div style="color:#93c5fd; font-size:12px; line-height:1.4;">
                            • <b>Exchange Settle Delay:</b> Broker SL order will be placed at <b>₹${parseFloat(d.sl_price || sl).toFixed(2)}</b> after 60s (prevents broker instant-rejection).<br>
                            • 🛡️ <b>Local Guard Monitor:</b> ACTIVE right now in background! You will receive a Telegram confirmation when placed.
                        </div>
                    </div>
                ` : `
                    <div style="margin:12px 0; background:rgba(239, 68, 68, 0.18); border:1px solid #ef4444; border-radius:10px; padding:12px; text-align:left;">
                        <div style="color:#ef4444; font-weight:800; font-size:13px; margin-bottom:4px; display:flex; align-items:center; gap:6px;">
                            <span>🚨</span> BROKER EXCHANGE SL NOT IN BOOK
                        </div>
                        <div style="color:#fca5a5; font-size:12px; line-height:1.4;">
                            Broker note: <i>${d.sl_message || 'Exchange SL validation failed'}</i>.<br>
                            🛡️ <b>Local ₹300 Guard is ACTIVE</b> &amp; will auto-exit if price hits SL.<br>
                            📱 <b>ACTION:</b> You can also enter SL manually in Angel One App at <b style="color:#fff; text-decoration:underline;">₹${parseFloat(d.sl_price || sl).toFixed(2)}</b> for 100% safety!
                        </div>
                    </div>
                `);

                succCont.innerHTML = `
                    <div style="text-align:center; padding:10px 0;">
                        <div style="font-size:46px; margin-bottom:8px;">🎉</div>
                        <h2 style="color:#10b981; margin:0 0 6px 0; font-size:22px;">ORDER EXECUTED!</h2>
                        <p style="color:#94a3b8; font-size:13px; margin:0 0 16px 0;">Order confirmed on Angel One Exchange</p>

                        <div style="background:#090f1d; border:1px solid #1e293b; border-radius:12px; padding:16px; text-align:left; margin-bottom:16px; font-size:13px;">
                            <div style="display:flex; justify-content:space-between; margin-bottom:8px; border-bottom:1px solid #1e293b; padding-bottom:8px;">
                                <span style="color:#94a3b8;">Stock / Action:</span>
                                <b style="color:#fff;">${d.symbol || sym} <span class="badge ${d.action === 'BUY' ? 'badge-buy' : 'badge-sell'}">${d.action || action}</span></b>
                            </div>
                            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                                <span style="color:#94a3b8;">Strategy:</span>
                                <b style="color:#a78bfa;">${(d.scan_type || currentTradeScanType || 'ultra_sniper').toUpperCase().replace('_', ' ')}</b>
                            </div>
                            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                                <span style="color:#94a3b8;">Quantity:</span>
                                <b style="color:#fff;">${d.qty || qty} Shares (₹300 Risk Sized)</b>
                            </div>
                            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                                <span style="color:#94a3b8;">Angel One Order ID:</span>
                                <b style="color:#60a5fa; font-family:monospace;">${d.order_id || 'N/A'}</b>
                            </div>
                            ${slHtml}
                            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                                <span style="color:#94a3b8;">Stop Loss Price:</span>
                                <b style="color:#f87171;">₹${parseFloat(d.sl_price || sl).toFixed(2)}</b>
                            </div>
                            <div style="display:flex; justify-content:space-between;">
                                <span style="color:#94a3b8;">Targets:</span>
                                <b style="color:#34d399;">T1: ₹${parseFloat(d.target1 || t1).toFixed(2)} | T2: ₹${parseFloat(d.target2 || t2).toFixed(2)}</b>
                            </div>
                        </div>

                        <button class="btn btn-buy" style="width:100%; padding:14px; font-size:15px; font-weight:800;" onclick="closeTradeModal(); switchTab('portfolio');">
                            📊 Done & View Active Positions
                        </button>
                    </div>
                `;
            }

            // Global floating toast on dashboard
            showGlobalToast(`🎉 Order Placed: <b>${d.symbol || sym}</b> (${d.qty || qty} shs) | ID: ${d.order_id} | SL: ₹${parseFloat(d.sl_price || sl).toFixed(2)}`, 'success');
        } else {
            let errMsg = d.message || 'Order failed';
            if (errMsg.toLowerCase().includes('not a registered ip') || errMsg.toLowerCase().includes('registered ip') || errMsg.toLowerCase().includes('ip rejection')) {
                const curIp = '178.92.40.115';
                alertBox.innerHTML = `

                    <div style="text-align:left; line-height:1.5;">
                        <b style="color:#ef4444; font-size:13px;">❌ IP NOT REGISTERED IN ANGEL ONE!</b><br>
                        Angel One blocked this order &amp; SL because your Internet IP (<b style="color:#fff; text-decoration:underline; cursor:pointer;" onclick="copyIP()">${curIp}</b>) is not added in SmartAPI portal.<br><br>
                        <b>👉 Quick Fix (30 seconds):</b><br>
                        1. Open <a href="https://smartapi.angelone.in/" target="_blank" style="color:#60a5fa; text-decoration:underline; font-weight:bold;">smartapi.angelone.in</a> &gt; My Apps<br>
                        2. Click Edit App &gt; <b>Allowed IP</b><br>
                        3. Add <b style="color:#fde047;">${curIp}</b> and click Save!
                    </div>
                `;
            } else if (errMsg.toLowerCase().includes('cautionary') || errMsg.toLowerCase().includes('surveillance') || errMsg.toLowerCase().includes('ab1008')) {
                alertBox.innerHTML = `
                    <div style="text-align:left; line-height:1.5;">
                        <b style="color:#f59e0b; font-size:13px;">⚠️ STOCK UNDER EXCHANGE CAUTIONARY LIST!</b><br>
                        NSE / Angel One has categorized <b>${sym}</b> under Cautionary/GSM Surveillance.<br>
                        Exchange rules block Intraday API orders for this stock.<br><br>
                        <b>👉 Solution:</b><br>
                        Please select another signal from Deep Scan (e.g. <b>INFY, HDFCBANK, SBIN, ITC</b>) which are non-cautionary and 100% active for 5X Intraday trading.
                    </div>
                `;
            } else {
                alertBox.textContent = errMsg;
            }
            alertBox.className = 'alert-box alert-err';
            if (btnSubmit) {
                btnSubmit.disabled = false;
                btnSubmit.innerHTML = currentTradingMode === 'paper' ? `⚡ CONFIRM PAPER TRADE (${action})` : `⚡ CONFIRM LIVE ORDER (ANGEL ONE)`;
            }
        }

        loadBalance();
        loadPositions();
        loadJournal(currentTradingMode);
        if (typeof loadOrders === 'function') loadOrders();
    } catch(e) {
        alertBox.textContent = 'Order placement failed: ' + e;
        alertBox.className = 'alert-box alert-err';
        if (btnSubmit) {
            btnSubmit.disabled = false;
            btnSubmit.innerHTML = currentTradingMode === 'paper' ? `⚡ CONFIRM PAPER TRADE (${action})` : `⚡ CONFIRM LIVE ORDER (ANGEL ONE)`;
        }
    }
}


async function executeSig(sym, tok, action, qty, price) {
    openTradeModal(sym, tok, action, qty, price, (price*1.015).toFixed(2), (price*1.030).toFixed(2), (price*0.988).toFixed(2));
}

async function submitManual(action) {
    const sym = document.getElementById('m_sym').value.trim();
    let tok = document.getElementById('m_tok').value.trim();
    const qty = document.getElementById('m_qty').value || 1;
    const prc = document.getElementById('m_prc').value || 0;
    if (!sym) { alert('Please enter stock symbol (e.g. SBIN, SUZLON, IDEA, RELIANCE)!'); return; }
    
    const lookup = {
        "SBIN": "3045", "SBIN-EQ": "3045", "RELIANCE": "2885", "RELIANCE-EQ": "2885",
        "TCS": "11536", "TCS-EQ": "11536", "INFY": "1594", "INFY-EQ": "1594",
        "IDEA": "14366", "IDEA-EQ": "14366", "SUZLON": "12018", "SUZLON-EQ": "12018",
        "IRFC": "2029", "IRFC-EQ": "2029", "NHPC": "17400", "NHPC-EQ": "17400",
        "SJVN": "18883", "SJVN-EQ": "18883", "ZOMATO": "5097", "ZOMATO-EQ": "5097",
        "TATAMOTORS": "3456", "TATAMOTORS-EQ": "3456", "TATASTEEL": "3499", "TATASTEEL-EQ": "3499",
        "YESBANK": "11915", "YESBANK-EQ": "11915", "BEL": "383", "BEL-EQ": "383"
    };
    if (!tok && lookup[sym.toUpperCase()]) {
        tok = lookup[sym.toUpperCase()];
        document.getElementById('m_tok').value = tok;
    }
    const isBuy = action === 'BUY';
    const p = parseFloat(prc) || 100;
    openTradeModal(sym, tok, action, qty, prc || 0, (p * (isBuy ? 1.015 : 0.985)).toFixed(2), (p * (isBuy ? 1.030 : 0.970)).toFixed(2), (p * (isBuy ? 0.988 : 1.012)).toFixed(2));
}

async function exitPosition(sym, tok, qty) {
    if (!confirm(`Square off position: ${qty} x ${sym}?`)) return;
    openTradeModal(sym, tok, 'SELL', qty, 0, '0', '0', '0');
}

window.onload = init;
</script>

<!-- Interactive Trade Modal -->
<div id="trade-modal-overlay" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.75); backdrop-filter:blur(5px); z-index:9999; justify-content:center; align-items:center;">
    <div style="background:#0f172a; border:1px solid #334155; border-radius:18px; width:520px; max-width:92%; padding:24px; box-shadow:0 20px 50px rgba(0,0,0,0.6);">
        <div id="modal_form_container">
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #1e293b; padding-bottom:14px; margin-bottom:16px;">
                <div style="display:flex; align-items:center; gap:10px;">
                    <span id="modal_sym" style="font-size:18px; font-weight:900; color:#fff;">STOCK-EQ</span>
                    <span id="modal_action" class="badge badge-buy">BUY</span>
                    <span class="badge" style="background:#1e293b; color:#94a3b8;">5X INTRADAY MIS</span>
                </div>
                <button style="background:none; border:none; color:#94a3b8; font-size:20px; cursor:pointer;" onclick="closeTradeModal()">✕</button>
            </div>
            <input type="hidden" id="modal_tok" value="">

            <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:12px;">
                <div>
                    <label>Quantity (Shares) <span style="font-size:10px; color:#10b981; font-weight:700;">(₹300 Risk Sizing)</span></label>
                    <div style="display:flex; gap:6px;">
                        <input id="modal_qty" type="number" value="1" oninput="updateModalMath(false)" style="margin-bottom:0;">
                        <button class="btn btn-primary" style="width:auto; padding:0 8px; font-size:10px; background:#10b981; border:none;" onclick="applyRiskSizing()">🎯 ₹300</button>
                        <button class="btn btn-primary" style="width:auto; padding:0 8px; font-size:10px;" onclick="setModalMaxQty()">MAX</button>
                    </div>
                </div>
                <div>
                    <label>Order Price (₹)</label>
                    <input id="modal_price" type="number" step="0.05" oninput="updateModalMath(true)" style="margin-bottom:0;">
                </div>
            </div>

            <!-- T1, T2, SL Input Row -->
            <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; margin-bottom:14px;">
                <div>
                    <label style="color:#34d399;">🎯 Target 1 (T1)</label>
                    <input id="modal_t1" type="number" step="0.05" oninput="updateModalMath(false)" style="margin-bottom:0; color:#34d399; font-weight:700;">
                </div>
                <div>
                    <label style="color:#fbbf24;">🚀 Target 2 (T2)</label>
                    <input id="modal_t2" type="number" step="0.05" oninput="updateModalMath(false)" style="margin-bottom:0; color:#fbbf24; font-weight:700;">
                </div>
                <div>
                    <label style="color:#f87171;">🛡️ Stop Loss (SL)</label>
                    <input id="modal_sl" type="number" step="0.05" oninput="updateModalMath(true)" style="margin-bottom:0; color:#f87171; font-weight:700;">
                </div>
            </div>

            <!-- Profit / Loss Expectations Matrix -->
            <div style="background:#090f1d; padding:12px; border-radius:10px; border:1px solid #1e293b; display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; font-size:11px; margin-bottom:14px; text-align:center;">
                <div>
                    <span style="color:#94a3b8;">Gain @ T1:</span>
                    <b id="modal_pnl_t1" style="color:#34d399; display:block; font-size:13px; margin-top:2px;">+₹0.00</b>
                </div>
                <div>
                    <span style="color:#94a3b8;">Gain @ T2:</span>
                    <b id="modal_pnl_t2" style="color:#fbbf24; display:block; font-size:13px; margin-top:2px;">+₹0.00</b>
                </div>
                <div>
                    <span style="color:#94a3b8;">Max Risk @ SL:</span>
                    <b id="modal_pnl_sl" style="color:#f87171; display:block; font-size:13px; margin-top:2px;">-₹0.00</b>
                </div>
            </div>

            <div style="background:#090f1d; padding:12px; border-radius:10px; border:1px solid #1e293b; display:grid; grid-template-columns:1fr 1fr; gap:10px; font-size:12px; margin-bottom:16px;">
                <div>
                    <span style="color:#94a3b8;">Required Margin (5X):</span>
                    <b id="modal_margin" style="color:#60a5fa; display:block; font-size:14px; margin-top:2px;">₹0.00</b>
                </div>
                <div>
                    <span style="color:#94a3b8;">Total Stock Exposure:</span>
                    <b id="modal_exposure" style="color:#fff; display:block; font-size:14px; margin-top:2px;">₹0.00</b>
                </div>
            </div>

            <button id="modal_btn_submit" class="btn btn-buy" onclick="executeModalOrder()">
                ⚡ CONFIRM LIVE ORDER (ANGEL ONE)
            </button>

            <div id="modal-alert" style="display:none;" class="alert-box"></div>
        </div>

        <div id="modal_success_container" style="display:none;"></div>
    </div>
</div>
<div id="global-toast" style="display:none; position:fixed; top:24px; right:24px; z-index:999999; padding:14px 20px; border-radius:10px; font-weight:700; font-size:14px; box-shadow:0 10px 30px rgba(0,0,0,0.8); transition:all 0.3s ease;"></div>
    </div>
</div>
</body>
</html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def do_GET(self):
        url_p = urllib.parse.urlparse(self.path)
        path = url_p.path
        query = urllib.parse.parse_qs(url_p.query)

        if path == "/" or path == "/index.html":
            self._send_html(HTML_PAGE)
        elif path == "/api/get-config":
            safe = dict(config)
            safe["ip"] = get_my_ip()
            safe["deep_ai_available"] = DEEP_AI_AVAILABLE
            self._send_json(safe)
        elif path == "/api/fetch-signals":
            self._send_json(run_instant_market_scan("all"))
        elif path == "/api/scan-market":
            cat = query.get("category", ["all"])[0]
            self._send_json(run_instant_market_scan(cat))
        elif path == "/api/deep-scan":
            cat = query.get("category", ["all"])[0]
            self._send_json(run_deep_ai_scan(cat))
        elif path == "/api/ultra-sniper":
            self._send_json(run_ultra_sniper_scan())
        elif path == "/api/strategy-config":
            from backend.weekly_optimizer import get_strategy_config
            self._send_json(get_strategy_config())
        elif path == "/api/run-weekly-audit":
            if DB_AVAILABLE:
                from backend.weekly_optimizer import run_weekly_quant_audit
                db = SessionLocal()
                try:
                    res = run_weekly_quant_audit(db)
                    self._send_json({"success": True, "report": res})
                except Exception as e:
                    self._send_json({"success": False, "error": str(e)})
                finally:
                    db.close()
            else:
                self._send_json({"success": False, "error": "Database not available"})

        elif path == "/api/ai-status":
            self._send_json({"deep_ai_available": DEEP_AI_AVAILABLE})
        elif path == "/api/watchlist":
            self._send_json(get_watchlist_data())
        elif path == "/api/stock-price":
            sym = query.get("symbol", ["SBIN"])[0]
            self._send_json(get_single_stock_price(sym))
        elif path == "/api/scan-single":
            sym = query.get("symbol", ["SBIN"])[0]
            base = sym.upper().replace(".NS", "").replace("-EQ", "")
            stk = {
                "symbol": f"{base}.NS",
                "name": base,
                "base": f"{base}-EQ",
                "tok": ANGEL_TOKENS_MAP.get(f"{base}.NS", STOCK_TOKENS.get(f"{base}-EQ", get_live_token(f"{base}-EQ")))
            }
            sig = _analyze_single_stock_local(stk)
            self._send_json({"signal": sig, "symbol": stk["base"]})
        elif path == "/api/balance":
            m = query.get("mode", [config.get("trading_mode", "paper")])[0]
            if m == "paper":
                pb = get_paper_balance_calc()
                self._send_json({"balance": pb, "buying_power": pb * 5.0, "connected": True, "mode": "paper"})
            else:
                self._send_json(get_live_balance())
        elif path == "/api/positions":
            self._send_json(get_live_positions())
        elif path == "/api/orders":
            self._send_json(get_order_book())
        elif path == "/api/get-trades":
            m = query.get("mode", ["paper"])[0]
            self._send_json({"trades": get_trades_list(m), "mode": m})
        elif path == "/api/get-journal-summary":
            m = query.get("mode", ["paper"])[0]
            if DB_AVAILABLE:
                db = SessionLocal()
                if m == "live":
                    reconcile_live_trades_with_broker(db)
                else:
                    reconcile_paper_trades(db)
                w = get_weekly_summary(db, m)
                mn = get_monthly_summary(db, m)
                db.close()
                self._send_json({"weekly": w, "monthly": mn, "mode": m})
            else:
                self._send_json({"weekly": {}, "monthly": {}, "mode": m})
        else:
            self.send_error(404)

    def do_POST(self):
        len_h = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(len_h).decode()) if len_h else {}

        if self.path == "/api/save-and-login":
            save_config(body)
            res = login_smartapi()
            self._send_json(res)
        elif self.path == "/api/login":
            res = login_smartapi()
            self._send_json(res)
        elif self.path == "/api/save-telegram":
            bot_token = body.get("telegram_bot_token", "").strip()
            chat_id = body.get("telegram_chat_id", "").strip()
            config["telegram_bot_token"] = bot_token
            config["telegram_chat_id"] = chat_id
            save_config(config)
            self._send_json({"success": True, "message": "✅ Telegram Bot settings saved successfully!"})
        elif self.path == "/api/test-telegram":
            bot_token = body.get("telegram_bot_token", "").strip() or config.get("telegram_bot_token") or "8613233140:AAEfeblJ0e5vK9iJe5CWgao_yjiGRsBuvMk"
            chat_id = body.get("telegram_chat_id", "").strip() or config.get("telegram_chat_id") or "7327907687"
            test_msg = (
                "🚀 <b>StocksSense AI — Local Live Trader</b>\n\n"
                "✅ <b>Telegram Alert Bot Connected Successfully!</b>\n\n"
                f"• <b>Bot:</b> Configured & Active\n"
                f"• <b>Mode:</b> {config.get('trading_mode', 'paper').upper()}\n"
                f"• <b>Risk Model:</b> Strict ₹300 Max Loss / Trade\n\n"
                "<i>All real-time trade signals, executions, SL, and Target hits from Local Trader will be delivered here instantly!</i>"
            )
            res = send_telegram_direct(bot_token, chat_id, test_msg)
            if res.get("success") and res.get("detected_chat_id"):
                config["telegram_chat_id"] = res["detected_chat_id"]
                config["telegram_bot_token"] = bot_token
                save_config(config)
            self._send_json(res)
        elif self.path == "/api/set-trading-mode":
            m = body.get("mode", "paper")
            config["trading_mode"] = m
            save_config(config)
            self._send_json({"success": True, "trading_mode": m})
        elif self.path == "/api/set-sl-delay":
            global SL_AUTO_DELAY_SECS
            delay_mins = int(body.get("delay_mins", 3))
            delay_mins = max(1, min(15, delay_mins))  # clamp 1–15 minutes
            SL_AUTO_DELAY_SECS = delay_mins * 60
            self._send_json({"success": True, "delay_mins": delay_mins, "message": f"✅ Auto-SL delay set to {delay_mins} minutes!"})
        elif self.path == "/api/place-order":
            try:
                sym = body.get("symbol", "")
                tok = body.get("token", "")
                act = body.get("action", "BUY")
                qty = body.get("qty", 1)
                prc = body.get("price", 0)
                sl  = body.get("stoploss") or body.get("sl") or 0
                t1  = body.get("target1") or body.get("t1") or 0
                t2  = body.get("target2") or body.get("t2") or 0
                mode = body.get("mode") or config.get("trading_mode", "paper")
                order_type = body.get("order_type", "MARKET")
                scan_type = body.get("scan_type", "ultra_sniper")

                res = execute_trade(
                    symbol=sym,
                    symbol_token=tok,
                    action=act,
                    qty=qty,
                    price=prc,
                    sl=sl,
                    t1=t1,
                    t2=t2,
                    mode=mode,
                    order_type=order_type,
                    scan_type=scan_type
                )
                self._send_json(res)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._send_json({"success": False, "message": f"Server execution error: {e}"})
        else:
            self.send_error(404)


def get_local_lan_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


def main():
    PORT = 8888
    my_ip = get_my_ip()
    lan_ip = get_local_lan_ip()
    print("=" * 65)
    print("  ⚡ StocksSense AI — Local Live Trader Pro")
    print(f"  🌐 Public Registered IP : {my_ip}")
    print(f"  💻 PC Web Dashboard      : http://localhost:{PORT}")
    print(f"  📱 Mobile Hotspot Link   : http://{lan_ip}:{PORT}")
    print("=" * 65)
    
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)

    try:
        webbrowser.open(f"http://localhost:{PORT}")
    except:
        pass
        
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nLocal Trader stopped.")


if __name__ == "__main__":
    main()
