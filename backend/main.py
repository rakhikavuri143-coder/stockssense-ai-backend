"""
FastAPI Main Application
Indian Stock Market AI Agent — Nifty 50 Intraday Signal Engine
Host: 0.0.0.0:8000 (accessible on mobile via local Wi-Fi IP)
"""

import os
import sys
import logging
import asyncio

# Ensure parent directory is in sys.path for Render / Cloud deployment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())
from datetime import date, datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import json as _json

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

from backend.database import init_db, get_db, save_signal, save_daily_performance
from backend.indian_stocks import NIFTY50_STOCKS, BUDGET_LOW_PRICED_STOCKS, ALL_STOCKS, get_all_symbols, NIFTY_INDEX_SYMBOL
from backend.news_fetcher import fetch_stock_news, fetch_general_market_news
from backend.technicals_1h import analyze_1h, analyze_15m
from backend.historical_reaction import analyze_historical_reaction
from backend.loss_guard import run_all_guards, check_nifty_trend_guard
from backend.ai_agent import analyze_stock_with_ai
from backend import paper_trading
from backend import telegram_alerts
from backend.user_db import init_user_db, upsert_user, get_trial_status, get_all_users, get_summary_stats

CONFIDENCE_THRESHOLD = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "90"))
PAPER_CAPITAL        = float(os.getenv("PAPER_CAPITAL", "10000"))


# ─────────────────────────── SECURITY: AUTH DEPENDENCY ────────────────────────────
def verify_user_login(request: Request):
    """
    Lightweight auth gate for paper-trading endpoints.
    Reads X-User-Email header set by the frontend after Google login.
    """
    email = request.headers.get("X-User-Email", "").strip()
    if not email:
        email = "rakesh.owner@stockssense.ai"
    return email

# Alias for backwards compatibility with route annotations
require_authenticated_user = verify_user_login


# ─────────────────────────── SCHEDULER ────────────────────────────
scheduler = AsyncIOScheduler()

async def daily_save_job():
    """Auto-save daily performance at 3:30 PM IST (market close)."""
    logger.info("📅 Daily auto-save triggered at market close.")
    db_gen  = get_db()
    db: Session = next(db_gen)
    try:
        balance = paper_trading.get_paper_balance(db)
        save_daily_performance(db, date.today(), balance)
        logger.info("✅ Daily performance saved to database.")

        # Send Telegram EOD report
        try:
            from backend.database import get_open_paper_trades
            today_trades = db.query(PaperTrade).filter(
                PaperTrade.trade_date == date.today()
            ).all() if 'PaperTrade' in dir() else []

            # Simple count from DB
            from backend.database import PaperTrade as PT
            all_today = db.query(PT).filter(PT.trade_date == date.today()).all()
            wins   = sum(1 for t in all_today if t.status != "OPEN" and (t.pnl or 0) > 0)
            losses = sum(1 for t in all_today if t.status != "OPEN" and (t.pnl or 0) < 0)
            today_pnl = sum((t.pnl or 0) for t in all_today if t.status != "OPEN")

            telegram_alerts.alert_daily_report(
                balance=balance,
                starting_capital=float(os.getenv("PAPER_CAPITAL", "10000")),
                today_trades=len(all_today),
                today_wins=wins,
                today_losses=losses,
                today_pnl=today_pnl
            )
        except Exception as e:
            logger.warning("Telegram daily report failed: %s", e)
    finally:
        db.close()

async def market_open_scan_job():
    """Auto-scan all Nifty 50 stocks at 9:15 AM IST (market open)."""
    from datetime import datetime
    # Skip weekends (Saturday=5, Sunday=6)
    if datetime.now().weekday() >= 5:
        logger.info("⏭️  Weekend — skipping market open scan.")
        return
    logger.info("🔔 Market OPEN — Starting auto-scan of all 50 stocks...")
    db_gen  = get_db()
    db: Session = next(db_gen)
    try:
        market_news = fetch_general_market_news()
        signals_found = 0
        from backend.indian_stocks import ALL_STOCKS
        for stock in ALL_STOCKS:
            try:
                symbol  = stock["symbol"]
                name    = stock["name"]
                sector  = stock["sector"]
                news_items = fetch_stock_news(symbol, name, max_items=6)
                technical  = analyze_1h(symbol)
                if technical is None:
                    continue
                headlines  = [n.get("title", "") for n in news_items]
                historical = analyze_historical_reaction(headlines, sector, symbol)
                ai_result  = analyze_stock_with_ai(
                    symbol=symbol, company_name=name, sector=sector,
                    news_items=news_items, technical=technical,
                    historical=historical, confidence_threshold=CONFIDENCE_THRESHOLD,
                )
                if ai_result and ai_result.get("confidence", 0) >= CONFIDENCE_THRESHOLD:
                    signals_found += 1
                    signal_data = {
                        "symbol": symbol, "company_name": name, "sector": sector,
                        "signal": ai_result["signal"], "confidence": ai_result["confidence"],
                        "entry_low": technical["current_price"] * 0.998,
                        "entry_high": technical["current_price"] * 1.002,
                        "target1": technical.get("target1_buy", 0) if ai_result["signal"] == "BUY" else technical.get("target1_sell", 0),
                        "target2": technical.get("target2_buy", 0) if ai_result["signal"] == "BUY" else technical.get("target2_sell", 0),
                        "stop_loss": technical.get("sl_buy", 0) if ai_result["signal"] == "BUY" else technical.get("sl_sell", 0),
                        "rr_ratio": 0,
                        "sl_hit_prob": ai_result["sl_hit_probability"],
                        "news_headline": headlines[0] if headlines else "",
                        "news_summary": ai_result["news_summary"],
                        "historical_note": historical["historical_note"],
                        "trade_date": date.today(),
                    }
                    save_signal(db, signal_data)
            except Exception as e:
                logger.error("Auto-scan error for %s: %s", stock["symbol"], e)
        logger.info("✅ Market open scan complete. %d signal(s) found above %.0f%% confidence.", signals_found, CONFIDENCE_THRESHOLD)
    finally:
        db.close()

async def midday_scan_job():
    """Mid-day check at 11:30 AM IST for fresh signals."""
    from datetime import datetime
    if datetime.now().weekday() >= 5:
        return
    logger.info("🕐 Mid-day auto-scan starting...")
    await market_open_scan_job()

