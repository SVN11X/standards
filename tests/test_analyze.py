"""The model analyzer with fake executors: no real model, no download and no paid endpoint. Run: python -m unittest discover -s tests"""
import datetime as dt
import os
import socket
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

CATALOG = {"models": [
    {"id": "good:1b", "executor": "ollama", "provider": "ollama-local", "cost": "local", "data": {"stores": "no", "trains": "no"}},
    {"id": "bad:1b", "executor": "ollama", "provider": "ollama-local", "cost": "local", "data": {"stores": "no", "trains": "no"}},
    {"id": "embed:1b", "executor": "ollama", "provider": "ollama-local", "cost": "local", "capabilities": ["embedding"]},
    {"id": "missing:3b", "executor": "ollama", "provider": "ollama-local", "cost": "local", "source": "https://example.com/missing"},
    {"id": "fix-free", "executor": "opencode", "provider": "zen", "cost": "free-promo", "data": {"stores": "no", "trains": "no"}},
    {"id": "limit-free", "executor": "opencode", "provider": "zen", "cost": "free-promo", "data": {"stores": "no", "trains": "no"}},
    {"id": "after-limit-free", "executor": "opencode", "provider": "zen", "cost": "free-promo", "data": {"stores": "no", "trains": "no"}},
    {"id": "lazy-free", "executor": "opencode", "provider": "other", "cost": "free-promo", "data": {"stores": "yes", "trains": "yes"},
     "requests_per_day": 20},
    {"id": "unchecked-free", "executor": "opencode", "provider": "zen", "cost": "free-promo", "data": {"stores": "no", "trains": "no"},
     "source": "https://example.com/models"},
    {"id": "paid-pro", "executor": "opencode", "provider": "zen", "cost": "paid", "data": {"stores": "no", "trains": "no"}},
    {"id": "mystery-free", "executor": "opencode", "provider": "zen", "cost": "free-promo", "data": {"stores": "unknown", "trains": "unknown"}},
]}
CHECKED = ("fix-free", "limit-free", "after-limit-free", "lazy-free", "paid-pro", "mystery-free")


