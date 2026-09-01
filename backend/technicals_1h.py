"""
1-Hour + 15-Minute Multi-Timeframe Technical Indicator Engine
Computes: VWAP, RSI 14, EMA 9/21, ATR, RVOL, Swing Highs/Lows, Stop Loss
Upgrade 2: Multi-Timeframe Dual Lock (15M + 1H Confluence)
"""

import logging
import time
import yfinance as yf
import pandas as pd
import ta as ta_lib
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory lightweight caches for fast scans (bounded size to prevent RAM growth)
_tech_1h_cache: dict[str, tuple[float, dict]] = {}
_tech_15m_cache: dict[str, tuple[float, dict]] = {}
_data_5y_cache: dict[str, tuple[float, Optional[float], Optional[float], list[dict]]] = {}

TECH_CACHE_TTL = 15    # 15 seconds live cache for real-time tick accuracy
DATA5Y_CACHE_TTL = 3600 # 1 hour for 5Y historical daily candles


# ─────────────────────────── DATA FETCHING ────────────────────────────

def fetch_1h_data(symbol: str, period: str = "5d") -> Optional[pd.DataFrame]:
    """Fetch 1-Hour OHLCV candle data for the given NSE symbol."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval="1h")
        if df.empty or len(df) < 10:
            logger.warning("Insufficient 1H data for %s", symbol)
            return None
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        logger.error("Failed to fetch 1H data for %s: %s", symbol, e)
        return None


def fetch_15m_data(symbol: str, period: str = "2d") -> Optional[pd.DataFrame]:
    """Fetch 15-Minute OHLCV candle data for the given NSE symbol (Upgrade 2: Multi-Timeframe)."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval="15m")
        if df.empty or len(df) < 8:
            return None
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        logger.error("Failed to fetch 15M data for %s: %s", symbol, e)
        return None


def analyze_15m(symbol: str) -> Optional[dict]:
    """
    Upgrade 2: 15-Minute timeframe analysis for precise entry timing.
    Returns: {trend_15m, rsi_15m, price_vs_vwap_15m, rvol_15m, is_bullish_15m, is_bearish_15m}
    """
    now = time.time()
    if symbol in _tech_15m_cache:
        ts, cached = _tech_15m_cache[symbol]
        if now - ts < TECH_CACHE_TTL:
            return cached

    df15 = fetch_15m_data(symbol)
    if df15 is None:
        return None

    try:
        vwap15  = compute_vwap(df15)
        rsi15   = compute_rsi(df15)
        ema9_15  = compute_ema(df15, 9)
        ema21_15 = compute_ema(df15, 21)
        rvol15  = compute_rvol(df15)

        last_price15 = round(float(df15["Close"].iloc[-1]), 2)
        last_vwap15  = round(float(vwap15.iloc[-1]), 2)
        last_rsi15   = round(float(rsi15.iloc[-1]) if rsi15 is not None and not pd.isna(rsi15.iloc[-1]) else 50.0, 2)
        last_ema9_15  = round(float(ema9_15.iloc[-1]), 2)
        last_ema21_15 = round(float(ema21_15.iloc[-1]), 2)

        if last_ema9_15 > last_ema21_15 and last_price15 > last_vwap15:
            trend_15m = "BULLISH"
        elif last_ema9_15 < last_ema21_15 and last_price15 < last_vwap15:
            trend_15m = "BEARISH"
        else:
            trend_15m = "SIDEWAYS"

        is_bullish_15m = (
            trend_15m == "BULLISH" and
            last_price15 > last_vwap15 and
            40 <= last_rsi15 <= 75
        )
        is_bearish_15m = (
            trend_15m == "BEARISH" and
            last_price15 < last_vwap15 and
            25 <= last_rsi15 <= 60
        )

        result = {
            "trend_15m":          trend_15m,
            "rsi_15m":            last_rsi15,
            "vwap_15m":           last_vwap15,
            "price_vs_vwap_15m":  "ABOVE" if last_price15 > last_vwap15 else "BELOW",
            "rvol_15m":           rvol15,
            "is_bullish_15m":     is_bullish_15m,
            "is_bearish_15m":     is_bearish_15m,
        }
        if len(_tech_15m_cache) > 80:
            _tech_15m_cache.clear()
        _tech_15m_cache[symbol] = (now, result)
        del df15, vwap15, rsi15, ema9_15, ema21_15
        return result
    except Exception as e:
        logger.error("15M analysis failed for %s: %s", symbol, e)
        return None