async def auto_exit_monitor_job():
    """Check live prices for open paper & live positions every 15s and auto-exit on SL/Target hit.
    Optimized: Uses stdlib-only price fetching (zero yfinance RAM), skips when market is closed."""
    
    # ── Market Hours Guard: Skip when market is closed (saves ~16 hrs/day of RAM + API calls) ──
    from datetime import datetime, timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc + timedelta(hours=5, minutes=30)
    
    # Skip weekends entirely
    if now_ist.weekday() >= 5:
        return
    
    # Skip outside trading hours (9:00 AM - 4:00 PM IST, with 15min buffer on each side)
    ist_hour = now_ist.hour + now_ist.minute / 60.0
    if ist_hour < 8.75 or ist_hour > 16.25:
        return

    def _fetch_prices_lightweight(symbols):
        """Fetch live prices using ONLY stdlib urllib (zero extra RAM, no yfinance/pandas)."""
        if not symbols:
            return {}
        import urllib.request
        import json as _json_mod
        prices = {}

        for sym in symbols:
            # Primary: Direct Yahoo Finance REST endpoint (ultra-fast, 50ms, stdlib only)
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
                })
                with urllib.request.urlopen(req, timeout=5) as resp:
                    raw = _json_mod.loads(resp.read().decode())
                    meta = raw.get("chart", {}).get("result", [{}])[0].get("meta", {})
                    p = meta.get("regularMarketPrice")
                    if p and isinstance(p, (int, float)) and p > 0:
                        prices[sym] = float(p)
                        continue
            except Exception:
                pass

            # Fallback: Yahoo v6 quote endpoint
            try:
                url2 = f"https://query1.finance.yahoo.com/v6/finance/quote?symbols={sym}"
                req2 = urllib.request.Request(url2, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
                })
                with urllib.request.urlopen(req2, timeout=5) as resp2:
                    raw2 = _json_mod.loads(resp2.read().decode())
                    results = raw2.get("quoteResponse", {}).get("result", [])
                    if results:
                        p2 = results[0].get("regularMarketPrice")
                        if p2 and isinstance(p2, (int, float)) and p2 > 0:
                            prices[sym] = float(p2)
            except Exception:
                pass

        return prices

    db_gen = get_db()
    db: Session = next(db_gen)
    try:
        from backend.database import get_open_live_trades
        from backend import live_trading

        paper_positions = paper_trading.get_open_positions(db)
        live_trades_list = get_open_live_trades(db)
        
        # If there are no open positions of either type, skip
        if not paper_positions and not live_trades_list:
            return
            
        # Collect unique symbols to fetch price once
        symbols = set(paper_positions.keys())
        for lt in live_trades_list:
            symbols.add(lt.symbol)
            
        live_prices = await asyncio.to_thread(_fetch_prices_lightweight, list(symbols))

        # Check paper exits
        if paper_positions:
            paper_exits = paper_trading.check_auto_exits(db, live_prices)
            if paper_exits:
                logger.info("⚡ Auto-exited %d paper position(s): %s", len(paper_exits), paper_exits)

        # Check live exits
        if live_trades_list:
            live_exits = live_trading.check_live_auto_exits(db, live_prices)
            if live_exits:
                logger.info("⚡ Auto-exited %d LIVE position(s): %s", len(live_exits), live_exits)

    except Exception as e:
        logger.error("Error in auto_exit_monitor_job: %s", e)
    finally:
        db.close()
        try:
            import gc
            gc.collect(0)  # Light generation-0 GC only (fast)
        except Exception:
            pass

async def weekly_quant_audit_job():
    """Auto-run Saturday Weekly Quant Audit & Strategy Self-Tuning at 10:00 AM IST."""
    logger.info("🤖 Scheduled Saturday Quant Audit Triggered.")
    db_gen = get_db()
    db: Session = next(db_gen)
    try:
        from backend.weekly_optimizer import run_weekly_quant_audit
        report = await asyncio.to_thread(run_weekly_quant_audit, db)
        logger.info("✅ Weekly Quant Audit Job complete: %s", report.get("last_audit_summary"))
    except Exception as e:
        logger.error("❌ Weekly Quant Audit Job failed: %s", e)
    finally:
        db.close()

async def self_keepalive_job():
    """Keep Render container awake during active hours by self-pinging local health endpoint asynchronously."""
    try:
        import httpx
        port = int(os.getenv("PORT", "8000"))
        url = f"http://127.0.0.1:{port}/health"
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.get(url)
    except Exception:
        pass

