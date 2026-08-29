import os
import sys
import traceback

print("Starting custom run_server.py wrapper...")

try:
    import uvicorn
    # Try importing main to catch any import-time errors
    print("Importing backend.main...")
    import backend.main
    
    if __name__ == "__main__":
        port = int(os.getenv("PORT", "8000"))
        print(f"Starting uvicorn on port {port}...")
        uvicorn.run("backend.main:app", host="0.0.0.0", port=port)
except Exception as e:
    print("=" * 60)
    print("CRITICAL STARTUP ERROR DETECTED:")
    print("=" * 60)
    traceback.print_exc()
    print("=" * 60)
    sys.exit(1)