def fetch_5y_lightweight_summary(symbol: str) -> tuple[Optional[float], Optional[float], list[dict]]:
    """Fetch and downsample 5-Year daily data into lightweight JSON (<2KB), avoiding heavy DataFrame RAM retention."""
    now = time.time()
    if symbol in _data_5y_cache:
        ts, high52, low52, data = _data_5y_cache[symbol]
        if now - ts < DATA5Y_CACHE_TTL:
            return high52, low52, data

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="5y", interval="1d")
        if df is None or df.empty:
            if len(_data_5y_cache) > 80:
                _data_5y_cache.clear()
            _data_5y_cache[symbol] = (now, None, None, [])
            return None, None, []

        df.index = pd.to_datetime(df.index)
        one_year_cutoff = df.index.max() - pd.Timedelta(days=365)
        one_year_df     = df[df.index >= one_year_cutoff]
        week52_high = round(float(one_year_df["High"].max()), 2) if not one_year_df.empty else None
        week52_low  = round(float(one_year_df["Low"].min()), 2) if not one_year_df.empty else None

        # Sample to monthly points only (max ~60 points = ~2KB)
        df_monthly     = df.resample("ME").agg({"Close": "last", "High": "max", "Low": "min", "Volume": "sum"}).dropna()
        five_year_data = [
            {"date": str(idx.date()), "close": round(float(row["Close"]), 2),
             "high": round(float(row["High"]), 2), "low": round(float(row["Low"]), 2),
             "volume": int(row["Volume"])}
            for idx, row in df_monthly.iterrows()
        ]

        if len(_data_5y_cache) > 80:
            _data_5y_cache.clear()
        _data_5y_cache[symbol] = (now, week52_high, week52_low, five_year_data)
        del df, one_year_df, df_monthly
        return week52_high, week52_low, five_year_data
    except Exception as e:
        logger.error("Failed to fetch 5Y lightweight data for %s: %s", symbol, e)
        return None, None, []


# ─────────────────────────── INDICATORS ────────────────────────────

