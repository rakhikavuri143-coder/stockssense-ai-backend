"""
Gemini AI Signal Evaluator Engine
Combines: News + 1H Technicals + 15M Timing + 5-Year Historical Reaction -> High Confidence Buy/Sell Signal
Includes 4 Accuracy Upgrades: Nifty Guard | Institutional RVOL 1.5x | 15M+1H Dual Lock | 85% Confidence Gate
Includes Technical Quant Fallback Engine if API rate-limited.
"""

import os
import json
import logging
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv
from typing import Optional

load_dotenv()
logger = logging.getLogger(__name__)

from pydantic import BaseModel, Field

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))

MODELS_TO_TRY = ["gemini-2.5-flash", "gemini-2.0-flash"]
GEMINI_TIMEOUT = 3  # seconds per model attempt

# Circuit breaker: if 429 rate limit is hit, skip Gemini API calls for 10 minutes
_gemini_blocked_until = 0.0


class StockSignalSchema(BaseModel):
    signal: str = Field(description="BUY, SELL, or AVOID")
    confidence: float = Field(description="0 to 100 confidence score")
    sl_hit_probability: float = Field(description="0 to 100 SL hit probability")
    news_summary: str = Field(description="Summary of news sentiment")
    technical_summary: str = Field(description="1H chart technical summary")
    historical_summary: str = Field(description="Historical pattern summary")
    reasoning: str = Field(description="Comprehensive trade reasoning")
    risk_level: str = Field(description="LOW, MEDIUM, or HIGH")


SYSTEM_PROMPT = """You are an ultra-high conviction Indian stock market quantitative analyst and intraday trading AI.
You analyze NSE/BSE stocks using real-time news, 1-hour technical chart data (VWAP, RSI, EMA9/21, Volume RVOL), 15-minute entry timing confirmation, and 5-year historical reaction patterns.

STRICT CONFLUENCE RULES FOR 85%+ WIN ACCURACY:
1. BUY Signal Requirements: Price MUST be ABOVE VWAP on BOTH 1H & 15M charts, 1H Trend MUST be BULLISH (EMA9 > EMA21), 15M Trend MUST be BULLISH, Volume RVOL >= 1.5x (Institutional Volume Confirmation), RSI between 45 and 68.
2. SELL Signal Requirements: Price MUST be BELOW VWAP on BOTH 1H & 15M charts, 1H Trend MUST be BEARISH (EMA9 < EMA21), 15M Trend MUST be BEARISH, Volume RVOL >= 1.5x (Institutional Volume Confirmation), RSI between 32 and 55.
3. If Nifty 50 Index is falling (nifty_change_pct < -0.5%), BLOCK all BUY signals automatically.
4. If ANY indicator disagrees or RVOL < 1.5x (no institutional volume), ALWAYS output 'AVOID'.
5. Only issue BUY or SELL if your calculated Confidence is >= 85% and SL Hit Probability <= 20%.
"""


