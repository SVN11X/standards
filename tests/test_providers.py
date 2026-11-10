"""Provider adapters and model discovery against fake servers. No real provider is called. Run: python -m unittest discover -s tests"""
import base64
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import analyze  # noqa: E402
import bench_tasks  # noqa: E402
import fakes  # noqa: E402
import orchestrate  # noqa: E402
import providers  # noqa: E402

SECRET = "test-key"
TODAY = dt.date.today().isoformat()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="std-providers-"))
        self.old = {key: os.environ.get(key) for key in ("STANDARDS_HOME", "STANDARDS_COST_MODE", "FAKE_API_KEY", "PLAN_API_KEY")}
        os.environ.update(STANDARDS_HOME=str(self.tmp / "home"), FAKE_API_KEY=SECRET, PLAN_API_KEY=SECRET)
        os.environ.pop("STANDARDS_COST_MODE", None)
        self.server, self.url = fakes.start_provider()
        self.known = fakes.provider_settings(self.url)
        self.real_load = providers.load
        providers.load = lambda path=None: self.known
        self.conf = orchestrate.policy()
        self.conf["limits"]["ollama_timeout_s"] = 10
        self.local = {"folders": [{"path": str(self.tmp), "class": "personal-public"}],
                      "free_providers": [{"id": "fake", "checked": TODAY}, {"id": "plan", "checked": TODAY}]}
        self.listings = analyze.discover_providers(self.conf, self.local, known=self.known)

    def tearDown(self):
        providers.load = self.real_load
        self.server.shutdown()
        self.server.server_close()
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def explain(self, model, local=None, mode=None):
        return orchestrate.explain("api", model, self.tmp, self.conf, local if local is not None else self.local, mode)

    def bench(self, task, model, **options):
        return orchestrate.bench_run(task, "api", model, conf=self.conf, local=self.local, **options)


