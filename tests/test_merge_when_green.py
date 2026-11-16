"""Checked merges: the owner's setting, the conditions before a merge, the guard hook and the autopilot path."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hooks"))

import guard  # noqa: E402
import merge_when_green as mwg  # noqa: E402
import plan_autopilot as autopilot  # noqa: E402

HEAD = "a" * 40
PR = {"number": 7, "url": "https://github.com/o/r/pull/7", "state": "OPEN", "isDraft": False, "headRefOid": HEAD,
      "mergeable": "MERGEABLE", "baseRefName": "main", "title": "feat: x"}
GREEN = [{"name": "check / standard", "bucket": "pass"}, {"name": "docs", "bucket": "skipping"}]


class FakeGh:
    """Answers gh like GitHub would and records every call."""

    def __init__(self, pr=None, files="src/app.py\n", checks=None):
        self.pr, self.files, self.calls = {**PR, **(pr or {})}, files, []
        self.checks = list(checks) if checks is not None else [GREEN]

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["pr", "view"]:
            return json.dumps(self.pr)
        if args[:2] == ["pr", "diff"]:
            return self.files
        if args[:2] == ["pr", "checks"]:
            rows = self.checks.pop(0) if len(self.checks) > 1 else self.checks[0]
            if rows is None:
                raise mwg.Refused("gh pr checks failed: no checks reported on the 'x' branch")
            return json.dumps(rows)
        return ""

    def merged(self):
        return [c for c in self.calls if c[:2] == ["pr", "merge"]]


def merge(fake, **kw):
    return mwg.merge("7", "o/r", run=fake, setting=kw.pop("setting", "when-green"), sleep=lambda s: None, **kw)


class Setting(unittest.TestCase):
    def test_only_when_green_turns_merges_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "local.yml"
            self.assertEqual(mwg.owner_setting(path), "ask")
            path.write_text("cost_mode: local-only\nautopilot:\n  merge: when-green\n", encoding="utf-8")
            self.assertEqual(mwg.owner_setting(path), "when-green")
            path.write_text("autopilot:\n  merge: always\n", encoding="utf-8")
            self.assertEqual(mwg.owner_setting(path), "ask")

    def test_the_setting_is_read_without_pyyaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "local.yml"
            path.write_text("autopilot:\n  other: 1\n  merge: 'when-green'\nfolders: []\n", encoding="utf-8")
            with mock.patch.dict(sys.modules, {"yaml": None}):
                self.assertEqual(mwg.owner_setting(path), "when-green")
            path.write_text("merge: when-green\n", encoding="utf-8")
            with mock.patch.dict(sys.modules, {"yaml": None}):
                self.assertEqual(mwg.owner_setting(path), "ask")

    def test_consent_records_the_setting_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "local.yml").write_text("cost_mode: local-only\n", encoding="utf-8")
            env = {**os.environ, "STANDARDS_HOME": tmp}
            ran = subprocess.run([sys.executable, str(ROOT / "scripts" / "orchestrate.py"), "consent", "--merge", "when-green"],
                                 capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(ran.returncode, 0, ran.stderr)
            self.assertEqual(mwg.owner_setting(Path(tmp) / "local.yml"), "when-green")
            self.assertIn("cost_mode: local-only", (Path(tmp) / "local.yml").read_text(encoding="utf-8"))


class Conditions(unittest.TestCase):
    def test_a_green_pull_request_merges_on_its_checked_head_without_admin(self):
        fake = FakeGh()
        result = merge(fake)
        self.assertTrue(result["merged"])
        self.assertEqual(fake.merged(), [["pr", "merge", "7", "--repo", "o/r", "--squash", "--match-head-commit", HEAD]])
        self.assertFalse(any("--admin" in c or "--auto" in c for c in fake.calls))

    def test_without_the_owner_setting_nothing_is_merged(self):
        fake = FakeGh()
        with self.assertRaisesRegex(mwg.Refused, "consent --merge when-green"):
            merge(fake, setting="ask")
        self.assertEqual(fake.calls, [])

    def test_failed_running_or_missing_checks_refuse(self):
        for rows, reason in (([{"name": "test", "bucket": "fail"}, *GREEN], "checks failed: test"),
                             ([{"name": "test", "bucket": "cancel"}], "checks failed: test"),
                             ([{"name": "test", "bucket": "pending"}], "still running"),
                             (None, "no check ran")):
            fake = FakeGh(checks=[rows])
            with self.subTest(reason), self.assertRaisesRegex(mwg.Refused, reason):
                merge(fake)
            self.assertEqual(fake.merged(), [])

    def test_wait_follows_running_checks_until_they_pass(self):
        ticks = iter(range(0, 1000, 10))
        fake = FakeGh(checks=[[{"name": "test", "bucket": "pending"}], None, GREEN])
        result = mwg.merge("7", run=fake, setting="when-green", wait=600, sleep=lambda s: None, clock=lambda: next(ticks))
        self.assertTrue(result["merged"])
        self.assertEqual(sum(c[:2] == ["pr", "checks"] for c in fake.calls), 3)

    def test_closed_conflicting_and_owner_only_changes_refuse(self):
        cases = ((FakeGh(pr={"state": "MERGED"}), "not open"),
                 (FakeGh(pr={"mergeable": "CONFLICTING"}), "merge conflict"),
                 (FakeGh(files="src/a.py\n.github/workflows/ci.yml\n"), "workflows, deploy or secrets"),
                 (FakeGh(files=".env.production\n"), "workflows, deploy or secrets"),
                 (FakeGh(files="infra/main.tf\n"), "workflows, deploy or secrets"),
                 (FakeGh(files="wrangler.toml\n"), "workflows, deploy or secrets"))
        for fake, reason in cases:
            with self.subTest(reason), self.assertRaisesRegex(mwg.Refused, reason):
                merge(fake)
            self.assertEqual(fake.merged(), [])

    def test_a_draft_is_marked_ready_and_a_dry_run_merges_nothing(self):
        fake = FakeGh(pr={"isDraft": True})
        merge(fake)
        self.assertLess(fake.calls.index(["pr", "ready", "7", "--repo", "o/r"]), fake.calls.index(fake.merged()[0]))
        dry = FakeGh(pr={"isDraft": True})
        self.assertFalse(merge(dry, dry=True)["merged"])
        self.assertFalse(any(c[:2] in (["pr", "merge"], ["pr", "ready"]) for c in dry.calls))


class Guard(unittest.TestCase):
    def decide(self, setting, command="gh pr merge 7 --squash"):
        with tempfile.TemporaryDirectory() as tmp:
            if setting:
                (Path(tmp) / "local.yml").write_text(f"autopilot:\n  merge: {setting}\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"STANDARDS_HOME": tmp}):
                return guard.decide({"tool_input": {"command": command}, "cwd": tmp})["hookSpecificOutput"]

    def test_without_the_setting_a_merge_asks_the_owner(self):
        self.assertEqual(self.decide(None)["permissionDecision"], "ask")
        self.assertEqual(self.decide("ask")["permissionDecision"], "ask")

    def test_with_the_setting_a_raw_merge_is_sent_to_the_checked_merge(self):
        out = self.decide("when-green")
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn(str(ROOT / "scripts" / "merge_when_green.py"), out["permissionDecisionReason"])

    def test_an_admin_merge_still_asks_the_owner(self):
        self.assertEqual(self.decide("when-green", "gh pr merge 7 --admin --squash")["permissionDecision"], "ask")

    def test_the_checked_merge_itself_is_not_stopped(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"STANDARDS_HOME": tmp}):
            self.assertIsNone(guard.decide({"tool_input": {"command": "python scripts/merge_when_green.py 7 --wait 1800"},
                                            "cwd": tmp}))


class Autopilot(unittest.TestCase):
    def test_a_ruleset_with_required_checks_is_enough_for_native_auto_merge(self):
        rules = [{"type": "pull_request"}, {"type": "required_status_checks",
                                            "parameters": {"required_status_checks": [{"context": "check / standard"}],
                                                           "strict_required_status_checks_policy": False}}]
        with mock.patch.object(autopilot, "checked_run", return_value=json.dumps(rules)) as run:
            autopilot.required_checks(Path("."), "o/r", "main")
        self.assertEqual(run.call_count, 1)
        empty = [{"type": "required_status_checks", "parameters": {"required_status_checks": []}}]
        with mock.patch.object(autopilot, "checked_run", side_effect=[json.dumps(empty), json.dumps({})]):
            with self.assertRaises(autopilot.Blocked):
                autopilot.required_checks(Path("."), "o/r", "main")

    def publish(self, ci_state, merged=None):
        plan = {"plan_id": "p1", "goal": "x", "final_regression": ["python -m unittest"]}
        url = "https://github.com/o/r/pull/7"

        def fake_run(args, *, cwd, timeout=120):
            return json.dumps([{"number": 7, "url": url, "headRefOid": HEAD}]) if args[:3] == ["gh", "pr", "list"] else ""
        gate = mock.Mock(return_value={"merged": True}) if merged is None else mock.Mock(side_effect=merged)
        with mock.patch.object(autopilot, "ensure_base"), \
             mock.patch.object(autopilot.orchestrate, "git", return_value="main"), \
             mock.patch.object(autopilot, "integration_ready", return_value=(Path("."), "execute/p1", HEAD)), \
             mock.patch.object(autopilot, "gh_repo", return_value=("o/r", "main")), \
             mock.patch.object(autopilot, "regression"), \
             mock.patch.object(autopilot, "pr_body", return_value="body"), \
             mock.patch.object(autopilot, "record_publication"), \
             mock.patch.object(autopilot, "required_checks") as native, \
             mock.patch.object(autopilot, "follow_ci", return_value={"state": ci_state}), \
             mock.patch.object(autopilot, "checked_run", side_effect=fake_run), \
             mock.patch.object(mwg, "merge", gate):
            return autopilot.publish(plan, Path("."), auto_merge=True, watch=True), gate, native

    def test_after_green_checks_autopilot_merges_through_the_gate(self):
        out, gate, native = self.publish("pass")
        self.assertTrue(out["merged"])
        self.assertEqual(gate.call_args.args[:2], ("7", "o/r"))
        native.assert_not_called()

    def test_autopilot_does_not_merge_when_checks_did_not_pass(self):
        with self.assertRaisesRegex(autopilot.Blocked, "ended pending"):
            self.publish("pending")

    def test_a_gate_refusal_leaves_the_pull_request_open(self):
        with self.assertRaisesRegex(autopilot.Blocked, "not merged: it changes files"):
            self.publish("pass", merged=mwg.Refused("it changes files the owner keeps"))


if __name__ == "__main__":
    unittest.main()