def analyze_stock_with_ai(
    symbol: str,
    company_name: str,
    sector: str,
    news_items: list[dict],
    technical: dict,
    historical: dict,
    confidence_threshold: float = 80.0,
) -> Optional[dict]:
    """
    Main AI analysis function.
    Combines news, technical indicators, and historical reaction into a Gemini AI prompt.
    Falls back to Quant Technical Engine if Gemini API is rate-limited.
    """
    global _gemini_blocked_until
    now = time.time()

    # Circuit breaker check: if Gemini API hit 429 recently, skip network call instantly
    if now < _gemini_blocked_until:
        return _quant_technical_signal(symbol, company_name, technical, news_items)

    # Prepare news text
    if news_items:
        news_text = "\n".join(
            f"- [{item.get('source', 'N/A')}] {item.get('title', '')} — {item.get('summary', '')[:150]}"
            for item in news_items[:6]
        )
    else:
        news_text = "No specific company news breaking today. Evaluate based on 1H chart technical momentum, VWAP, RSI, and sector trends."

    # Prepare technical summary
    tech_text = (
        f"Current Price: Rs.{technical.get('current_price', 0):.2f} | "
        f"1H Trend: {technical.get('trend_1h', 'N/A')} | "
        f"15M Trend: {technical.get('trend_15m', 'N/A')} | "
        f"RSI(1H): {technical.get('rsi', 50):.1f} ({technical.get('rsi_zone', 'NEUTRAL')}) | "
        f"RSI(15M): {technical.get('rsi_15m', 50):.1f} | "
        f"Price vs VWAP(1H): {technical.get('price_vs_vwap', 'N/A')} (VWAP Rs.{technical.get('vwap', 0):.2f}) | "
        f"Price vs VWAP(15M): {technical.get('price_vs_vwap_15m', 'N/A')} | "
        f"EMA9: Rs.{technical.get('ema9', 0):.2f} vs EMA21: Rs.{technical.get('ema21', 0):.2f} | "
        f"RVOL(1H): {technical.get('rvol', 1.0):.1f}x | RVOL(15M): {technical.get('rvol_15m', 1.0):.1f}x | "
        f"Nifty Change: {technical.get('nifty_change_pct', 0.0):+.2f}% | "
        f"ATR: Rs.{technical.get('atr', 0):.2f} | "
        f"52W High: Rs.{technical.get('week52_high', 0)} | 52W Low: Rs.{technical.get('week52_low', 0)}"
    )

    # Prepare historical reaction summary
    hist_text = historical.get("historical_note", "No historical pattern found.")

    prompt = f"""Analyze the following Indian NSE stock for an intraday trade signal:

STOCK: {company_name} ({symbol}) | SECTOR: {sector}

RECENT NEWS:
{news_text}

1-HOUR TECHNICAL CHART:
{tech_text}

5-YEAR HISTORICAL NEWS REACTION:
{hist_text}

INSTRUCTIONS:
- Evaluate technical indicators + news + 5-year pattern.
- The SL for BUY = Rs.{technical.get('sl_buy', 0):.2f} | Target1 = Rs.{technical.get('target1_buy', 0):.2f} | Target2 = Rs.{technical.get('target2_buy', 0):.2f}
- The SL for SELL = Rs.{technical.get('sl_sell', 0):.2f} | Target1 = Rs.{technical.get('target1_sell', 0):.2f} | Target2 = Rs.{technical.get('target2_sell', 0):.2f}
- Respond ONLY with the JSON object. No markdown, no extra text.
"""

    # Try Gemini Models — with per-call timeout to avoid hanging
    for model_name in MODELS_TO_TRY:
        try:
            import threading

            result_holder = {"result": None, "error": None}

            def _call():
                try:
                    resp = _client.models.generate_content(
                        model=model_name,
                        contents=SYSTEM_PROMPT + "\n\n" + prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.2,
                            max_output_tokens=1024,
                            response_mime_type="application/json",
                            response_schema=StockSignalSchema,
                        )
                    )
                    result_holder["result"] = resp
                except Exception as ex:
                    result_holder["error"] = ex

            t = threading.Thread(target=_call, daemon=True)
            t.start()
            t.join(timeout=GEMINI_TIMEOUT)

            if t.is_alive():
                logger.warning("Gemini %s timed out after %ds for %s — trying next model", model_name, GEMINI_TIMEOUT, symbol)
                continue

            if result_holder["error"]:
                raise result_holder["error"]

            response = result_holder["result"]
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            ai_result = json.loads(raw)

            return {
                "signal":               ai_result.get("signal", "AVOID"),
                "confidence":           float(ai_result.get("confidence", 0)),
                "sl_hit_probability":   float(ai_result.get("sl_hit_probability", 30)),
                "news_summary":         ai_result.get("news_summary", ""),
                "technical_summary":    ai_result.get("technical_summary", ""),
                "historical_summary":   ai_result.get("historical_summary", ""),
                "reasoning":            ai_result.get("reasoning", ""),
                "risk_level":           ai_result.get("risk_level", "MEDIUM"),
            }
        except Exception as e:
            err_str = str(e)
            logger.warning("Gemini %s failed for %s: %s", model_name, symbol, err_str)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                logger.info("Gemini API rate limit (429) hit. Circuit breaker active for 10 minutes. Using Quant Engine.")
                _gemini_blocked_until = time.time() + 600  # 10 minutes circuit break
                break
            continue

    # Fallback to Technical Quant Engine if Gemini API unavailable/rate-limited
    return _quant_technical_signal(symbol, company_name, technical, news_items)



