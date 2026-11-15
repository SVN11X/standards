"""Ready-queue scheduler and resource pools, with no git and no model. Run: python -m unittest discover -s tests"""
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import scheduler  # noqa: E402


def loop(ids, deps=None, clash=(), work=None, **kw):
    deps = {uid: set((deps or {}).get(uid, ())) for uid in ids}
    kw.setdefault("poll_s", 0.01)
    return scheduler.Scheduler(ids, deps, {frozenset(c) for c in clash}, work or (lambda uid: "passed"), **kw)


class PoolTests(unittest.TestCase):
    def test_take_is_all_or_nothing(self):
        pools = scheduler.Pools({"local": 1, "remote_free": 2})
        self.assertTrue(pools.take(["local"]))
        self.assertFalse(pools.take(["remote_free", "local"]))
        self.assertEqual(pools.used, {"local": 1, "remote_free": 0})

    def test_rate_limit_shrinks_and_passes_grow_back(self):
        pools = scheduler.Pools({"remote_free": 2}, grow_after=2)
        pools.shrink("remote_free", "u1 hit a rate limit")
        pools.shrink("remote_free", "again")
        self.assertEqual(pools.limits["remote_free"], 1)
        pools.success("remote_free")
        self.assertEqual(pools.limits["remote_free"], 1)
        pools.success("remote_free")
        self.assertEqual(pools.limits["remote_free"], 2)
        pools.success("remote_free")
        pools.success("remote_free")
        self.assertEqual(pools.limits["remote_free"], 2)
        self.assertEqual([c["limit"] for c in pools.changes], [1, 2])

    def test_wait_take_gives_up_when_cancelled(self):
        pools = scheduler.Pools({"local": 1})
        pools.take(["local"])
        stop = threading.Event()
        stop.set()
        self.assertFalse(pools.wait_take(["local"], 5, stop))


class SchedulerTests(unittest.TestCase):
    def test_dependent_starts_when_its_own_dependency_ends_not_the_batch(self):
        """u2 needs u1. u3 is slow and independent. A batch runner would start u2 only after u3."""
        started_u2 = threading.Event()
        order = []

        def work(uid):
            order.append(uid)
            if uid == "u2":
                started_u2.set()
            if uid == "u3" and not started_u2.wait(5):
                return "failed"
            return "passed"

        result = loop(["u1", "u3", "u2"], {"u2": ["u1"]}, work=work, max_parallel=2)
        result.run()
        self.assertEqual(result.final, {"u1": "passed", "u2": "passed", "u3": "passed"})

    def test_units_that_clash_never_run_together(self):
        active, peak, lock = set(), [0], threading.Lock()

        def work(uid):
            with lock:
                active.add(uid)
                peak[0] = max(peak[0], len(active))
            time.sleep(0.05)
            with lock:
                active.discard(uid)
            return "passed"

        metrics = loop(["a", "b"], clash=[("a", "b")], work=work, max_parallel=2).run()
        self.assertEqual(peak[0], 1)
        self.assertEqual(metrics["peak_parallel"], 1)

    def test_failed_dependency_skips_only_its_dependents(self):
        result = loop(["a", "b", "c"], {"b": ["a"]}, work=lambda uid: "failed" if uid == "a" else "passed", max_parallel=2)
        result.run()
        self.assertEqual(result.final, {"a": "failed", "b": "skipped", "c": "passed"})

    def test_pause_stops_new_assignments_and_leaves_the_rest_pending(self):
        wishes = {}

        def work(uid):
            wishes["paused"] = True
            return "passed"

        result = loop(["a", "b"], {"b": ["a"]}, work=work, control=lambda: wishes)
        metrics = result.run()
        self.assertEqual(result.final, {"a": "passed"})
        self.assertTrue(metrics["paused"])
        self.assertEqual(metrics["pending"], ["b"])

    def test_cancel_before_start_never_runs_the_unit(self):
        ran = []
        result = loop(["a", "b"], work=lambda uid: ran.append(uid) or "passed", control=lambda: {"cancel": ["b"]})
        result.run()
        self.assertEqual((ran, result.final["b"]), (["a"], "cancelled"))

    def test_a_pool_held_from_outside_blocks_after_the_stall_limit(self):
        result = loop(["a"], claim=lambda uid: None, stall_s=0.05)
        result.run()
        self.assertEqual(result.final, {"a": "blocked"})

    def test_pool_limit_caps_units_at_once_and_wait_is_measured(self):
        pools = scheduler.Pools({"remote_free": 1})
        metrics = loop(["a", "b"], work=lambda uid: time.sleep(0.05) or "passed", claim=lambda uid: ["remote_free"],
                       pools=pools, max_parallel=2).run()
        self.assertEqual(metrics["pool_peak"], {"remote_free": 1})
        self.assertGreater(metrics["units"]["b"]["wait_s"], 0.03)

    def test_rate_limited_unit_shrinks_its_pool(self):
        pools = scheduler.Pools({"remote_free": 2})
        metrics = loop(["a"], work=lambda uid: ("failed", {"failure_code": "rate_limit"}), claim=lambda uid: ["remote_free"],
                       pools=pools).run()
        self.assertEqual(metrics["pool_changes"][0]["limit"], 1)

    def test_a_unit_that_raises_fails_alone(self):
        def work(uid):
            if uid == "a":
                raise ValueError("broken")
            return "passed"

        result = loop(["a", "b"], work=work, max_parallel=2)
        result.run()
        self.assertEqual(result.final, {"a": "failed", "b": "passed"})


if __name__ == "__main__":
    unittest.main()
