#!/usr/bin/env python3
"""Ready-queue scheduler: a unit starts the moment its own dependencies passed, never when a whole batch ends.

It holds no model and no git logic. The executor loop gives it the unit ids, their dependencies, the pairs
that may not run together and three callables. `claim(uid)` answers which resource pools the unit takes now,
or None to wait. `work(uid)` runs the unit and returns its final status, or (status, info). `control()`
returns the owner's wishes: {"paused": bool, "cancel": [ids]}. Every transition is reported to `on_event`,
so watching a run costs no model call.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

DONE = "passed"


class Pools:
    """Slots per resource, such as remote_free, local or tests. A limit shrinks after a rate limit and grows back."""

    def __init__(self, limits: dict[str, int], grow_after: int = 3):
        self.ceiling = {name: max(1, int(size)) for name, size in limits.items()}
        self.limits = dict(self.ceiling)
        self.used = {name: 0 for name in limits}
        self.peak = {name: 0 for name in limits}
        self.streak = {name: 0 for name in limits}
        self.grow_after = grow_after
        self.changes: list[dict] = []
        self.cond = threading.Condition()

    def free(self, names) -> bool:
        with self.cond:
            return all(self.used.get(n, 0) < self.limits.get(n, 1) for n in names)

    def take(self, names) -> bool:
        """Take one slot in every named pool, or none of them."""
        with self.cond:
            if not all(self.used.get(n, 0) < self.limits.get(n, 1) for n in names):
                return False
            for name in names:
                self.used[name] = self.used.get(name, 0) + 1
                self.peak[name] = max(self.peak.get(name, 0), self.used[name])
            return True

    def give(self, names) -> None:
        with self.cond:
            for name in names:
                self.used[name] = max(0, self.used.get(name, 0) - 1)
            self.cond.notify_all()

    def wait_take(self, names, timeout: float, stop: threading.Event | None = None) -> bool:
        """Block until every named pool has a slot. False when the time ran out or the unit was cancelled."""
        end = time.monotonic() + timeout
        with self.cond:
            while not all(self.used.get(n, 0) < self.limits.get(n, 1) for n in names):
                left = end - time.monotonic()
                if left <= 0 or (stop is not None and stop.is_set()):
                    return False
                self.cond.wait(min(left, 0.2))
            for name in names:
                self.used[name] = self.used.get(name, 0) + 1
                self.peak[name] = max(self.peak.get(name, 0), self.used[name])
            return True

    def shrink(self, name: str, why: str) -> None:
        """One slot less, never below one. A provider that refuses requests gets fewer of them at once."""
        with self.cond:
            self.streak[name] = 0
            if self.limits.get(name, 1) > 1:
                self.limits[name] -= 1
                self.changes.append({"pool": name, "limit": self.limits[name], "why": why})

    def success(self, name: str) -> None:
        """After `grow_after` passed units in a row the pool gets one slot back, up to its configured size."""
        with self.cond:
            if name not in self.ceiling:
                return
            self.streak[name] = self.streak.get(name, 0) + 1
            if self.streak[name] >= self.grow_after and self.limits[name] < self.ceiling[name]:
                self.limits[name] += 1
                self.streak[name] = 0
                self.changes.append({"pool": name, "limit": self.limits[name], "why": f"{self.grow_after} units passed in a row"})
                self.cond.notify_all()


class Scheduler:
    def __init__(self, ids: list[str], deps: dict[str, set[str]], clash: set[frozenset], work, claim=None,
                 pools: Pools | None = None, max_parallel: int = 1, done=(), control=None, on_event=None,
                 clock=time.monotonic, poll_s: float = 0.2, stall_s: float = 900.0):
        self.ids, self.deps, self.clash = list(ids), deps, clash
        self.work, self.claim = work, claim or (lambda uid: [])
        self.pools = pools or Pools({})
        self.max_parallel = max(1, int(max_parallel or 1))
        self.final: dict[str, str] = {uid: DONE for uid in done}
        self.control, self.on_event = control, on_event
        self.clock, self.poll_s, self.stall_s = clock, poll_s, stall_s
        self.times: dict[str, dict] = {}
        self.peak = 0

    def emit(self, kind: str, uid: str | None = None, **fields) -> None:
        if self.on_event:
            self.on_event({"event": kind, "unit": uid, **fields})

    def settle(self, uid: str, status: str, note: str) -> None:
        """End a unit that never ran: cancelled, or its dependency did not pass."""
        self.final[uid] = status
        self.emit("finished", uid, status=status, note=note, ran=False)

    def run(self) -> dict:
        """Run until nothing is left, or until the owner paused and the running units ended."""
        start = self.clock()
        pending = [uid for uid in self.ids if uid not in self.final]
        ready_since: dict[str, float] = {}
        running: dict = {}
        stalled = None
        paused = False
        with ThreadPoolExecutor(max_workers=self.max_parallel) as pool:
            while pending or running:
                wishes = self.control() if self.control else {}
                paused = bool(wishes.get("paused"))
                for uid in [u for u in pending if u in (wishes.get("cancel") or [])]:
                    pending.remove(uid)
                    self.settle(uid, "cancelled", "cancelled by the owner before it started")
                for uid in list(pending):
                    bad = [d for d in self.deps.get(uid, ()) if d in self.final and self.final[d] != DONE]
                    if bad:
                        pending.remove(uid)
                        self.settle(uid, "skipped", "waits on " + ", ".join(sorted(bad)))
                for uid in list(pending):
                    if paused or len(running) >= self.max_parallel:
                        break
                    if not all(self.final.get(d) == DONE for d in self.deps.get(uid, ())):
                        continue
                    ready_since.setdefault(uid, self.clock())
                    if any(frozenset((uid, other)) in self.clash for other, _ in running.values()):
                        continue
                    slots = self.claim(uid)
                    if slots is None or not self.pools.take(slots):
                        continue
                    pending.remove(uid)
                    now = self.clock()
                    self.times[uid] = {"wait_s": round(now - ready_since[uid], 3), "started_s": round(now - start, 3)}
                    running[pool.submit(self.work, uid)] = (uid, slots)
                    self.peak = max(self.peak, len(running))
                    self.emit("started", uid, pools=slots, wait_s=self.times[uid]["wait_s"], running=len(running))
                if not running:
                    if paused or not pending:
                        break
                    # Nothing runs and nothing could start: a pool is held from outside, such as a busy GPU.
                    stalled = stalled if stalled is not None else self.clock()
                    if self.clock() - stalled >= self.stall_s:
                        for uid in list(pending):
                            pending.remove(uid)
                            self.settle(uid, "blocked", f"no resource slot became free in {int(self.stall_s)}s")
                        break
                    time.sleep(self.poll_s)
                    continue
                stalled = None
                finished, _ = wait(list(running), timeout=self.poll_s, return_when=FIRST_COMPLETED)
                for future in finished:
                    uid, slots = running.pop(future)
                    try:
                        result = future.result()
                    except Exception as error:  # one broken unit must not stop the independent ones
                        result = ("failed", {"note": f"{type(error).__name__}: {error}"})
                    status, info = result if isinstance(result, tuple) else (result, {})
                    slots = info["pools"] if "pools" in info else slots
                    self.pools.give(slots)
                    now = self.clock()
                    self.times[uid]["run_s"] = round(now - start - self.times[uid]["started_s"], 3)
                    self.final[uid] = status
                    for name in slots:
                        if info.get("failure_code") == "rate_limit":
                            self.pools.shrink(name, f"{uid} hit a rate limit")
                        elif status == DONE:
                            self.pools.success(name)
                    self.emit("finished", uid, status=status, run_s=self.times[uid]["run_s"], ran=True,
                              failure_code=info.get("failure_code"))
        return {"total_s": round(self.clock() - start, 3), "peak_parallel": self.peak, "paused": paused and bool(pending),
                "pending": list(pending), "units": self.times, "pool_peak": dict(self.pools.peak),
                "pool_changes": list(self.pools.changes)}
