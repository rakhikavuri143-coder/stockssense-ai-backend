"""
backend/broker_angelone.py
StocksSense AI — Angel One SmartAPI Connector
Handles authentication via TOTP, order placement, and position fetching.
"""

import os
import logging
import httpx
import pyotp
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

ANGELONE_URL = "https://apiconnect.angelbroking.com"

_SERVER_PUBLIC_IP = None

def get_proxy_url() -> Optional[str]:
    """Get outbound proxy URL if configured (e.g. Fixie, QuotaGuard, or generic HTTP/HTTPS proxy)."""
    return (
        os.getenv("FIXIE_URL")
        or os.getenv("QUOTAGUARDSTATIC_URL")
        or os.getenv("SMARTAPI_PROXY_URL")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("HTTP_PROXY")
    )


def get_httpx_client(timeout: float = 10.0) -> httpx.Client:
    """Return an httpx.Client with optional static IP proxy configured."""
    proxy = get_proxy_url()
    if proxy:
        logger.info("🌐 Using Outbound Proxy for Angel One: %s", proxy.split("@")[-1] if "@" in proxy else proxy)
        return httpx.Client(proxy=proxy, timeout=timeout)
    return httpx.Client(timeout=timeout)


def get_server_public_ip() -> str:
    """Dynamically resolve outbound server IP for Angel One headers."""
    global _SERVER_PUBLIC_IP
    if _SERVER_PUBLIC_IP:
        return _SERVER_PUBLIC_IP
    
    env_ip = os.getenv("ANGELONE_CLIENT_PUBLIC_IP")
    if env_ip:
        _SERVER_PUBLIC_IP = env_ip.strip()
        return _SERVER_PUBLIC_IP

    _SERVER_PUBLIC_IP = "216.24.57.252"
    return _SERVER_PUBLIC_IP


def generate_totp(totp_secret: str) -> str:
    """Generate dynamic 6-digit TOTP code using the secret key."""
    try:
        import re
        # Strip spaces and sanitize common base32 typos (0 -> O, 1 -> I, 8 -> B)
        clean_secret = totp_secret.strip().replace(" ", "").upper()
        clean_secret = clean_secret.replace("0", "O").replace("1", "I").replace("8", "B")
        clean_secret = re.sub(r'[^A-Z2-7]', '', clean_secret)
        if len(clean_secret) % 8 != 0:
            clean_secret = clean_secret + '=' * (-len(clean_secret) % 8)
        totp = pyotp.TOTP(clean_secret)
        return totp.now()
    except Exception as e:
        logger.error("Failed to generate TOTP: %s", e)
        raise e


def login_smartapi(client_code: str, password: str, api_key: str, totp_secret: str) -> tuple[Optional[Dict], str]:
    """
    Log in to Angel One SmartAPI using client_code, password, and TOTP secret.
    Returns (auth_tokens_dict, error_message).
    """
    try:
        totp_code = generate_totp(totp_secret)
    except Exception as te:
        return None, f"Invalid TOTP Secret Key format: {te}"
    
    endpoints = [
        f"{ANGELONE_URL}/rest/auth/angelbroking/user/v1/loginByPassword",
        f"{ANGELONE_URL}/publisher-apis/api/v1/user/login/v3"
    ]
    
    payload = {
        "clientcode": client_code.upper().strip(),
        "password": password.strip(),
        "totp": totp_code
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-PrivateKey": api_key.strip(),
        "Accept": "application/json",
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": get_server_public_ip(),
        "X-MACaddress": "fe-80-00-00-00-00",
        "MACAddress": "fe-80-00-00-00-00"
    }

    last_err = "Unknown error"
    with get_httpx_client(timeout=10.0) as client:
        for url in endpoints:
            try:
                response = client.post(url, json=payload, headers=headers)
                data = _safe_json(response)
                
                if data.get("status") is True and "data" in data:
                    tokens = data["data"]
                    logger.info("✅ Angel One SmartAPI login successful for client %s via %s", client_code, url)
                    session = {
                        "jwtToken": tokens.get("jwtToken") or tokens.get("token"),
                        "refreshToken": tokens.get("refreshToken", ""),
                        "feedToken": tokens.get("feedToken", ""),
                        "client_code": client_code,
                        "api_key": api_key
                    }
                    return session, ""
                else:
                    msg = data.get("message") or f"Auth Failed (HTTP {response.status_code})"
                    errcode = data.get("errorcode") or data.get("errorCode") or ""
                    last_err = f"{msg} (Code: {errcode})" if errcode else msg
                    logger.warning("⚠️ Angel One login failed on endpoint %s: %s", url, last_err)
            except Exception as e:
                last_err = str(e)
                logger.error("Exception during Angel One login on %s: %s", url, e)

    logger.error("❌ All Angel One SmartAPI login endpoints failed. Last error: %s", last_err)
    return None, last_err