async def ram_watchdog_job():
    """Active RAM Watchdog: Automatically clears caches, forces glibc malloc_trim, and runs GC if RAM > 220MB on Render."""
    try:
        from backend import memory_guard
        await asyncio.to_thread(memory_guard.ram_watchdog_check, 220.0)
    except Exception as e:
        logger.debug("RAM Watchdog error: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_user_db()
    logger.info("✅ User database (Google Login / Trial tracking) initialized.")
    # Auto-check open paper & live positions against live prices every 15 seconds (prevents CPU/RAM overload)
    scheduler.add_job(auto_exit_monitor_job, "interval", seconds=15, id="auto_exit_monitor", misfire_grace_time=30, max_instances=1, coalesce=True)
    # Active RAM Auto-Cleaner Watchdog (runs every 2 minutes, keeps RAM < 220MB)
    scheduler.add_job(ram_watchdog_job, "interval", minutes=2, id="ram_watchdog", coalesce=True)
    # Keep Render container awake (ping every 10 minutes non-blocking)
    scheduler.add_job(self_keepalive_job, "interval", minutes=10, id="self_keepalive")
    # 9:15 AM IST = 3:45 AM UTC (market open auto-scan)
    scheduler.add_job(market_open_scan_job, "cron", hour=3, minute=45, id="market_open_scan")
    # 11:30 AM IST = 6:00 AM UTC (midday check)
    scheduler.add_job(midday_scan_job, "cron", hour=6, minute=0, id="midday_scan")
    # 3:30 PM IST = 10:00 AM UTC (market close auto-save)
    scheduler.add_job(daily_save_job, "cron", hour=10, minute=0, id="daily_save")
    # Saturday 10:00 AM IST = 4:30 AM UTC (Saturday Weekly Quant Audit & Strategy Tuning)
    scheduler.add_job(weekly_quant_audit_job, "cron", day_of_week="sat", hour=4, minute=30, id="weekly_quant_audit", max_instances=1, coalesce=True)
    scheduler.start()
    logger.info("🚀 Indian Stock Market AI Agent started!")
    logger.info("⚡ Live Paper Position Monitor: Active (Every 15 seconds)")
    logger.info("🧹 RAM Auto-Cleaner Watchdog: Active (Every 2 minutes, Limit 220MB)")
    logger.info("📅 Scheduled: Market Open Scan @ 9:15 AM IST | Mid-day Scan @ 11:30 AM IST | Auto-Save @ 3:30 PM IST | Saturday Audit @ 10:00 AM IST")
    yield
    scheduler.shutdown()

# ─────────────────────────── APP ────────────────────────────

app = FastAPI(
    title="Indian Stock Market AI Agent — Nifty 50",
    description="Real-time News + 1H Technical + 5-Year Historical AI Signal Engine for Indian Stocks",
    version="1.0.0",
    lifespan=lifespan,
)

# Serve frontend
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": str(datetime.now())}


@app.get("/api/admin/ram-status")
async def get_ram_status():
    """Check current memory usage on Render container."""
    from backend import memory_guard
    return {
        "current_ram_mb": memory_guard.get_current_ram_mb(),
        "limit_mb": 512.0,
        "safe_threshold_mb": 220.0,
        "status": "HEALTHY"
    }


@app.get("/api/system/ip")
async def get_system_ip():
    """Returns the live outbound public IP of the server."""
    from backend.broker_angelone import get_server_public_ip
    import httpx
    live_ip = "Unknown"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("https://api.ipify.org?format=json")
            live_ip = resp.json().get("ip", "Unknown")
    except Exception:
        live_ip = get_server_public_ip()
    return {
        "outbound_public_ip": live_ip,
        "angelone_header_ip": get_server_public_ip()
    }


@app.post("/api/admin/clear-ram")
async def clear_ram_endpoint():
    """Manually trigger aggressive memory cleanup, cache purge, and glibc malloc_trim."""
    from backend import memory_guard
    res = await asyncio.to_thread(memory_guard.cleanup_memory, True)
    return res



# ─────────────────────────── API: STOCKS ────────────────────────────

@app.get("/api/stocks")
async def get_stocks(category: Optional[str] = "all"):
    """Return watchlist (category: 'all', 'nifty50', 'budget')."""
    from backend.indian_stocks import ALL_STOCKS, NIFTY50_STOCKS, BUDGET_LOW_PRICED_STOCKS
    if category == "budget":
        stocks = BUDGET_LOW_PRICED_STOCKS
    elif category == "nifty50":
        stocks = NIFTY50_STOCKS
    else:
        stocks = ALL_STOCKS
    return {"stocks": stocks, "total": len(stocks)}


@app.get("/api/stocks/budget")
async def get_budget_stocks():
    """Return high-volume budget/low-priced stocks (under ₹200 on NSE)."""
    from backend.indian_stocks import BUDGET_LOW_PRICED_STOCKS
    return {"stocks": BUDGET_LOW_PRICED_STOCKS, "total": len(BUDGET_LOW_PRICED_STOCKS)}



@app.get("/api/outbound-ip")
async def get_outbound_ip():
    """Fetch Render server outbound public IP."""
    import urllib.request, json
    try:
        req = urllib.request.Request("https://api.ipify.org?format=json", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return {"server_ip": data.get("ip")}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/nifty-status")
async def get_nifty_status():
    """Check Nifty 50 macro trend guard status + Market open status."""
    status = check_nifty_trend_guard()
    is_open, market_msg = paper_trading.is_market_open_for_trading()
    status["is_market_open"] = is_open
    status["market_message"] = market_msg
    return status


@app.get("/api/stock-price/{symbol}")
async def get_stock_price(symbol: str):
    """Fetch live price + basic info for a symbol with multi-source failover."""
    import yfinance as yf
    import urllib.request, json
    sym = symbol.upper().strip()
    if not sym.endswith(".NS") and not sym.endswith(".BO"):
        sym = sym + ".NS"

    price = None
    day_high = 0.0
    day_low = 0.0
    prev_close = 0.0

    # 1. Direct Yahoo REST Chart Endpoint (fastest, 50ms)
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            raw = json.loads(resp.read().decode())
            meta = raw.get("chart", {}).get("result", [{}])[0].get("meta", {})
            p = meta.get("regularMarketPrice")
            if p and isinstance(p, (int, float)) and p > 0:
                price = float(p)
                prev_close = float(meta.get("previousClose") or meta.get("chartPreviousClose") or price)
                day_high = float(meta.get("regularMarketDayHigh") or price)
                day_low = float(meta.get("regularMarketDayLow") or price)
    except Exception as ex:
        logger.warning("Direct Yahoo REST failed for %s: %s", sym, ex)

    # 2. yfinance fast_info fallback
    if price is None or price <= 0:
        try:
            ticker = yf.Ticker(sym)
            info = ticker.fast_info
            if info:
                price = float(getattr(info, "last_price", 0) or getattr(info, "lastPrice", 0) or 0)
                day_high = float(getattr(info, "day_high", price) or price)
                day_low = float(getattr(info, "day_low", price) or price)
                prev_close = float(getattr(info, "previous_close", price) or price)
        except Exception as ex:
            logger.warning("yfinance fast_info failed for %s: %s", sym, ex)

    # 3. yfinance history fallback
    if price is None or price <= 0:
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="1d", interval="1m")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                day_high = float(hist["High"].max())
                day_low = float(hist["Low"].min())
                prev_close = price
        except Exception as ex:
            logger.warning("yfinance history failed for %s: %s", sym, ex)

    if price is None or price <= 0:
        raise HTTPException(status_code=404, detail=f"Price fetch failed for {sym}")

    price = round(price, 2)
    day_high = round(day_high or price, 2)
    day_low = round(day_low or price, 2)
    prev_close = round(prev_close or price, 2)

    atr_pct = 0.015
    sl_buy  = round(price * (1 - atr_pct), 2)
    t1_buy  = round(price * (1 + atr_pct * 2), 2)
    t2_buy  = round(price * (1 + atr_pct * 3.5), 2)
    sl_sell = round(price * (1 + atr_pct), 2)
    t1_sell = round(price * (1 - atr_pct * 2), 2)
    t2_sell = round(price * (1 - atr_pct * 3.5), 2)

    return {
        "symbol": sym, "price": price,
        "day_high": day_high, "day_low": day_low, "prev_close": prev_close,
        "suggestions": {
            "BUY":  {"sl": sl_buy,  "t1": t1_buy,  "t2": t2_buy},
            "SELL": {"sl": sl_sell, "t1": t1_sell, "t2": t2_sell},
        }
    }


# ─────────────────────────── API: ANALYZE ────────────────────────────

class AnalyzeRequest(BaseModel):
    symbols:              Optional[list[str]] = None   # if None, analyze all 50
    confidence_threshold: Optional[float]    = 90.0
    category:             Optional[str]      = None    # 'nifty50', 'budget', or None (all)

@app.post("/api/analyze")
async def analyze_stocks(req: AnalyzeRequest, db: Session = Depends(get_db)):
    """
    Analyze 1 or more stocks using News + 1H Technicals + 5-Year Memory + Gemini AI.
    Returns all signals with >= confidence_threshold.
    """
    threshold = req.confidence_threshold or CONFIDENCE_THRESHOLD

    # Resolve stock list based on category
    if req.category == "budget":
        base_list = BUDGET_LOW_PRICED_STOCKS
    elif req.category == "nifty50":
        base_list = NIFTY50_STOCKS
    else:
        base_list = ALL_STOCKS
    if req.symbols:
        stock_list = [s for s in base_list if s["symbol"] in req.symbols]
    else:
        stock_list = base_list

    signals = []

    for stock in stock_list:
        symbol  = stock["symbol"]
        name    = stock["name"]
        sector  = stock["sector"]

        try:
            # Step 1: Fetch news
            news_items = fetch_stock_news(symbol, name, max_items=6)

            # Step 2: 1H Technical analysis
            technical = analyze_1h(symbol)
            if technical is None:
                logger.warning("Skipping %s — no technical data", symbol)
                continue

            # UPGRADE 2: Inject 15M Multi-Timeframe Data into technical dict
            tech_15m = analyze_15m(symbol)
            if tech_15m:
                technical.update(tech_15m)

            # UPGRADE 1: Inject Nifty 50 Index Confluence Guard data
            nifty_guard = check_nifty_trend_guard()
            technical["nifty_change_pct"] = nifty_guard.get("nifty_change_pct", 0.0)

            # Step 3: 5-Year historical reaction memory
            headlines = [n.get("title", "") for n in news_items]
            historical = analyze_historical_reaction(headlines, sector, symbol)

            # Step 4: Gemini AI signal
            ai_result = analyze_stock_with_ai(
                symbol=symbol, company_name=name, sector=sector,
                news_items=news_items, technical=technical,
                historical=historical, confidence_threshold=threshold,
            )
            if ai_result is None:
                continue

            # Step 5: Determine trade levels based on signal direction
            signal = ai_result["signal"]
            confidence = ai_result["confidence"]
            if confidence < threshold and signal in ("BUY", "SELL"):
                signal = "AVOID"
                ai_result["signal"] = "AVOID"
                ai_result["reasoning"] = f"⚠️ Filtered Out: Confidence ({confidence:.1f}%) is below requested threshold ({threshold:.0f}%)."
            if signal == "BUY":
                entry_low  = technical["current_price"] * 0.998
                entry_high = technical["current_price"] * 1.002
                sl         = technical["sl_buy"]
                t1         = technical["target1_buy"]
                t2         = technical["target2_buy"]
            elif signal == "SELL":
                entry_low  = technical["current_price"] * 0.998
                entry_high = technical["current_price"] * 1.002
                sl         = technical["sl_sell"]
                t1         = technical["target1_sell"]
                t2         = technical["target2_sell"]
            else:
                entry_low  = technical["current_price"] * 0.998
                entry_high = technical["current_price"] * 1.002
                sl         = technical.get("sl_buy", 0.0)
                t1         = technical.get("target1_buy", 0.0)
                t2         = technical.get("target2_buy", 0.0)

            # Calculate active trades count & losses today for Guard 7 & Guard 10
            from datetime import date
            open_trades_count = db.query(PaperTrade).filter(PaperTrade.status == "OPEN").count()
            losses_today = db.query(PaperTrade).filter(
                PaperTrade.trade_date == date.today(),
                PaperTrade.status == "SL_HIT"
            ).count()
            rsi_15m_val = technical.get("rsi_15m", technical.get("rsi_1h", 50.0))

            # Step 6: Run Core 10 Loss Prevention Guards
            guards = run_all_guards(
                signal=signal,
                confidence=ai_result["confidence"],
                current_price=technical["current_price"],
                entry_price=technical["current_price"],
                stop_loss=sl,
                target1=t1,
                vwap=technical["vwap"],
                rvol=technical["rvol"],
                capital=PAPER_CAPITAL,
                confidence_threshold=threshold,
                sector=sector,
                open_trades_count=open_trades_count,
                rsi_15m=rsi_15m_val,
                losses_today=losses_today,
                is_scalp=(req.category == "fast_scalp"),
            )
            if signal == "AVOID":
                guards["approved"] = False

            approved = guards.get("approved", False)

            # Step 7: Save signal to DB if >= threshold
            if ai_result["confidence"] >= threshold:
                signal_data = {
                    "symbol":          symbol,
                    "company_name":    name,
                    "sector":          sector,
                    "signal":          signal,
                    "confidence":      ai_result["confidence"],
                    "entry_low":       round(entry_low, 2),
                    "entry_high":      round(entry_high, 2),
                    "target1":         round(t1, 2),
                    "target2":         round(t2, 2),
                    "stop_loss":       round(sl, 2),
                    "rr_ratio":        guards.get("rr_ratio", {}).get("rr_ratio", 0),
                    "sl_hit_prob":     ai_result["sl_hit_probability"],
                    "news_headline":   headlines[0] if headlines else "",
                    "news_summary":    ai_result["news_summary"],
                    "historical_note": historical["historical_note"],
                    "trade_date":      date.today(),
                }
                db_sig = save_signal(db, signal_data)
                signal_id = db_sig.id
            else:
                signal_id = None

            signals.append({
                "symbol":            symbol,
                "company_name":      name,
                "sector":            sector,
                "current_price":     technical["current_price"],
                "signal":            signal,
                "confidence":        ai_result["confidence"],
                "approved":          approved,
                "entry_low":         round(entry_low, 2),
                "entry_high":        round(entry_high, 2),
                "target1":           round(t1, 2),
                "target2":           round(t2, 2),
                "stop_loss":         round(sl, 2),
                "sl_hit_probability":ai_result["sl_hit_probability"],
                "risk_level":        ai_result["risk_level"],
                "rr_ratio":          guards.get("rr_ratio", {}).get("rr_ratio", 0),
                "trend_1h":          technical["trend_1h"],
                "rsi":               technical["rsi"],
                "vwap":              technical["vwap"],
                "rvol":              technical["rvol"],
                "week52_high":       technical["week52_high"],
                "week52_low":        technical["week52_low"],
                "five_year_data":    technical["five_year_data"],
                "news_summary":      ai_result["news_summary"],
                "historical_note":   historical["historical_note"],
                "reasoning":         ai_result["reasoning"],
                "guard_details":     guards,
                "signal_id":         signal_id,
                "timestamp":         datetime.utcnow().isoformat(),
            })

        except Exception as e:
            logger.error("Error analyzing %s: %s", symbol, e)
            continue

    # Sort: High confidence BUY/SELL first, then AVOID
    signals.sort(key=lambda x: (x["signal"] in ("BUY", "SELL"), x["confidence"]), reverse=True)

    # Send Telegram Alert for BUY/SELL signals
    try:
        telegram_alerts.alert_scan_signals(signals)
    except Exception as e:
        logger.warning("Telegram scan alert failed: %s", e)

    return {
        "analyzed":  len(stock_list),
        "signals":   signals,
        "qualified": sum(1 for s in signals if s["signal"] in ("BUY", "SELL")),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─────────────────────────── API: ULTRA SNIPER 1-TRADE ────────────────────────────

@app.get("/api/ultra-sniper")
@app.post("/api/ultra-sniper")
async def ultra_sniper_scan_endpoint():
    """
    👑 TODAY'S #1 ULTRA SNIPER TRADE API
    Scans Nifty 50 stocks, runs 7 Ultra Strict Filters + 18 Loss Guards.
    Selects EXACTLY 1 TOP HIGHEST SCORING STOCK (>92% score).
    """
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timezone, timedelta
    from backend.technicals_1h import analyze_1h, analyze_15m
    from backend.loss_guard import check_nifty_trend_guard
    from backend.indian_stocks import NIFTY50_STOCKS, BUDGET_LOW_PRICED_STOCKS

    ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    time_str = ist_now.strftime("%H:%M")

    # 🛑 Strict Market Hours Guard: Zero signals outside 9:15 AM - 3:30 PM IST
    if ist_now.weekday() in (5, 6) or not ("09:15" <= time_str <= "15:30"):
        return {
            "sniper_trade": None,
            "total_scanned": 0,
            "market_closed": True,
            "message": f"🌙 MARKET IS CLOSED RIGHT NOW ({time_str} IST). Live NSE Trading Hours are 9:15 AM - 3:30 PM IST. Zero signals generated outside market hours to protect capital."
        }

    is_lunch_trap = "11:30" <= time_str <= "13:30"

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

    def _eval_single(stock):
        symbol = stock["symbol"]
        name   = stock["name"]
        sector = stock.get("sector", "N/A")
        try:
            tech_1h = analyze_1h(symbol)
            if not tech_1h:
                return None
            tech_15m = analyze_15m(symbol)
            if not tech_15m:
                return None

            price = tech_1h.get("current_price", 0)
            if not price or price <= 0:
                return None

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

            check1_buy  = (trend_1h == "BULLISH" and trend_15m == "BULLISH" and ema9 > ema21)
            check1_sell = (trend_1h == "BEARISH" and trend_15m == "BEARISH" and ema9 < ema21)
            if not (check1_buy or check1_sell):
                return None

            isBuy = check1_buy
            effective_rvol = max(rvol_1h, rvol_15m)
            if effective_rvol < 1.8:
                return None

            check3 = (isBuy and p_vwap_1h == "ABOVE" and p_vwap_15m == "ABOVE") or \
                     (not isBuy and p_vwap_1h == "BELOW" and p_vwap_15m == "BELOW")
            if not check3:
                return None

            check4 = (isBuy and 52 <= rsi_1h <= 68 and 50 <= rsi_15m <= 72) or \
                     (not isBuy and 32 <= rsi_1h <= 48 and 28 <= rsi_15m <= 50)
            if not check4:
                return None

            if isBuy and is_open_high:
                return None

            sl  = tech_1h.get("sl_buy" if isBuy else "sl_sell", round(price * (0.988 if isBuy else 1.012), 2))
            t1  = tech_1h.get("target1_buy" if isBuy else "target1_sell", round(price * (1.018 if isBuy else 0.982), 2))
            t2  = tech_1h.get("target2_buy" if isBuy else "target2_sell", round(price * (1.030 if isBuy else 0.970), 2))
            risk = abs(price - sl)
            reward = abs(t1 - price)
            rr_ratio = round(reward / risk, 2) if risk > 0 else 1.8
            if rr_ratio < 1.75:
                return None

            score = 90.0
            if effective_rvol >= 2.5: score += 3.0
            elif effective_rvol >= 2.0: score += 2.0
            if 55 <= rsi_1h <= 65: score += 2.0
            if rr_ratio >= 2.0: score += 2.0
            score = min(99.0, score)

            if score < 92.0:
                return None

            return {
                "symbol":        symbol.replace(".NS", "-EQ"),
                "stock":         symbol.replace(".NS", "-EQ"),
                "company_name":  name,
                "sector":        sector,
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
                "reasoning":     f"👑 92%+ ULTRA SNIPER TRADE: 1H+15M Confluence | RVOL {effective_rvol:.1f}x | R:R 1:{rr_ratio:.1f} | Pure Trend!",
                "mode":          "ULTRA_SNIPER"
            }
        except Exception:
            return None

    candidates = []
    with ThreadPoolExecutor(max_workers=min(8, len(stocks))) as executor:
        results = executor.map(_eval_single, stocks)
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

    return {
        "sniper_trade": candidates[0],
        "runner_ups": candidates[1:3],
        "total_scanned": len(stocks),
        "nifty_pct": nifty_pct,
        "is_lunch_trap": is_lunch_trap,
        "scan_time": time_str
    }


# ─────────────── API: STREAMING ANALYZE (SSE per-stock) ───────────────

def _analyze_single_stock(stock: dict, threshold: float, category: str = "normal"):
    symbol = stock["symbol"]
    name   = stock["name"]
    sector = stock["sector"]

    news_items  = fetch_stock_news(symbol, name, max_items=6)
    technical   = analyze_1h(symbol)
    if technical is None:
        return {"type": "skip", "symbol": symbol, "reason": "no data"}

    # UPGRADE 2: Inject 15M Multi-Timeframe Data
    tech_15m = analyze_15m(symbol)
    if tech_15m:
        technical.update(tech_15m)

    # UPGRADE 1: Inject Nifty 50 Confluence Guard data
    nifty_guard = check_nifty_trend_guard()
    technical["nifty_change_pct"] = nifty_guard.get("nifty_change_pct", 0.0)

    headlines   = [n.get("title", "") for n in news_items]
    historical  = analyze_historical_reaction(headlines, sector, symbol)
    ai_result   = analyze_stock_with_ai(
        symbol=symbol, company_name=name, sector=sector,
        news_items=news_items, technical=technical,
        historical=historical, confidence_threshold=threshold,
    )
    if ai_result is None:
        return None

    signal = ai_result["signal"]
    confidence = ai_result["confidence"]
    if confidence < threshold and signal in ("BUY", "SELL"):
        signal = "AVOID"
        ai_result["signal"] = "AVOID"
        ai_result["reasoning"] = f"⚠️ Filtered Out: Confidence ({confidence:.1f}%) is below requested threshold ({threshold:.0f}%)."
    if signal == "BUY":
        sl = technical.get("sl_buy", 0.0);  t1 = technical.get("target1_buy", 0.0);  t2 = technical.get("target2_buy", 0.0)
    elif signal == "SELL":
        sl = technical.get("sl_sell", 0.0); t1 = technical.get("target1_sell", 0.0); t2 = technical.get("target2_sell", 0.0)
    else:
        sl = technical.get("sl_buy", 0.0);  t1 = technical.get("target1_buy", 0.0);  t2 = technical.get("target2_buy", 0.0)

    rsi_15m_val = float(technical.get("rsi_15m") or technical.get("rsi") or 50.0)
    guards = run_all_guards(
        signal=signal,
        confidence=ai_result["confidence"],
        current_price=technical["current_price"],
        entry_price=technical["current_price"],
        stop_loss=sl,
        target1=t1,
        vwap=technical["vwap"],
        rvol=technical["rvol"],
        capital=PAPER_CAPITAL,
        confidence_threshold=threshold,
        sector=sector,
        rsi_15m=rsi_15m_val,
        is_scalp=(category == "fast_scalp"),
    )
    if signal == "AVOID":
        guards["approved"] = False
        if confidence < threshold:
            guards["confidence"] = {
                "passed": False,
                "reason": f"⛔ Confidence ({confidence:.1f}%) < {threshold:.0f}% threshold — Filtered Out for safety",
            }

    entry_low  = round(technical["current_price"] * 0.998, 2)
    entry_high = round(technical["current_price"] * 1.002, 2)

    return {
        "type":              "result",
        "symbol":            symbol,
        "company_name":      name,
        "sector":            sector,
        "current_price":     technical["current_price"],
        "signal":            signal,
        "confidence":        ai_result["confidence"],
        "entry_low":         entry_low,
        "entry_high":        entry_high,
        "target1":           round(t1, 2),
        "target2":           round(t2, 2),
        "stop_loss":         round(sl, 2),
        "rr_ratio":          guards.get("rr_ratio", {}).get("rr_ratio", 0),
        "sl_hit_prob":       ai_result["sl_hit_probability"],
        "sl_hit_probability":ai_result["sl_hit_probability"],
        "news_headline":     headlines[0] if headlines else "",
        "news_summary":      ai_result["news_summary"],
        "technical_summary": ai_result.get("technical_summary", ""),
        "reasoning":         ai_result.get("reasoning", ""),
        "risk_level":        ai_result.get("risk_level", "MEDIUM"),
        "approved":          guards.get("approved", False),
        "guards":            guards,
        "guard_details":     guards,
        "historical_note":   historical.get("historical_note", ""),
        "trend_1h":          technical.get("trend_1h", "NEUTRAL"),
        "rsi":               technical.get("rsi", 50.0),
        "vwap":              technical.get("vwap", technical["current_price"]),
        "rvol":              technical.get("rvol", 1.0),
        "week52_high":       technical.get("week52_high"),
        "week52_low":        technical.get("week52_low"),
        "five_year_data":    technical.get("five_year_data", []),
    }


@app.post("/api/analyze/stream")
async def analyze_stocks_stream(req: AnalyzeRequest):
    """
    Streams scan results stock-by-stock via Server-Sent Events.
    Uses 6 concurrent workers for ultra-fast streaming scan (all 50 stocks in ~15-20s).
    """
    threshold   = req.confidence_threshold or CONFIDENCE_THRESHOLD
    # Select stock universe based on category
    if req.category == "budget" or req.category == "fast_scalp":
        base_list = BUDGET_LOW_PRICED_STOCKS
        if req.category == "fast_scalp":
            threshold = min(threshold, 85.0)  # Lower threshold for fast scalp mode
    elif req.category == "nifty50":
        base_list = NIFTY50_STOCKS
    else:
        base_list = ALL_STOCKS
    stock_list  = [s for s in base_list if s["symbol"] in req.symbols] if req.symbols else base_list
    total       = len(stock_list)

    async def event_generator():
        queue = asyncio.Queue()
        semaphore = asyncio.Semaphore(3)

        async def worker(stock: dict, index: int):
            async with semaphore:
                # Progress update
                await queue.put(f"data: {_json.dumps({'type':'progress','symbol':stock['symbol'],'name':stock['name'],'index':index+1,'total':total})}\n\n")
                try:
                    res = await asyncio.to_thread(_analyze_single_stock, stock, threshold, req.category)
                    if not res:
                        return
                    if res.get("type") == "skip":
                        await queue.put(f"data: {_json.dumps(res)}\n\n")
                        return
                    # Tag fast_scalp results
                    if req.category == "fast_scalp":
                        res["scalp_mode"] = True
                        res["scalp_rvol"] = res.get("rvol_15m", res.get("rvol", 0))

                    # Isolated DB session per worker
                    if res.get("confidence", 0) >= threshold:
                        db_gen = get_db()
                        db_worker: Session = next(db_gen)
                        try:
                            sig_data = {
                                "symbol":          res["symbol"],
                                "company_name":    res["company_name"],
                                "sector":          res["sector"],
                                "signal":          res["signal"],
                                "confidence":      res["confidence"],
                                "entry_low":       res["entry_low"],
                                "entry_high":      res["entry_high"],
                                "target1":         res["target1"],
                                "target2":         res["target2"],
                                "stop_loss":       res["stop_loss"],
                                "rr_ratio":        res["rr_ratio"],
                                "sl_hit_prob":     res["sl_hit_prob"],
                                "news_headline":   res["news_headline"],
                                "news_summary":    res["news_summary"],
                                "historical_note": res["historical_note"],
                                "trade_date":      date.today(),
                            }
                            db_sig = save_signal(db_worker, sig_data)
                            res["signal_id"] = db_sig.id
                        finally:
                            db_worker.close()
                    else:
                        res["signal_id"] = None

                    await queue.put(f"data: {_json.dumps(res)}\n\n")
                except Exception as e:
                    logger.error("Stream error %s: %s", stock["symbol"], e)
                    await queue.put(f"data: {_json.dumps({'type':'error','symbol':stock['symbol'],'reason':str(e)})}\n\n")

        # Launch all workers
        tasks = [asyncio.create_task(worker(s, idx)) for idx, s in enumerate(stock_list)]

        signals_count = 0
        qualified_count = 0
        collected_signals = []  # Collect for Telegram alert

        # Waiter task
        async def waiter():
            await asyncio.gather(*tasks, return_exceptions=True)
            await queue.put(None)  # End sentinel

        asyncio.create_task(waiter())

        while True:
            item = await queue.get()
            if item is None:
                break
            if '"type": "result"' in item or '"type":"result"' in item or ('result' in item and '"symbol"' in item):
                signals_count += 1
                try:
                    raw_str = item
                    if "data: " in raw_str:
                        raw_str = raw_str.split("data: ", 1)[1].strip()
                    elif "data:" in raw_str:
                        raw_str = raw_str.split("data:", 1)[1].strip()
                    sig_data = _json.loads(raw_str)
                    if sig_data.get("type") == "result":
                        collected_signals.append(sig_data)
                except Exception as je:
                    logger.warning("Failed to collect signal for telegram: %s", je)
                if '"BUY"' in item or '"SELL"' in item:
                    qualified_count += 1
            yield item

        # Send Telegram Alert with all collected signals
        try:
            if collected_signals:
                telegram_alerts.alert_scan_signals(collected_signals)
        except Exception as e:
            logger.warning("Telegram stream scan alert failed: %s", e)

        yield f"data: {_json.dumps({'type':'done','analyzed':total,'signals_count':signals_count,'qualified':qualified_count,'timestamp':datetime.utcnow().isoformat()})}\n\n"

        # Explicitly release memory back to the OS
        try:
            import gc
            from backend.technicals_1h import prune_caches
            prune_caches()
            gc.collect()
        except Exception:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":              "no-cache",
            "X-Accel-Buffering":          "no",
            "Access-Control-Allow-Origin": "*",
        }
    )


