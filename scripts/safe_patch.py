#!/usr/bin/env python3
"""Build a patch for git am and prove it applies, without touching the owner's working tree.

Commands:
  create   write the commits between --base and --head as one patch file, then run check on it
  check    apply a patch with git am in a temporary worktree at --base, run the tests there, and
           compare the resulting tree with --expect (for example the branch the patch came from)

Rollback for the owner after git am: `git am --abort` while it is still running, or
`git reset --keep ORIG_HEAD` right after it finished.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence  # noqa: E402

IDENTITY = ["-c", "user.name=safe-patch", "-c", "user.email=safe-patch@localhost", "-c", "core.autocrlf=false"]


def git(repo: Path, *args, check=True) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *IDENTITY, "-C", str(repo), *args], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=False)
    if check and result.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result


def check_patch(repo: Path, patch: Path, base: str, test: str | None = None, expect: str | None = None) -> list[dict]:
    results = []
    repro = f"python scripts/safe_patch.py check --patch {patch.name} --base {base}"
    base_sha = git(repo, "rev-parse", "--verify", f"{base}^{{commit}}").stdout.strip()
    with tempfile.TemporaryDirectory() as tmp:
        worktree = Path(tmp) / "apply"
        git(repo, "worktree", "add", "-q", "--detach", str(worktree), base_sha)
        try:
            applied = git(worktree, "am", "--keep-cr", str(patch.resolve()), check=False)
            ok = applied.returncode == 0
            results.append(evidence.result("patch.applies", "delivery", "PASS" if ok else "FAIL", severity="critical",
                                           evidence=f"git am on {base_sha[:12]}" + ("" if ok else f": {applied.stderr.strip()[:400]}"),
                                           repro=repro, expected="the patch applies cleanly with git am",
                                           fix="rebuild the patch from the right base commit"))
            if not ok:
                git(worktree, "am", "--abort", check=False)
            if ok and expect:
                want = git(repo, "rev-parse", f"{expect}^{{tree}}").stdout.strip()
                got = git(worktree, "rev-parse", "HEAD^{tree}").stdout.strip()
                results.append(evidence.result("patch.same-tree", "delivery", "PASS" if want == got else "FAIL",
                                               severity="high", evidence=f"tree {got[:12]} vs {expect} {want[:12]}",
                                               repro=repro, expected="the patched tree equals the source branch"))
            if ok and test:
                ran = subprocess.run(test, cwd=worktree, shell=True, capture_output=True, text=True,
                                     encoding="utf-8", errors="replace", timeout=1800, check=False)
                results.append(evidence.result("patch.tests", "delivery", "PASS" if ran.returncode == 0 else "FAIL",
                                               severity="high", evidence=(ran.stdout + ran.stderr)[-1500:],
                                               repro=f"{repro} --test {test!r}", expected="tests pass after the patch"))
            elif test:
                results.append(evidence.result("patch.tests", "delivery", "NOT_RUN", severity="high",
                                               evidence="the patch did not apply, so the tests could not run"))
        finally:
            git(repo, "worktree", "remove", "--force", str(worktree), check=False)
            git(repo, "worktree", "prune", check=False)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create")
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--base", required=True)
    p.add_argument("--head", default="HEAD")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--test")
    p = sub.add_parser("check")
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--patch", type=Path, required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--expect")
    p.add_argument("--test")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if args.command == "create":
        if args.out.resolve().is_relative_to(repo):
            parser.error("write the patch outside the repository")
        count = git(repo, "rev-list", "--count", f"{args.base}..{args.head}").stdout.strip()
        if count == "0":
            parser.error(f"no commits between {args.base} and {args.head}")
        patch = git(repo, "format-patch", "--stdout", f"{args.base}..{args.head}").stdout
        args.out.write_text(patch, encoding="utf-8", newline="\n")
        print(f"wrote {count} commits to {args.out}")
        results = check_patch(repo, args.out, args.base, args.test, expect=args.head)
    else:
        results = check_patch(repo, args.patch, args.base, args.test, expect=args.expect)
    for item in results:
        print(f"{item['status']:<7} {item['id']}: {item['evidence'][:200]}")
    print(json.dumps({"verdict": evidence.verdict(results)}))
    return 0 if evidence.verdict(results) == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
