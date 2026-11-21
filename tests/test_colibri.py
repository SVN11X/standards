"""Colibri as a local provider: discovery, channel, routing without silent substitution, the ecosystem doctor."""
import datetime as dt
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import analyze  # noqa: E402
import bench_tasks  # noqa: E402
import colibri  # noqa: E402
import ecosystem  # noqa: E402
import orchestrate  # noqa: E402


class Models(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"data": [{"id": "fake-coder"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def serve():
    server = http.server.HTTPServer(("127.0.0.1", 0), Models)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class ColibriTests(unittest.TestCase):
    def test_detect_reads_model_ids(self):
        server = serve()
        try:
            info = orchestrate.detect_colibri({"url": f"http://127.0.0.1:{server.server_port}"})
        finally:
            server.shutdown()
            server.server_close()
        self.assertTrue(info["up"])
        self.assertEqual(info["models"], ["fake-coder"])

    def test_detect_reports_a_stopped_server(self):
        info = orchestrate.detect_colibri({"url": "http://127.0.0.1:9"}, timeout=0.5)
        self.assertFalse(info["up"])
        self.assertIn("error", info)

    def test_loopback_colibri_is_local_and_a_remote_one_is_not(self):
        conf = orchestrate.policy()
        self.assertEqual(orchestrate.channel("opencode", "colibri/fake-coder", conf), "local")
        conf["executors"]["colibri"]["url"] = "http://example.com:8000"
        self.assertEqual(orchestrate.channel("colibri", "fake-coder", conf), "remote_free")

    def test_stopped_colibri_is_refused_and_never_replaced(self):
        conf, caps = orchestrate.policy(), {"opencode": {"path": "opencode"}, "colibri": {"up": False, "models": []}}
        ok, why, model = orchestrate.eligible("colibri", "edit-small", ROOT, 0, conf, {}, caps)
        self.assertFalse(ok)
        self.assertIsNone(model)
        self.assertIn("not running", why)

    def test_running_colibri_needs_proof_where_the_policy_asks_for_it(self):
        conf, local = orchestrate.policy(), {}
        caps = {"opencode": {"path": "opencode"}, "colibri": {"up": True, "models": ["fake-coder"]}}
        ok, _, model = orchestrate.eligible("colibri", "edit-small", ROOT, 0, conf, local, caps, {}, None, False, {})
        self.assertTrue(ok)
        self.assertEqual(model, "colibri/fake-coder")
        ok, why, _ = orchestrate.eligible("colibri", "edit-large", ROOT, 0, conf, local, caps, {}, None, True, {})
        self.assertFalse(ok)
        self.assertIn("bench class", why)

    def test_ecosystem_spec_keeps_the_four_owner_models(self):
        keep = ecosystem.spec()["ollama"]["keep"]
        self.assertEqual(sorted(keep), sorted(["qwen3.5:4b", "qwen3.5:9b", "qwen2.5:7b", "qwen3-embedding:0.6b"]))
        self.assertFalse(set(keep) & set(ecosystem.spec()["ollama"]["install"]))

    def test_register_refuses_when_colibri_is_down(self):
        original = colibri.probe
        colibri.probe = lambda conf=None: {"up": False, "models": []}
        try:
            self.assertFalse(colibri.register(ROOT / "nonexistent")["ok"])
        finally:
            colibri.probe = original


class McpRegistrationTests(unittest.TestCase):
    def test_mcp_entry_denies_the_tools_that_change_the_machine_and_keeps_other_keys(self):
        data = {"tools": {"webfetch": False}, "mcp": {"other": {"type": "remote", "url": "https://example.test"}}}
        colibri.apply_mcp(data, {"home": "C:/colibri"})
        entry = data["mcp"]["colibri"]
        self.assertEqual((entry["type"], entry["command"][-1], entry["enabled"]), ("local", "mcp", True))
        self.assertTrue(entry["command"][-2].replace("\\", "/").endswith("c/coli"))
        self.assertIn("other", data["mcp"])
        self.assertEqual({k: v for k, v in data["tools"].items() if v is False},
                         {"webfetch": False, "colibri_install": False, "colibri_start": False, "colibri_stop": False})
        self.assertTrue(all(name.startswith("colibri_") for name in colibri.DENIED_MCP_TOOLS))


class AnalyzerAndPinTests(unittest.TestCase):
    """Colibri in the analyzer coverage, and a request that pins Colibri: the model served, its evidence and the block reason."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        old = os.environ.get("STANDARDS_HOME")
        os.environ["STANDARDS_HOME"] = self.tmp.name
        self.addCleanup(lambda: os.environ.__setitem__("STANDARDS_HOME", old) if old else os.environ.pop("STANDARDS_HOME", None))
        self.real_load = orchestrate.providers.load
        orchestrate.providers.load = lambda path=None: {}
        self.addCleanup(setattr, orchestrate.providers, "load", self.real_load)
        self.conf = orchestrate.policy()
        self.caps = {"opencode": {"path": "opencode", "models": []}, "colibri": {"up": True, "models": ["fake-coder"], "url": "x"},
                     "ollama": {"up": False}}

    def history(self, model, verified, n, timeout=False, task="fix-bug"):
        rows = [{"task": task, "executor": "colibri", "model": model, "seconds": 600, "verified": verified, "timeout": timeout,
                 "date": dt.datetime.now(dt.timezone.utc).isoformat(), "grader": bench_tasks.grader_version(task)}] * n
        with orchestrate.bench_file().open("a", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(row) + "\n" for row in rows))

    def colibri_records(self, caps, local=None, local_agents=False):
        found = analyze.coverage(self.conf, local or {}, caps, {}, "local-only", local_agents)
        return {r["model"]: r for r in found if analyze.route_key(r)[0] == "colibri"}

    def test_a_served_model_is_eligible_as_a_coding_agent_only_with_local_agents(self):
        record = self.colibri_records(self.caps)["colibri/fake-coder"]
        self.assertEqual((record["status"], record["tasks"]), ("eligible", []))
        self.assertIn("--local-agents", record["cannot"][0])
        record = self.colibri_records(self.caps, local_agents=True)["colibri/fake-coder"]
        self.assertEqual(record["tasks"], list(bench_tasks.AGENT_TASKS))
        steps, _ = analyze.build_plan([record], self.conf, runs=1, tasks=["fix-bug"])
        self.assertEqual([(s["executor"], s["model"], s["task"]) for s in steps if s["executor"] != "tools"],
                         [("colibri", "colibri/fake-coder", "fix-bug")])

    def test_a_stopped_colibri_is_unavailable_and_keeps_the_history_of_its_id(self):
        self.history("colibri/qwen3-coder-30b", False, 1, timeout=True)
        caps = {**self.caps, "colibri": {"up": False, "models": []}}
        record = self.colibri_records(caps)["colibri/qwen3-coder-30b"]
        self.assertEqual(record["status"], "unavailable")
        self.assertIn("fix-bug: 0 of 1 runs accepted (3 needed), 1 timed out", record["evidence"])
        self.assertEqual(record["fix"], "python scripts/colibri.py ensure")

    def test_another_served_id_keeps_its_own_evidence(self):
        self.history("colibri/old-coder", True, 3)
        records = self.colibri_records(self.caps)
        self.assertEqual(records["colibri/old-coder"]["status"], "not-served")
        self.assertIn("3 of 3", records["colibri/old-coder"]["evidence"])
        self.assertEqual(records["colibri/fake-coder"]["evidence"], "no bench run yet")

    def test_an_opencode_alias_of_the_colibri_model_is_counted_once(self):
        today = dt.date.today().isoformat()
        found = analyze.coverage(self.conf, {"free_models": [{"id": "colibri/fake-coder", "checked": today}]}, self.caps, {}, "local-only")
        same = [r for r in found if r["model"] == "colibri/fake-coder"]
        self.assertEqual([r["executor"] for r in same], ["colibri"])

    def route(self, task="edit-small", caps=None, model=None):
        return orchestrate.route(task, ROOT, conf=self.conf, local={}, caps=caps or self.caps, mode="local-only", catalog={},
                                 cool={}, pin="colibri", model=model)

    def test_a_pinned_colibri_names_the_model_and_its_evidence(self):
        self.history("colibri/fake-coder", False, 1, timeout=True)
        decision = self.route()
        self.assertEqual((decision["executor"], decision["model"], decision["fallbacks"]), ("colibri", "colibri/fake-coder", []))
        self.assertIn("fix-bug: 0 of 1 runs accepted (3 needed), 1 timed out", decision["reasons"][-1])

    def test_a_pinned_colibri_is_blocked_with_the_reason_and_never_replaced(self):
        down = self.route(caps={**self.caps, "colibri": {"up": False, "models": []}})
        self.assertEqual((down["executor"], down["fallbacks"]), ("blocked", []))
        self.assertIn("Colibri is not running", down["rejected"][0]["why"])
        other = self.route(model="other-coder")
        self.assertEqual(other["executor"], "blocked")
        self.assertIn("serves colibri/fake-coder, not colibri/other-coder", other["rejected"][0]["why"])
        self.history("colibri/fake-coder", False, 2, timeout=True)
        failed = self.route()
        self.assertEqual(failed["executor"], "blocked")
        self.assertIn("failed the bench class", failed["rejected"][0]["why"])
        unlisted = self.route(task="classify")
        self.assertEqual(unlisted["executor"], "blocked")
        self.assertIn("does not list colibri for classify", unlisted["reasons"][0])

    def test_counters_nobody_reported_read_n_a(self):
        text = orchestrate.usage_text({"model": "colibri/fake-coder", "input_chars": 900, "seconds": 12.5})
        self.assertEqual(text, "model colibri/fake-coder, input n/a tokens (900 characters), output n/a tokens, 12.5 s")

    def test_the_night_run_does_not_repeat_a_failure_with_nothing_changed(self):
        self.history("colibri/fake-coder", False, 2, timeout=True)
        record = self.colibri_records(self.caps, local_agents=True)["colibri/fake-coder"]
        steps, cut = analyze.build_plan([record], self.conf, tasks=["fix-bug"])
        self.assertFalse([s for s in steps if s["executor"] == "colibri"])
        self.assertEqual(cut[0]["status"], "failed-before")
        again, _ = analyze.build_plan([record], self.conf, runs=1, tasks=["fix-bug"])
        self.assertTrue([s for s in again if s["executor"] == "colibri"])

    def test_two_fresh_passes_get_only_the_missing_run(self):
        self.history("colibri/fake-coder", True, 2)
        record = self.colibri_records(self.caps, local_agents=True)["colibri/fake-coder"]
        steps, _ = analyze.build_plan([record], self.conf, tasks=["fix-bug"])
        self.assertEqual([s["run"] for s in steps if s["executor"] == "colibri"], [3])

    def test_an_edit_task_counts_as_authorized_through_its_bench_class(self):
        found = [{"executor": "colibri", "model": "colibri/fake-coder", "status": "eligible", "tasks": ["fix-bug"]}]
        table = {r["task"]: r for r in orchestrate.model_states(found, self.conf)}
        self.assertEqual(table["edit-small"]["authorized"], "yes")


if __name__ == "__main__":
    unittest.main()