class Transport(Base):
    def test_models_are_listed_and_classified(self):
        models = {m["id"]: m for m in providers.list_models("fake", self.known["fake"])}
        self.assertEqual((models["acme/good:free"]["free"], models["acme/paid"]["free"], models["acme/noprice"]["free"]), (True, False, None))
        self.assertEqual((models["acme/good:free"]["vision"], models["acme/textonly:free"]["vision"], models["acme/unsure:free"]["vision"]),
                         (True, False, None))
        self.assertEqual((models["acme/good:free"]["tools"], models["acme/textonly:free"]["tools"]), (True, False))
        self.assertEqual(models["acme/embed-text:free"]["kind"], "other")
        self.assertFalse(models["acme/retired:free"]["active"])
        self.assertEqual(providers.normalize_model("openrouter", {"id": "openrouter/free"})["kind"], "router")

    def test_every_failure_has_a_kind(self):
        conf = self.known["fake"]
        chat = lambda model, **kw: providers.chat(conf, model, [{"role": "user", "content": "hi"}], **kw)  # noqa: E731
        with self.assertRaises(providers.ProviderError) as limit:
            chat("acme/limit:free")
        self.assertEqual((limit.exception.kind, limit.exception.retry_after), ("rate-limit", "3600"))
        with self.assertRaises(providers.ProviderError) as money:
            chat("acme/bill:free")
        self.assertEqual(money.exception.kind, "payment")
        with self.assertRaises(providers.ProviderError) as tools:
            chat("acme/unsure:free", tools=bench_tasks.TOOLS)
        self.assertEqual(tools.exception.kind, "unsupported")
        with self.assertRaises(providers.ProviderError) as gone:
            providers.call(conf, "GET", "/nothing")
        self.assertEqual(gone.exception.kind, "not-found")
        closed = dict(conf, base_url="http://127.0.0.1:9/v1")
        with self.assertRaises(providers.ProviderError) as network:
            providers.call(closed, "GET", "/models", retries=0)
        self.assertEqual(network.exception.kind, "network")

    def test_a_server_error_is_retried_once(self):
        waits = []
        fakes.Provider.outage = 1
        reply, _ = providers.call(self.known["fake"], "POST", "/chat/completions",
                                  {"model": "acme/good:free", "messages": [{"role": "user", "content": "x"}]}, sleep=waits.append)
        self.assertIn("choices", reply)
        fakes.Provider.outage = 5
        with self.assertRaises(providers.ProviderError) as down:
            providers.call(self.known["fake"], "POST", "/chat/completions", {"model": "acme/good:free", "messages": []}, sleep=waits.append)
        self.assertEqual((down.exception.kind, len(waits)), ("unavailable", 2))

    def test_the_key_never_shows_and_never_travels(self):
        os.environ["FAKE_API_KEY"] = "wrong-SECRET-value"
        with self.assertRaises(providers.ProviderError) as refused:
            providers.list_models("fake", self.known["fake"])
        self.assertEqual(refused.exception.kind, "auth")
        self.assertNotIn("wrong-SECRET-value", str(refused.exception))
        os.environ["FAKE_API_KEY"] = SECRET
        elsewhere = dict(self.known["fake"], base_url=f"{self.url}/elsewhere/v1")
        with self.assertRaises(providers.ProviderError):
            providers.call(elsewhere, "GET", "/models", retries=0)
        with self.assertRaises(providers.ProviderError) as plain:
            providers.base_url({"base_url": "http://example.com/v1"})
        self.assertEqual(plain.exception.kind, "config")
        self.assertEqual(providers.missing_env({"key_env": "NOPE_KEY", "base_url": "https://x/{NOPE_ACCOUNT}/v1"}), ["NOPE_KEY", "NOPE_ACCOUNT"])
        os.environ.pop("FAKE_API_KEY")
        with self.assertRaises(providers.ProviderError) as missing:
            providers.call(self.known["fake"], "GET", "/models")
        self.assertEqual(missing.exception.kind, "no-key")

    def test_an_image_is_really_sent(self):
        item = bench_tasks.vision_items()[0]
        reply = providers.chat(self.known["fake"], "acme/good:free",
                               [{"role": "user", "content": bench_tasks.VISION_PROMPT, "images": [item["image"]]}], want_json=True)
        sent = fakes.Provider.bodies[-1]["messages"][0]["content"]
        url = next(part["image_url"]["url"] for part in sent if part["type"] == "image_url")
        self.assertTrue(url.startswith("data:image/png;base64,"))
        self.assertTrue(base64.b64decode(url.split(",", 1)[1]).startswith(b"\x89PNG"))
        self.assertEqual(json.loads(reply["message"]["content"]), item["expected"])
        with self.assertRaises(providers.ProviderError) as no_vision:
            providers.chat(self.known["plan"], "any", [{"role": "user", "content": "x", "images": [item["image"]]}])
        self.assertEqual(no_vision.exception.kind, "unsupported")

    def test_tools_round_trip(self):
        chat = lambda messages, tools: providers.chat(self.known["fake"], "acme/good:free", messages, tools)["message"]  # noqa: E731
        for case in bench_tasks.TOOL_CASES:
            self.assertEqual(bench_tasks.tool_case_ok(case, chat), (True, ""))
        sent = fakes.Provider.bodies[-1]["messages"]
        self.assertEqual(sent[1]["tool_calls"][0]["type"], "function")
        self.assertIsInstance(sent[1]["tool_calls"][0]["function"]["arguments"], str)
        self.assertEqual(sent[2]["tool_call_id"], sent[1]["tool_calls"][0]["id"])

    def test_account_check(self):
        self.assertEqual(providers.preflight("fake", self.known["fake"])["remaining"], 40)
        fakes.Provider.remaining = 0
        self.assertFalse(providers.preflight("fake", self.known["fake"])["ok"])
        self.assertIsNone(providers.preflight("plan", self.known["plan"])["remaining"])


