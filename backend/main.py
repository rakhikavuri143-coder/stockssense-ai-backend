"""
FastAPI Main Application
Indian Stock Market AI Agent — Nifty 50 Intraday Signal Engine
Host: 0.0.0.0:8000 (accessible on mobile via local Wi-Fi IP)
"""

import os
import logging
import asyncio
from datetime import date, datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
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
from backend.indian_stocks import NIFTY50_STOCKS, get_all_symbols, NIFTY_INDEX_SYMBOL
from backend.news_fetcher import fetch_stock_news, fetch_general_market_news
from backend.technicals_1h import analyze_1h, analyze_15m
from backend.historical_reaction import analyze_historical_reaction
from backend.loss_guard import run_all_guards, check_nifty_trend_guard
from backend.ai_agent import analyze_stock_with_ai
from backend import paper_trading
from backend import telegram_alerts

CONFIDENCE_THRESHOLD = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "90"))
PAPER_CAPITAL        = float(os.getenv("PAPER_CAPITAL", "10000"))

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
        for stock in NIFTY50_STOCKS:
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
    """Check live prices for open paper positions every 15s and auto-exit on SL/Target hit."""
    def _fetch_prices(symbols):
        import yfinance as yf
        prices = {}
        for sym in symbols:
            try:
                ticker = yf.Ticker(sym)
                fast_info = getattr(ticker, "fast_info", None)
                if fast_info and getattr(fast_info, "last_price", None):
                    prices[sym] = float(fast_info.last_price)
                else:
                    hist = ticker.history(period="1d", interval="1m")
                    if not hist.empty:
                        prices[sym] = float(hist["Close"].iloc[-1])
            except Exception as ex:
                logger.warning("Auto-exit price fetch failed for %s: %s", sym, ex)
        return prices

    db_gen = get_db()
    db: Session = next(db_gen)
    try:
        open_positions = paper_trading.get_open_positions(db)
        if not open_positions:
            return
        symbols = list(open_positions.keys())
        live_prices = await asyncio.to_thread(_fetch_prices, symbols)

        exits = paper_trading.check_auto_exits(db, live_prices)
        if exits:
            logger.info("⚡ Auto-exited %d paper position(s): %s", len(exits), exits)
    except Exception as e:
        logger.error("Error in auto_exit_monitor_job: %s", e)
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Auto-check open paper positions against live prices every 15 seconds
    scheduler.add_job(auto_exit_monitor_job, "interval", seconds=15, id="auto_exit_monitor")
    # 9:15 AM IST = 3:45 AM UTC (market open auto-scan)
    scheduler.add_job(market_open_scan_job, "cron", hour=3, minute=45, id="market_open_scan")
    # 11:30 AM IST = 6:00 AM UTC (midday check)
    scheduler.add_job(midday_scan_job, "cron", hour=6, minute=0, id="midday_scan")
    # 3:30 PM IST = 10:00 AM UTC (market close auto-save)
    scheduler.add_job(daily_save_job, "cron", hour=10, minute=0, id="daily_save")
    scheduler.start()
    logger.info("🚀 Indian Stock Market AI Agent started!")
    logger.info("⚡ Live Paper Position Monitor: Active (Every 15 seconds)")
    logger.info("📅 Scheduled: Market Open Scan @ 9:15 AM IST | Mid-day Scan @ 11:30 AM IST | Auto-Save @ 3:30 PM IST")
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


# ─────────────────────────── API: STOCKS ────────────────────────────

@app.get("/api/stocks")
async def get_stocks():
    """Return full Nifty 50 watchlist."""
    return {"stocks": NIFTY50_STOCKS, "total": len(NIFTY50_STOCKS)}


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
    """Fetch live price + basic info for a symbol (for manual trade modal)."""
    import yfinance as yf
    sym = symbol.upper().strip()
    if not sym.endswith(".NS") and not sym.endswith(".BO"):
        sym = sym + ".NS"
    try:
        ticker = yf.Ticker(sym)
        info   = ticker.fast_info
        price  = round(float(info.last_price), 2)
        day_high  = round(float(info.day_high), 2)
        day_low   = round(float(info.day_low), 2)
        prev_close = round(float(info.previous_close), 2)
        # Suggest SL = 1.5% below (BUY) and T1/T2 based on ATR-lite
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
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Price fetch failed: {e}")


# ─────────────────────────── API: ANALYZE ────────────────────────────

class AnalyzeRequest(BaseModel):
    symbols:              Optional[list[str]] = None   # if None, analyze all 50
    confidence_threshold: Optional[float]    = 90.0

