"""Unit tests for the verification and orchestration scripts. Run: python -m unittest discover -s tests"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hooks"))

import autopilot  # noqa: E402
import bench_tasks  # noqa: E402
import evidence  # noqa: E402
import memory  # noqa: E402
import orchestrate  # noqa: E402
import preserve  # noqa: E402
import safe_patch  # noqa: E402
import session_probe  # noqa: E402
import standard  # noqa: E402


def git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@localhost", "-C", str(repo), *args],
                   check=True, capture_output=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="std-test-"))
        self.old_home = os.environ.get("STANDARDS_HOME")
        os.environ["STANDARDS_HOME"] = str(self.tmp / "home")

    def tearDown(self):
        if self.old_home is None:
            os.environ.pop("STANDARDS_HOME", None)
        else:
            os.environ["STANDARDS_HOME"] = self.old_home
        subprocess.run(["git", "worktree", "prune"], cwd=self.tmp, capture_output=True, check=False)

    def repo(self, name="repo"):
        path = self.tmp / name
        path.mkdir()
        (path / "a.txt").write_text("one\n", encoding="utf-8")
        git(path, "init", "-q")
        git(path, "add", "-A")
        git(path, "commit", "-q", "-m", "init")
        return path


class Autopilot(Base):
    def test_linked_worktree(self):
        repo = self.repo()
        linked = self.tmp / "linked"
        git(repo, "worktree", "add", "-q", "-b", "auto", str(linked))
        self.assertTrue((linked / ".git").is_file())
        (linked / "docs").mkdir()
        (linked / "docs" / "improvement-plan.md").write_text("- [ ] next item\n", encoding="utf-8")
        hook = {"cwd": str(linked / "docs"), "session_id": f"t-{os.getpid()}"}
        self.assertIsNone(autopilot.decide(hook))
        marker = Path(subprocess.run(["git", "-C", str(linked), "rev-parse", "--git-path", "standard-autopilot"],
                                     capture_output=True, text=True, check=True).stdout.strip())
        marker = marker if marker.is_absolute() else linked / marker
        marker.write_text("", encoding="utf-8")
        self.assertEqual(autopilot.repository_root(linked / "docs").resolve(), linked.resolve())
        decision = autopilot.decide(hook)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("1 pending", decision["reason"])


class Timeouts(Base):
    def test_a_timeout_also_stops_the_child_that_holds_the_pipe(self):
        child = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); time.sleep(60)"
        result = orchestrate.run([sys.executable, "-c", child], timeout=2)
        self.assertTrue(result["timeout"])
        self.assertLess(result["seconds"], 25)


class WorkingFolder(Base):
    def test_pwd_follows_the_folder_the_command_runs_in(self):
        result = orchestrate.run([sys.executable, "-c", "import os; print(os.environ.get('PWD'))"], cwd=self.tmp,
                                 env={**os.environ, "PWD": "/somewhere/else"})
        self.assertEqual(result["stdout"].strip(), str(self.tmp))


class Route(Base):
    caps = {"ollama": {"up": False}, "opencode": {"path": "/bin/opencode"}}

    def local(self, cls="personal-public", **extra):
        return {"folders": [{"path": str(self.tmp), "class": cls, **extra}],
                "free_models": [{"id": "opencode/glm-5.3-flash-free", "checked": dt.date.today().isoformat()}]}

    def test_tools_first(self):
        self.assertEqual(orchestrate.route("lint", self.tmp, local={}, caps=self.caps)["executor"], "tools")

    def test_small_edit_goes_to_opencode(self):
        decision = orchestrate.route("edit-small", self.tmp, local=self.local(), caps=self.caps)
        self.assertEqual((decision["executor"], decision["model"]), ("opencode", "opencode/glm-5.3-flash-free"))

    def test_bench_history_picks_the_model(self):
        local = self.local()
        local["free_models"].append({"id": "opencode/deepseek-v4.1-flash-free", "checked": dt.date.today().isoformat()})
        rows = [{"task": "fix-bug", "executor": "opencode", "model": m, "seconds": s, "verified": True}
                for m, s in (("opencode/glm-5.3-flash-free", 24), ("opencode/deepseek-v4.1-flash-free", 21))] * 3
        rows.append({"task": "fix-bug", "executor": "opencode", "model": "opencode/glm-5.3-flash-free", "seconds": 5, "verified": True})
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        decision = orchestrate.route("fix-test", self.tmp, local=local, caps=self.caps)
        self.assertEqual(decision["model"], "opencode/deepseek-v4.1-flash-free")
        self.assertIn("measured on this machine", " ".join(decision["reasons"]))

    def test_a_failed_specific_class_is_not_rescued_by_a_broader_one(self):
        def rows(task, model, ok):
            return [{"task": task, "executor": "ollama", "model": model, "seconds": 5, "verified": ok,
                     "grader": bench_tasks.grader_version(task)}] * 3
        history = (rows("classify", "a:1b", True) + rows("summarize", "a:1b", False)
                   + rows("classify", "b:1b", True) + rows("classify", "c:1b", True) + rows("summarize", "c:1b", True))
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in history) + "\n", encoding="utf-8")
        passed = orchestrate.measured_models("summarize-short", orchestrate.policy())
        self.assertEqual({key[1]: row["task"] for key, row in passed.items()}, {"b:1b": "classify", "c:1b": "summarize"})
        self.assertEqual(len(orchestrate.measured_models("classify", orchestrate.policy())), 3)

    def test_old_runs_and_other_identities_do_not_count(self):
        now = dt.datetime.now(dt.timezone.utc)
        def row(executor, days=1, **hardware):
            return {"task": "fix-bug", "executor": executor, "model": "m", "seconds": 5, "verified": True,
                    "date": (now - dt.timedelta(days=days)).isoformat(), "hardware": hardware}
        current = {"opencode": "1.4.2", "gpu": {"name": "RTX A"}}
        keep = orchestrate.fresh_rows([row("opencode", opencode="1.4.9"), row("opencode", 31, opencode="1.4.9"),
                                       row("opencode", opencode="1.5.0"), row("ollama", gpu={"name": "RTX A"}),
                                       row("ollama", gpu={"name": "RTX B"}), row("opencode", opencode=None)], 30, current, now)
        self.assertEqual([(r["executor"], r["hardware"]) for r in keep],
                         [("opencode", {"opencode": "1.4.9"}), ("ollama", {"gpu": {"name": "RTX A"}}), ("opencode", {"opencode": None})])
        legacy = {"task": "fix-bug", "executor": "opencode", "model": "m", "seconds": 5, "verified": True}
        self.assertEqual(orchestrate.fresh_rows([legacy], 30, current, now), [legacy])

    def test_models_lifecycle_states_and_expiry(self):
        now = dt.datetime.now(dt.timezone.utc)
        stamp = (now - dt.timedelta(days=10)).isoformat()
        rows = [{"task": "classify", "executor": "ollama", "model": "a:1b", "seconds": 5, "verified": True, "date": stamp,
                 "grader": bench_tasks.grader_version("classify")}] * 3
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        found = [{"executor": "ollama", "model": "a:1b", "status": "eligible", "tasks": ["classify"]},
                 {"executor": "ollama", "model": "b:1b", "status": "eligible", "tasks": ["classify"]},
                 {"executor": "ollama", "model": "c:1b", "status": "unknown-cost", "tasks": []}]
        table = {(r["task"], r["model"]): r for r in orchestrate.model_states(found, orchestrate.policy(), now)}
        tested = table[("classify", "a:1b")]
        self.assertEqual((tested["tested"], tested["authorized"]), ("yes (classify)", "yes"))
        self.assertEqual(tested["expires"], (dt.datetime.fromisoformat(stamp) + dt.timedelta(days=30)).date().isoformat())
        self.assertEqual(table[("classify", "b:1b")]["tested"], "no")
        self.assertNotIn(("classify", "c:1b"), table)

    def test_a_model_that_failed_the_class_is_not_a_model_nobody_measured(self):
        def rows(model, verified, n):
            return [{"task": "fix-bug", "executor": "colibri", "model": model, "seconds": 600, "verified": verified,
                     "grader": bench_tasks.grader_version("fix-bug")}] * n
        history = rows("colibri/slow", False, 2) + rows("colibri/once", False, 1) + rows("colibri/good", True, 3)
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in history) + "\n", encoding="utf-8")
        conf = orchestrate.policy()
        failed = orchestrate.failed_models("edit-small", conf)
        self.assertEqual({key[1] for key in failed}, {"colibri/slow"})
        self.assertEqual({key[1] for key in orchestrate.measured_models("edit-small", conf)}, {"colibri/good"})

    def test_a_proven_local_ollama_model_is_a_candidate_of_the_opencode_executor(self):
        conf = orchestrate.policy()
        stats = {"runs": 3, "pass_rate": 1.0, "p50_s": 300.0}
        caps = {"opencode": {"path": "opencode"}}
        measured = {("opencode", "ollama/m:9b"): stats}
        ok, _, model = orchestrate.eligible("opencode", "edit-small", Path("."), 0, conf, {}, caps, measured,
                                            "local-only", False, {}, set())
        self.assertEqual((ok, model), (True, "ollama/m:9b"))
        ok, _, model = orchestrate.eligible("opencode", "edit-small", Path("."), 0, conf, {}, caps, {},
                                            "local-only", False, {}, set())
        self.assertFalse(ok)

    def test_models_lists_a_proven_model_the_coverage_does_not_know(self):
        rows = [{"task": "fix-bug", "executor": "opencode", "model": "ollama/m:9b", "seconds": 300, "verified": True,
                 "date": dt.datetime.now(dt.timezone.utc).isoformat(), "grader": bench_tasks.grader_version("fix-bug")}] * 3
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        table = {(r["task"], r["model"]): r for r in orchestrate.model_states([], orchestrate.policy())}
        row = table[("edit-small", "ollama/m:9b")]
        self.assertEqual((row["tested"], row["discovered"]), ("yes (fix-bug)", "not in the coverage"))

    def test_stale_history_does_not_prove_a_model(self):
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90)).isoformat()
        rows = [{"task": "classify", "executor": "ollama", "model": "a:1b", "seconds": 5, "verified": True, "date": old,
                 "grader": bench_tasks.grader_version("classify")}] * 3
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        self.assertEqual(orchestrate.measured_models("classify", orchestrate.policy()), {})

    def test_runs_graded_by_an_older_rule_do_not_count(self):
        old = [{"task": "summarize", "executor": "ollama", "model": "a:1b", "seconds": 5, "verified": False}] * 3
        new = [{"task": "summarize", "executor": "ollama", "model": "a:1b", "seconds": 6, "verified": True}] * 3
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in old) + "\n", encoding="utf-8")
        for row in new:
            orchestrate.append_bench(dict(row))
        rows = orchestrate.bench_rows()
        self.assertEqual((len(rows), len(orchestrate.current_rows(rows))), (6, 3))
        summary = orchestrate.summarize_bench(rows)[0]
        self.assertEqual((summary["runs"], summary["pass_rate"]), (3, 1.0))
        self.assertIn(("ollama", "a:1b"), orchestrate.measured_models("summarize-short", orchestrate.policy()))
        classify = [{"task": "classify", "executor": "ollama", "model": "a:1b", "seconds": 5, "verified": True}]
        self.assertEqual(len(orchestrate.current_rows(classify)), 1)

    def test_risk_and_size_block_without_proof(self):
        yellow = orchestrate.route("edit-small", self.tmp, risk="yellow", local=self.local(), caps=self.caps)
        self.assertEqual(yellow["executor"], "blocked")
        self.assertEqual(yellow["review"], "owner")
        self.assertEqual(orchestrate.route("edit-small", self.tmp, files=9, local=self.local(), caps=self.caps)["executor"], "blocked")

    def test_private_needs_explicit_consent(self):
        self.assertEqual(orchestrate.route("edit-small", self.tmp, local=self.local("personal-private"), caps=self.caps)["executor"], "blocked")
        allowed = self.local("personal-private", allow_remote_free=True)
        self.assertEqual(orchestrate.route("edit-small", self.tmp, local=allowed, caps=self.caps)["executor"], "opencode")

    def test_repository_can_only_be_stricter(self):
        (self.tmp / ".standard.yml").write_text("privacy: work\n", encoding="utf-8")
        self.assertEqual(orchestrate.privacy_class(self.tmp, orchestrate.policy(), self.local())[0], "work")
        (self.tmp / ".standard.yml").write_text("privacy: personal-public\n", encoding="utf-8")
        self.assertEqual(orchestrate.privacy_class(self.tmp, orchestrate.policy(), self.local("restricted"))[0], "restricted")


class CostAndData(Base):
    caps = {"ollama": {"up": False}, "opencode": {"path": "/bin/opencode"}}
    ollama = {"up": True, "models": ["qwen3.5:4b", "qwen3-embedding:0.6b"], "loaded": [], "remote": []}

    def local(self, cls="personal-public", models=("opencode/glm-5.3-flash-free",), **extra):
        today = dt.date.today().isoformat()
        return {"folders": [{"path": str(self.tmp), "class": cls, "allow_remote_free": True}],
                "free_models": [{"id": m, "checked": today} for m in models], **extra}

    def route(self, task, **kwargs):
        kwargs.setdefault("local", self.local())
        kwargs.setdefault("caps", self.caps)
        return orchestrate.route(task, self.tmp, **kwargs)

    def test_unknown_task_never_reaches_claude_in_a_free_mode(self):
        for mode in (None, "free-strict", "existing-subscription"):
            blocked = self.route("no-such-task", mode=mode)
            self.assertEqual(blocked["executor"], "blocked", mode)
        self.assertIn("classify the task type or ask the planner", " ".join(blocked["reasons"]))
        self.assertEqual(self.route("no-such-task", local=self.local("restricted"))["executor"], "blocked")

    def test_planner_types_route_to_the_planner_and_review_deep_stays_blocked(self):
        for task in ("plan", "web-direction"):
            for mode in (None, "free-strict", "existing-subscription"):
                decision = self.route(task, mode=mode)
                self.assertEqual(decision["executor"], "planner", (task, mode))
                self.assertIn("planner work: the owner asks Claude directly", decision["reasons"])
        self.assertEqual(self.route("review-deep", mode="free-strict")["executor"], "blocked")
        self.assertEqual(self.route("review-deep")["executor"], "blocked")

    def test_free_strict_keeps_the_free_path(self):
        decision = self.route("edit-small", mode="free-strict")
        self.assertEqual((decision["executor"], decision["model"]), ("opencode", "opencode/glm-5.3-flash-free"))
        self.assertEqual(self.route("lint", mode="local-only")["executor"], "tools")

    def test_local_only_sends_nothing_out(self):
        self.assertEqual(self.route("edit-small", mode="local-only")["executor"], "blocked")
        caps = {"ollama": self.ollama, "opencode": {"path": "/bin/opencode"}}
        decision = self.route("classify", mode="local-only", caps=caps)
        self.assertEqual((decision["executor"], decision["model"]), ("ollama", "qwen3.5:4b"))

    def test_a_run_cannot_loosen_the_owner_mode(self):
        local = self.local(cost_mode="free-strict")
        self.assertEqual(orchestrate.cost_mode(orchestrate.policy(), local, "existing-subscription")[0], "free-strict")
        self.assertEqual(orchestrate.cost_mode(orchestrate.policy(), local, "local-only")[0], "local-only")
        stricter = self.local(cost_mode="local-only")
        self.assertEqual(self.route("edit-small", local=stricter, mode="existing-subscription")["executor"], "blocked")

    def test_risk_needs_the_owner_and_a_proven_model_not_a_brand(self):
        for mode in (None, "free-strict"):
            yellow = self.route("edit-small", risk="yellow", mode=mode)
            self.assertEqual((yellow["executor"], yellow["review"]), ("blocked", "owner"), mode)
        rows = [{"task": "fix-bug", "executor": "opencode", "model": "opencode/glm-5.3-flash-free", "seconds": 20, "verified": True}] * 3
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        proven = self.route("edit-small", risk="yellow", mode="free-strict")
        self.assertEqual((proven["executor"], proven["review"]), ("opencode", "owner"))

    def test_large_edits_need_the_large_bench(self):
        rows = [{"task": "fix-bug", "executor": "opencode", "model": "opencode/glm-5.3-flash-free", "seconds": 20, "verified": True}] * 3
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        self.assertEqual(self.route("edit-large", mode="free-strict")["executor"], "blocked")
        self.assertEqual(self.route("edit-small", files=9, mode="free-strict")["executor"], "blocked")
        rows = [dict(r, task="fix-multi") for r in rows]
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        self.assertEqual(self.route("edit-large", mode="free-strict")["executor"], "opencode")
        self.assertEqual(self.route("edit-small", files=9, mode="free-strict")["executor"], "opencode")

    def test_refactor_needs_the_refactor_module_bench(self):
        rows = [{"task": "fix-multi", "executor": "opencode", "model": "opencode/glm-5.3-flash-free", "seconds": 20, "verified": True}] * 3
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        self.assertEqual(self.route("refactor", mode="free-strict")["executor"], "blocked")
        rows = [dict(r, task="refactor-module") for r in rows]
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        self.assertEqual(self.route("refactor", mode="free-strict")["executor"], "opencode")

    def test_thirteen_files_need_the_refactor_module_bench(self):
        rows = [{"task": "fix-multi", "executor": "opencode", "model": "opencode/glm-5.3-flash-free", "seconds": 20, "verified": True}] * 3
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        refused = self.route("edit-small", files=13, mode="free-strict")
        self.assertEqual(refused["executor"], "blocked")
        self.assertIn("13 files is more than", refused["rejected"][0]["why"])
        rows = [dict(r, task="refactor-module") for r in rows]
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        self.assertEqual(self.route("edit-small", files=13, mode="free-strict")["executor"], "opencode")

    def test_nine_files_still_need_fix_multi(self):
        rows = [{"task": "fix-bug", "executor": "opencode", "model": "opencode/glm-5.3-flash-free", "seconds": 20, "verified": True}] * 3
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        self.assertEqual(self.route("edit-small", files=9, mode="free-strict")["executor"], "blocked")
        rows = [dict(r, task="fix-multi") for r in rows]
        orchestrate.bench_file().write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        self.assertEqual(self.route("edit-small", files=9, mode="free-strict")["executor"], "opencode")

    def test_data_use_decides_before_the_name(self):
        both = ("opencode/mimo-v2.6-flash-free", "opencode/longcat-2.5-free")
        self.assertEqual(self.route("edit-small", local=self.local(models=both))["model"], "opencode/longcat-2.5-free")
        private = self.local("personal-private", models=("opencode/mimo-v2.6-flash-free",))
        refused = self.route("edit-small", local=private, mode="free-strict")
        self.assertEqual(refused["executor"], "blocked")
        self.assertIn("may train", refused["rejected"][0]["why"])
        unknown = self.route("edit-small", local=self.local(models=("opencode/jev-1.13-free",)), mode="free-strict")
        self.assertIn("no recorded data policy", unknown["rejected"][0]["why"])
        stranger = self.local(models=("opencode/never-heard-of-it",))
        self.assertEqual(self.route("edit-small", local=stranger, mode="free-strict")["executor"], "blocked")
        stranger["free_models"][0]["data_use"] = "none"
        self.assertEqual(self.route("edit-small", local=stranger, mode="free-strict")["executor"], "opencode")

    def test_the_owner_cannot_soften_what_the_catalog_says(self):
        private = self.local("personal-private", models=("opencode/mimo-v2.6-flash-free",))
        private["free_models"][0]["data_use"] = "none"
        self.assertEqual(self.route("edit-small", local=private, mode="free-strict")["executor"], "blocked")

    def test_paid_unknown_and_expired_offers_are_refused(self):
        today = dt.date.today()
        for change, text in (({"cost": "paid"}, "paid cost"), ({"cost": "unknown"}, "unknown cost"), ({"cost": "trial"}, "trial cost"),
                             ({"review_by": (today - dt.timedelta(days=1)).isoformat()}, "checked again")):
            entry = {"id": "x-free", "executor": "opencode", "cost": "free-promo", "data": {"stores": "no", "trains": "no"}, **change}
            decision = self.route("edit-small", local=self.local(models=("opencode/x-free",)), mode="free-strict",
                                  catalog={"models": [entry]})
            self.assertEqual(decision["executor"], "blocked", change)
            self.assertIn(text, decision["rejected"][0]["why"])

    def test_localhost_is_not_proof_of_local(self):
        conf = orchestrate.policy()
        work = self.local("work")
        self.assertTrue(orchestrate.gate("ollama", "qwen3.5:4b", self.tmp, conf, work, "local-only")[0])
        for model in ("big-model:cloud", "glm-5.3-cloud"):
            self.assertFalse(orchestrate.gate("ollama", model, self.tmp, conf, work)[0], model)
        proxied = {"ollama": {"remote": ["qwen3.5:4b"]}}
        self.assertFalse(orchestrate.gate("ollama", "qwen3.5:4b", self.tmp, conf, work, caps=proxied)[0])
        conf["executors"]["ollama"]["url"] = "http://gateway.example.com:11434"
        self.assertFalse(orchestrate.gate("ollama", "qwen3.5:4b", self.tmp, conf, work)[0])
        self.assertFalse(orchestrate.gate("gateway", "any", self.tmp, orchestrate.policy(), work)[0])

    def test_embedding_and_capabilities(self):
        oconf = dict(orchestrate.policy()["executors"]["ollama"], prefer=["qwen3-embedding:0.6b", "qwen3.5:4b"])
        self.assertEqual(orchestrate.pick_ollama_model(oconf, self.ollama)[0], "qwen3.5:4b")
        self.assertIsNone(orchestrate.pick_ollama_model(oconf, self.ollama, needs=["vision"])[0])
        seen = dict(self.ollama, capabilities={"qwen3.5:4b": ["completion", "vision"]})
        self.assertEqual(orchestrate.pick_ollama_model(oconf, seen, needs=["vision"])[0], "qwen3.5:4b")
        blocked = orchestrate.delegate_ollama("hello", model="qwen3-embedding:0.6b", caps=self.ollama)
        self.assertEqual(blocked["state"], "blocked")

    def test_split_model_only_with_its_own_history(self):
        oconf = dict(orchestrate.policy()["executors"]["ollama"], prefer=["qwen3.5:9b"])
        info = {"models": ["qwen3.5:9b"], "loaded": [{"name": "qwen3.5:9b", "gpu_share": 0.57}], "remote": []}
        self.assertIsNone(orchestrate.pick_ollama_model(oconf, info)[0])
        measured = {("ollama", "qwen3.5:9b"): {"p50_s": 9.0}}
        self.assertEqual(orchestrate.pick_ollama_model(oconf, info, measured)[0], "qwen3.5:9b")

    def test_delegation_is_gated_too(self):
        repo = self.repo()
        local = self.local(models=("opencode/glm-5.3-flash-free",))
        run = orchestrate.delegate_opencode(repo, "Change a.txt", ["a.txt"], None, model="opencode/glm-5.3-flash-free",
                                            local=local, mode="local-only", command=[sys.executable, "-c", "raise SystemExit(9)"])
        self.assertEqual(run["state"], "blocked")
        unchecked = orchestrate.delegate_opencode(repo, "Change a.txt", ["a.txt"], None, model="opencode/big-pickle", local=local,
                                                  command=[sys.executable, "-c", "raise SystemExit(9)"])
        self.assertEqual(unchecked["state"], "blocked")
        self.assertNotIn("worktree", unchecked)

    def test_table_names_every_task(self):
        conf = orchestrate.policy()
        rows = orchestrate.route_table(self.tmp, local=self.local(), caps=self.caps, mode="free-strict")
        by_task = {row["task"]: row for row in rows}
        self.assertEqual(set(by_task), set(conf["tasks"]) | set(conf["planner_tasks"]))
        self.assertEqual(by_task["plan"]["agent"], "planner")
        self.assertIn("planner work", by_task["plan"]["why"])
        self.assertEqual(by_task["edit-small"]["model"], "opencode/glm-5.3-flash-free")

    def test_no_task_mode_or_class_ever_routes_to_claude(self):
        conf = orchestrate.policy()
        for task in [*conf["tasks"], *conf["planner_tasks"], "no-such-task"]:
            for mode in conf["cost"]["order"]:
                for cls in conf["privacy"]["order"]:
                    decision = self.route(task, local=self.local(cls), caps=self.caps, mode=mode)
                    self.assertNotEqual(decision["executor"], "claude", (task, mode, cls))

    def test_stale_notes_point_to_the_source(self):
        catalog = {"models": [{"id": "old-free", "executor": "opencode", "source": "https://example.com/models", "checked": "2020-01-01"}]}
        local = {"free_models": [{"id": "opencode/old-free", "checked": "2020-01-01"}]}
        notes = " ".join(orchestrate.stale_notes(orchestrate.policy(), catalog, local))
        self.assertIn("https://example.com/models", notes)
        self.assertIn("opencode/old-free", notes)


class WindowsLaunch(Base):
    def test_bare_names_get_their_full_path(self):
        python = Path(sys.executable).name
        self.assertTrue(os.path.isabs(orchestrate.resolve([python, "-V"])[0]))
        self.assertEqual(orchestrate.resolve(["no-such-tool-xyz"]), ["no-such-tool-xyz"])
        self.assertIsNone(orchestrate.run(["no-such-tool-xyz"])["exit"])

    def test_mcp_launch_on_windows(self):
        launch = ["npx", "-y", "pkg@1.0.0"]
        expected = ["cmd", "/c", *launch] if os.name == "nt" else launch
        self.assertEqual(orchestrate.windows_launch(launch), expected)


class OpenCodeMerge(Base):
    def test_merge_keeps_keys_and_is_idempotent(self):
        target = self.tmp / "oc"
        target.mkdir()
        (target / "opencode.jsonc").write_text('{\n  // mine\n  "model": "a/b",\n  "permission": {"bash": "allow"},\n}\n', encoding="utf-8")
        orchestrate.cmd_merge_opencode(target)
        merged = json.loads((target / "opencode.json").read_text(encoding="utf-8"))
        self.assertEqual(merged["model"], "a/b")
        self.assertEqual(merged["permission"]["bash"]["git push --force*"], "deny")
        self.assertEqual(merged["permission"]["bash"]["*"], "allow")
        backups = list(target.glob("*.bak-*"))
        orchestrate.cmd_merge_opencode(target)
        self.assertEqual(len(list(target.glob("*.bak-*"))), len(backups))


class SafePatch(Base):
    def test_roundtrip(self):
        repo = self.repo()
        git(repo, "checkout", "-q", "-b", "work")
        (repo / "a.txt").write_text("two\n", encoding="utf-8")
        git(repo, "commit", "-q", "-am", "change")
        out = self.tmp / "out.patch"
        code = safe_patch.main(["create", "--repo", str(repo), "--base", "HEAD~1", "--out", str(out),
                                "--test", f'"{sys.executable}" -c "import sys; sys.exit(0)"'])
        self.assertEqual(code, 0)
        self.assertEqual(subprocess.run(["git", "-C", str(repo), "worktree", "list"], capture_output=True,
                                        text=True, check=True).stdout.count("\n"), 1)


class Preserve(Base):
    def test_unchanged_passes_and_snapshot_lives_in_git(self):
        repo = self.repo()
        (repo / "docs").mkdir()
        (repo / "docs" / "preservation.yml").write_text("protect: ['a.txt']\n", encoding="utf-8")
        self.assertEqual(preserve.main(["snapshot", "--repo", str(repo)]), 0)
        self.assertIn(".git", str(preserve.default_baseline(repo)))
        self.assertEqual(preserve.main(["compare", "--repo", str(repo)]), 0)
        (repo / "a.txt").write_text("changed\n", encoding="utf-8")
        self.assertEqual(preserve.main(["compare", "--repo", str(repo)]), 1)


class Memory(Base):
    def test_facts_need_a_reference(self):
        db = memory.connect(self.tmp / "m.db")
        with self.assertRaises(ValueError):
            memory.add(db, "decision", "Use FTS5", source="owner")
        memory.add(db, "decision", "Use FTS5 first", ref="docs/005", source="owner")
        self.assertEqual(len(memory.search(db, "fts5")), 1)

    def test_hints_expire_and_facts_stay(self):
        db = memory.connect(self.tmp / "m.db")
        memory.add(db, "decision", "Keep the scroll scenes", ref="docs/decisions/0003", source="owner")
        hint = memory.add(db, "note", "The router probably prefers GLM")
        db.execute("UPDATE entries SET created = datetime('now', '-200 days')")
        db.commit()
        self.assertEqual({e["source"] for e in memory.export(db)}, {"owner", "agent"})
        self.assertGreater(memory.age_days(memory.export(db)[0]["created"]), memory.OLD_DAYS)
        self.assertEqual(memory.expire(db, 180), 1)
        left = memory.export(db)
        self.assertEqual([e["source"] for e in left], ["owner"])
        self.assertNotIn(hint, [e["id"] for e in left])
        self.assertEqual(memory.search(db, "router"), [])


class Evidence(Base):
    def test_report_matches_schema(self):
        report = evidence.build_report("t", "quick", [evidence.result("a", "c", "PASS")])
        paths = evidence.write_report(report, self.tmp / "r")
        self.assertTrue(paths[1].read_text(encoding="utf-8").startswith("# t: PASS"))
        report["results"][0]["status"] = "OK"
        with self.assertRaises(ValueError):
            evidence.write_report(report, self.tmp / "r2")


class Bench(Base):
    def test_percentiles(self):
        rows = [{"task": "t", "executor": "e", "model": "m", "seconds": s, "verified": True} for s in (10, 20, 30, 40)]
        rows.append({"task": "t", "executor": "e", "model": "m", "seconds": 5, "verified": False})
        summary = orchestrate.summarize_bench(rows)[0]
        self.assertEqual((summary["runs"], summary["pass_rate"], summary["p50_s"]), (5, 0.8, 30))


class Probe(Base):
    def test_only_in_standard_repositories(self):
        repo = self.repo()
        self.assertIsNone(session_probe.context(repo))
        (repo / ".standard.yml").write_text("profile: software\n", encoding="utf-8")
        text = session_probe.context(repo)
        self.assertIn("route", text)
        self.assertIn("privacy of this folder", text)


class WebSubprofiles(Base):
    def web_repo(self, **options):
        repo = self.tmp / "site"
        standard.init_repo(repo, {"profile": "web", "name": "site", "options": options, "setup_done": True,
                                  "description": "Test site."})
        return repo

    def test_requests_reach_their_subprofile(self):
        cases = {"Explain how the device is assembled as the reader scrolls": "scroll-storytelling",
                 "Let people change the bandwidth with sliders and see the estimated time": "interactive-data",
                 "An orb that reacts to the microphone signal": "reactive-object",
                 "A portfolio with expressive typography": "editorial",
                 "An exercise with a tutor character that reacts": "characters"}
        for request, expected in cases.items():
            choice = standard.choose_subprofile(request)
            self.assertEqual(choice["subprofile"], expected, request)
            self.assertTrue(choice["summary"])
        self.assertIsNone(standard.choose_subprofile("Make this page more dynamic")["subprofile"])

    def test_the_owner_choice_wins_and_a_named_one_wins_over_it(self):
        repo = self.web_repo(experience="editorial")
        stored = standard.choose_subprofile("Compare two plans with sliders and a chart", repo)
        self.assertEqual((stored["subprofile"], "owner" in stored["why"]), ("editorial", True))
        named = standard.choose_subprofile("Use web/personajes for this exercise", repo)
        self.assertEqual(named["subprofile"], "characters")

    def test_rules_reach_agents_and_old_configs_still_work(self):
        repo = self.web_repo(experience="reactive-object")
        agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("experience = reactive-object", agents)
        self.assertIn("stays still when the pointer moves", agents)
        self.assertLess(len(agents.splitlines()), 150)
        old = standard.resolve(standard.load_profile("web"), {"motion": "subtle", "theme": "both"})
        self.assertEqual(old["problems"], [])
        self.assertFalse([rule for rule in old["option_rules"] if rule.startswith("experience")])

    def test_summaries_fit_a_small_model(self):
        limit = orchestrate.policy()["limits"]["ollama_max_input_chars"]
        specs = bench_tasks.subprofiles()
        self.assertEqual(len(specs), 5)
        self.assertLess(sum(len(spec["summary"]) for spec in specs.values()), limit // 2)
        choices = set(standard.load_profile("web")["options"]["experience"]["choices"])
        self.assertEqual(choices, set(specs) | {"standard"})

    def test_static_design_measures(self):
        sys.path.insert(0, str(ROOT / "skills" / "web-improve" / "scripts"))
        import audit_site
        site = self.tmp / "bad"
        site.mkdir()
        (site / "DESIGN.md").write_text("## Tokens\n\n`--duration-fast: 150ms`\n", encoding="utf-8")
        (site / "index.html").write_text('<html><body><h1>A</h1><h3>B</h3><img src="a.png"></body></html>', encoding="utf-8")
        (site / "site.css").write_text("h1{font-family:Georgia}p{font-family:'Fira Code'}a{font-family:Inter;transition:color 333ms}", encoding="utf-8")
        (site / "orb.js").write_text("function tick(){requestAnimationFrame(tick)}", encoding="utf-8")
        found = {item["check"] for item in audit_site.design_measures(site)["findings"]}
        self.assertEqual(found, {"font-families", "duration-outside-tokens", "script-ignores-reduced-motion", "missing-lang",
                                 "image-without-alt", "image-without-size", "heading-order", "no-reduced-motion-rule"})
        clean = audit_site.design_measures(ROOT / "skills" / "web-improve" / "gallery")
        self.assertEqual(clean["findings"], [])


if __name__ == "__main__":
    unittest.main()
