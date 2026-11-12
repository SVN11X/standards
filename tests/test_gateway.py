"""Gateway adapter against a fake gateway on loopback. No real gateway is installed and no network is used.
Each class names a condition of the FreeLLMAPI entry in radar/radar.yml. Run: python -m unittest discover -s tests"""
import copy
import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import fakes  # noqa: E402
import orchestrate  # noqa: E402
import providers  # noqa: E402

TODAY = dt.date.today().isoformat()
MESSAGES = [{"role": "user", "content": "hello"}]


class GatewayBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="std-gateway-"))
        self.old = {key: os.environ.get(key) for key in ("STANDARDS_HOME", "STANDARDS_COST_MODE", "FAKE_API_KEY")}
        os.environ.update(STANDARDS_HOME=str(self.tmp / "home"), FAKE_API_KEY="test-key")
        os.environ.pop("STANDARDS_COST_MODE", None)
        self.server, self.url = fakes.start_gateway()
        self.known = fakes.gateway_settings(self.url)
        self.real_load = providers.load
        providers.load = lambda path=None: self.known
        self.conf = orchestrate.policy()
        self.conf["limits"]["ollama_timeout_s"] = 10
        self.local = {"folders": [{"path": str(self.tmp), "class": "personal-public"}],
                      "free_providers": [{"id": "gate", "checked": TODAY}]}

    def tearDown(self):
        providers.load = self.real_load
        self.server.shutdown()
        self.server.server_close()
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def chat(self):
        return providers.chat(self.known["gate"], "auto", MESSAGES)

    def delegate(self):
        return orchestrate.delegate_api("hello", "gate/auto", conf=self.conf, repo=self.tmp, local=self.local)


class AllowedList(GatewayBase):
    """Condition 1: the gateway can be limited to an allowed list before anything is sent."""

    def test_the_list_travels_with_the_request(self):
        self.chat()
        self.assertEqual(fakes.Gateway.bodies[0]["gateway"]["allow"], ["groq/llama-3", "mistral/small"])

    def test_an_empty_or_missing_list_sends_nothing(self):
        for allow in ([], None, ["no-slash"]):
            self.known["gate"]["gateway"] = {"allow": allow}
            with self.assertRaises(providers.ProviderError) as caught:
                self.chat()
            self.assertEqual(caught.exception.kind, "config")
        self.assertEqual(fakes.Gateway.bodies, [])

    def test_a_delegate_with_no_list_is_not_sent(self):
        self.known["gate"]["gateway"] = {}
        self.assertEqual(self.delegate()["state"], "failed")
        self.assertEqual(fakes.Gateway.bodies, [])


class Fallback(GatewayBase):
    """Condition 2: the internal fallback stays inside the list."""

    def test_fallback_moves_to_the_next_allowed_provider(self):
        fakes.Gateway.down = {"groq/llama-3"}
        self.assertEqual(self.chat()["provider"], "mistral/small")

    def test_fallback_never_reaches_a_provider_outside_the_list(self):
        fakes.Gateway.down = {"groq/llama-3", "mistral/small"}
        with self.assertRaises(providers.ProviderError) as caught:
            self.chat()
        self.assertEqual(caught.exception.kind, "unavailable")

    def test_a_gateway_that_ignores_the_list_is_refused(self):
        fakes.Gateway.leaky = True
        fakes.Gateway.down = {"groq/llama-3", "mistral/small"}
        with self.assertRaises(providers.ProviderError) as caught:
            self.chat()
        self.assertEqual(caught.exception.kind, "privacy")
        run = self.delegate()
        self.assertEqual(run["state"], "failed")
        self.assertNotIn("effective_provider", run)


class Answered(GatewayBase):
    """Condition 3: the provider that answered is recorded."""

    def test_the_answering_provider_is_recorded(self):
        fakes.Gateway.down = {"groq/llama-3"}
        run = self.delegate()
        self.assertEqual(run["effective_provider"], "mistral/small")
        self.assertEqual(run["checks"]["reply"], "PASS")

    def test_a_reply_that_does_not_say_is_refused(self):
        fakes.Gateway.silent = True
        with self.assertRaises(providers.ProviderError) as caught:
            self.chat()
        self.assertEqual(caught.exception.kind, "bad-reply")


class NoCharge(GatewayBase):
    """Condition 4: no charge is possible, fusion and caching stay off."""

    def test_the_request_turns_fusion_caching_and_billing_off(self):
        self.chat()
        sent = fakes.Gateway.bodies[0]["gateway"]
        self.assertEqual((sent["fusion"], sent["cache"], sent["billing"]), (False, False, "refuse"))

    def test_a_setting_that_turns_fusion_or_caching_on_sends_nothing(self):
        for flag in ("fusion", "cache"):
            self.known["gate"]["gateway"] = {"allow": ["groq/llama-3"], flag: True}
            with self.assertRaises(providers.ProviderError):
                self.chat()
        self.assertEqual(fakes.Gateway.bodies, [])

    def test_a_fused_or_cached_reply_is_refused(self):
        for flag in ("fusion", "cached"):
            setattr(fakes.Gateway, flag, True)
            with self.assertRaises(providers.ProviderError) as caught:
                self.chat()
            self.assertEqual(caught.exception.kind, "privacy")
            setattr(fakes.Gateway, flag, False)

    def test_a_charge_fails_the_run(self):
        fakes.Gateway.charge = True
        self.assertEqual(self.delegate()["checks"]["no_charge"], "FAIL")

    def test_a_gateway_priced_as_paid_is_not_called(self):
        self.known["gate"]["cost"] = "paid"
        ok, _, code = orchestrate.explain("api", "gate/auto", self.tmp, self.conf, self.local)
        self.assertEqual((ok, code), (False, "paid"))
        self.assertEqual(fakes.Gateway.bodies, [])


class Remote(GatewayBase):
    """orchestrate.py counts any gateway as remote, even on a loopback address."""

    def test_a_work_or_restricted_repository_never_reaches_it(self):
        for cls in ("work", "restricted"):
            local = {**self.local, "folders": [{"path": str(self.tmp), "class": cls}]}
            ok, _, code = orchestrate.explain("api", "gate/auto", self.tmp, self.conf, local)
            self.assertEqual((ok, code), (False, "privacy"))

    def test_local_only_mode_refuses_it(self):
        ok, _, code = orchestrate.explain("api", "gate/auto", self.tmp, self.conf, self.local, "local-only")
        self.assertEqual((ok, code), (False, "cost-mode"))

    def test_a_local_executor_pointed_at_a_gateway_is_still_remote(self):
        local = {**self.local, "folders": [{"path": str(self.tmp), "class": "work"}]}
        for executor in ("ollama", "colibri"):
            conf = copy.deepcopy(self.conf)
            conf["executors"].setdefault(executor, {})["url"] = self.url
            self.assertEqual(orchestrate.channel(executor, "auto", conf), "remote_free")
            self.assertFalse(orchestrate.explain(executor, "auto", self.tmp, conf, local)[0])

    def test_a_real_local_address_stays_local(self):
        conf = copy.deepcopy(self.conf)
        conf["executors"]["ollama"]["url"] = "http://127.0.0.1:9"
        self.assertEqual(orchestrate.channel("ollama", "llama3", conf), "local")


if __name__ == "__main__":
    unittest.main()