@app.post("/api/analyze")
async def analyze_stocks(req: AnalyzeRequest, db: Session = Depends(get_db)):
    """
    Analyze 1 or more stocks using News + 1H Technicals + 5-Year Memory + Gemini AI.
    Returns all signals with >= confidence_threshold.
    """
    threshold = req.confidence_threshold or CONFIDENCE_THRESHOLD

    # Resolve stock list
    if req.symbols:
        stock_list = [s for s in NIFTY50_STOCKS if s["symbol"] in req.symbols]
    else:
        stock_list = NIFTY50_STOCKS

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
            ) if signal in ("BUY", "SELL") else {"approved": False}

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


# ─────────────── API: STREAMING ANALYZE (SSE per-stock) ───────────────

def _analyze_single_stock(stock: dict, threshold: float):
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

    guards = run_all_guards(
        signal=signal, confidence=ai_result["confidence"],
        current_price=technical["current_price"], entry_price=technical["current_price"],
        stop_loss=sl, target1=t1, vwap=technical["vwap"], rvol=technical["rvol"],
        capital=PAPER_CAPITAL, confidence_threshold=threshold,
    ) if signal in ("BUY", "SELL") else {"approved": False}

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
        "news_headline":     headlines[0] if headlines else "",
        "news_summary":      ai_result["news_summary"],
        "technical_summary": ai_result.get("technical_summary", ""),
        "reasoning":         ai_result.get("reasoning", ""),
        "risk_level":        ai_result.get("risk_level", "MEDIUM"),
        "approved":          guards.get("approved", False),
        "guards":            guards,
        "historical_note":   historical.get("historical_note", ""),
    }


@app.post("/api/analyze/stream")
async def analyze_stocks_stream(req: AnalyzeRequest):
    """
    Streams scan results stock-by-stock via Server-Sent Events.
    Uses 6 concurrent workers for ultra-fast streaming scan (all 50 stocks in ~15-20s).
    """
    threshold   = req.confidence_threshold or CONFIDENCE_THRESHOLD
    stock_list  = [s for s in NIFTY50_STOCKS if s["symbol"] in req.symbols] if req.symbols else NIFTY50_STOCKS
    total       = len(stock_list)

    async def event_generator():
        queue = asyncio.Queue()
        semaphore = asyncio.Semaphore(6)

        async def worker(stock: dict, index: int):
            async with semaphore:
                # Progress update
                await queue.put(f"data: {_json.dumps({'type':'progress','symbol':stock['symbol'],'name':stock['name'],'index':index+1,'total':total})}\n\n")
                try:
                    res = await asyncio.to_thread(_analyze_single_stock, stock, threshold)
                    if not res:
                        return
                    if res.get("type") == "skip":
                        await queue.put(f"data: {_json.dumps(res)}\n\n")
                        return

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
            if '"type": "result"' in item:
                signals_count += 1
                try:
                    sig_data = _json.loads(item.split("data: ", 1)[1].strip())
                    collected_signals.append(sig_data)
                except Exception:
                    pass
                if '"BUY"' in item or '"SELL"' in item:
                    qualified_count += 1
            yield item

        # Send Telegram Alert with all collected signals
        try:
            telegram_alerts.alert_scan_signals(collected_signals)
        except Exception as e:
            logger.warning("Telegram stream scan alert failed: %s", e)

        yield f"data: {_json.dumps({'type':'done','analyzed':total,'signals_count':signals_count,'qualified':qualified_count,'timestamp':datetime.utcnow().isoformat()})}\n\n"

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
    company_name: str
    action:       str          # BUY or SELL
    entry_price:  float
    quantity:     int
    stop_loss:    float
    target1:      float
    target2:      float
    signal_id:    Optional[int] = None

@app.post("/api/paper/buy-sell")
async def paper_order(req: PaperOrderRequest, db: Session = Depends(get_db)):
    result = paper_trading.place_paper_order(
        db=db, symbol=req.symbol, company_name=req.company_name,
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
async def close_paper(req: ClosePositionRequest, db: Session = Depends(get_db)):
    result = paper_trading.close_paper_position(db, req.symbol, req.exit_price, req.exit_reason)
    return result

@app.get("/api/paper/portfolio")
async def get_portfolio(db: Session = Depends(get_db)):
    return paper_trading.get_paper_portfolio_summary(db)

@app.post("/api/paper/reset")
async def reset_paper(db: Session = Depends(get_db)):
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
async def manual_paper_order(req: ManualOrderRequest, db: Session = Depends(get_db)):
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


# ─────────────────────────── API: JOURNAL / ANALYTICS ────────────────────────────

@app.get("/api/journal/weekly")
async def weekly_summary(db: Session = Depends(get_db)):
    from backend.database import get_weekly_summary
    return get_weekly_summary(db)

@app.get("/api/journal/monthly")
async def monthly_summary(db: Session = Depends(get_db)):
    from backend.database import get_monthly_summary
    return get_monthly_summary(db)

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
async def get_paper_trades(limit: int = 100, db: Session = Depends(get_db)):
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

# ─────────────────────────── ENTRY POINT ────────────────────────────

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host=host, port=port, reload=True)