class Gate(Base):
    def test_free_only_with_a_price_of_zero_and_the_owner_check(self):
        self.assertTrue(self.explain("fake/acme/good:free")[0])
        self.assertEqual(self.explain("fake/acme/paid")[2], "paid")
        self.assertEqual(self.explain("fake/acme/noprice")[2], "unknown-cost")
        self.assertEqual(self.explain("fake/acme/never-listed")[2], "retired")
        self.assertEqual(self.explain("trial/any")[2], "paid")
        self.assertEqual(self.explain("gone/any")[2], "retired")
        self.assertEqual(self.explain("cli/any")[2], "no-adapter")
        self.assertEqual(self.explain("nowhere/any")[2], "no-adapter")
        unchecked = dict(self.local, free_providers=[])
        self.assertEqual(self.explain("fake/acme/good:free", unchecked)[2], "owner-check")
        old = dict(self.local, free_providers=[{"id": "fake", "checked": "2020-01-01"}])
        self.assertEqual(self.explain("fake/acme/good:free", old)[2], "owner-check")
        one = dict(self.local, free_providers=[], free_models=[{"id": "fake/acme/good:free", "checked": TODAY}])
        self.assertTrue(self.explain("fake/acme/good:free", one)[0])

    def test_an_old_price_list_proves_nothing(self):
        path = providers.cache_file("fake")
        listing = json.loads(path.read_text())
        listing["fetched"] = "2020-01-01T00:00:00+00:00"
        path.write_text(json.dumps(listing))
        self.assertEqual(self.explain("fake/acme/good:free")[2], "unknown-cost")
        path.unlink()
        self.assertEqual(self.explain("fake/acme/good:free")[2], "unknown-cost")

    def test_private_and_work_code_stay_protected(self):
        def folder(cls, **extra):
            return dict(self.local, folders=[{"path": str(self.tmp), "class": cls, **extra}])
        self.assertEqual(self.explain("fake/acme/good:free", folder("work"))[2], "privacy")
        self.assertEqual(self.explain("fake/acme/good:free", folder("restricted"))[2], "privacy")
        self.assertEqual(self.explain("fake/acme/good:free", folder("personal-private"))[2], "privacy")
        self.assertTrue(self.explain("fake/acme/good:free", folder("personal-private", allow_remote_free=True))[0])
        self.assertEqual(self.explain("plan/any", folder("personal-private", allow_remote_free=True))[2], "privacy")
        self.assertTrue(self.explain("plan/any")[0])
        softened = dict(folder("personal-private", allow_remote_free=True), free_providers=[{"id": "plan", "checked": TODAY, "data_use": "none"}])
        self.assertEqual(self.explain("plan/any", softened)[2], "privacy")
        self.assertEqual(self.explain("fake/acme/good:free", mode="local-only")[2], "cost-mode")
        self.assertTrue(self.explain("fake/acme/good:free", mode="free-strict")[0])

    def test_an_ollama_cloud_model_has_unknown_cost(self):
        local = dict(self.local, free_models=[{"id": "big:cloud", "checked": TODAY, "data_use": "none"}])
        ok, why, code = orchestrate.explain("ollama", "big:cloud", self.tmp, self.conf, local)
        self.assertEqual((ok, code), (False, "unknown-cost"))


class Bench(Base):
    def test_a_good_model_passes_by_api(self):
        for task in ("classify", "extract", "summarize", "web-subprofile", "tool-call", "vision"):
            row = self.bench(task, "fake/acme/good:free")
            self.assertTrue(row.get("verified"), (task, row.get("skipped"), row.get("error"), row.get("notes")))
            self.assertEqual((row["via"], row["effective_model"]), ("api", "acme/good:free"))
        self.assertEqual(row["requests"], len(bench_tasks.VISION))
        self.assertTrue(any(isinstance(m.get("content"), list) for body in fakes.Provider.bodies for m in body["messages"]))

    def test_what_cannot_be_evaluated_is_not_a_zero(self):
        not_listed = self.bench("vision", "fake/acme/textonly:free")
        self.assertIn("does not list", not_listed["skipped"])
        refused = self.bench("tool-call", "fake/acme/unsure:free")
        self.assertEqual((refused["code"], refused.get("verified")), ("not-evaluated", False))
        self.assertIn("not evaluated", refused["skipped"])
        unsent = self.bench("tool-call", "plan/any")
        self.assertIn("does not send tools", unsent["skipped"])
        for row in (not_listed, refused, unsent):
            self.assertFalse(row.get("rate_limited"))

    def test_a_limit_a_bill_or_a_charge_stops_the_provider(self):
        for model, text in (("fake/acme/limit:free", "rate-limit"), ("fake/acme/bill:free", "payment"), ("fake/acme/charge:free", "charge")):
            row = self.bench("classify", model)
            self.assertIn(text, row["skipped"], model)
            self.assertTrue(row["rate_limited"], model)
            self.assertEqual(row["requests"], 1)
        fakes.Provider.remaining = 0
        before = len(fakes.Provider.bodies)
        out = self.bench("classify", "fake/acme/good:free")
        self.assertTrue(out["rate_limited"])
        self.assertEqual(len(fakes.Provider.bodies), before)

    def test_another_model_answering_fails(self):
        row = self.bench("classify", "fake/acme/swap:free")
        self.assertFalse(row["verified"])
        self.assertIn("zzz/another-model answered", row["error"])
        self.assertTrue(providers.same_model("acme/x:free", "acme/x"))
        self.assertFalse(providers.same_model("acme/x:free", "acme/y"))

    def test_no_key_is_pending_and_sends_nothing(self):
        local = dict(self.local, free_providers=[*self.local["free_providers"], {"id": "keyless", "checked": TODAY}])
        before = len(fakes.Provider.seen)
        row = orchestrate.bench_run("classify", "api", "keyless/any", conf=self.conf, local=local)
        self.assertEqual(row["code"], "no-key")
        paid = self.bench("classify", "fake/acme/paid")
        self.assertEqual(paid["code"], "paid")
        self.assertEqual(len(fakes.Provider.seen), before)

    def test_delegate_checks_the_reply(self):
        run = orchestrate.delegate_api('Answer JSON {"ok": true}.', "fake/acme/good:free", want_json=True, conf=self.conf,
                                       repo=self.tmp, local=self.local)
        self.assertEqual(run["state"], "verified")
        blocked = orchestrate.delegate_api("hi", "fake/acme/paid", conf=self.conf, repo=self.tmp, local=self.local)
        self.assertEqual(blocked["state"], "blocked")
        charged = orchestrate.delegate_api("hi", "fake/acme/charge:free", conf=self.conf, repo=self.tmp, local=self.local)
        self.assertEqual(charged["checks"]["no_charge"], "FAIL")

    def test_route_uses_a_provider_model_only_after_it_passed(self):
        caps = {"ollama": {"up": False}, "opencode": {}}
        route = lambda **kw: orchestrate.route("classify", self.tmp, conf=self.conf, local=self.local, caps=caps, mode="free-strict", **kw)  # noqa: E731
        self.assertEqual(route()["executor"], "blocked")
        rows = [{"task": "classify", "executor": "api", "model": "fake/acme/good:free", "seconds": 4, "verified": True}] * 3
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        chosen = route()
        self.assertEqual((chosen["executor"], chosen["model"]), ("api", "fake/acme/good:free"))
        os.environ.pop("FAKE_API_KEY")
        self.assertEqual(route()["executor"], "blocked")