def place_smartapi_order(
    auth_data: Dict,
    symbol: str,
    symbol_token: str,
    transaction_type: str,  # BUY or SELL
    quantity: int,
    price: float,
    order_type: str = "LIMIT",  # LIMIT or MARKET
    exchange: str = "NSE",      # NSE or BSE
    product_type: str = "INTRADAY"  # INTRADAY, DELIVERY, CARRYFORWARD
) -> Dict:
    """
    Place an order in Angel One using SmartAPI.
    """
    url = f"{ANGELONE_URL}/rest/secure/angelbroking/order/v1/placeOrder"
    
    payload = {
        "variety": "NORMAL",
        "tradingsymbol": symbol,
        "symboltoken": symbol_token,
        "transactiontype": transaction_type.upper(),
        "exchange": exchange.upper(),
        "ordertype": order_type.upper(),
        "producttype": product_type.upper(),
        "duration": "DAY",
        "price": str(round(price, 2)) if order_type.upper() == "LIMIT" else "0",
        "quantity": str(quantity),
        "squareoff": "0.00",
        "stoploss": "0.00"
    }

    headers = {
        "Authorization": f"Bearer {auth_data['jwtToken']}",
        "Content-Type": "application/json",
        "X-PrivateKey": auth_data["api_key"],
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": get_server_public_ip(),
        "X-MACaddress": "fe-80-00-00-00-00",
        "MACAddress": "fe-80-00-00-00-00"
    }

    try:
        with get_httpx_client(timeout=7.0) as client:
            response = client.post(url, json=payload, headers=headers)
            data = _safe_json(response)
            if data.get("status") is True and "data" in data:
                order_id = data["data"].get("uniqueorderid") or data["data"].get("orderid")
                logger.info("✅ Order placed successfully! Order ID: %s", order_id)
                return {"success": True, "order_id": order_id, "message": "Order placed successfully"}
            else:
                msg = data.get("message") or f"Execution Failed (HTTP {response.status_code})"
                logger.error("❌ Order placement failed: %s", msg)
                return {"success": False, "message": msg}
    except Exception as e:
        logger.error("Exception during order placement: %s", e)
        return {"success": False, "message": str(e)}


def _safe_json(response) -> dict:
    if response and hasattr(response, "text") and response.text and response.text.strip():
        try:
            return response.json()
        except Exception:
            pass
    return {}

def get_smartapi_positions(auth_data: Dict) -> Optional[List[Dict]]:
    """
    Fetch all active positions for the logged in user.
    """
    url = f"{ANGELONE_URL}/rest/secure/angelbroking/order/v1/getPosition"
    
    headers = {
        "Authorization": f"Bearer {auth_data['jwtToken']}",
        "Content-Type": "application/json",
        "X-PrivateKey": auth_data["api_key"],
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": get_server_public_ip(),
        "X-MACaddress": "fe-80-00-00-00-00",
        "MACAddress": "fe-80-00-00-00-00"
    }

    try:
        with get_httpx_client(timeout=10.0) as client:
            response = client.get(url, headers=headers)
            data = _safe_json(response)
            if data.get("status") is True:
                return data.get("data", [])
            else:
                if data.get("message"):
                    logger.warning("⚠️ Could not fetch positions: %s", data.get("message"))
                return None
    except Exception as e:
        logger.warning("Note: Exception fetching positions: %s", e)
        return None


