#!/usr/bin/env python3
"""Shared result format for verify.py, preserve.py and adversarial.py.

Every check produces one result with a status:
  PASS     the check ran and the expectation held
  FAIL     the check ran and found a problem
  SKIP     the check does not apply here, with the reason in evidence
  ERROR    the check itself broke, so nothing is known
  NOT_RUN  a required check could not run. It never counts as a pass.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

STATUSES = ("PASS", "FAIL", "SKIP", "ERROR", "NOT_RUN")
SEVERITIES = ("critical", "high", "medium", "low", "info")
SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "verify-report.schema.json"


def result(check_id: str, category: str, status: str, *, severity: str = "medium", evidence: str = "",
           artifact: str | None = None, repro: str | None = None, error: str | None = None,
           expected: str | None = None, fix: str | None = None, required: bool = True) -> dict:
    assert status in STATUSES, status
    assert severity in SEVERITIES, severity
    return {"id": check_id, "category": category, "severity": severity, "status": status, "required": required,
            "evidence": evidence[-2000:], "artifact": artifact, "repro": repro, "error": (error or None) and error[-2000:],
            "expected": expected, "fix": fix, "at": now()}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def environment() -> dict:
    def version(cmd):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
            return (out.stdout or out.stderr).strip().splitlines()[0][:80]
        except (OSError, IndexError, subprocess.TimeoutExpired):
            return None
    return {"os": platform.platform(), "python": platform.python_version(), "git": version(["git", "--version"]),
            "cwd": os.getcwd(), "executable": sys.executable}


def verdict(results: list[dict]) -> str:
    """The run passes only when every required check passed or was skipped with a reason."""
    for item in results:
        if not item["required"]:
            continue
        if item["status"] in {"FAIL", "ERROR", "NOT_RUN"}:
            return "FAIL"
        if item["status"] == "SKIP" and not item["evidence"].strip():
            return "FAIL"
    return "PASS"


def counts(results: list[dict]) -> dict:
    return {status: sum(1 for r in results if r["status"] == status) for status in STATUSES}


def validate(data, schema: dict, where: str = "$") -> list[str]:
    """A small JSON Schema subset: type, required, properties, items, enum, additionalProperties false."""
    errors = []
    kinds = schema.get("type")
    if kinds:
        allowed = kinds if isinstance(kinds, list) else [kinds]
        mapping = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None),
                   "integer": int, "number": (int, float)}
        ok = any(isinstance(data, mapping[k]) and not (k in {"integer", "number"} and isinstance(data, bool))
                 for k in allowed)
        if not ok:
            return [f"{where}: expected {kinds}, got {type(data).__name__}"]
    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{where}: {data!r} is not one of {schema['enum']}")
    if isinstance(data, dict):
        for key in schema.get("required", []):
            if key not in data:
                errors.append(f"{where}: missing {key}")
        props = schema.get("properties", {})
        for key, value in data.items():
            if key in props:
                errors += validate(value, props[key], f"{where}.{key}")
            elif schema.get("additionalProperties") is False:
                errors.append(f"{where}: unexpected {key}")
    if isinstance(data, list) and "items" in schema:
        for index, value in enumerate(data):
            errors += validate(value, schema["items"], f"{where}[{index}]")
    return errors


def build_report(name: str, level: str, results: list[dict], extra: dict | None = None) -> dict:
    report = {"schema": "standards/verify-report/v1", "name": name, "level": level, "created": now(),
              "environment": environment(), "verdict": verdict(results), "counts": counts(results),
              "results": results}
    report.update(extra or {})
    return report


def write_report(report: dict, out_dir: Path) -> tuple[Path, Path]:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    problems = validate(report, schema)
    if problems:
        raise ValueError("report does not match its schema: " + "; ".join(problems[:5]))
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "report.json"
    md_path = out_dir / "report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(markdown(report), encoding="utf-8")
    return json_path, md_path


def markdown(report: dict) -> str:
    c = report["counts"]
    lines = [f"# {report['name']}: {report['verdict']}", "",
             f"Level {report['level']}. Created {report['created']} on {report['environment']['os']}, "
             f"Python {report['environment']['python']}.", "",
             f"PASS {c['PASS']}, FAIL {c['FAIL']}, ERROR {c['ERROR']}, NOT_RUN {c['NOT_RUN']}, SKIP {c['SKIP']}.", "",
             "| Status | Check | Category | Severity | Evidence |", "| --- | --- | --- | --- | --- |"]
    order = {s: i for i, s in enumerate(("FAIL", "ERROR", "NOT_RUN", "SKIP", "PASS"))}
    for item in sorted(report["results"], key=lambda r: (order[r["status"]], r["id"])):
        text = (item["error"] or item["evidence"] or "").replace("\n", " ").replace("|", "/")[:160]
        flag = "" if item["required"] else " (optional)"
        lines.append(f"| {item['status']} | {item['id']}{flag} | {item['category']} | {item['severity']} | {text} |")
    problems = [r for r in report["results"] if r["status"] in {"FAIL", "ERROR", "NOT_RUN"}]
    if problems:
        lines += ["", "## How to reproduce and fix", ""]
        for item in problems:
            lines.append(f"- {item['id']}: run `{item['repro'] or 'n/a'}`. Expected: {item['expected'] or 'n/a'}. "
                         f"Fix: {item['fix'] or 'see the evidence'}.")
    return "\n".join(lines) + "\n"
