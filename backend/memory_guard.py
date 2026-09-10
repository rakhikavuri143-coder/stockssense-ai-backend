"""
backend/memory_guard.py
StocksSense AI — Real-Time RAM Auto-Cleaner & Memory Watchdog
Monitors process memory and aggressively purges caches, forces glibc malloc_trim,
and runs GC when memory approaches limits on Render.
"""

import os
import gc
import ctypes
import logging
import platform

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
        "🧹 RAM Auto-Cleaned: %.1f MB -> %.1f MB (Freed: %.1f MB | GC Objects: %d | malloc_trim: %s)",
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


def ram_watchdog_check(threshold_mb: float = 220.0) -> dict:
    """
    Watchdog function run periodically by APScheduler.
    If RAM exceeds threshold (default 220 MB on 512 MB Render limit), triggers aggressive purge.
    """
    current_ram = get_current_ram_mb()
    if current_ram >= threshold_mb or current_ram == 0.0:
        logger.warning("⚠️ RAM usage (%.1f MB) >= threshold (%.1f MB). Triggering Auto RAM Cleaner...", current_ram, threshold_mb)
        return cleanup_memory(force=True)
    else:
        # Routine light garbage collection
        gc.collect(0)
        return {
            "status": "normal",
            "current_ram_mb": current_ram,
            "threshold_mb": threshold_mb
        }