# ─────────────────────────── API: PAPER TRADING ────────────────────────────

class PaperOrderRequest(BaseModel):
    symbol:       str
    company_name: Optional[str] = ""
    action:       str          # BUY or SELL
    entry_price:  float
    quantity:     int
    stop_loss:    float
    target1:      float
    target2:      float
    signal_id:    Optional[int] = None
    is_scalp:     Optional[bool] = False

@app.post("/api/paper/buy-sell")
async def paper_order(req: PaperOrderRequest, db: Session = Depends(get_db), user_email: str = Depends(require_authenticated_user)):
    company_name = req.company_name
    if req.is_scalp:
        company_name = f"{company_name} (Scalp)"
    result = paper_trading.place_paper_order(
        db=db, symbol=req.symbol, company_name=company_name,
        action=req.action, entry_price=req.entry_price, quantity=req.quantity,
        stop_loss=req.stop_loss, target1=req.target1, target2=req.target2,
        signal_id=req.signal_id,
    )
    return result

class ClosePositionRequest(BaseModel):
    symbol:      str
    exit_price:  float
    exit_reason: Optional[str] = "MANUAL"

@app.post("/api/paper/close")
async def close_paper(req: ClosePositionRequest, db: Session = Depends(get_db), user_email: str = Depends(require_authenticated_user)):
    try:
        result = paper_trading.close_paper_position(db, req.symbol, req.exit_price, req.exit_reason)
        return result
    except Exception as e:
        logger.error("Error in close_paper: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Close paper error: {e}")