class Coverage(Base):
    caps = {"ollama": {"up": False}, "opencode": {}}

    def found(self, **options):
        local = options.pop("local", self.local)
        records = analyze.coverage(self.conf, local, self.caps, {"models": []}, listings=options.pop("listings", self.listings),
                                   known=self.known, **options)
        return {record["model"] if record["model"] != "(the service)" else record["provider"]: record for record in records}

    def test_every_model_has_a_state_and_a_reason(self):
        found = self.found()
        states = {name: record["status"] for name, record in found.items()}
        self.assertEqual(states["fake/acme/good:free"], "eligible")
        self.assertEqual(states["fake/acme/paid"], "paid")
        self.assertEqual(states["fake/acme/noprice"], "unknown-cost")
        self.assertEqual(states["fake/acme/embed-text:free"], "not-chat")
        self.assertEqual(states["fake/acme/retired:free"], "retired")
        self.assertEqual((states["keyless"], states["trial"], states["gone"], states["cli"]), ("no-key", "paid", "retired", "no-adapter"))
        self.assertTrue(all(record.get("why") and record.get("endpoint") and record.get("provider") for record in found.values()))
        self.assertEqual(set(found), {f"fake/{m['id']}" for m in fakes.PROVIDER_MODELS} | {f"plan/{m['id']}" for m in fakes.PROVIDER_MODELS}
                         | {"keyless", "trial", "gone", "cli"})
        good = found["fake/acme/good:free"]
        self.assertIn("vision", good["tasks"])
        text_only = found["fake/acme/textonly:free"]
        self.assertNotIn("vision", text_only["tasks"])
        self.assertTrue(any("vision" in line for line in text_only["cannot"]))
        self.assertTrue(any("capability not evaluated" in line for line in found["plan/acme/good:free"]["cannot"]))

    def test_without_the_owner_check_everything_waits(self):
        found = self.found(local=dict(self.local, free_providers=[]))
        self.assertEqual(found["fake/acme/good:free"]["status"], "owner-check")
        self.assertIn("consent --free-provider fake", found["fake/acme/good:free"]["fix"])

    def test_local_only_asks_no_provider(self):
        before = len(fakes.Provider.seen)
        self.assertEqual(analyze.discover_providers(self.conf, self.local, "local-only", self.known), {})
        found = self.found(mode="local-only", listings={})
        self.assertEqual(found["fake"]["status"], "cost-mode")
        self.assertEqual(len(fakes.Provider.seen), before)

    def test_a_failed_listing_is_a_state_not_a_crash(self):
        os.environ["FAKE_API_KEY"] = "wrong"
        listings = analyze.discover_providers(self.conf, self.local, known=self.known)
        found = self.found(listings=listings)
        self.assertEqual(found["fake"]["status"], "discovery-failed")
        self.assertIn("auth", found["fake"]["why"])

    def test_the_plan_respects_the_request_budget(self):
        ready, _ = analyze.candidates(self.conf, self.local, self.caps, {"models": []}, listings=self.listings, known=self.known)
        quotas = analyze.account_quotas(self.listings, self.known)
        self.assertEqual(quotas, {"fake": 40})
        steps, cut = analyze.build_plan(ready, self.conf, runs=3, quotas=quotas, models=["fake/"])
        used = sum(step["requests"] for step in steps if step["provider"] == "fake")
        self.assertLessEqual(used, 40)
        self.assertTrue(any("requests fake gives" in item["why"] for item in cut))
        text = "\n".join(analyze.plan_lines(steps, cut, [], self.conf, "free-strict"))
        self.assertIn("API requests", text)
        fakes.Provider.remaining = 0
        steps, _ = analyze.build_plan(ready, self.conf, runs=1, quotas=analyze.account_quotas(self.listings, self.known), models=["fake/"])
        self.assertFalse([step for step in steps if step["provider"] == "fake"])


