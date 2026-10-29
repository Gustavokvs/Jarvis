"""
Action: Optimize RAM / Memory Cleanup.
Allows Ramma to optimize RAM usage, run garbage collection, and trim working set memory.
"""
from core.ram_optimizer import optimize_ram


def execute(parameters: dict) -> str:
    res = optimize_ram()
    if res.get("success"):
        freed = res.get("freed_mb", 0)
        used_gb = res.get("ram_used_gb", 0)
        pct = res.get("ram_percent", 0)
        return f"RAM optimized successfully! Freed {freed} MB. Current RAM usage: {used_gb} GB ({pct}%)."
    else:
        return f"RAM optimization encountered an issue: {res.get('error', 'unknown error')}"


TOOL = {
    "name": "optimize_ram",
    "description": (
        "Optimizes RAM usage by running Python garbage collection and trimming OS working set memory "
        "to free up RAM without losing any capabilities or data. Use when memory usage is high "
        "or when the user asks to optimize RAM or free up memory."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
    },
    "handler": execute,
}