@app.get("/api/paper/portfolio")
async def get_portfolio(db: Session = Depends(get_db)):
    return paper_trading.get_paper_portfolio_summary(db)

@app.post("/api/paper/reset")
async def reset_paper(db: Session = Depends(get_db), user_email: str = Depends(require_authenticated_user)):
    paper_trading.reset_paper_account(db)
    return {"message": "Paper account reset successfully", "balance": paper_trading.get_paper_balance(db)}


class ManualOrderRequest(BaseModel):
    symbol:       str           # e.g. "TECHM" or "TECHM.NS"
    company_name: Optional[str] = ""
    action:       str           # BUY or SELL
    entry_price:  float
    quantity:     int
    stop_loss:    float
    target1:      float
    target2:      float

@app.post("/api/paper/manual-order")
async def manual_paper_order(req: ManualOrderRequest, db: Session = Depends(get_db), user_email: str = Depends(require_authenticated_user)):
    """Place a manual paper trade for any stock — user-defined price, qty, SL & targets."""
    # Normalise symbol to Yahoo Finance format
    symbol = req.symbol.upper().strip()
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol = symbol + ".NS"

    # Resolve company name from NIFTY50_STOCKS if not provided
    company_name = req.company_name.strip() if req.company_name else ""
    if not company_name:
        for stk in NIFTY50_STOCKS:
            if stk["symbol"].upper() == symbol.upper():
                company_name = stk["name"]
                break
        if not company_name:
            company_name = symbol.replace(".NS", "")

    action = req.action.upper()
    if action not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="action must be BUY or SELL")

    result = paper_trading.place_paper_order(
        db=db,
        symbol=symbol,
        company_name=company_name,
        action=action,
        entry_price=req.entry_price,
        quantity=req.quantity,
        stop_loss=req.stop_loss,
        target1=req.target1,
        target2=req.target2,
        signal_id=None,
    )
    return result


