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


def generate_totp(totp_secret: str) -> str:
    """Generate dynamic 6-digit TOTP code using the secret key."""
    try:
        import re
        # Strip spaces and sanitize common base32 typos (0 -> O, 1 -> I, 8 -> B)
        clean_secret = totp_secret.strip().replace(" ", "").upper()
        clean_secret = clean_secret.replace("0", "O").replace("1", "I").replace("8", "B")
        clean_secret = re.sub(r'[^A-Z2-7]', '', clean_secret)
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
        "X-ClientPublicIP": "106.201.200.22",
        "X-MACaddress": "fe-80-00-00-00-00",
        "MACAddress": "fe-80-00-00-00-00"
    }

    last_err = "Unknown error"
    for url in endpoints:
        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=10.0)
            data = response.json()
            
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
                msg = data.get("message") or "Auth Failed"
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
        "price": str(round(price, 2)),
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
        "X-ClientPublicIP": "106.201.200.22",
        "X-MACaddress": "fe-80-00-00-00-00",
        "MACAddress": "fe-80-00-00-00-00"
    }

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        data = response.json()
        if data.get("status") is True and "data" in data:
            order_id = data["data"].get("uniqueorderid") or data["data"].get("orderid")
            logger.info("✅ Order placed successfully! Order ID: %s", order_id)
            return {"success": True, "order_id": order_id, "message": "Order placed successfully"}
        else:
            logger.error("❌ Order placement failed: %s", data.get("message"))
            return {"success": False, "message": data.get("message", "Unknown error")}
    except Exception as e:
        logger.error("Exception during order placement: %s", e)
        return {"success": False, "message": str(e)}


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
        "X-ClientPublicIP": "106.201.200.22",
        "X-MACaddress": "fe-80-00-00-00-00",
        "MACAddress": "fe-80-00-00-00-00"
    }

    try:
        response = httpx.get(url, headers=headers, timeout=10.0)
        data = response.json()
        if data.get("status") is True:
            return data.get("data", [])
        else:
            logger.error("❌ Failed to fetch positions: %s", data.get("message"))
            return None
    except Exception as e:
        logger.error("Exception fetching positions: %s", e)
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
        "X-ClientPublicIP": "106.201.200.22",
        "X-MACaddress": "fe-80-00-00-00-00",
        "MACAddress": "fe-80-00-00-00-00"
    }
    try:
        response = httpx.get(url, headers=headers, timeout=10.0)
        data = response.json()
        if data.get("status") is True and "data" in data:
            return data.get("data", {})
        else:
            logger.error("❌ Failed to fetch RMS funds: %s", data.get("message"))
            return None
    except Exception as e:
        logger.error("Exception fetching RMS funds: %s", e)
        return None


_token_map_cache = {}

def fetch_and_cache_tokens() -> dict:
    """Download and cache Angel One scrip master tokens for NSE Equity."""
    global _token_map_cache
    if _token_map_cache:
        return _token_map_cache
    
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    try:
        logger.info("📥 Downloading Angel One Scrip Master for token mapping...")
        response = httpx.get(url, timeout=10.0)
        if response.status_code == 200:
            scrip_list = response.json()
            temp_map = {}
            for item in scrip_list:
                if item.get("exch_seg") == "NSE" and item.get("symbol", "").endswith("-EQ"):
                    base_name = item["symbol"].replace("-EQ", "")
                    temp_map[base_name] = {
                        "token": item["token"],
                        "trading_symbol": item["symbol"]
                    }
            _token_map_cache = temp_map
            logger.info("✅ Cached %d NSE Equity tokens in memory.", len(_token_map_cache))
            return _token_map_cache
    except Exception as e:
        logger.error("❌ Failed to cache Scrip Master: %s. Using hardcoded fallbacks.", e)
    return {}


def get_angelone_token_and_symbol(yahoo_symbol: str) -> tuple[Optional[str], Optional[str]]:
    """
    Given a Yahoo Finance symbol like 'RELIANCE.NS', return (token, tradingsymbol) for Angel One.
    e.g., 'RELIANCE.NS' -> ('3045', 'RELIANCE-EQ')
    """
    base = yahoo_symbol.upper().replace(".NS", "").replace(".BO", "").strip()
    
    # Try cache first
    cache = fetch_and_cache_tokens()
    if base in cache:
        return cache[base]["token"], cache[base]["trading_symbol"]
    
    # Hardcoded fallbacks for testing or if download fails
    fallbacks = {
        "IDEA": ("14366", "IDEA-EQ"),
        "RELIANCE": ("3045", "RELIANCE-EQ"),
        "TCS": ("11536", "TCS-EQ"),
        "SBIN": ("3063", "SBIN-EQ"),
        "WIPRO": ("3787", "WIPRO-EQ"),
        "ADANIPORTS": ("15083", "ADANIPORTS-EQ")
    }
    if base in fallbacks:
        return fallbacks[base]
        
    return None, None

