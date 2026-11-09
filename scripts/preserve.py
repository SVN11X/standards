#!/usr/bin/env python3
"""Keep protected data from disappearing by accident.

Commands:
  snapshot   record the hash and size of every protected file, and the ids in protected JSON lists
  compare    compare the working tree with the snapshot. Deletions, edits, lost ids, duplicates,
             broken JSON and counts under the minimum fail, unless docs/preservation.yml allows them.
  coverage   compare the items an extraction expected with the items it produced, and write the
             missing ones to a file so the extraction can resume from there.

The rules live in docs/preservation.yml of the repository:

  protect: ["data/**", "assets/img/**"]
  json_ids:
    - {file: data/questions.json, path: questions, id: id, min_count: 349}
  allow:
    - {path: data/old.json, change: delete, reason: "replaced by questions.json", until: 2026-12-31}

The snapshot lives inside the git folder by default, so it is never committed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required. Install it with: pip install pyyaml")

CONFIG = Path("docs") / "preservation.yml"


def load_config(repo: Path, path: Path | None) -> dict:
    target = path if path else repo / CONFIG
    if not target.exists():
        return {}
    return yaml.safe_load(target.read_text(encoding="utf-8")) or {}


def default_baseline(repo: Path) -> Path:
    try:
        out = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-path", "standards/preserve-baseline.json"],
                             capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        path = Path(out)
        return path if path.is_absolute() else repo / path
    except (OSError, subprocess.SubprocessError):
        return repo / ".preserve-baseline.json"


def glob_match(rel: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(rel, pattern):
            return True
        if pattern.endswith("/**") and (rel == pattern[:-3] or rel.startswith(pattern[:-2])):
            return True
    return False


def protected_files(repo: Path, patterns: list[str]) -> list[str]:
    files = []
    for path in repo.rglob("*"):
        if not path.is_file() or ".git" in path.relative_to(repo).parts:
            continue
        rel = path.relative_to(repo).as_posix()
        if glob_match(rel, patterns):
            files.append(rel)
    return sorted(files)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def dig(data, dotted: str):
    for part in [p for p in (dotted or "").split(".") if p]:
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def json_ids(repo: Path, rule: dict) -> tuple[list | None, str | None]:
    path = repo / rule["file"]
    if not path.exists():
        return None, f"{rule['file']} does not exist"
    try:
        items = dig(json.loads(path.read_text(encoding="utf-8")), rule.get("path", ""))
    except (ValueError, KeyError, IndexError, TypeError) as error:
        return None, f"{rule['file']} is not valid JSON or has no {rule.get('path') or 'root'} list: {error}"
    if not isinstance(items, list):
        return None, f"{rule['file']}: {rule.get('path') or 'root'} is not a list"
    key = rule.get("id", "id")
    return [item.get(key) if isinstance(item, dict) else item for item in items], None


def snapshot(repo: Path, config: dict) -> dict:
    files = {}
    for rel in protected_files(repo, config.get("protect") or []):
        path = repo / rel
        files[rel] = {"sha256": sha256(path), "size": path.stat().st_size}
    ids = {}
    for rule in config.get("json_ids") or []:
        values, problem = json_ids(repo, rule)
        ids[rule["file"]] = {"ids": values, "error": problem}
    return {"created": evidence.now(), "files": files, "ids": ids}


def allowance(config: dict, rel: str, change: str, today: dt.date) -> tuple[bool, str]:
    for item in config.get("allow") or []:
        if not fnmatch.fnmatch(rel, str(item.get("path", ""))) or item.get("change", "any") not in {change, "any"}:
            continue
        until = item.get("until")
        if until and dt.date.fromisoformat(str(until)) < today:
            return False, f"the exception for {rel} expired on {until}"
        if not str(item.get("reason", "")).strip():
            return False, f"the exception for {rel} has no reason"
        return True, f"allowed: {item['reason']}"
    return False, ""


def compare(repo: Path, config: dict, baseline: dict, today: dt.date | None = None) -> list[dict]:
    today = today or dt.date.today()
    results = []
    repro = "python scripts/preserve.py compare"
    current = snapshot(repo, config)
    old, new = baseline.get("files", {}), current["files"]
    for rel in sorted(set(old) - set(new)):
        ok, why = allowance(config, rel, "delete", today)
        results.append(evidence.result(f"preserve.missing:{rel}", "data", "PASS" if ok else "FAIL", severity="high",
                                       evidence=why or f"{rel} was in the snapshot and is gone", repro=repro,
                                       expected="the file still exists, or docs/preservation.yml allows its deletion",
                                       fix="restore it with git checkout, or declare the deletion with a reason"))
    for rel in sorted(set(old) & set(new)):
        if old[rel]["sha256"] != new[rel]["sha256"]:
            ok, why = allowance(config, rel, "modify", today)
            results.append(evidence.result(f"preserve.changed:{rel}", "data", "PASS" if ok else "FAIL", severity="medium",
                                           evidence=why or f"{rel} changed: {old[rel]['size']} to {new[rel]['size']} bytes",
                                           repro=repro, expected="protected files keep their content unless allowed",
                                           fix="revert the change, or declare it in docs/preservation.yml"))
    added = sorted(set(new) - set(old))
    if added:
        results.append(evidence.result("preserve.added", "data", "PASS", severity="info", required=False,
                                       evidence=f"{len(added)} new protected files, first: {', '.join(added[:5])}"))
    by_hash: dict[str, list[str]] = {}
    for rel, meta in new.items():
        if meta["size"]:
            by_hash.setdefault(meta["sha256"], []).append(rel)
    old_dupes = {h for h, _ in _dupes(old).items()}
    fresh = {h: paths for h, paths in by_hash.items() if len(paths) > 1 and h not in old_dupes}
    results.append(evidence.result("preserve.duplicate-files", "data", "FAIL" if fresh else "PASS", severity="low",
                                   required=False, evidence="; ".join(", ".join(p) for p in fresh.values())[:500]
                                   or "no new identical files"))
    for rel in new:
        if rel.endswith(".json"):
            try:
                json.loads((repo / rel).read_text(encoding="utf-8"))
            except ValueError as error:
                results.append(evidence.result(f"preserve.json:{rel}", "data", "FAIL", severity="high",
                                               evidence=f"{rel} is not valid JSON: {error}", repro=repro,
                                               expected="valid JSON", fix="restore the last good version"))
    for rule in config.get("json_ids") or []:
        name = rule["file"]
        values, problem = json_ids(repo, rule)
        if problem:
            results.append(evidence.result(f"preserve.ids:{name}", "data", "FAIL", severity="high", evidence=problem,
                                           repro=repro, expected="a readable list"))
            continue
        present = [v for v in values if v is not None]
        dupes = sorted({str(v) for v in present if present.count(v) > 1})
        missing_ids = [v for v in values if v is None]
        before = (baseline.get("ids", {}).get(name) or {}).get("ids") or []
        lost = sorted({str(v) for v in before if v is not None} - {str(v) for v in present})
        problems = []
        if dupes:
            problems.append(f"repeated ids: {', '.join(dupes[:10])}")
        if missing_ids:
            problems.append(f"{len(missing_ids)} items without {rule.get('id', 'id')}")
        if lost:
            ok, why = allowance(config, name, "delete-ids", today)
            if not ok:
                problems.append(f"{len(lost)} ids lost since the snapshot: {', '.join(lost[:10])}")
        minimum = rule.get("min_count")
        if minimum is not None and len(values) < int(minimum):
            problems.append(f"{len(values)} items, fewer than the minimum {minimum}")
        results.append(evidence.result(f"preserve.ids:{name}", "data", "FAIL" if problems else "PASS", severity="high",
                                       evidence="; ".join(problems) or f"{len(values)} items, ids unique, none lost",
                                       repro=repro, expected="unique ids, none lost, count at or above the minimum",
                                       fix="restore the lost items or declare the change with change: delete-ids"))
    for item in config.get("allow") or []:
        until = item.get("until")
        if until and dt.date.fromisoformat(str(until)) < today:
            results.append(evidence.result(f"preserve.expired:{item.get('path')}", "data", "FAIL", severity="low",
                                           required=False, evidence=f"exception expired on {until}",
                                           fix="remove the exception from docs/preservation.yml"))
    return results


def _dupes(files: dict) -> dict:
    seen: dict[str, list[str]] = {}
    for rel, meta in files.items():
        if meta.get("size"):
            seen.setdefault(meta["sha256"], []).append(rel)
    return {h: p for h, p in seen.items() if len(p) > 1}


def read_items(path: Path, dotted: str, key: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = dig(json.loads(text), dotted)
        return [str(item.get(key) if isinstance(item, dict) else item) for item in data]
    if path.suffix == ".jsonl":
        return [str(json.loads(line).get(key)) for line in text.splitlines() if line.strip()]
    return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]


def coverage(expected: list[str], found: list[str]) -> dict:
    expected_set = list(dict.fromkeys(expected))
    found_set = set(found)
    missing = [item for item in expected_set if item not in found_set]
    duplicates = sorted({item for item in found if found.count(item) > 1})
    extra = sorted(found_set - set(expected_set))
    return {"expected": len(expected_set), "found": len(found_set), "missing": missing, "duplicates": duplicates,
            "extra": extra, "complete": not missing and not duplicates}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("snapshot", "compare"):
        p = sub.add_parser(name)
        p.add_argument("--repo", type=Path, default=Path.cwd())
        p.add_argument("--config", type=Path)
        p.add_argument("--baseline", type=Path)
        p.add_argument("--json", action="store_true")
    p = sub.add_parser("coverage")
    p.add_argument("--expected", type=Path, required=True, help="text with one item per line, or JSON/JSONL")
    p.add_argument("--found", type=Path, required=True)
    p.add_argument("--path", default="", help="dotted path to the list inside a JSON file")
    p.add_argument("--id", default="id")
    p.add_argument("--resume-out", type=Path, help="write the missing items here, one per line")
    args = parser.parse_args(argv)

    if args.command == "coverage":
        report = coverage(read_items(args.expected, args.path, args.id), read_items(args.found, args.path, args.id))
        if args.resume_out:
            args.resume_out.write_text("\n".join(report["missing"]) + ("\n" if report["missing"] else ""), encoding="utf-8")
        print(json.dumps({**report, "missing": report["missing"][:50]}, indent=2))
        return 0 if report["complete"] else 1

    repo = args.repo.resolve()
    config = load_config(repo, args.config)
    if not config.get("protect") and not config.get("json_ids"):
        print(f"No rules in {CONFIG}. Nothing to protect yet.")
        return 0
    baseline_path = args.baseline or default_baseline(repo)
    if args.command == "snapshot":
        data = snapshot(repo, config)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"snapshot of {len(data['files'])} files and {len(data['ids'])} id lists in {baseline_path}")
        return 0
    if not baseline_path.exists():
        print(f"No snapshot at {baseline_path}. Run snapshot first, before the change.")
        return 2
    results = compare(repo, config, json.loads(baseline_path.read_text(encoding="utf-8")))
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for item in results:
            if item["status"] != "PASS" or item["severity"] != "info":
                print(f"{item['status']:<5} {item['id']}: {item['evidence']}")
    return 0 if evidence.verdict(results) == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