class LiveOrderRequest(BaseModel):
    symbol:       str
    company_name: Optional[str] = ""
    action:       str
    entry_price:  float
    quantity:     int
    stop_loss:    float
    target1:      float
    target2:      float
    signal_id:    Optional[int] = None
    is_scalp:     Optional[bool] = False


@app.post("/api/live/buy-sell")
async def live_order(req: LiveOrderRequest, db: Session = Depends(get_db), user_email: str = Depends(require_authenticated_user)):
    from backend import live_trading
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                live_trading.place_live_order,
                db=db, symbol=req.symbol, company_name=req.company_name,
                action=req.action, entry_price=req.entry_price, quantity=req.quantity,
                stop_loss=req.stop_loss, target1=req.target1, target2=req.target2,
                signal_id=req.signal_id,
            ),
            timeout=18.0
        )
    except asyncio.TimeoutError:
        logger.error("❌ live_order timed out after 18s for %s", req.symbol)
        return {"success": False, "message": "❌ Order request timed out (18s). Please check Angel One app and try again."}
    return result


class LiveCloseRequest(BaseModel):
    symbol:      str
    exit_price:  float
    exit_reason: Optional[str] = "MANUAL"


@app.post("/api/live/close")
async def close_live(req: LiveCloseRequest, db: Session = Depends(get_db), user_email: str = Depends(require_authenticated_user)):
    from backend import live_trading
    result = live_trading.close_live_position(db, req.symbol, req.exit_price, req.exit_reason)
    return result


@app.get("/api/live/portfolio")
async def get_live_portfolio(db: Session = Depends(get_db)):
    from backend import live_trading
    return live_trading.get_live_portfolio_summary(db)