def get_smartapi_rms(auth_data: Dict) -> Optional[Dict]:
    """
    Fetch live RMS funds/margin balance from Angel One SmartAPI.
    Endpoint: GET /rest/secure/angelbroking/user/v1/getRMS
    """
    url = f"{ANGELONE_URL}/rest/secure/angelbroking/user/v1/getRMS"
    headers = {
        "Authorization": f"Bearer {auth_data['jwtToken']}",
        "Content-Type": "application/json",
        "X-PrivateKey": auth_data["api_key"],
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": get_server_public_ip(),
        "X-MACaddress": "fe-80-00-00-00-00",
        "MACAddress": "fe-80-00-00-00-00"
    }
    try:
        with get_httpx_client(timeout=10.0) as client:
            response = client.get(url, headers=headers)
            data = _safe_json(response)
            if data.get("status") is True and "data" in data:
                return data.get("data", {})
            else:
                if data.get("message"):
                    logger.warning("⚠️ Could not fetch RMS funds: %s", data.get("message"))
                return None
    except Exception as e:
        logger.warning("Note: Exception fetching RMS funds: %s", e)
        return None


STATIC_SCRIP_TOKENS = {
    "RELIANCE": {
        "token": "2885",
        "trading_symbol": "RELIANCE-EQ"
    },
    "TCS": {
        "token": "11536",
        "trading_symbol": "TCS-EQ"
    },
    "HDFCBANK": {
        "token": "1333",
        "trading_symbol": "HDFCBANK-EQ"
    },
    "ICICIBANK": {
        "token": "4963",
        "trading_symbol": "ICICIBANK-EQ"
    },
    "INFY": {
        "token": "1594",
        "trading_symbol": "INFY-EQ"
    },
    "HINDUNILVR": {
        "token": "1394",
        "trading_symbol": "HINDUNILVR-EQ"
    },
    "ITC": {
        "token": "1660",
        "trading_symbol": "ITC-EQ"
    },
    "SBIN": {
        "token": "3045",
        "trading_symbol": "SBIN-EQ"
    },
    "BHARTIARTL": {
        "token": "10604",
        "trading_symbol": "BHARTIARTL-EQ"
    },
    "KOTAKBANK": {
        "token": "1922",
        "trading_symbol": "KOTAKBANK-EQ"
    },
    "LT": {
        "token": "11483",
        "trading_symbol": "LT-EQ"
    },
    "HCLTECH": {
        "token": "7229",
        "trading_symbol": "HCLTECH-EQ"
    },
    "MARUTI": {
        "token": "10999",
        "trading_symbol": "MARUTI-EQ"
    },
    "AXISBANK": {
        "token": "5900",
        "trading_symbol": "AXISBANK-EQ"
    },
    "SUNPHARMA": {
        "token": "3351",
        "trading_symbol": "SUNPHARMA-EQ"
    },
    "BAJFINANCE": {
        "token": "317",
        "trading_symbol": "BAJFINANCE-EQ"
    },
    "ULTRACEMCO": {
        "token": "11532",
        "trading_symbol": "ULTRACEMCO-EQ"
    },
    "WIPRO": {
        "token": "3787",
        "trading_symbol": "WIPRO-EQ"
    },
    "M&M": {
        "token": "2031",
        "trading_symbol": "M&M-EQ"
    },
    "NTPC": {
        "token": "11630",
        "trading_symbol": "NTPC-EQ"
    },
    "TITAN": {
        "token": "3506",
        "trading_symbol": "TITAN-EQ"
    },
    "ASIANPAINT": {
        "token": "236",
        "trading_symbol": "ASIANPAINT-EQ"
    },
    "POWERGRID": {
        "token": "14977",
        "trading_symbol": "POWERGRID-EQ"
    },
    "TATASTEEL": {
        "token": "3499",
        "trading_symbol": "TATASTEEL-EQ"
    },
    "ADANIENT": {
        "token": "25",
        "trading_symbol": "ADANIENT-EQ"
    },
    "ADANIPORTS": {
        "token": "15083",
        "trading_symbol": "ADANIPORTS-EQ"
    },
    "COALINDIA": {
        "token": "20374",
        "trading_symbol": "COALINDIA-EQ"
    },
    "ONGC": {
        "token": "2475",
        "trading_symbol": "ONGC-EQ"
    },
    "TECHM": {
        "token": "13538",
        "trading_symbol": "TECHM-EQ"
    },
    "GRASIM": {
        "token": "1232",
        "trading_symbol": "GRASIM-EQ"
    },
    "BRITANNIA": {
        "token": "547",
        "trading_symbol": "BRITANNIA-EQ"
    },
    "HDFCLIFE": {
        "token": "467",
        "trading_symbol": "HDFCLIFE-EQ"
    },
    "CIPLA": {
        "token": "694",
        "trading_symbol": "CIPLA-EQ"
    },
    "APOLLOHOSP": {
        "token": "157",
        "trading_symbol": "APOLLOHOSP-EQ"
    },
    "EICHERMOT": {
        "token": "910",
        "trading_symbol": "EICHERMOT-EQ"
    },
    "BPCL": {
        "token": "526",
        "trading_symbol": "BPCL-EQ"
    },
    "TATACONSUM": {
        "token": "3432",
        "trading_symbol": "TATACONSUM-EQ"
    },
    "JSWSTEEL": {
        "token": "11723",
        "trading_symbol": "JSWSTEEL-EQ"
    },
    "DIVISLAB": {
        "token": "10940",
        "trading_symbol": "DIVISLAB-EQ"
    },
    "DRREDDY": {
        "token": "881",
        "trading_symbol": "DRREDDY-EQ"
    },
    "INDUSINDBK": {
        "token": "5258",
        "trading_symbol": "INDUSINDBK-EQ"
    },
    "HEROMOTOCO": {
        "token": "1348",
        "trading_symbol": "HEROMOTOCO-EQ"
    },
    "HINDALCO": {
        "token": "1363",
        "trading_symbol": "HINDALCO-EQ"
    },
    "NESTLEIND": {
        "token": "17963",
        "trading_symbol": "NESTLEIND-EQ"
    },
    "BAJAJ-AUTO": {
        "token": "16669",
        "trading_symbol": "BAJAJ-AUTO-EQ"
    },
    "SHRIRAMFIN": {
        "token": "4306",
        "trading_symbol": "SHRIRAMFIN-EQ"
    },
    "SBILIFE": {
        "token": "21808",
        "trading_symbol": "SBILIFE-EQ"
    },
    "BEL": {
        "token": "383",
        "trading_symbol": "BEL-EQ"
    },
    "SUZLON": {
        "token": "12018",
        "trading_symbol": "SUZLON-EQ"
    },
    "IDFCFIRSTB": {
        "token": "11184",
        "trading_symbol": "IDFCFIRSTB-EQ"
    },
    "PNB": {
        "token": "10666",
        "trading_symbol": "PNB-EQ"
    },
    "YESBANK": {
        "token": "11915",
        "trading_symbol": "YESBANK-EQ"
    },
    "IRFC": {
        "token": "2029",
        "trading_symbol": "IRFC-EQ"
    },
    "NHPC": {
        "token": "17400",
        "trading_symbol": "NHPC-EQ"
    },
    "SAIL": {
        "token": "2963",
        "trading_symbol": "SAIL-EQ"
    },
    "IOC": {
        "token": "1624",
        "trading_symbol": "IOC-EQ"
    },
    "GMRAIRPORT": {
        "token": "13528",
        "trading_symbol": "GMRAIRPORT-EQ"
    },
    "IDBI": {
        "token": "1476",
        "trading_symbol": "IDBI-EQ"
    },
    "UCOBANK": {
        "token": "11223",
        "trading_symbol": "UCOBANK-EQ"
    },
    "UNIONBANK": {
        "token": "10753",
        "trading_symbol": "UNIONBANK-EQ"
    },
    "NBCC": {
        "token": "31415",
        "trading_symbol": "NBCC-EQ"
    },
    "SJVN": {
        "token": "18883",
        "trading_symbol": "SJVN-EQ"
    },
    "RCF": {
        "token": "2866",
        "trading_symbol": "RCF-EQ"
    },
    "FEDERALBNK": {
        "token": "1023",
        "trading_symbol": "FEDERALBNK-EQ"
    },
    "ETERNAL": {
        "token": "5097",
        "trading_symbol": "ETERNAL-EQ"
    },
    "TATAMOTORS": {
        "token": "3456",
        "trading_symbol": "TATAMOTORS-EQ"
    },
    "LTIM": {
        "token": "17818",
        "trading_symbol": "LTIM-EQ"
    },
    "HFCL": {
        "token": "1406",
        "trading_symbol": "HFCL-EQ"
    }
}

