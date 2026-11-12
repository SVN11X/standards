#!/usr/bin/env python3
"""Cross-model review: a different model than the author returns a JSON verdict on a diff.

Findings that cite files or lines outside the diff are dropped. One fix round runs
when a high finding survives validation.

Usage: python scripts/review.py DIFF_FILE --author MODEL --reviewer MODEL [--repo DIR]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import orchestrate  # noqa: E402

SEVERITIES = ("high", "medium", "low")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def diff_lines(diff: str) -> dict[str, set[int]]:
    """New-side line numbers that the diff shows, per file."""
    shown: dict[str, set[int]] = {}
    current, number = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            name = line[4:].strip()
            current = None if name == "/dev/null" else (name[2:] if name.startswith("b/") else name)
            if current:
                shown.setdefault(current, set())
        elif line.startswith("--- ") or line.startswith("diff "):
            continue
        elif (match := HUNK.match(line)):
            number = int(match.group(1))
        elif current and line[:1] in ("+", " "):
            shown[current].add(number)
            number += 1
    return shown


def validate_findings(findings, shown: dict[str, set[int]]) -> tuple[list[dict], list[dict]]:
    """Split findings into kept and dropped. A finding must cite a file and lines the diff shows."""
    kept, dropped = [], []
    for item in findings if isinstance(findings, list) else []:
        if not isinstance(item, dict):
            dropped.append({"finding": item, "reason": "not an object"})
            continue
        start, end = item.get("line_start"), item.get("line_end", item.get("line_start"))
        reason = None
        if item.get("severity") not in SEVERITIES:
            reason = "unknown severity"
        elif not isinstance(item.get("message"), str) or not item["message"].strip():
            reason = "no message"
        elif item.get("file") not in shown:
            reason = "file not in diff"
        elif not all(isinstance(n, int) and not isinstance(n, bool) for n in (start, end)) or start > end:
            reason = "bad line range"
        elif not all(n in shown[item["file"]] for n in range(start, end + 1)):
            reason = "lines not in diff"
        if reason:
            dropped.append({"finding": item, "reason": reason})
        else:
            kept.append(item)
    return kept, dropped


def prompt_for(diff: str) -> str:
    return ("Review this diff. Reply with JSON only: {\"verdict\": \"pass\" or \"fail\", \"findings\": "
            "[{\"severity\": \"high|medium|low\", \"file\": str, \"line_start\": int, \"line_end\": int, "
            "\"message\": str}]}. Cite only lines the diff shows. Use high only for a defect that breaks "
            "behavior or security.\n\n" + diff)


def ollama_reviewer(repo: Path, model: str):
    """A reviewer that goes through the same gate and Ollama call as every other model request."""
    def call(prompt: str) -> dict:
        data = orchestrate.delegate_ollama(prompt, model, want_json=True, repo=repo)
        parsed = data.get("parsed")
        if not isinstance(parsed, dict):
            raise ValueError(f"reviewer gave no JSON ({data.get('state')})")
        return parsed
    return call


def one_pass(diff: str, reviewer) -> dict:
    try:
        raw = reviewer(prompt_for(diff))
    except (OSError, ValueError) as error:
        return {"verdict": "error", "findings": [], "dropped": [], "error": str(error)[:300]}
    if not isinstance(raw, dict):
        return {"verdict": "error", "findings": [], "dropped": [], "error": "reply is not an object"}
    kept, dropped = validate_findings(raw.get("findings"), diff_lines(diff))
    if any(f["severity"] == "high" for f in kept):
        verdict = "fail"
    else:
        verdict = "warn" if kept else "pass"
    return {"verdict": verdict, "findings": kept, "dropped": dropped}


def review(diff: str, author: str, reviewer_model: str, reviewer, fixer=None) -> dict:
    """Review a diff. `reviewer(prompt) -> dict`. `fixer(findings) -> new diff` runs once on a high finding."""
    if not author or not reviewer_model or orchestrate.same_model(author, reviewer_model):
        return {"verdict": "blocked", "reason": "the reviewer must be a different model than the author",
                "findings": [], "dropped": [], "rounds": 0}
    result = one_pass(diff, reviewer)
    result["rounds"] = 1
    if result["verdict"] == "fail" and fixer is not None:
        highs = [f for f in result["findings"] if f["severity"] == "high"]
        fixed = fixer(highs)
        if fixed:
            second = one_pass(fixed, reviewer)
            second.update(rounds=2, first_findings=result["findings"], diff=fixed)
            return second
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("diff_file")
    parser.add_argument("--author", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--repo", default=".")
    args = parser.parse_args(argv)
    diff = Path(args.diff_file).read_text(encoding="utf-8")
    result = review(diff, args.author, args.reviewer, ollama_reviewer(Path(args.repo), args.reviewer))
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"] in ("pass", "warn") else 1


if __name__ == "__main__":
    sys.exit(main())