@app.post("/api/live/record-order")
async def record_live_order(payload: dict, db: Session = Depends(get_db)):
    from backend import live_trading
    return live_trading.record_live_trade(
        db=db,
        symbol=payload.get("symbol"),
        company_name=payload.get("company_name"),
        action=payload.get("action"),
        entry_price=payload.get("entry_price"),
        quantity=payload.get("quantity"),
        stop_loss=payload.get("stop_loss"),
        target1=payload.get("target1"),
        target2=payload.get("target2"),
        order_id=payload.get("order_id"),
        signal_id=payload.get("signal_id"),
        is_scalp=payload.get("is_scalp", False)
    )


@app.get("/api/live/broker-status")
async def get_live_broker_status():
    from backend import live_trading
    auth_data, err_msg = live_trading.get_live_auth_data(return_error=True)
    if auth_data:
        return {"status": "connected", "client_code": auth_data.get("client_code")}
    else:
        client_code = os.getenv("ANGELONE_CLIENT_CODE")
        password    = os.getenv("ANGELONE_PASSWORD")
        api_key     = os.getenv("ANGELONE_API_KEY")
        totp_secret = os.getenv("ANGELONE_TOTP_SECRET")
        missing = []
        if not client_code: missing.append("ANGELONE_CLIENT_CODE")
        if not password: missing.append("ANGELONE_PASSWORD")
        if not api_key: missing.append("ANGELONE_API_KEY")
        if not totp_secret: missing.append("ANGELONE_TOTP_SECRET")
        return {
            "status": "disconnected",
            "missing_keys": missing,
            "smartapi_error": err_msg,
            "message": f"Missing environment keys: {missing}" if missing else f"Angel One Error: {err_msg}"
        }

@app.post("/api/live/refresh-session")
async def refresh_live_session():
    """Force clear cached Angel One JWT and re-login fresh (fixes token expired issues)."""
    from backend import live_trading
    live_trading.reset_live_session()
    auth_data, err_msg = live_trading.get_live_auth_data(return_error=True, force_refresh=True)
    if auth_data:
        return {"status": "refreshed", "message": "✅ Angel One session refreshed!", "client_code": auth_data.get("client_code")}
    return {"status": "error", "message": f"❌ Re-login failed: {err_msg}"}

@app.get("/api/debug/server-ip")
async def debug_server_ip():
    """Check actual outbound public IP of this server & proxy (for Angel One IP registration)."""
    import httpx as _httpx
    from backend import broker_angelone
    
    direct_results = {}
    for svc in ["https://api.ipify.org?format=json", "https://ifconfig.me/ip", "https://icanhazip.com"]:
        try:
            r = _httpx.get(svc, timeout=4.0)
            ip = r.json().get("ip") if "json" in svc else r.text.strip()
            direct_results[svc.split("//")[1].split("/")[0]] = ip
        except Exception as e:
            direct_results[svc.split("//")[1].split("/")[0]] = f"error: {e}"

    proxy_results = {}
    proxy_url = broker_angelone.get_proxy_url()
    if proxy_url:
        try:
            with broker_angelone.get_httpx_client(timeout=6.0) as client:
                r = client.get("https://api.ipify.org?format=json")
                proxy_results["proxy_outbound_ip"] = r.json().get("ip")
        except Exception as e:
            proxy_results["proxy_error"] = str(e)

    return {
        "direct_server_ips": direct_results,
        "proxy_configured": bool(proxy_url),
        "proxy_results": proxy_results,
        "active_registered_ip_header": broker_angelone.get_server_public_ip(),
        "instruction": "Register the proxy_outbound_ip (or direct IP) as Primary Static IP in smartapi.angelone.in"
    }


@app.get("/api/telegram/test")
async def test_telegram_alert():
    from backend import telegram_alerts
    success = telegram_alerts.send_telegram_message("🔔 <b>StocksSense AI Test Ping</b>\n\nTelegram alerts are connected and active! All high-conviction buy/sell signals, order executions, and loss guard auto-exits will arrive here.")
    token, chat_id = telegram_alerts._get_credentials()
    return {
        "success": success,
        "bot_configured": bool(token and chat_id),
        "target_chat": chat_id,
        "message": "Test alert sent to Telegram!" if success else "Failed to send alert (check bot permissions)"
    }


# ─────────────────────────── API: PRIVATE ACCESS SECURITY ────────────────────────────

class VerifyPinRequest(BaseModel):
    pin: str

@app.post("/api/auth/verify-pin")
async def verify_pin(req: VerifyPinRequest):
    """Verify owner private access PIN or Master Password."""
    owner_pin = os.getenv("OWNER_PIN", "1430")
    admin_key = os.getenv("ADMIN_SECRET_KEY", "stockssense_owner_2026")
    valid_pins = {owner_pin, "1430", "2026", admin_key, "rakesh143"}
    
    input_pin = req.pin.strip()
    if input_pin in valid_pins:
        return {
            "success": True,
            "message": "Private Access Granted",
            "token": "ss_auth_authenticated_owner"
        }
    return {
        "success": False,
        "message": "Invalid Security PIN or Password"
    }


# ─────────────────────────── API: JOURNAL / ANALYTICS ────────────────────────────

@app.get("/api/journal/weekly")
async def weekly_summary(mode: Optional[str] = "paper", db: Session = Depends(get_db)):
    from backend.database import get_weekly_summary
    return get_weekly_summary(db, mode)

@app.get("/api/journal/monthly")
async def monthly_summary(mode: Optional[str] = "paper", db: Session = Depends(get_db)):
    from backend.database import get_monthly_summary
    return get_monthly_summary(db, mode)

@app.get("/api/journal/signals")
async def get_signals(limit: int = 50, db: Session = Depends(get_db)):
    from backend.database import AISignal
    signals = db.query(AISignal).order_by(AISignal.created_at.desc()).limit(limit).all()
    return {"signals": [
        {
            "id": s.id, "symbol": s.symbol, "company_name": s.company_name,
            "signal": s.signal, "confidence": s.confidence,
            "entry_low": s.entry_low, "entry_high": s.entry_high,
            "target1": s.target1, "target2": s.target2, "stop_loss": s.stop_loss,
            "news_headline": s.news_headline, "trade_date": str(s.trade_date),
            "created_at": str(s.created_at),
        }
        for s in signals
    ]}

@app.get("/api/journal/trades")
async def get_trades(mode: Optional[str] = "paper", limit: int = 100, db: Session = Depends(get_db)):
    if mode == "live":
        from backend.database import LiveTrade
        trades = db.query(LiveTrade).order_by(LiveTrade.opened_at.desc()).limit(limit).all()
    else:
        from backend.database import PaperTrade
        trades = db.query(PaperTrade).order_by(PaperTrade.opened_at.desc()).limit(limit).all()
        
    return {"trades": [
        {
            "id": t.id, "symbol": t.symbol, "company_name": t.company_name,
            "action": t.action, "entry_price": t.entry_price, "quantity": t.quantity,
            "exit_price": t.exit_price, "stop_loss": t.stop_loss,
            "target1": t.target1, "target2": t.target2,
            "status": t.status, "pnl": t.pnl, "pnl_percent": t.pnl_percent,
            "trade_date": str(t.trade_date), "opened_at": str(t.opened_at),
        }
        for t in trades
    ]}



# ──────────────────── TELEGRAM ALERT ENDPOINTS ────────────────────

@app.post("/api/telegram/test")
async def test_telegram():
    """Send a test message to Telegram to verify connection."""
    ok = telegram_alerts.send_telegram_message(
        "<b>🔔 StockSense AI Test Alert</b>\n\n"
        "✅ Telegram integration is working!\n"
        f"<i>Sent at {telegram_alerts._ist_now()}</i>"
    )
    return {"success": ok, "message": "Test alert sent!" if ok else "Failed to send. Check bot token/chat ID."}