def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Volume Weighted Average Price."""
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    vwap = (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()
    return vwap


def compute_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return ta_lib.momentum.RSIIndicator(df["Close"], window=period).rsi()


def compute_ema(df: pd.DataFrame, span: int) -> pd.Series:
    return df["Close"].ewm(span=span, adjust=False).mean()


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return ta_lib.volatility.AverageTrueRange(df["High"], df["Low"], df["Close"], window=period).average_true_range()


def compute_rvol(df: pd.DataFrame, window: int = 20) -> float:
    """Relative Volume vs 20-period avg volume."""
    if len(df) < window + 1:
        return 1.0
    avg_vol = df["Volume"].iloc[-(window + 1):-1].mean()
    last_vol = df["Volume"].iloc[-1]
    if avg_vol == 0:
        return 1.0
    return round(last_vol / avg_vol, 2)


def find_swing_lows(df: pd.DataFrame, window: int = 5) -> pd.Series:
    """Detect swing lows over a rolling window for Stop Loss placement."""
    return df["Low"].rolling(window=window).min()


def find_swing_highs(df: pd.DataFrame, window: int = 5) -> pd.Series:
    """Detect swing highs over a rolling window for short Stop Loss placement."""
    return df["High"].rolling(window=window).max()


# ─────────────────────────── MAIN TECHNICAL ANALYSIS ────────────────────────────

def analyze_1h(symbol: str) -> Optional[dict]:
    """
    Full 1-Hour technical analysis for a symbol with 3-minute in-memory caching.
    Returns a structured dict with all technical indicators and trade levels.
    """
    now = time.time()
    if symbol in _tech_1h_cache:
        ts, cached_dict = _tech_1h_cache[symbol]
        if now - ts < TECH_CACHE_TTL:
            return cached_dict

    df = fetch_1h_data(symbol)
    if df is None:
        _tech_1h_cache[symbol] = (now, None)
        return None

    # Compute indicators
    vwap     = compute_vwap(df)
    rsi      = compute_rsi(df)
    ema9     = compute_ema(df, 9)
    ema21    = compute_ema(df, 21)
    atr      = compute_atr(df)
    rvol     = compute_rvol(df)
    sw_lows  = find_swing_lows(df)
    sw_highs = find_swing_highs(df)

    # Fetch 100% Live Real-Time Tick Price from fast_info
    ticker_obj = yf.Ticker(symbol)
    fast_info = getattr(ticker_obj, "fast_info", None)
    if fast_info and getattr(fast_info, "last_price", None) and float(fast_info.last_price) > 0:
        current_price = round(float(fast_info.last_price), 2)
    else:
        current_price = round(float(df["Close"].iloc[-1]), 2)
    last_vwap    = round(float(vwap.iloc[-1]), 2)
    last_rsi     = round(float(rsi.iloc[-1]) if rsi is not None and not pd.isna(rsi.iloc[-1]) else 50.0, 2)
    last_ema9    = round(float(ema9.iloc[-1]), 2)
    last_ema21   = round(float(ema21.iloc[-1]), 2)
    last_atr     = round(float(atr.iloc[-1]) if atr is not None and not pd.isna(atr.iloc[-1]) else 0.0, 2)
    swing_low    = round(float(sw_lows.iloc[-1]), 2)
    swing_high   = round(float(sw_highs.iloc[-1]), 2)

    # 1-Hour Trend Direction
    if last_ema9 > last_ema21 and current_price > last_vwap:
        trend_1h = "BULLISH"
    elif last_ema9 < last_ema21 and current_price < last_vwap:
        trend_1h = "BEARISH"
    else:
        trend_1h = "SIDEWAYS"

    # RSI Zone
    rsi_zone = "OVERSOLD" if last_rsi < 35 else ("OVERBOUGHT" if last_rsi > 65 else "NEUTRAL")

    # Price vs VWAP
    price_vs_vwap = "ABOVE" if current_price > last_vwap else "BELOW"

    # Stop Loss calculation (ATR-based + Structural)
    calc_sl_buy = current_price - (1.5 * last_atr if last_atr > 0 else current_price * 0.01)
    if swing_low < current_price:
        sl_buy = round(min(swing_low, calc_sl_buy), 2)
    else:
        sl_buy = round(calc_sl_buy, 2)

    calc_sl_sell = current_price + (1.5 * last_atr if last_atr > 0 else current_price * 0.01)
    if swing_high > current_price:
        sl_sell = round(max(swing_high, calc_sl_sell), 2)
    else:
        sl_sell = round(calc_sl_sell, 2)

    # Target 1 & 2 (1:1.8 & 1:3.0 R:R guarantee)
    buy_risk  = max(current_price * 0.005, current_price - sl_buy)
    sell_risk = max(current_price * 0.005, sl_sell - current_price)

    target1_buy  = round(current_price + buy_risk  * 1.8, 2)
    target2_buy  = round(current_price + buy_risk  * 3.0, 2)
    target1_sell = round(current_price - sell_risk * 1.8, 2)
    target2_sell = round(current_price - sell_risk * 3.0, 2)

    # 52-week High/Low and 5Y lightweight sampled points
    week52_high, week52_low, five_year_data = fetch_5y_lightweight_summary(symbol)

    # Check Open = High (Institutional Selling Trap Flag)
    day_open = float(df["Open"].iloc[0]) if "Open" in df else current_price
    day_high = float(df["High"].max()) if "High" in df else current_price
    is_open_high = (day_high - day_open) <= (day_open * 0.0015) if day_open > 0 else False

    result = {
        "symbol":          symbol,
        "current_price":   current_price,
        "trend_1h":        trend_1h,
        "rsi":             last_rsi,
        "rsi_zone":        rsi_zone,
        "ema9":            last_ema9,
        "ema21":           last_ema21,
        "vwap":            last_vwap,
        "price_vs_vwap":   price_vs_vwap,
        "atr":             last_atr,
        "rvol":            rvol,
        "is_open_high":    is_open_high,
        "swing_low":       swing_low,
        "swing_high":      swing_high,
        "sl_buy":          sl_buy,
        "sl_sell":         sl_sell,
        "target1_buy":     target1_buy,
        "target2_buy":     target2_buy,
        "target1_sell":    target1_sell,
        "target2_sell":    target2_sell,
        "week52_high":     week52_high,
        "week52_low":      week52_low,
        "five_year_data":  five_year_data,
    }
    if len(_tech_1h_cache) > 80:
        _tech_1h_cache.clear()
    _tech_1h_cache[symbol] = (now, result)
    del df, vwap, rsi, ema9, ema21, atr
    return result