class NightWithProviders(Base):
    def test_local_work_finishes_while_a_provider_waits_for_its_key(self):
        ollama, url = fakes.start_ollama()
        try:
            os.environ["FAKE_API_KEY"] = "SECRET-do-not-store"
            fakes.Provider.key = "SECRET-do-not-store"
            fakes.Ollama.extra = [{"name": "newcomer:2b", "size": 1_500_000_000}]
            self.conf["executors"]["ollama"].update(url=url, prefer=[])
            self.conf["analysis"].update(runs=1)
            caps = {"ollama": orchestrate.detect_ollama(self.conf["executors"]["ollama"], show=True), "opencode": {},
                    "gpu": {"vram_total_mib": 6144}, "ram_bytes": 16 * 1024 ** 3}
            listings = analyze.discover_providers(self.conf, self.local, known=self.known)
            said = []
            state = analyze.run_plan(self.conf, self.local, caps, {"models": []}, tasks=["classify", "vision"], say=said.append,
                                     listings=listings, known=self.known, models=["newcomer", "good"])
            self.assertTrue(state["complete"])
            rows = {(r["task"], r["executor"], r["model"]): r for r in orchestrate.bench_rows()}
            self.assertTrue(rows[("classify", "ollama", "newcomer:2b")]["verified"])
            self.assertTrue(rows[("classify", "api", "fake/acme/good:free")]["verified"])
            self.assertTrue(rows[("vision", "api", "fake/acme/good:free")]["verified"])
            waiting = [item for item in state["left_out"] if item["provider"] == "keyless"]
            self.assertEqual(waiting[0]["status"], "no-key")
            report = analyze.build_report(self.conf, {"models": []}, state=state)
            self.assertIn("missing in the environment: KEYLESS_API_KEY_NOT_SET", report)
            self.assertIn("Inference by API or by a program", report)
            self.assertNotIn("## Full agent", report)
            self.assertIn("not a score of zero", report)
            stored = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in (self.tmp / "home").rglob("*") if path.is_file())
            for text in (stored, report, "\n".join(said), json.dumps(listings)):
                self.assertNotIn("SECRET-do-not-store", text)
        finally:
            fakes.Provider.key = SECRET
            ollama.shutdown()
            ollama.server_close()

    def test_a_limit_stops_that_provider_and_nothing_else(self):
        self.conf["analysis"].update(runs=1)
        said = []
        state = analyze.run_plan(self.conf, self.local, {"ollama": {"up": False}, "opencode": {}}, {"models": []}, tasks=["classify"],
                                 say=said.append, listings=self.listings, known=self.known, models=["fake/acme/limit", "fake/acme/swap", "plan/acme/good"])
        rows = [(r["executor"], r["model"]) for r in orchestrate.bench_rows()]
        self.assertFalse([row for row in rows if row[1] and row[1].startswith("fake/")])
        self.assertIn("fake", state["stopped"])
        self.assertIn("not used again", state["done"]["classify|api|fake/acme/swap:free|1"]["skipped"])
        self.assertIn(("api", "plan/acme/good:free"), rows)
        self.assertIn(("tools", None), rows)
        self.assertTrue(state["complete"])