class Analyzer(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="std-analyze-"))
        self.old = {key: os.environ.get(key) for key in ("STANDARDS_HOME", "STANDARDS_COST_MODE")}
        os.environ["STANDARDS_HOME"] = str(self.tmp / "home")
        os.environ.pop("STANDARDS_COST_MODE", None)
        self.server, url = fakes.start_ollama()
        self.real_load = orchestrate.providers.load
        orchestrate.providers.load = lambda path=None: {}
        self.conf = orchestrate.policy()
        self.conf["executors"]["ollama"].update(url=url, prefer=["good:1b"])
        self.conf["executors"]["opencode"]["command"] = [sys.executable, str(fakes.write_agent(self.tmp)), "{model}", "{message}"]
        self.conf["limits"]["opencode_timeout_s"] = 30
        self.conf["analysis"].update(runs=1)
        today = dt.date.today().isoformat()
        self.local = {"free_models": [{"id": f"opencode/{name}", "checked": today} for name in CHECKED]}
        self.caps = {"ollama": orchestrate.detect_ollama(self.conf["executors"]["ollama"], show=True),
                     "opencode": {"path": "/bin/opencode", "version": "fake"}}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        orchestrate.providers.load = self.real_load
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def run_plan(self, **options):
        said = []
        state = analyze.run_plan(self.conf, self.local, self.caps, CATALOG, say=said.append, **options)
        return state, said

    def test_plan_comes_from_the_catalog_and_the_rules(self):
        ready, left_out = analyze.candidates(self.conf, self.local, self.caps, CATALOG)
        names = {f"{r['executor']}:{r['model']}" for r in ready}
        self.assertEqual(names, {"ollama:good:1b", "ollama:bad:1b", "ollama:swap:1b", "opencode:opencode/fix-free",
                                 "opencode:opencode/limit-free", "opencode:opencode/after-limit-free", "opencode:opencode/lazy-free"})
        self.assertIn("not in the catalog", next(r for r in ready if r["model"] == "swap:1b")["why"])
        why = {item["model"]: item for item in left_out}
        self.assertEqual(why["missing:3b"]["fix"], "ollama pull missing:3b")
        self.assertIn("search only", why["embed:1b"]["why"])
        self.assertIn("needs your check", why["unchecked-free"]["why"])
        self.assertIn("consent --free-model", why["unchecked-free"]["fix"])
        self.assertIn("paid cost", why["opencode/paid-pro"]["why"])
        self.assertIn("no recorded data policy", why["opencode/mystery-free"]["why"])
        steps, cut = analyze.build_plan(ready, self.conf, runs=3)
        lazy = [s for s in steps if s["model"] == "opencode/lazy-free"]
        self.assertEqual(len(lazy), 2)
        self.assertIn("10 runs left out", next(c for c in cut if c["model"] == "opencode/lazy-free")["why"])
        text = "\n".join(analyze.plan_lines(steps, cut, left_out, self.conf, "existing-subscription"))
        self.assertIn("Longest it can take", text)
        self.assertIn("Remote in total", text)
        self.assertIn("python scripts/analyze.py prepare", text)
        self.assertIn("1 not installed", text)
        self.assertNotIn("ollama pull", text)
        self.assertIn("Cut by a budget", text)

    def test_local_only_plans_no_remote_step(self):
        ready, left_out = analyze.candidates(self.conf, self.local, self.caps, CATALOG, mode="local-only")
        self.assertTrue(all(not r["remote"] for r in ready))
        self.assertIn("local-only", next(i for i in left_out if i["model"] == "opencode/fix-free")["why"])

    def test_night_run_report_and_resume(self):
        state, said = self.run_plan()
        self.assertTrue(state["complete"])
        rows = orchestrate.bench_rows()
        by = {(r["task"], r["model"]): r for r in rows}
        for task in ("classify", "extract", "summarize", "web-subprofile", "tool-call", "vision", "review-diff", "decompose"):
            self.assertTrue(by[(task, "good:1b")]["verified"], task)
            self.assertFalse(by[(task, "bad:1b")]["verified"], task)
        self.assertTrue(by[("design-judge-sample", "good:1b")]["verified"])
        self.assertEqual(by[("classify", "good:1b")]["cold_load_s"], 1.5)
        self.assertEqual(by[("classify", "good:1b")]["effective_model"], "good:1b")
        self.assertEqual(by[("classify", "good:1b")]["night"], state["id"])
        for task in ("fix-bug", "fix-multi", "docs-small", "refactor-module"):
            self.assertTrue(by[(task, "opencode/fix-free")]["verified"], task)
        self.assertFalse(by[("fix-bug", "opencode/lazy-free")]["verified"])
        self.assertNotIn(("docs-small", "opencode/lazy-free"), by)
        limited = [r for r in rows if r["model"] == "opencode/limit-free"]
        self.assertEqual(len(limited), 1)
        self.assertTrue(limited[0]["rate_limited"])
        self.assertFalse([r for r in rows if r["model"] == "opencode/after-limit-free"])
        self.assertTrue(by[("fix-bug", "opencode/lazy-free")])
        self.assertNotIn("/api/pull", fakes.Ollama.seen)
        self.assertFalse(fakes.Ollama.loaded)
        self.assertFalse(analyze.state_file().exists())
        report = analyze.build_report(self.conf, CATALOG, state=state)
        self.assertIn("## Proposed split", report)
        self.assertIn("## Full agent", report)
        self.assertIn("## Inference by API or by a program", report)
        self.assertIn("limit was reached", report)
        self.assertIn("ollama pull missing:3b", report)
        self.assertIn("made-up sample", report)
        path = analyze.write_report(None, conf=self.conf, catalog=CATALOG, state=state)
        self.assertNotIn(str(ROOT), str(path.resolve()))

    def test_resume_skips_what_finished(self):
        first, _ = self.run_plan(budget_s=0)
        self.assertFalse(first["complete"])
        self.assertFalse(orchestrate.bench_rows())
        results = []

        def interrupt_after_four(line):
            results.append(line)
            if line.startswith(("pass", "fail")) and sum(1 for text in results if text.startswith(("pass", "fail"))) == 4:
                raise KeyboardInterrupt

        stopped = analyze.run_plan(self.conf, self.local, self.caps, CATALOG, say=interrupt_after_four)
        self.assertFalse(stopped["complete"])
        self.assertTrue(analyze.state_file().exists())
        self.assertEqual(len(orchestrate.bench_rows()), 4)
        self.assertEqual(fakes.Ollama.loaded, [])
        full, said = self.run_plan()
        self.assertTrue(full["complete"])
        self.assertIn("4 already done", said[0])
        keys = [(r["task"], r["executor"], r["model"]) for r in orchestrate.bench_rows()]
        self.assertEqual(len(keys), len(set(keys)))

    def test_the_report_says_how_many_old_runs_it_left_out(self):
        rows = [{"task": "summarize", "executor": "ollama", "model": "good:1b", "seconds": 5, "verified": False, "date": orchestrate.now()}]
        self.assertIn("1 older runs are left out", analyze.build_report(self.conf, CATALOG, rows=rows))

    def test_one_local_model_at_a_time(self):
        fakes.Ollama.loaded.append("bad:1b")
        analyze.unload_other_models("good:1b", self.conf)
        self.assertEqual(fakes.Ollama.loaded, [])

    def test_a_model_that_answers_as_another_fails(self):
        row = orchestrate.bench_chat("classify", "ollama", "swap:1b", conf=self.conf, caps=self.caps["ollama"], local=self.local,
                                     catalog=CATALOG)
        self.assertFalse(row["verified"])
        self.assertIn("other:9b answered", row["error"])
        one = orchestrate.delegate_ollama("hello", model="swap:1b", conf=self.conf, caps=self.caps["ollama"], local=self.local)
        self.assertEqual(one["checks"]["effective_model"], "FAIL")

    def test_no_request_leaves_the_machine(self):
        real = socket.socket.connect
        outside = []

        def watch(sock, address):
            if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1", "localhost"):
                outside.append(address)
                raise OSError("blocked by the test")
            return real(sock, address)
        socket.socket.connect = watch
        try:
            self.run_plan()
        finally:
            socket.socket.connect = real
        self.assertEqual(outside, [])

    def test_prepare_gives_the_commands_and_changes_nothing(self):
        before = sorted(p.name for p in orchestrate.home().iterdir())
        text = "\n".join(analyze.prepare_lines(self.conf, self.local, self.caps, CATALOG))
        self.assertIn("ollama pull missing:3b", text)
        self.assertIn("consent --free-model", text)
        self.assertIn("made-up sample", text)
        self.assertEqual(before, sorted(p.name for p in orchestrate.home().iterdir()))

    def test_owner_pairs_replace_the_sample(self):
        folder = orchestrate.home() / "design-pairs"
        folder.mkdir(parents=True)
        (folder / "a.png").write_bytes(bench_tasks.toolbar([bench_tasks.GRAY]))
        (folder / "b.png").write_bytes(bench_tasks.toolbar([bench_tasks.DARK]))
        (folder / "pairs.yml").write_text("pairs:\n  - {id: home, a: a.png, b: b.png, choice: b}\n", encoding="utf-8")
        pairs, sample = bench_tasks.design_pairs()
        self.assertEqual((len(pairs), sample), (1, False))


