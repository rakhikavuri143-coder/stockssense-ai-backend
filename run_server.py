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
        print(f"Starting uvicorn on port {port} with stability limits...")
        uvicorn.run(
            "backend.main:app",
            host="0.0.0.0",
            port=port,
            workers=1,
            timeout_keep_alive=30,
            limit_concurrency=20,
            limit_max_requests=1000,
        )
except Exception as e:
    print("=" * 60)
    print("CRITICAL STARTUP ERROR DETECTED:")
    print("=" * 60)
    traceback.print_exc()
    print("=" * 60)
    sys.exit(1)
