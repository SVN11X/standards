#!/usr/bin/env python3
"""Read-only triage of legacy BLOCKED entries in docs/improvement-plan.md.

Nothing is marked complete automatically. The source of truth stays in the plan;
this only splits actual human decisions from work executable by existing tools.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Classification is conservative; missing or unfamiliar blockers require review.
RULES = (
    ("analyzer", "run `analyze.py`", "technical", "Run existing analyzer with real models and current privacy gate"),
    ("powershell", "analyze-models.ps1", "technical", "Parse the script in Windows PowerShell, then run the safe checks"),
    ("model-sources", "official pages again", "review", "Recheck official sources; do not assert checked without evidence"),
    ("design-pairs", "pairs of screens", "human", "Supply actual examples of preferred visual design"),
    ("planner-policy", "free model may plan", "human", "Approve the planning and deep-review policy"),
    ("pages", "publish the gallery", "human", "Approve public publication and repository visibility"),
    ("provider-keys", "real service with the owner's key", "credential", "Provide credentials through the existing secure provider setup"),
    ("providers-policy", "providers.yml` says", "review", "Verify provider data handling and approve any sensitive policy change"),
    ("vision", "opencode run --file", "technical", "Try a verified vision-capable free/local model and synthetic image"),
    ("new-bench", "refactor-module", "technical", "Measure refactor-module, review-diff and decompose with existing analyzer"),
    ("gateway", "FreeLLMAPI", "credential", "Verify gateway against real API after explicit provider approval"),
)


def classify(line: str) -> dict:
    for key, needle, category, next_step in RULES:
        if needle.lower() in line.lower():
            return {"id": key, "category": category, "next": next_step, "text": line.strip()}
    return {"id": "unclassified", "category": "review", "next": "Identify and triage this new blocker",
            "text": line.strip()}


def snapshot(repo: Path = ROOT) -> dict:
    path = Path(repo) / "docs" / "improvement-plan.md"
    if not path.is_file():
        return {"error": f"plan not available: {path}", "items": [], "counts": {}}
    lines = path.read_text(encoding="utf-8").splitlines()
    blocked = [line for line in lines if re.search(r"\bBLOCKED\s*:", line)]
    items = [classify(line) for line in blocked]
    return {"source": str(path), "items": items,
            "counts": {category: sum(item["category"] == category for item in items)
                       for category in ("technical", "human", "credential", "review")}}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=ROOT)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    result = snapshot(args.repo)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Pending blockers (classification, not an execution result):")
        for item in result["items"]:
            print(f"  [{item['category']}] {item['id']}: {item['next']}")
        print("No blocker is considered resolved without a saved verification result.")
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