class Graders(unittest.TestCase):
    def test_summary_with_an_invented_command_fails(self):
        item = bench_tasks.SUMMARIZE[0]
        good = {"summary": "Use a worktree per branch.", "commands": ["git worktree list"]}
        quoted = {"summary": "Use a worktree per branch.", "commands": ['"git worktree add ../hotfix -b hotfix main"', "`git worktree prune`"]}
        self.assertTrue(bench_tasks.summarize_ok(item, quoted)[0])
        self.assertFalse(bench_tasks.summarize_ok(bench_tasks.SUMMARIZE[1], {"summary": "Ollama keeps a model loaded.",
                                                                             "commands": ["ollama stop <model_name>"]})[0])
        self.assertTrue(bench_tasks.summarize_ok(bench_tasks.SUMMARIZE[1], {"summary": "Ollama keeps a model loaded for a while.", "commands": []})[0])
        self.assertFalse(bench_tasks.summarize_ok(bench_tasks.SUMMARIZE[1], {"summary": "It is about cooking pasta.", "commands": []})[0])
        self.assertTrue(bench_tasks.summarize_ok(item, good)[0])
        for bad in ({"summary": "Use a worktree per branch with `git checkout --worktrees`.", "commands": []},
                    {"summary": "Use a worktree per branch.", "commands": ["git worktree nuke"]},
                    {"summary": "Run git checkout --worktrees on the branch worktree.", "commands": []},
                    {"summary": "Short.", "commands": []}):
            self.assertFalse(bench_tasks.summarize_ok(item, bad)[0], bad)

    def test_tool_sequence(self):
        case = bench_tasks.TOOL_CASES[0]
        self.assertTrue(bench_tasks.tool_case_ok(case, lambda m, t: fakes.answer({"messages": m, "tools": t}))[0])
        def script(names):
            left = list(names)
            return lambda m, t: ({"tool_calls": [{"function": {"name": left.pop(0), "arguments": {"path": "calc.py", "target": "t.py"}}}]}
                                 if left else {"content": "Found it."})
        self.assertTrue(bench_tasks.tool_case_ok(case, script(["read_file", "read_file", "read_file", "run_tests"]))[0])
        self.assertIn("before", bench_tasks.tool_case_ok(case, script(["run_tests", "read_file"]))[1])
        self.assertFalse(bench_tasks.tool_case_ok(case, script(["read_file"]))[0])
        wrong = lambda m, t: {"tool_calls": [{"function": {"name": "delete_repo", "arguments": {}}}]}  # noqa: E731
        self.assertIn("does not exist", bench_tasks.tool_case_ok(case, wrong)[1])
        self.assertFalse(bench_tasks.tool_case_ok(case, lambda m, t: {"content": "It is fine."})[0])
        guess = bench_tasks.TOOL_CASES[1]
        made_up = lambda m, t: (fakes.answer({"messages": m, "tools": t}) if len(m) == 1 else {"content": "It sets port 8080."})  # noqa: E731
        self.assertFalse(bench_tasks.tool_case_ok(guess, made_up)[0])

    def test_images_are_valid_and_differ(self):
        items = bench_tasks.vision_items()
        self.assertEqual(len({i["image"] for i in items}), len(items))
        import base64
        self.assertTrue(base64.b64decode(items[0]["image"]).startswith(b"\x89PNG\r\n\x1a\n"))

    def test_judge_needs_both_orders(self):
        pair = bench_tasks.sample_pairs()[0]
        self.assertFalse(bench_tasks.judge_ok(pair, lambda prompt, images: {"choice": "b"}))
        self.assertTrue(bench_tasks.judge_ok(pair, lambda prompt, images: {"choice": "b" if images[1] == pair["b"] else "a"}))

    def test_selector_baseline(self):
        self.assertEqual(bench_tasks.suggest_subprofile("Compare two plans with sliders and a chart")[0], "interactive-data")
        self.assertIsNone(bench_tasks.suggest_subprofile("Make this page more dynamic")[0])

    def test_refactor_module_hidden_ast_check_rejects_a_copy(self):
        import subprocess
        spec = bench_tasks.AGENT_TASKS["refactor-module"]
        self.assertGreaterEqual(len(spec["files"]), 6)
        self.assertLessEqual(len(spec["files"]), 8)
        with tempfile.TemporaryDirectory() as tmp:
            repo = orchestrate.make_bench_repo(Path(tmp) / "r", "refactor-module")
            (repo / "test_hidden.py").write_text(spec["hidden"], encoding="utf-8")
            # A module that only re-exports a second copy keeps the behavior but still defines the function twice.
            (repo / "app" / "text.py").write_text(bench_tasks.SLUG, encoding="utf-8")
            for name in ("posts", "users", "tags"):
                path = repo / "app" / f"{name}.py"
                path.write_text("from app.text import slugify\n\n\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
            run = subprocess.run([sys.executable, "-B", "-m", "unittest", "test_hidden"], cwd=repo, capture_output=True, text=True, check=False)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("test_defined_once_in_text", run.stderr)

    def test_agent_fixtures_fail_before_and_pass_after(self):
        import subprocess
        for task in bench_tasks.AGENT_TASKS:
            with tempfile.TemporaryDirectory() as tmp:
                repo = orchestrate.make_bench_repo(Path(tmp) / "r", task)
                (repo / "test_hidden.py").write_text(bench_tasks.AGENT_TASKS[task]["hidden"], encoding="utf-8")
                before = subprocess.run([sys.executable, "-B", "-m", "unittest", "test_hidden"], cwd=repo, capture_output=True, check=False)
                self.assertNotEqual(before.returncode, 0, task)
                (repo / ".delegate-task.md").write_text(bench_tasks.AGENT_TASKS[task]["task"], encoding="utf-8")
                subprocess.run([sys.executable, str(fakes.write_agent(Path(tmp))), "m", "x"], cwd=repo, check=True, capture_output=True)
                after = subprocess.run([sys.executable, "-m", "unittest", "test_hidden"], cwd=repo, capture_output=True, check=False)
                self.assertEqual(after.returncode, 0, task)


if __name__ == "__main__":
    unittest.main()
