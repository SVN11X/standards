#!/usr/bin/env python3
"""Read Lighthouse JSON reports and say what they measured. It runs nothing and uses no network.

Several reports of one state are runs of the same page: the report gives the median of each metric and score, the
spread of the performance score, and the failing audits and largest contentful paint element of the median run.

Usage: python speed_report.py summary RUN.json [RUN.json ...] [--json]
       python speed_report.py compare --before RUN.json ... --after RUN.json ... [--json]

Make a report with: npx lighthouse URL --output=json --output-path=run1.json --form-factor=mobile
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

CATEGORIES = ("performance", "accessibility", "best-practices", "seo")
# Audit id, short name, unit and the upper end of "good" in that unit.
METRICS = (("first-contentful-paint", "FCP", "s", 1.8), ("largest-contentful-paint", "LCP", "s", 2.5),
           ("total-blocking-time", "TBT", "ms", 200), ("cumulative-layout-shift", "CLS", "", 0.1),
           ("speed-index", "SI", "s", 3.4))
METRIC_IDS = {m[0] for m in METRICS} | {"interactive", "max-potential-fid", "first-meaningful-paint"}


def load(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    # A PageSpeed Insights reply holds the Lighthouse result one level down.
    return data.get("lighthouseResult", data) if isinstance(data, dict) else {}


def metric(lhr: dict, audit: str, unit: str) -> float | None:
    value = ((lhr.get("audits") or {}).get(audit) or {}).get("numericValue")
    if not isinstance(value, (int, float)):
        return None
    return round(value / 1000, 2) if unit == "s" else round(value, 3 if unit == "" else 0)


def scores(lhr: dict) -> dict:
    out = {}
    for name in CATEGORIES:
        score = ((lhr.get("categories") or {}).get(name) or {}).get("score")
        out[name] = round(score * 100) if isinstance(score, (int, float)) else None
    return out


def first_node(details) -> dict | None:
    """The first element a details block names, whatever version of Lighthouse nested it."""
    if isinstance(details, dict):
        if isinstance(details.get("node"), dict):
            return details["node"]
        for value in details.values():
            found = first_node(value)
            if found:
                return found
    elif isinstance(details, list):
        for value in details:
            found = first_node(value)
            if found:
                return found
    return None


def saving_ms(audit: dict) -> float:
    details = audit.get("details") or {}
    if isinstance(details.get("overallSavingsMs"), (int, float)):
        return float(details["overallSavingsMs"])
    savings = audit.get("metricSavings") or {}
    return float(sum(v for k, v in savings.items() if k != "CLS" and isinstance(v, (int, float))))


def failing(lhr: dict, limit: int = 10) -> list[dict]:
    """Audits under 0.9 that are not the metrics themselves, the largest estimated saving first."""
    found = []
    for audit_id, audit in (lhr.get("audits") or {}).items():
        score = audit.get("score")
        if audit_id in METRIC_IDS or not isinstance(score, (int, float)) or score >= 0.9:
            continue
        if audit.get("scoreDisplayMode") in ("notApplicable", "manual", "informative", "error"):
            continue
        node = first_node(audit.get("details"))
        found.append({"id": audit_id, "title": audit.get("title"), "score": round(score, 2),
                      "saving_ms": round(saving_ms(audit)), "display": audit.get("displayValue"),
                      "element": (node or {}).get("snippet")})
    return sorted(found, key=lambda a: (-a["saving_ms"], a["score"]))[:limit]


def element(lhr: dict, *audit_ids: str) -> str | None:
    for audit_id in audit_ids:
        node = first_node(((lhr.get("audits") or {}).get(audit_id) or {}).get("details"))
        if node:
            return node.get("snippet") or node.get("selector") or node.get("nodeLabel")
    return None


def median(values: list) -> float | None:
    seen = [v for v in values if isinstance(v, (int, float))]
    return round(statistics.median(seen), 3) if seen else None


def summary(reports: list[dict]) -> dict:
    """Medians over the runs of one state. The median run is the one whose performance score is the median."""
    if not reports:
        raise ValueError("no report given")
    runs = [{"scores": scores(r), "metrics": {short: metric(r, audit, unit) for audit, short, unit, _ in METRICS}} for r in reports]
    perf = [run["scores"]["performance"] for run in runs]
    ranked = sorted(range(len(reports)), key=lambda i: (perf[i] is None, perf[i] or 0))
    middle = reports[ranked[len(ranked) // 2]]
    settings = middle.get("configSettings") or {}
    known = [p for p in perf if p is not None]
    metrics = {short: median([run["metrics"][short] for run in runs]) for _, short, _, _ in METRICS}
    return {"url": middle.get("finalDisplayedUrl") or middle.get("finalUrl") or middle.get("requestedUrl"),
            "lighthouse": middle.get("lighthouseVersion"), "form_factor": settings.get("formFactor"),
            "throttling": settings.get("throttlingMethod"), "runs": len(reports),
            "scores": {name: median([run["scores"][name] for run in runs]) for name in CATEGORIES},
            "performance_spread": (max(known) - min(known)) if known else None,
            "metrics": metrics,
            "good": {short: (metrics[short] <= limit if metrics[short] is not None else None) for _, short, _, limit in METRICS},
            "lcp_element": element(middle, "largest-contentful-paint-element"),
            "shifting_element": element(middle, "layout-shifts", "layout-shift-elements"),
            "failing": failing(middle),
            "note": None if len(reports) >= 3 else "fewer than 3 runs: the score moves between runs, so a median of 3 is the minimum"}


def compare(before: list[dict], after: list[dict]) -> dict:
    """Two states side by side. A change in the performance score inside the spread of the runs is not an improvement."""
    a, b = summary(before), summary(after)
    delta = {name: (round(b["scores"][name] - a["scores"][name], 1)
                    if a["scores"][name] is not None and b["scores"][name] is not None else None) for name in CATEGORIES}
    metrics = {short: (round(b["metrics"][short] - a["metrics"][short], 3)
                       if a["metrics"][short] is not None and b["metrics"][short] is not None else None)
               for _, short, _, _ in METRICS}
    spread = max(x for x in (a["performance_spread"], b["performance_spread"], 0) if x is not None)
    moved = delta["performance"]
    verdict = ("not measured" if moved is None else "inside the spread between runs, not an improvement"
               if abs(moved) <= spread else "better" if moved > 0 else "worse")
    warnings = []
    if (a["form_factor"], a["lighthouse"]) != (b["form_factor"], b["lighthouse"]):
        warnings.append("the two states ran with another form factor or Lighthouse version, so they are not comparable")
    return {"before": a, "after": b, "score_change": delta, "metric_change": metrics, "performance": verdict,
            "warnings": warnings}


def print_summary(data: dict, title: str = "") -> None:
    units = {short: unit for _, short, unit, _ in METRICS}
    print(f"{title}{data['url']}  {data['form_factor']}  Lighthouse {data['lighthouse']}  {data['runs']} run(s)")
    print("  scores: " + "  ".join(f"{name} {data['scores'][name]}" for name in CATEGORIES)
          + f"  (performance spread {data['performance_spread']})")
    print("  metrics: " + "  ".join(f"{short} {value}{units[short]}{'' if data['good'][short] in (True, None) else ' (not good)'}"
                                    for short, value in data["metrics"].items()))
    if data["lcp_element"]:
        print(f"  LCP element: {data['lcp_element'][:160]}")
    if data["shifting_element"]:
        print(f"  shifting element: {data['shifting_element'][:160]}")
    for audit in data["failing"]:
        print(f"  - {audit['id']} (score {audit['score']}, saving about {audit['saving_ms']} ms)"
              + (f": {audit['element'][:120]}" if audit["element"] else ""))
    if data["note"]:
        print(f"  note: {data['note']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("summary")
    one.add_argument("runs", nargs="+")
    one.add_argument("--json", action="store_true")
    two = sub.add_parser("compare")
    two.add_argument("--before", nargs="+", required=True)
    two.add_argument("--after", nargs="+", required=True)
    two.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "summary":
        data = summary([load(p) for p in args.runs])
        print(json.dumps(data, indent=2)) if args.json else print_summary(data)
        return 0
    data = compare([load(p) for p in args.before], [load(p) for p in args.after])
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print_summary(data["before"], "before: ")
        print_summary(data["after"], "after:  ")
        print("change: " + "  ".join(f"{k} {v:+}" for k, v in data["score_change"].items() if v is not None)
              + f"  performance {data['performance']}")
        for warning in data["warnings"]:
            print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