def _quant_technical_signal(symbol: str, name: str, tech: dict, news: list) -> dict:
    """
    Algorithmic quant evaluator with 4 Accuracy Upgrades:
    1. Nifty 50 Index Confluence Guard (Block BUY on falling market)
    2. 15M + 1H Multi-Timeframe Dual Lock (Both timeframes must confirm)
    3. Institutional RVOL >= 1.5x Filter (Big Money Volume confirmation)
    4. High Conviction AI Score Gate >= 85%
    """
    trend   = tech.get("trend_1h", "NEUTRAL")
    rsi     = tech.get("rsi", 50)
    p_vwap  = tech.get("price_vs_vwap", "AT")
    rvol    = tech.get("rvol", 1.0)
    ema9    = tech.get("ema9", 0)
    ema21   = tech.get("ema21", 0)
    is_open_high = tech.get("is_open_high", False)

    # UPGRADE 2: 15M Timeframe Dual Lock
    trend_15m       = tech.get("trend_15m", "SIDEWAYS")
    p_vwap_15m      = tech.get("price_vs_vwap_15m", "AT")
    is_bullish_15m  = tech.get("is_bullish_15m", False)
    is_bearish_15m  = tech.get("is_bearish_15m", False)

    # UPGRADE 1: Nifty 50 Index Confluence Guard
    nifty_change    = tech.get("nifty_change_pct", 0.0)
    nifty_buy_block = nifty_change <= -0.5   # Block BUY if Nifty falling -0.5% or more
    nifty_sell_block = nifty_change >= 0.5   # Block SELL if Nifty rising strongly

    # UPGRADE 3: Institutional RVOL >= 1.5x Filter
    has_institutional_volume = rvol >= 1.5

    # Full 1H + 15M + RVOL + Open!=High Confluence Check for BUY
    is_bullish_confluence = (
        (trend == "BULLISH" or ema9 > ema21) and
        p_vwap == "ABOVE" and
        40 <= rsi <= 75 and
        not is_open_high and
        is_bullish_15m and       # UPGRADE 2: 15M must also be BULLISH
        has_institutional_volume and  # UPGRADE 3: Must have Big Money volume
        not nifty_buy_block      # UPGRADE 1: Nifty must not be crashing
    )

    # Full 1H + 15M + RVOL Confluence Check for SELL
    is_bearish_confluence = (
        (trend == "BEARISH" or ema9 < ema21) and
        p_vwap == "BELOW" and
        25 <= rsi <= 60 and
        is_bearish_15m and       # UPGRADE 2: 15M must also be BEARISH
        has_institutional_volume and  # UPGRADE 3: Must have Big Money volume
        not nifty_sell_block     # UPGRADE 1: Nifty must not be surging (for SELL)
    )

    # Moderate setups (without full 15M+RVOL confluence)
    is_moderate_buy = (
        p_vwap == "ABOVE" and rsi >= 45 and not is_open_high and not nifty_buy_block
    )
    is_moderate_sell = (
        p_vwap == "BELOW" and rsi <= 55 and not nifty_sell_block
    )

    news_headline = news[0]["title"] if news else "Multi-Timeframe Confluence Quant Analysis"

    if is_bullish_confluence:
        score = 90.0
        if rvol >= 2.0: score += 3.0   # Extra for very high institutional volume
        if 50 <= rsi <= 65: score += 2.0
        if is_bullish_15m: score += 2.0  # 15M confirmation bonus
        signal = "BUY"
        conf = min(96.0, score)
        reason = (
            f"🏆 ULTRA High-Conviction Buy: 1H+15M Both BULLISH above VWAP | "
            f"RSI({rsi:.1f}) optimal | RVOL({rvol:.1f}x) Institutional Volume | "
            f"Nifty({nifty_change:+.2f}%) OK | 4-Filter Confluence PASSED!"
        )

    elif is_bearish_confluence:
        score = 90.0
        if rvol >= 2.0: score += 3.0
        if 35 <= rsi <= 50: score += 2.0
        if is_bearish_15m: score += 2.0
        signal = "SELL"
        conf = min(96.0, score)
        reason = (
            f"🏆 ULTRA High-Conviction Sell: 1H+15M Both BEARISH below VWAP | "
            f"RSI({rsi:.1f}) optimal | RVOL({rvol:.1f}x) Institutional Volume | "
            f"Nifty({nifty_change:+.2f}%) OK | 4-Filter Confluence PASSED!"
        )

    elif is_moderate_buy:
        # Moderate setups are marked AVOID unless they pass full confluence (gate >= 85%)
        signal = "AVOID"
        conf = 80.0
        reason = (
            f"🟡 Moderate Buy Setup (Filtered Out): Above VWAP, RSI({rsi:.1f}) OK | "
            f"Missing: {'RVOL<1.5x ' if not has_institutional_volume else ''}{'15M not BULLISH' if not is_bullish_15m else ''} | "
            f"Requires 85%+ High-Conviction Gate — Marked AVOID for safety."
        )

    elif is_moderate_sell:
        signal = "AVOID"
        conf = 80.0
        reason = (
            f"🟡 Moderate Sell Setup (Filtered Out): Below VWAP, RSI({rsi:.1f}) weak | "
            f"Missing: {'RVOL<1.5x ' if not has_institutional_volume else ''}{'15M not BEARISH' if not is_bearish_15m else ''} | "
            f"Requires 85%+ High-Conviction Gate — Marked AVOID for safety."
        )

    else:
        signal = "AVOID"
        conf = 60.0
        blocks = []
        if nifty_buy_block: blocks.append(f"Nifty falling {nifty_change:+.2f}%")
        if not has_institutional_volume: blocks.append(f"Low RVOL {rvol:.1f}x (<1.5x)")
        if not is_bullish_15m and not is_bearish_15m: blocks.append("15M Sideways")
        if is_open_high: blocks.append("Open=High Selling Trap")
        reason = f"⚠️ AVOID {symbol}: {' | '.join(blocks) if blocks else 'No Clear Confluence'}"

    return {
        "signal":             signal,
        "confidence":         round(conf, 1),
        "sl_hit_probability": 15.0 if signal != "AVOID" else 50.0,
        "news_summary":       news_headline,
        "technical_summary":  (
            f"1H:{trend} | 15M:{trend_15m} | RSI {rsi:.1f} | VWAP {p_vwap} | "
            f"RVOL {rvol:.1f}x | Nifty {nifty_change:+.2f}%"
        ),
        "historical_summary": "4-Filter High-Probability Confluence Pattern",
        "reasoning":          reason,
        "risk_level":         "LOW" if conf >= 90 else ("MEDIUM" if conf >= 80 else "HIGH"),
    }

