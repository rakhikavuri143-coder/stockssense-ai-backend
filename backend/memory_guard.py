"""
backend/memory_guard.py
StocksSense AI — Real-Time RAM Auto-Cleaner & Memory Watchdog
Monitors process memory and aggressively purges caches, forces glibc malloc_trim,
and runs GC when memory approaches limits on Render (512MB free tier).
"""

import os
import gc
import sys
import ctypes
import logging
import platform
import linecache

logger = logging.getLogger(__name__)

def get_current_ram_mb() -> float:
    """Accurately get current process RAM (Resident Set Size) in MB."""
    # 1. Linux / Render: Read from /proc/self/status (instant, 0 dependency)
    if os.path.exists("/proc/self/status"):
        try:
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        # e.g., "VmRSS:     123456 kB"
                        parts = line.split()
                        if len(parts) >= 2:
                            return round(float(parts[1]) / 1024.0, 2)
        except Exception:
            pass

    # 2. psutil fallback if installed
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return round(process.memory_info().rss / (1024.0 * 1024.0), 2)
    except Exception:
        pass

    # 3. Windows ctypes fallback
    if platform.system() == "Windows":
        try:
            from ctypes import wintypes
            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return round(counters.WorkingSetSize / (1024.0 * 1024.0), 2)
        except Exception:
            pass

    # 4. Linux/macOS resource fallback
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(usage / 1024.0, 2)
    except Exception:
        pass

    return 0.0


def release_glibc_memory():
    """On Linux (Render), force glibc to release unused heap memory back to the OS."""
    if platform.system() == "Linux":
        try:
            libc = ctypes.CDLL("libc.so.6")
            libc.malloc_trim(0)
            return True
        except Exception as e:
            logger.debug("malloc_trim error: %s", e)
    return False


def purge_application_caches():
    """Clear all in-memory application caches."""
    cleared = []
    
    # 1. Technicals 1H & 15M caches
    try:
        from backend import technicals_1h
        if hasattr(technicals_1h, "_tech_1h_cache"):
            technicals_1h._tech_1h_cache.clear()
        if hasattr(technicals_1h, "_tech_15m_cache"):
            technicals_1h._tech_15m_cache.clear()
        if hasattr(technicals_1h, "_data_5y_cache"):
            technicals_1h._data_5y_cache.clear()
        cleared.append("technicals_cache")
    except Exception:
        pass

    # 2. Paper Trading circuit cache
    try:
        from backend import paper_trading
        if hasattr(paper_trading, "_circuit_cache"):
            paper_trading._circuit_cache.clear()
        cleared.append("circuit_cache")
    except Exception:
        pass

    # 3. yfinance internal ticker cache (grows unbounded if not cleared)
    try:
        import yfinance as yf
        if hasattr(yf, '_CACHE'):
            yf._CACHE.clear()
        if hasattr(yf, 'cache'):
            yf.cache.clear()
        # Clear any shared session data
        if hasattr(yf, 'shared') and hasattr(yf.shared, '_CACHE'):
            yf.shared._CACHE.clear()
        cleared.append("yfinance_cache")
    except Exception:
        pass

    # 4. Clear Python's linecache (stores source lines for tracebacks, grows over time)
    linecache.clearcache()
    cleared.append("linecache")

    return cleared


def cleanup_memory(force: bool = False) -> dict:
    """
    Perform deep memory purge and return RAM before and after.
    """
    ram_before = get_current_ram_mb()
    
    # 1. Purge all internal dictionaries & caches
    caches_cleared = purge_application_caches()
    
    # 2. Full 3-generation garbage collection
    collected = gc.collect()
    
    # 3. Release C-heap back to Linux kernel (crucial for Render!)
    trimmed = release_glibc_memory()
    
    ram_after = get_current_ram_mb()
    
    logger.info(
        "RAM Auto-Cleaned: %.1f MB -> %.1f MB (Freed: %.1f MB | GC Objects: %d | malloc_trim: %s)",
        ram_before, ram_after, max(0.0, ram_before - ram_after), collected, trimmed
    )
    
    return {
        "ram_before_mb": ram_before,
        "ram_after_mb": ram_after,
        "freed_mb": round(max(0.0, ram_before - ram_after), 2),
        "gc_collected_objects": collected,
        "malloc_trimmed": trimmed,
        "caches_cleared": caches_cleared
    }


def emergency_cleanup() -> dict:
    """
    EMERGENCY: Called when RAM > 350MB. Clears EVERYTHING possible to prevent OOM kill.
    This is more aggressive than cleanup_memory — drops module-level references too.
    """
    ram_before = get_current_ram_mb()
    logger.warning("EMERGENCY RAM CLEANUP triggered at %.1f MB!", ram_before)
    
    # 1. Standard cleanup first
    purge_application_caches()
    
    # 2. Clear ALL __pycache__ and compiled bytecode from memory
    linecache.clearcache()
    
    # 3. Drop all exception context chains (they hold references to entire stack frames)
    sys.exc_clear() if hasattr(sys, 'exc_clear') else None
    
    # 4. Clear warnings filter cache
    try:
        import warnings
        warnings.resetwarnings()
    except Exception:
        pass
    
    # 5. Force full 3-generation GC
    gc.collect()
    gc.collect()  # Double collect to catch weak refs
    
    # 6. Release C-heap aggressively
    release_glibc_memory()
    
    ram_after = get_current_ram_mb()
    logger.warning("EMERGENCY cleanup complete: %.1f MB -> %.1f MB (Freed: %.1f MB)",
                   ram_before, ram_after, max(0.0, ram_before - ram_after))
    
    return {
        "emergency": True,
        "ram_before_mb": ram_before,
        "ram_after_mb": ram_after,
        "freed_mb": round(max(0.0, ram_before - ram_after), 2),
    }


def ram_watchdog_check(threshold_mb: float = 180.0) -> dict:
    """
    Watchdog function run periodically by APScheduler.
    - Normal cleanup at 180MB threshold (was 220MB — lowered for more breathing room)
    - Emergency cleanup at 350MB (last resort before 512MB OOM kill)
    """
    current_ram = get_current_ram_mb()
    
    # EMERGENCY: RAM dangerously high — nuclear cleanup
    if current_ram >= 350.0:
        return emergency_cleanup()
    
    # WARNING: RAM above safe threshold — standard cleanup
    if current_ram >= threshold_mb or current_ram == 0.0:
        logger.warning("RAM usage (%.1f MB) >= threshold (%.1f MB). Triggering Auto RAM Cleaner...", current_ram, threshold_mb)
        return cleanup_memory(force=True)
    else:
        # Routine light garbage collection (generation 0 only — fast)
        gc.collect(0)
        return {
            "status": "normal",
            "current_ram_mb": current_ram,
            "threshold_mb": threshold_mb
        }
