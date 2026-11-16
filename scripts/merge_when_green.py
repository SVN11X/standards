#!/usr/bin/env python3
"""Merge a pull request on the owner's behalf, only when its checks prove it and the owner allowed it.

The owner turns this on once with `python scripts/orchestrate.py consent --merge when-green`, which writes
`autopilot: {merge: when-green}` to ~/.standards/local.yml. Without that setting nothing is merged.

A pull request is merged only when all of this holds, checked right before the merge:
- it is open and has no merge conflict. A draft is marked ready first.
- at least one check ran on its head commit and every check passed or was skipped. With --wait the
  script waits for running checks, up to the given seconds.
- it changes no workflow, deploy or secret file. Those still wait for the owner.
- the merge names the head commit that was checked (--match-head-commit), so a push after the check
  cannot slip in, and it never uses --admin: every rule of the repository still applies.

Usage: python scripts/merge_when_green.py PR [--repo OWNER/NAME] [--method squash|merge|rebase] [--wait SECONDS] [--dry]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SCHEMA = "standards/merge-when-green/v1"
METHODS = ("squash", "merge", "rebase")
# Changes the owner keeps for themselves even with the setting on: how the project deploys and its secrets.
OWNER_ONLY = re.compile(r"(^|/)\.github/workflows/|(^|/)\.env($|\.)|secret|credential|(^|/)deploy|(^|/)wrangler\.(toml|jsonc?)$"
                        r"|(^|/)(Dockerfile|docker-compose\.ya?ml|compose\.ya?ml)$|\.tf$|(^|/)(Chart\.ya?ml|kustomization\.ya?ml)$", re.I)


class Refused(RuntimeError):
    """The pull request is not merged, and the reason says what is missing."""


def home() -> Path:
    return Path(os.environ.get("STANDARDS_HOME") or Path.home() / ".standards")


def owner_setting(path: Path | None = None) -> str:
    """'when-green' when the owner allowed merges, else 'ask'. Read without PyYAML too, so the hook can call it."""
    path = path or home() / "local.yml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "ask"
    try:
        import yaml
        data = yaml.safe_load(text) or {}
        value = ((data.get("autopilot") or {}) if isinstance(data, dict) else {}).get("merge")
    except Exception:  # noqa: BLE001 (no PyYAML: read the one key by hand)
        found = re.search(r"(?ms)^autopilot:\s*\n(?:[ \t]+.*\n)*?[ \t]+merge:\s*['\"]?([\w-]+)", text + "\n")
        value = found.group(1) if found else None
    return "when-green" if value == "when-green" else "ask"


def gh(args: list[str], run=None, timeout: int = 120) -> str:
    if run is not None:
        return run(args)
    out = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if out.returncode != 0:
        raise Refused(f"gh {' '.join(args[:3])} failed: {(out.stderr or out.stdout).strip()[:300]}")
    return out.stdout


def checks_of(pr: str, repo_args: list[str], run=None) -> dict:
    """The checks GitHub reports on the head of the pull request: {state, passed, failed, pending, skipped}."""
    try:
        rows = json.loads(gh(["pr", "checks", pr, *repo_args, "--json", "name,bucket"], run) or "[]")
    except Exception as error:  # noqa: BLE001 (gh fails when a pull request has no check at all)
        if "no checks reported" in str(error).lower():
            rows = []
        else:
            raise
    names = {bucket: [r.get("name") for r in rows if r.get("bucket") == bucket] for bucket in ("pass", "fail", "pending", "skipping", "cancel")}
    failed = names["fail"] + names["cancel"]
    state = "none" if not rows else "fail" if failed else "pending" if names["pending"] else "pass"
    return {"state": state, "passed": names["pass"], "failed": failed, "pending": names["pending"], "skipped": names["skipping"]}


def merge(pr: str, repo: str | None = None, method: str = "squash", wait: int = 0, dry: bool = False, run=None,
          sleep=time.sleep, clock=time.monotonic, setting: str | None = None) -> dict:
    """Merge one pull request when every condition holds. Raises Refused with the first condition that does not."""
    if (setting or owner_setting()) != "when-green":
        raise Refused("the owner's setting is ask. Turn merges on with: python scripts/orchestrate.py consent --merge when-green")
    if method not in METHODS:
        raise Refused(f"unknown merge method {method!r}")
    repo_args = ["--repo", repo] if repo else []
    info = json.loads(gh(["pr", "view", pr, *repo_args, "--json", "number,url,state,isDraft,headRefOid,mergeable,baseRefName,title"], run))
    if info.get("state") != "OPEN":
        raise Refused(f"{info.get('url')} is {str(info.get('state')).lower()}, not open")
    if info.get("mergeable") == "CONFLICTING":
        raise Refused(f"{info.get('url')} has a merge conflict with {info.get('baseRefName')}. Merge the base into it first")
    files = [line.strip() for line in gh(["pr", "diff", pr, *repo_args, "--name-only"], run).splitlines() if line.strip()]
    kept = [f for f in files if OWNER_ONLY.search(f)]
    if kept:
        raise Refused("it changes files the owner keeps for themselves (workflows, deploy or secrets): " + ", ".join(kept[:6]))
    began = clock()
    status = checks_of(pr, repo_args, run)
    while status["state"] in ("pending", "none") and clock() - began < wait:
        sleep(min(30, max(1, wait // 20)))
        status = checks_of(pr, repo_args, run)
    if status["state"] == "fail":
        raise Refused("checks failed: " + ", ".join(map(str, status["failed"])))
    if status["state"] == "pending":
        raise Refused("checks still running: " + ", ".join(map(str, status["pending"])) + ". Run again with --wait SECONDS")
    if status["state"] == "none":
        raise Refused("no check ran on this pull request, so nothing proves it")
    head = info["headRefOid"]
    result = {"schema": SCHEMA, "pr": info.get("url"), "head": head, "method": method, "checks": status, "files": len(files),
              "merged": False, "dry": dry}
    if dry:
        return result
    if info.get("isDraft"):
        gh(["pr", "ready", pr, *repo_args], run)
    # The head that was checked is the head that merges. No --admin: the repository's own rules still decide.
    gh(["pr", "merge", pr, *repo_args, f"--{method}", "--match-head-commit", head], run)
    result["merged"] = True
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pr", help="number, URL or branch of the pull request")
    parser.add_argument("--repo", help="OWNER/NAME when not run inside the repository")
    parser.add_argument("--method", choices=METHODS, default="squash")
    parser.add_argument("--wait", type=int, default=0, help="seconds to wait for running checks")
    parser.add_argument("--dry", action="store_true", help="check every condition and merge nothing")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(merge(args.pr, args.repo, args.method, args.wait, args.dry), indent=2))
    except (Refused, ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"not merged: {error}")
        return 1
    return 0


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
