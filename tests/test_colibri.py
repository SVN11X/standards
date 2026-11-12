"""Colibri as a local provider: discovery, channel, routing without silent substitution, the ecosystem doctor."""
import http.server
import json
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

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


if __name__ == "__main__":
    unittest.main()
