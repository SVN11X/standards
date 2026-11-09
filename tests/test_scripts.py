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
import evidence  # noqa: E402
import memory  # noqa: E402
import orchestrate  # noqa: E402
import preserve  # noqa: E402
import safe_patch  # noqa: E402
import session_probe  # noqa: E402


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


class Route(Base):
    caps = {"ollama": {"up": False}, "opencode": {"path": "/bin/opencode"}}

    def local(self, cls="personal-public", **extra):
        return {"folders": [{"path": str(self.tmp), "class": cls, **extra}],
                "free_models": [{"id": "opencode/glm-free", "checked": dt.date.today().isoformat()}]}

    def test_tools_first(self):
        self.assertEqual(orchestrate.route("lint", self.tmp, local={}, caps=self.caps)["executor"], "tools")

    def test_small_edit_goes_to_opencode(self):
        decision = orchestrate.route("edit-small", self.tmp, local=self.local(), caps=self.caps)
        self.assertEqual((decision["executor"], decision["model"]), ("opencode", "opencode/glm-free"))

    def test_risk_and_size_keep_it_with_claude(self):
        self.assertEqual(orchestrate.route("edit-small", self.tmp, risk="yellow", local=self.local(), caps=self.caps)["executor"], "claude")
        self.assertEqual(orchestrate.route("edit-small", self.tmp, files=9, local=self.local(), caps=self.caps)["executor"], "claude")

    def test_private_needs_explicit_consent(self):
        self.assertEqual(orchestrate.route("edit-small", self.tmp, local=self.local("personal-private"), caps=self.caps)["executor"], "claude")
        allowed = self.local("personal-private", allow_remote_free=True)
        self.assertEqual(orchestrate.route("edit-small", self.tmp, local=allowed, caps=self.caps)["executor"], "opencode")

    def test_repository_can_only_be_stricter(self):
        (self.tmp / ".standard.yml").write_text("privacy: work\n", encoding="utf-8")
        self.assertEqual(orchestrate.privacy_class(self.tmp, orchestrate.policy(), self.local())[0], "work")
        (self.tmp / ".standard.yml").write_text("privacy: personal-public\n", encoding="utf-8")
        self.assertEqual(orchestrate.privacy_class(self.tmp, orchestrate.policy(), self.local("restricted"))[0], "restricted")


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


if __name__ == "__main__":
    unittest.main()
