#!/usr/bin/env python3
"""Cross-model review: a different model than the author returns a JSON verdict on a diff.

Findings that cite files or lines outside the diff are dropped. One fix round runs
when a high finding survives validation. A diff longer than one part is reviewed one
part at a time, so the reviewer never gets a prompt cut at its context limit, and a
diff over the review limit is refused instead of judged in part.

Usage: python scripts/review.py DIFF_FILE --author MODEL --reviewer MODEL [--repo DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import orchestrate  # noqa: E402

SEVERITIES = ("high", "medium", "low")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
HUNK_FULL = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$")
# With num_ctx 4096 and a reply of 1500 tokens, 6000 characters of diff plus the instructions fit for code.
PART_CHARS = 6000
MAX_DIFF_CHARS = 100000


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


def limits(conf: dict | None) -> dict:
    """The part size and the largest diff a review takes, from the review section of the policy."""
    spec = (conf or {}).get("review") or {}
    return {"part_chars": int(spec.get("part_chars", PART_CHARS)), "max_chars": int(spec.get("max_diff_chars", MAX_DIFF_CHARS))}


def file_blocks(diff: str) -> list[dict]:
    """Each file of a git diff: its name, its header lines and its hunks, each hunk with its @@ line first."""
    blocks: list[dict] = []
    for line in diff.splitlines():
        if line.startswith("diff --git ") or not blocks:
            blocks.append({"name": None, "header": [], "hunks": []})
        block = blocks[-1]
        if line.startswith("@@"):
            block["hunks"].append([line])
        elif block["hunks"]:
            block["hunks"][-1].append(line)
        else:
            block["header"].append(line)
            if line.startswith("+++ ") and line[4:].strip() != "/dev/null":
                block["name"] = line[4:].strip().removeprefix("b/")
            elif line.startswith("--- ") and block["name"] is None and line[4:].strip() != "/dev/null":
                block["name"] = line[4:].strip().removeprefix("a/")
    return [b for b in blocks if b["header"] or b["hunks"]]


def cut_hunk(hunk: list[str], limit: int) -> list[list[str]]:
    """A hunk longer than `limit` characters as several hunks with their own @@ lines, so each keeps the line
    numbers of the file and a finding on it is validated as before."""
    match = HUNK_FULL.match(hunk[0])
    if not match or len("\n".join(hunk)) <= limit:
        return [hunk]
    old, new, rest = int(match.group(1)), int(match.group(2)), match.group(3)
    pieces, body, size, counts = [], [], 0, [0, 0]

    def flush():
        pieces.append([f"@@ -{old},{counts[0]} +{new},{counts[1]} @@{rest}", *body])

    for line in hunk[1:]:
        if body and size + len(line) + 1 > limit:
            flush()
            old, new = old + counts[0], new + counts[1]
            body, size, counts = [], 0, [0, 0]
        body.append(line)
        size += len(line) + 1
        if line.startswith("-"):
            counts[0] += 1
        elif line.startswith("+"):
            counts[1] += 1
        elif not line.startswith("\\"):
            counts[0] += 1
            counts[1] += 1
    if body:
        flush()
    return pieces


def parts(diff: str, limit: int = PART_CHARS) -> list[str]:
    """The diff in parts of about `limit` characters. A part holds whole files when they fit, and a file is cut only
    between hunks, or inside a hunk longer than a part. Every part keeps the header of each file it shows."""
    if len(diff) <= limit:
        return [diff]
    chunks: list[str] = []
    for block in file_blocks(diff):
        head = "\n".join(block["header"])
        room = max(limit - len(head) - 1, 200)
        pieces = [piece for hunk in block["hunks"] for piece in cut_hunk(hunk, room)]
        group: list[str] = []
        for piece in ["\n".join(p) for p in pieces]:
            if group and len(head) + sum(len(g) + 1 for g in group) + len(piece) > limit:
                chunks.append("\n".join([head, *group]) + "\n")
                group = []
            group.append(piece)
        chunks.append("\n".join([head, *group]) + "\n")
    out, current = [], ""
    for chunk in chunks:
        if current and len(current) + len(chunk) > limit:
            out.append(current)
            current = ""
        current += chunk
    return [*out, current] if current else out


def change_map(diff: str) -> list[str]:
    return [b["name"] for b in file_blocks(diff) if b["name"]]


def prompt_for(diff: str, scope: list[str] | None = None) -> str:
    whole = f" This diff is one part of a larger change to {', '.join(scope)}. Judge the lines shown here." if scope else ""
    return ("Review this diff. Reply with JSON only: {\"verdict\": \"pass\" or \"fail\", \"findings\": "
            "[{\"severity\": \"high|medium|low\", \"file\": str, \"line_start\": int, \"line_end\": int, "
            "\"message\": str}]}. Cite only lines the diff shows. Use high only for a defect that breaks "
            "behavior or security." + whole + "\n\n" + diff)


def ollama_reviewer(repo: Path, model: str):
    """A reviewer that goes through the same gate and Ollama call as every other model request. It gets the reply
    budget the review-diff bench class measured, so a real review is not cut where the bench was not."""
    def call(prompt: str) -> dict:
        data = orchestrate.delegate_ollama(prompt, model, want_json=True, repo=repo, task="review-diff")
        parsed = data.get("parsed")
        if not isinstance(parsed, dict):
            raise ValueError(f"reviewer gave no JSON ({data.get('state')})")
        return parsed
    return call


def one_pass(diff: str, reviewer, scope: list[str] | None = None) -> dict:
    try:
        raw = reviewer(prompt_for(diff, scope))
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


def review_parts(diff: str, reviewer, part_chars: int, seen: dict) -> dict:
    """One call per part. A part whose prompt was already judged in this review is not sent again: the reviewer
    runs at a fixed temperature and seed, so the same prompt gets the same answer. An error in any part ends
    the review, because a diff with an unjudged part cannot pass."""
    pieces = parts(diff, part_chars)
    scope = change_map(diff) if len(pieces) > 1 else None
    merged = {"verdict": "pass", "findings": [], "dropped": [], "parts": len(pieces), "calls": 0, "reused": 0}
    for piece in pieces:
        key = hashlib.sha256(prompt_for(piece, scope).encode("utf-8")).hexdigest()
        if key in seen:
            merged["reused"] += 1
            result = seen[key]
        else:
            merged["calls"] += 1
            result = one_pass(piece, reviewer, scope)
            if result["verdict"] != "error":
                seen[key] = result
        if result["verdict"] == "error":
            return {**merged, "verdict": "error", "error": result.get("error")}
        merged["findings"] += result["findings"]
        merged["dropped"] += result["dropped"]
    if any(f["severity"] == "high" for f in merged["findings"]):
        merged["verdict"] = "fail"
    elif merged["findings"]:
        merged["verdict"] = "warn"
    return merged


def review(diff: str, author: str, reviewer_model: str, reviewer, fixer=None, part_chars: int = PART_CHARS,
           max_chars: int = MAX_DIFF_CHARS) -> dict:
    """Review a diff. `reviewer(prompt) -> dict`. `fixer(findings) -> new diff` runs once on a high finding."""
    if not author or not reviewer_model or orchestrate.same_model(author, reviewer_model):
        return {"verdict": "blocked", "reason": "the reviewer must be a different model than the author",
                "findings": [], "dropped": [], "rounds": 0}
    if len(diff) > max_chars:
        return {"verdict": "blocked", "reason": f"the diff has {len(diff):,} characters, over the review limit of "
                f"{max_chars:,}. Split the work so a reviewer can judge all of it", "findings": [], "dropped": [], "rounds": 0}
    seen: dict = {}
    result = review_parts(diff, reviewer, part_chars, seen)
    result["rounds"] = 1
    if result["verdict"] == "fail" and fixer is not None:
        highs = [f for f in result["findings"] if f["severity"] == "high"]
        fixed = fixer(highs)
        if fixed and len(fixed) <= max_chars:
            second = review_parts(fixed, reviewer, part_chars, seen)
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
    result = review(diff, args.author, args.reviewer, ollama_reviewer(Path(args.repo), args.reviewer),
                    **limits(orchestrate.policy()))
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"] in ("pass", "warn") else 1


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
