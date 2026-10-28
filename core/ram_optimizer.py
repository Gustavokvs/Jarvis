"""
RAM Optimization & Garbage Collection Utility for Mark-LVI (Ramma).
Performs aggressive yet safe Python garbage collection and OS-level heap trimming
(EmptyWorkingSet on Windows) to minimize RAM consumption without sacrificing any capabilities.
"""
from __future__ import annotations

import gc
import ctypes
import platform
import psutil
import time
import sys
from typing import Dict, Any

_OS = platform.system()

# Força GC mais agressivo: limiares mais baixos = coleta mais frequente
# Default: (700, 10, 10) - mudamos para coletar gen0 mais agressivamente
gc.set_threshold(100, 10, 10)


def optimize_ram(aggressive: bool = False) -> Dict[str, Any]:
    """
    Performs full garbage collection and OS-level working set trimming
    to release unused memory back to the operating system.
    Returns memory stats before and after optimization.
    """
    try:
        mem_before = psutil.virtual_memory()
        process = psutil.Process()
        rss_before = process.memory_info().rss

        # 1. Force full Python garbage collection across all generations
        gc.collect(0)
        gc.collect(1)
        gc.collect(2)

        # 2. OS-specific heap and working set trimming
        if _OS == "Windows":
            try:
                # Trim process working set to push idle pages to pagefile/free memory
                ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
            except Exception:
                pass
            try:
                # Compact C runtime heap
                ctypes.cdll.msvcrt._heapmin()
            except Exception:
                pass
        elif _OS == "Linux":
            try:
                # Suggest kernel to trim malloc arenas if glibc >= 2.10
                import ctypes.util
                libc = ctypes.CDLL(ctypes.util.find_library("c"))
                if hasattr(libc, "malloc_trim"):
                    libc.malloc_trim(0)
            except Exception:
                pass

        # 3. Aggressive mode: clear internal caches, interned strings, etc.
        if aggressive:
            # Clear importlib cache
            sys.modules.pop('importlib._bootstrap', None)
            sys.modules.pop('importlib._bootstrap_external', None)
            # Clear regex cache
            import re
            re.purge()
            # One more GC pass after cache clearing
            gc.collect()

        mem_after = psutil.virtual_memory()
        rss_after = process.memory_info().rss
        freed_mb = max(0, (rss_before - rss_after) / (1024 * 1024))

        return {
            "success": True,
            "freed_mb": round(freed_mb, 2),
            "ram_percent": round(mem_after.percent, 1),
            "ram_used_gb": round(mem_after.used / (1024 ** 3), 2),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


class RAMOptimizerEngine:
    """
    Periodic background RAM optimizer that runs cleanup during idle periods
    or at regular intervals to keep Ramma lightweight.
    """
    def __init__(self, interval_seconds: int = 120):  # reduzido de 300 para 120s
        self.interval_seconds = interval_seconds
        self._last_optimized = time.monotonic()
        self._last_aggressive = time.monotonic()
        self._aggressive_interval = 600  # aggressive a cada 10 min

    def should_optimize(self) -> bool:
        return (time.monotonic() - self._last_optimized) >= self.interval_seconds

    def run_check(self, force_aggressive: bool = False) -> Dict[str, Any] | None:
        now = time.monotonic()
        aggressive = force_aggressive or (now - self._last_aggressive >= self._aggressive_interval)

        if self.should_optimize() or aggressive:
            self._last_optimized = now
            if aggressive:
                self._last_aggressive = now
            return optimize_ram(aggressive=aggressive)
        return None

    def quick_gc(self) -> None:
        """GC rápido sem stats - para chamar periodicamente no loop principal."""
        gc.collect(0)  # só gen0, bem rápido