class OllamaDiscovery(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="std-discover-"))
        self.old_home = os.environ.get("STANDARDS_HOME")
        os.environ["STANDARDS_HOME"] = str(self.tmp / "home")
        self.server, url = fakes.start_ollama()
        self.real_load = providers.load
        providers.load = lambda path=None: {}
        self.conf = orchestrate.policy()
        self.conf["executors"]["ollama"].update(url=url, prefer=[], never_chat=[])
        fakes.Ollama.extra = [{"name": "newcomer:2b", "size": 1_500_000_000},
                              {"name": "huge:70b", "size": 45_000_000_000},
                              {"name": "giant:cloud", "size": 400, "remote_host": "https://ollama.com", "remote_model": "giant"},
                              {"name": "plain:1b", "size": 900_000_000}]
        fakes.Ollama.silent = {"plain:1b"}
        self.caps = {"ollama": orchestrate.detect_ollama(self.conf["executors"]["ollama"], show=True), "opencode": {},
                     "gpu": {"vram_total_mib": 6144}, "ram_bytes": 16 * 1024 ** 3}

    def tearDown(self):
        providers.load = self.real_load
        self.server.shutdown()
        self.server.server_close()
        if self.old_home is None:
            os.environ.pop("STANDARDS_HOME", None)
        else:
            os.environ["STANDARDS_HOME"] = self.old_home

    def found(self, catalog=None):
        records = analyze.coverage(self.conf, {}, self.caps, catalog or {"models": []})
        return {record["model"]: record for record in records}

    def test_an_installed_model_appears_without_the_catalog(self):
        found = self.found()
        new = found["newcomer:2b"]
        self.assertEqual((new["status"], new["provider"], new["in_catalog"]), ("eligible", "ollama-local", False))
        self.assertIn("vision", new["tasks"])
        self.assertIn("tool-call", new["tasks"])
        self.assertTrue(new["endpoint"].startswith("http://127.0.0.1"))
        steps, _ = analyze.build_plan([new], self.conf, runs=1)
        self.assertIn("classify|ollama|newcomer:2b|1", [step["key"] for step in steps])

    def test_kinds_and_limits(self):
        found = self.found()
        self.assertEqual((found["embed:1b"]["status"], found["huge:70b"]["status"]), ("not-chat", "resources"))
        self.assertIn("GB", found["huge:70b"]["why"])
        cloud = found["giant:cloud"]
        self.assertEqual((cloud["provider"], cloud["remote"], cloud["status"]), ("ollama-cloud", True, "unknown-cost"))
        plain = found["plain:1b"]
        self.assertEqual(plain["status"], "eligible")
        self.assertNotIn("vision", plain["tasks"])
        self.assertTrue(any("capability not evaluated" in line for line in plain["cannot"]))

    def test_the_catalog_restricts_and_names_what_is_missing(self):
        catalog = {"models": [{"id": "newcomer:2b", "executor": "ollama", "blocked": "license does not allow this use"},
                              {"id": "wanted:3b", "executor": "ollama", "source": "https://example.com/wanted"}]}
        found = self.found(catalog)
        self.assertEqual((found["newcomer:2b"]["status"], found["newcomer:2b"]["why"]), ("blocked", "license does not allow this use"))
        self.assertEqual((found["wanted:3b"]["status"], found["wanted:3b"]["fix"]), ("not-installed", "ollama pull wanted:3b"))

    def test_an_unmeasured_machine_is_said_so(self):
        caps = dict(self.caps, gpu=None, ram_bytes=None)
        records = {r["model"]: r for r in analyze.coverage(self.conf, {}, caps, {"models": []})}
        self.assertEqual(records["huge:70b"]["status"], "eligible")
        self.assertIn("memory not measured", records["huge:70b"]["why"])

    def test_prepare_lists_states_without_fixed_counts(self):
        text = "\n".join(analyze.prepare_lines(self.conf, {}, self.caps, {"models": []}))
        for wanted in ("newcomer:2b", "ollama-cloud", "[not enough resources]", "[cost unknown]", "[not a chat model]", "Found, by provider:"):
            self.assertIn(wanted, text)
        every = "\n".join(analyze.prepare_lines(self.conf, {}, self.caps, {"models": []}, every=True))
        self.assertIn("giant:cloud", every)


if __name__ == "__main__":
    unittest.main()
