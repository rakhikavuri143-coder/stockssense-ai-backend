"""
scratch/test_angelone.py
Quick script to test Angel One SmartAPI login, connection, and order placement.
Run this script locally to verify your credentials and API execution.
"""

import os
import sys
from dotenv import load_dotenv

# Ensure parent dir is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.broker_angelone import login_smartapi, place_smartapi_order, get_smartapi_positions

load_dotenv()

def run_test():
    print("=" * 60)
    print("  ANGEL ONE SMARTAPI LOCAL TESTER")
    print("=" * 60)

    client_code = os.getenv("ANGELONE_CLIENT_CODE", "").strip()
    password = os.getenv("ANGELONE_PASSWORD", "").strip()
    api_key = os.getenv("ANGELONE_API_KEY", "").strip()
    totp_secret = os.getenv("ANGELONE_TOTP_SECRET", "").strip()

    if not all([client_code, password, api_key, totp_secret]):
        print("[ERROR] Missing credentials in .env file!")
        print("Please add these keys to your .env file:")
        print("  ANGELONE_CLIENT_CODE=...")
        print("  ANGELONE_PASSWORD=...")
        print("  ANGELONE_API_KEY=...")
        print("  ANGELONE_TOTP_SECRET=...")
        print("=" * 60)
        return

    print(f"Attempting login for Client: {client_code}...")
    auth = login_smartapi(client_code, password, api_key, totp_secret)
    
    if not auth:
        print("[ERROR] Login failed! Check your credentials, API Key, and TOTP secret.")
        print("=" * 60)
        return

    print("✅ LOGIN SUCCESSFUL!")
    print(f"JWT Token: {auth['jwtToken'][:30]}...")
    print(f"Feed Token: {auth['feedToken'][:30]}...")
    print("=" * 60)

    # Test 1: Fetch positions
    print("Fetching active positions...")
    positions = get_smartapi_positions(auth)
    if positions is not None:
        print(f"Success! Found {len(positions)} active positions.")
        for idx, pos in enumerate(positions):
            print(f"  {idx+1}. {pos.get('tradingsymbol')}: Qty {pos.get('netqty')} | Avg Price: {pos.get('avgprice')}")
    else:
        print("[WARN] Failed to fetch positions.")
    print("=" * 60)

    # Test 2: Place a simulated/test order (optional)
    confirm = input("Do you want to place a test BUY order of 1 Qty of IDEA (Vodafone Idea) @ LIMIT Rs. 10.00? (y/n): ")
    if confirm.lower() == 'y':
        print("\nPlacing test order...")
        # Vodafone Idea NSE symbol: IDEA-EQ, Token: 14366
        res = place_smartapi_order(
            auth_data=auth,
            symbol="IDEA-EQ",
            symbol_token="14366",
            transaction_type="BUY",
            quantity=1,
            price=10.00,
            order_type="LIMIT",
            exchange="NSE",
            product_type="INTRADAY"
        )
        if res.get("success"):
            print("🎉 ORDER COMPLETED SUCCESSFULLY!")
            print(f"Order ID: {res.get('order_id')}")
        else:
            print(f"❌ Order failed: {res.get('message')}")
    else:
        print("Order placement skipped.")
        
    print("=" * 60)
    print("Test complete!")
    print("=" * 60)

if __name__ == "__main__":
    run_test()
