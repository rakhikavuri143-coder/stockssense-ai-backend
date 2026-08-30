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
        # Strip spaces if any
        clean_secret = totp_secret.replace(" ", "").upper()
        totp = pyotp.TOTP(clean_secret)
        return totp.now()
    except Exception as e:
        logger.error("Failed to generate TOTP: %s", e)
        raise e


def login_smartapi(client_code: str, password: str, api_key: str, totp_secret: str) -> Optional[Dict]:
    """
    Log in to Angel One SmartAPI using client_code, password, and TOTP secret.
    Returns auth tokens dict on success.
    """
    totp_code = generate_totp(totp_secret)
    url = f"{ANGELONE_URL}/publisher-apis/api/v1/user/login/v3"
    
    payload = {
        "clientcode": client_code.upper(),
        "password": password,
        "totp": totp_code
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-PrivateKey": api_key,
        "Accept": "application/json"
    }

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        data = response.json()
        
        if data.get("status") is True and "data" in data:
            tokens = data["data"]
            logger.info("✅ Angel One SmartAPI login successful for client %s", client_code)
            return {
                "jwtToken": tokens["jwtToken"],
                "refreshToken": tokens["refreshToken"],
                "feedToken": tokens["feedToken"],
                "client_code": client_code,
                "api_key": api_key
            }
        else:
            logger.error("❌ Angel One login failed: %s", data.get("message"))
            return None
    except Exception as e:
        logger.error("Exception during Angel One login: %s", e)
        return None


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
        "X-ClientPublicIP": "106.201.200.22",  # Default placeholder IP
        "MACAddress": "00-00-00-00-00-00"
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
        "MACAddress": "00-00-00-00-00-00"
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