_token_map_cache = dict(STATIC_SCRIP_TOKENS)

def fetch_and_cache_tokens() -> dict:
    """Download and cache Angel One scrip master tokens for NSE Equity (fallback)."""
    global _token_map_cache
    if len(_token_map_cache) > len(STATIC_SCRIP_TOKENS):
        return _token_map_cache
    
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    try:
        logger.info("📥 Downloading Angel One Scrip Master for token mapping...")
        response = httpx.get(url, timeout=10.0)
        if response.status_code == 200:
            scrip_list = response.json()
            temp_map = dict(STATIC_SCRIP_TOKENS)
            for item in scrip_list:
                if item.get("exch_seg") == "NSE" and item.get("symbol", "").endswith("-EQ"):
                    base_name = item["symbol"].replace("-EQ", "")
                    temp_map[base_name] = {"token": item["token"], "trading_symbol": item["symbol"]}
            _token_map_cache = temp_map
            logger.info("✅ Cached %d NSE Equity tokens in memory.", len(_token_map_cache))
            return _token_map_cache
    except Exception as e:
        logger.warning("⚠️ Could not refresh Scrip Master online (%s). Using static token map (%d stocks).", e, len(STATIC_SCRIP_TOKENS))
    return _token_map_cache


def get_angelone_token_and_symbol(yahoo_symbol: str) -> tuple[Optional[str], Optional[str]]:
    """
    Given a Yahoo Finance symbol like 'ONGC-EQ', 'ONGC.NS', 'ONGC-EQ.NS' or 'RELIANCE', return (token, tradingsymbol) for Angel One.
    e.g., 'ONGC-EQ' -> ('2475', 'ONGC-EQ')
    """
    if not yahoo_symbol:
        return None, None
    raw = yahoo_symbol.upper().replace(".NS", "").replace(".BO", "").strip()
    base = raw.replace("-EQ", "").replace("-BE", "").replace("-SM", "").strip()
    
    # 1. Check static high-speed map (instant 0ms lookup)
    if base in STATIC_SCRIP_TOKENS:
        return STATIC_SCRIP_TOKENS[base]["token"], STATIC_SCRIP_TOKENS[base]["trading_symbol"]
    if raw in STATIC_SCRIP_TOKENS:
        return STATIC_SCRIP_TOKENS[raw]["token"], STATIC_SCRIP_TOKENS[raw]["trading_symbol"]
    
    # 2. Check dynamic cache
    if base in _token_map_cache:
        return _token_map_cache[base]["token"], _token_map_cache[base]["trading_symbol"]
    if raw in _token_map_cache:
        return _token_map_cache[raw]["token"], _token_map_cache[raw]["trading_symbol"]
        
    return None, None
