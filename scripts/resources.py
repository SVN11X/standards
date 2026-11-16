#!/usr/bin/env python3
"""What this machine has free right now: graphics memory, RAM and the models Ollama holds loaded.

The executor loop asks `local_busy` before it gives a unit to a local model, so two models never compete
for one graphics card. Every number comes from the system. A value that cannot be read is None, never a guess.

Usage: python scripts/resources.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import orchestrate  # noqa: E402


def ram_free_bytes() -> int | None:
    try:
        if os.name == "nt":
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("free", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong),
                            ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
            status = Status()
            status.length = ctypes.sizeof(Status)
            return int(status.free) if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) else None
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except (AttributeError, OSError, ValueError):
        pass
    return None


def snapshot(gpu=None) -> dict:
    """RAM and graphics memory at this moment, for the metrics of a plan."""
    gpu = orchestrate.detect_gpu() if gpu is None else gpu
    return {"ram_total_bytes": orchestrate.memory_bytes(), "ram_free_bytes": ram_free_bytes(),
            "vram_total_mib": (gpu or {}).get("vram_total_mib"), "vram_used_mib": (gpu or {}).get("vram_used_mib")}


def local_busy(model: str | None, conf: dict, gpu=None, loaded: list[str] | None = None) -> str | None:
    """Why a local model must wait, or None when it may start.

    It may start when the policy has no concurrency section, when no graphics card is reported (the slot count
    alone decides), when the model is the one Ollama already holds, or when the free graphics memory reaches
    concurrency.local_min_free_vram_mib.
    """
    limits = conf.get("concurrency")
    if not limits:
        return None
    need = limits.get("local_min_free_vram_mib", 1024)
    gpu = orchestrate.detect_gpu() if gpu is None else gpu
    if not gpu or gpu.get("vram_total_mib") is None:
        return None
    if loaded is None:
        try:
            found = orchestrate.detect_ollama(conf["executors"]["ollama"], timeout=1.0)
            loaded = [m.get("name") for m in found.get("loaded") or []]
        except (KeyError, OSError):
            loaded = []
    name = (model or "").split("/", 1)[1] if (model or "").startswith("ollama/") else model
    if name and name in loaded:
        return None
    free = gpu["vram_total_mib"] - (gpu.get("vram_used_mib") or 0)
    if free < need:
        return f"the graphics card has {free} MiB free and a local model needs {need} MiB"
    return None


if __name__ == "__main__":
    import console
    console.safe_output()
    print(json.dumps(snapshot(), indent=2))
