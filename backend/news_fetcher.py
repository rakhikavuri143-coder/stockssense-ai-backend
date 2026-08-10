"""
Real-Time Indian Market News Fetcher
Sources: Economic Times, Moneycontrol, Google News India, Yahoo Finance
"""

import feedparser
import httpx
import logging
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────── RSS FEED URLS ────────────────────────────

NEWS_FEEDS = {
    "Economic Times Markets":  "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "Economic Times Stocks":   "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "Moneycontrol Markets":    "https://www.moneycontrol.com/rss/marketsindia.xml",
    "Moneycontrol Business":   "https://www.moneycontrol.com/rss/business.xml",
    "Livemint Markets":        "https://www.livemint.com/rss/markets",
}

GOOGLE_NEWS_TEMPLATE = (
    "https://news.google.com/rss/search?q={query}+stock+NSE&hl=en-IN&gl=IN&ceid=IN:en"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# 15-minute in-memory cache for stock news
_news_cache: dict[str, tuple[float, list[dict]]] = {}
CACHE_TTL = 900  # 15 minutes


# ─────────────────────────── HELPERS ────────────────────────────

def _parse_feed(url: str, max_items: int = 10, timeout: float = 2.0) -> list[dict]:
    """Parse an RSS feed using httpx with strict timeout."""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=HEADERS) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return []
            raw_xml = resp.text
        feed = feedparser.parse(raw_xml)
        results = []
        for entry in feed.entries[:max_items]:
            results.append({
                "title":     entry.get("title", ""),
                "summary":   entry.get("summary", entry.get("description", "")),
                "link":      entry.get("link", ""),
                "published": entry.get("published", str(datetime.utcnow())),
                "source":    feed.feed.get("title", "Google News"),
            })
        return results
    except Exception as e:
        logger.warning("Feed parse error %s: %s", url, e)
        return []


def fetch_general_market_news(max_per_feed: int = 5) -> list[dict]:
    """Fetch top Indian market news from all general feeds."""
    all_news = []
    for name, url in NEWS_FEEDS.items():
        items = _parse_feed(url, max_per_feed)
        for item in items:
            item["feed_name"] = name
        all_news.extend(items)
    return all_news


def fetch_stock_news(symbol: str, company_name: str, max_items: int = 6) -> list[dict]:
    """Fetch specific news for a stock using Google News RSS with 15-min cache."""
    now = time.time()
    cache_key = f"{symbol}_{company_name}"
    if cache_key in _news_cache:
        timestamp, cached_news = _news_cache[cache_key]
        if now - timestamp < CACHE_TTL:
            return cached_news

    clean_symbol = symbol.replace(".NS", "").replace(".BO", "")
    query_name   = company_name.replace(" ", "+")
    url          = GOOGLE_NEWS_TEMPLATE.format(query=f"{query_name}+{clean_symbol}")

    results = []
    seen_titles = set()
    for item in _parse_feed(url, max_items, timeout=2.0):
        if item["title"] not in seen_titles:
            seen_titles.add(item["title"])
            item["stock_symbol"] = symbol
            results.append(item)

    news_list = results[:max_items]
    _news_cache[cache_key] = (now, news_list)
    return news_list


def fetch_nifty_macro_news(max_items: int = 5) -> list[dict]:
    """Fetch macro news affecting Nifty/RBI/SEBI/Budget."""
    url = GOOGLE_NEWS_TEMPLATE.format(query="Nifty+50+RBI+SEBI+India+market")
    results = []
    seen = set()
    for item in _parse_feed(url, max_items, timeout=2.0):
        if item["title"] not in seen:
            seen.add(item["title"])
            results.append(item)
    return results[:max_items]


def get_news_for_stocks(stocks: list[dict]) -> dict[str, list[dict]]:
    """
    For a list of stock dicts with 'symbol' and 'name',
    returns {symbol: [news_items]} mapping.
    """
    news_map = {}
    for stock in stocks:
        symbol = stock["symbol"]
        name   = stock["name"]
        news   = fetch_stock_news(symbol, name)
        news_map[symbol] = news
    return news_map