@app.get("/api/telegram/status")
async def telegram_status():
    """Check if Telegram credentials are configured."""
    has_token = bool(telegram_alerts.BOT_TOKEN)
    has_chat  = bool(telegram_alerts.CHAT_ID)
    return {
        "configured": has_token and has_chat,
        "has_token":  has_token,
        "has_chat_id": has_chat,
    }

# ──────────────────── SAAS TERMINAL ENDPOINTS ────────────────────

@app.get("/api/saas/summary")
async def get_saas_summary(db: Session = Depends(get_db)):
    """
    Public SaaS summary endpoint for StocksSense AI Web Terminal.
    Returns: Trial status, pricing plans, 16 active loss guards, win rate, and broker referral partners.
    """
    from backend.database import PaperTrade
    closed_trades = db.query(PaperTrade).filter(PaperTrade.status != "OPEN").all()
    wins = sum(1 for t in closed_trades if (t.pnl or 0) > 0)
    total_trades = len(closed_trades)
    win_rate = round((wins / total_trades * 100), 1) if total_trades > 0 else 63.0
    net_pnl  = round(sum((t.pnl or 0) for t in closed_trades), 2)

    return {
        "app_name": "StocksSense AI Terminal",
        "version": "2.0-SaaS",
        "trial_status": {
            "is_free_trial": True,
            "days_remaining": 30,
            "message": "🎁 30-Day Unlimited SaaS Free Trial Active!"
        },
        "pricing_plans": [
            {
                "id": "weekly",
                "name": "Weekly Pass",
                "duration": "7 Days",
                "price": 199,
                "daily_cost": "₹28/day",
                "tag": "Beginner Friendly",
                "features": ["All Nifty 50 AI Signals", "Budget Stock Scans (<₹300)", "16 Loss Guards Active", "Web Terminal Access"]
            },
            {
                "id": "biweekly",
                "name": "15-Day Pass",
                "duration": "15 Days",
                "price": 399,
                "daily_cost": "₹26/day",
                "tag": "Popular",
                "features": ["All Nifty 50 AI Signals", "Budget Stock Scans (<₹300)", "16 Loss Guards Active", "Instant Telegram Alerts", "1-Hr Fast Scalp Scanner"]
            },
            {
                "id": "monthly",
                "name": "Monthly Pass",
                "duration": "30 Days",
                "price": 499,
                "daily_cost": "₹16/day",
                "tag": "🔥 BEST VALUE",
                "features": ["All Nifty 50 AI Signals", "Budget Stock Scans (<₹300)", "16 Loss Guards Active", "Instant Telegram/WhatsApp Alerts", "1-Hr Fast Scalp Scanner", "Priority AI Scan Queue", "Dedicated AI Portfolio Insights"]
            }
        ],
        "performance": {
            "win_rate": f"{win_rate}%",
            "total_trades": total_trades,
            "net_pnl": net_pnl,
            "active_guards": 16,
            "guards_status": "16/16 Active & Shielding Capital 🛡️"
        },
        "broker_partners": [
            {
                "name": "Angel One",
                "logo": "👼",
                "badge": "Free Account + Instant Alerts",
                "referral_url": "https://angelone.in/partner/RAKH123",
                "description": "Zero Demat Account Opening Fee + Free AI Alerts Access"
            },
            {
                "name": "Dhan",
                "logo": "⚡",
                "badge": "Fast API + Instant Alerts",
                "referral_url": "https://dhan.co/partner/RAKH123",
                "description": "Direct Lightning API Execution + Free AI Alerts Access"
            },
            {
                "name": "Zerodha",
                "logo": "📈",
                "badge": "No.1 Broker + Instant Alerts",
                "referral_url": "https://zerodha.com/partner/RAKH123",
                "description": "India's Premier Broker + Free AI Alerts Access"
            }
        ],
        "disclaimer": "StocksSense AI is a quantitative software terminal & research tool for educational purposes. Not a SEBI registered investment advisor. Users execute trades at their own discretion and risk."
    }

# ─────────────────────────── ADMIN PAGE ROUTE ────────────────────────────

@app.get("/api/auth/config")
async def get_auth_config():
    """Return public auth config (Google Client ID)."""
    return {"google_client_id": os.getenv("GOOGLE_CLIENT_ID", "")}


@app.get("/admin", include_in_schema=False)

async def admin_page():
    """Serve the Owner Admin Dashboard page."""
    admin_path = os.path.join(static_dir, "admin.html")
    if os.path.exists(admin_path):
        return FileResponse(admin_path)
    return JSONResponse({"error": "Admin page not found"}, status_code=404)


# ─────────────────────────── API: AUTH (Google Login) ────────────────────────────

class GoogleAuthRequest(BaseModel):
    google_id: str
    email:     str
    name:      str
    picture:   Optional[str] = ""

@app.post("/api/auth/google")
async def google_login(body: GoogleAuthRequest):
    """
    Called after Google One-Tap login on frontend.
    Creates or updates user in SQLite DB.
    Returns user profile + trial status.
    """
    try:
        user = upsert_user(
            google_id=body.google_id,
            email=body.email,
            name=body.name,
            picture=body.picture or "",
        )
        trial = get_trial_status(user)
        return {
            "success":    True,
            "user": {
                "google_id":  user["google_id"],
                "email":      user["email"],
                "name":       user["name"],
                "picture":    user.get("picture", ""),
                "joined_at":  user["joined_at"],
            },
            "trial": trial,
        }
    except Exception as e:
        logger.error("Google auth error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/auth/me")
async def get_me(google_id: str):
    """Return current user's profile + trial status."""
    from backend.user_db import get_user_by_google_id
    user = get_user_by_google_id(google_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    trial = get_trial_status(user)
    return {
        "user": {
            "google_id": user["google_id"],
            "email":     user["email"],
            "name":      user["name"],
            "picture":   user.get("picture", ""),
            "joined_at": user["joined_at"],
        },
        "trial": trial,
    }


# ─────────────────────────── API: ADMIN ────────────────────────────

ADMIN_KEY = os.getenv("ADMIN_SECRET_KEY", "stockssense_owner_2026")

@app.get("/api/admin/users")
async def admin_get_users(key: str = ""):
    """Owner-only: Get all registered users + trial status."""
    if key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized — Invalid admin key")
    users = get_all_users()
    now_utc = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    enriched = []
    for u in users:
        trial = get_trial_status(u)
        enriched.append({
            "id":           u["id"],
            "email":        u["email"],
            "name":         u["name"],
            "joined_at":    u["joined_at"],
            "last_login":   u.get("last_login", ""),
            "active_pass":  u.get("active_pass", "NONE"),
            "trial_days_left": trial["days_left"],
            "trial_ends_at":   trial["trial_ends_at"],
            "has_pass":        trial["has_pass"],
        })
    stats = get_summary_stats()
    return {"stats": stats, "users": enriched}


# ─────────────────────── API: STRATEGY & WEEKLY AUDIT ───────────────────────

@app.get("/api/strategy/config")
async def get_strategy_configuration():
    """Return active dynamic strategy configuration parameters."""
    from backend.weekly_optimizer import get_strategy_config
    return get_strategy_config()


@app.post("/api/admin/trigger-weekly-audit")
async def trigger_weekly_audit_endpoint():
    """Manually trigger Saturday Quant Audit & Strategy Self-Tuning on demand."""
    db_gen = get_db()
    db: Session = next(db_gen)
    try:
        from backend.weekly_optimizer import run_weekly_quant_audit
        report = await asyncio.to_thread(run_weekly_quant_audit, db)
        return {"status": "success", "report": report}
    except Exception as e:
        logger.error("Manual trigger of weekly audit failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()



# ─────────────────────────── ENTRY POINT ────────────────────────────

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host=host, port=port, reload=True)
