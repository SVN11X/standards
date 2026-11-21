#!/usr/bin/env python3
"""Evaluate a skill: the same task runs several times, each run on its own, and a program scores every result.

A test can pass while the agent skipped a step the skill asks for. A skill's `evals.yml` names the task, a synthetic
repository to work in and the criteria of success. Each run starts from a fresh copy of that repository, gets the
skill text and the task, and its answer is graded criterion by criterion. A step that several runs skip points at
the instruction, not at one run: revise SKILL.md and run the eval again. No model grades another, as in the bench.

Commands:
  check    validate every skills/*/evals.yml
  run      SKILL --executor claude | opencode:<model> [--runs N]: run each case and grade it
  grade    SKILL --outputs DIR: grade answers saved by an earlier run again, after the criteria changed

evals.yml:
  runs: 3
  cases:
    - id: new-dependency
      task: Review the last commit of this repository.
      files: {app.py: "..."}            # the starting state, committed first
      change: {app.py: "..."}           # committed second, so the task can name "the last commit"
      criteria:
        - {id: names-line, pattern: "app\\.py:\\d+", why: "each finding names a file and a line"}
        - {id: radar, says: [radar], why: "a dependency outside the radar is a finding"}
        - {id: severity, any: [Blocker, Should fix, Consider], why: "findings carry a severity"}
        - {id: no-praise, absent: [great job, well done], why: "no praise"}
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
CHECKS = ("says", "any", "pattern", "absent")


def load(skill: str) -> dict:
    import yaml
    path = ROOT / "skills" / skill / "evals.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def problems(spec: dict, where: str) -> list[str]:
    found = []
    cases = spec.get("cases") or []
    if not cases:
        found.append(f"{where}: no cases")
    for case in cases:
        name = f"{where}:{case.get('id', '?')}"
        if not case.get("id") or not case.get("task") or not case.get("criteria"):
            found.append(f"{name}: a case needs id, task and criteria")
        for criterion in case.get("criteria") or []:
            if not criterion.get("id") or not criterion.get("why") or not any(key in criterion for key in CHECKS):
                found.append(f"{name}: criterion {criterion.get('id', '?')} needs id, why and one of {', '.join(CHECKS)}")
            elif "pattern" in criterion:
                try:
                    re.compile(criterion["pattern"])
                except re.error as error:
                    found.append(f"{name}: criterion {criterion['id']} has a pattern that does not compile ({error})")
    return found


def check_all() -> list[str]:
    found = []
    for path in sorted((ROOT / "skills").glob("*/evals.yml")):
        found += problems(load(path.parent.name), str(path.relative_to(ROOT)))
    return found


def met(criterion: dict, answer: str) -> bool:
    low = answer.lower()
    if "says" in criterion and not all(str(text).lower() in low for text in criterion["says"]):
        return False
    if "any" in criterion and not any(str(text).lower() in low for text in criterion["any"]):
        return False
    if "pattern" in criterion and not re.search(criterion["pattern"], answer):
        return False
    if "absent" in criterion and any(str(text).lower() in low for text in criterion["absent"]):
        return False
    return True


def grade(spec: dict, answers: dict[str, list[str]]) -> dict:
    """Per case: each run's score and each criterion met in k of n runs. A criterion half the runs or more missed is
    flagged as a gap of the skill, since the runs share only the instruction."""
    report = {}
    for case in spec.get("cases") or []:
        runs = answers.get(case["id"]) or []
        rows = [{criterion["id"]: met(criterion, answer) for criterion in case["criteria"]} for answer in runs]
        criteria = []
        for criterion in case["criteria"]:
            missed = sum(1 for row in rows if not row[criterion["id"]])
            criteria.append({"id": criterion["id"], "why": criterion["why"], "met": len(rows) - missed, "runs": len(rows),
                             "skill_gap": bool(rows) and missed * 2 >= len(rows)})
        report[case["id"]] = {"scores": [f"{sum(row.values())} of {len(row)}" for row in rows], "criteria": criteria}
    return report


def lines(report: dict) -> list[str]:
    out = []
    for case, data in report.items():
        out.append(f"{case}: runs scored {', '.join(data['scores']) or 'no run'}")
        for item in data["criteria"]:
            note = "  <- missed by half the runs or more: revise SKILL.md and run again" if item["skill_gap"] else ""
            out.append(f"  {item['id']}: met in {item['met']} of {item['runs']} ({item['why']}){note}")
    return out


def fixture(root: Path, case: dict) -> Path:
    import orchestrate
    repo = root / "repo"
    for stage, label in (("files", "start"), ("change", "the change to work on")):
        for rel, text in (case.get(stage) or {}).items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(text, encoding="utf-8")
        if stage == "files" or case.get("change"):
            if stage == "files":
                orchestrate.git(repo, "init", "-q")
            orchestrate.git(repo, "add", "-A")
            orchestrate.git(repo, "-c", "user.name=eval", "-c", "user.email=eval@localhost", "commit", "-q", "--allow-empty", "-m", label)
    return repo


def prompt(skill: str, case: dict) -> str:
    text = (ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    return f"Follow this skill for the task.\n\n<skill name=\"{skill}\">\n{text}\n</skill>\n\nTask: {case['task']}"


def run(skill: str, executor: str, runs: int | None = None, command: list[str] | None = None, mode: str | None = None,
        say=print) -> tuple[dict, Path]:
    """Run every case `runs` times on a fresh fixture, save each answer and grade them. Cost and privacy go through the gate."""
    import orchestrate
    spec = load(skill)
    conf, local = orchestrate.policy(), orchestrate.local_config()
    name, _, model = executor.partition(":")
    if name not in ("claude", "opencode"):
        raise ValueError("the executor is claude or opencode:<model>, an agent that can follow a skill")
    out = orchestrate.home() / "skill-evals" / skill / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    answers: dict[str, list[str]] = {}
    for case in spec["cases"]:
        for number in range(1, (runs or spec.get("runs") or 3) + 1):
            with tempfile.TemporaryDirectory() as tmp:
                repo = fixture(Path(tmp), case)
                ok, why = orchestrate.gate(name, model or None, repo, conf, orchestrate.bench_local(Path(tmp), local), mode)
                if not ok:
                    raise PermissionError(why)
                (repo / ".skill-task.md").write_text(prompt(skill, case), encoding="utf-8")
                message = "Read .skill-task.md in this folder and do exactly that task. Answer in plain text."
                template = command or conf["executors"][name]["command"]
                result = orchestrate.run(orchestrate.fill(template, model=model, message=message), cwd=repo,
                                         timeout=conf["limits"]["opencode_timeout_s"], env=orchestrate.child_env())
            answer = result["stdout"] + ("\n[timed out]" if result["timeout"] else "")
            (out / f"{case['id']}-{number}.txt").write_text(answer, encoding="utf-8")
            answers.setdefault(case["id"], []).append(answer)
            say(f"{case['id']} run {number}: exit {result['exit']} in {result['seconds']} s")
    report = grade(spec, answers)
    (out / "report.json").write_text(json.dumps({"skill": skill, "executor": executor, "report": report}, indent=2), encoding="utf-8")
    return report, out


def saved(folder: Path) -> dict[str, list[str]]:
    answers: dict[str, list[str]] = {}
    for path in sorted(folder.glob("*-[0-9]*.txt"), key=lambda p: (p.stem.rsplit("-", 1)[0], int(p.stem.rsplit("-", 1)[1]))):
        answers.setdefault(path.stem.rsplit("-", 1)[0], []).append(path.read_text(encoding="utf-8"))
    return answers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    p = sub.add_parser("run")
    p.add_argument("skill")
    p.add_argument("--executor", required=True, help="claude or opencode:<model>")
    p.add_argument("--runs", type=int)
    p.add_argument("--mode", choices=["local-only", "free-strict", "existing-subscription"])
    p = sub.add_parser("grade")
    p.add_argument("skill")
    p.add_argument("--outputs", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "check":
        found = check_all()
        print("\n".join(found) or "every evals.yml is valid")
        return 1 if found else 0
    if args.command == "grade":
        print("\n".join(lines(grade(load(args.skill), saved(args.outputs)))))
        return 0
    try:
        report, out = run(args.skill, args.executor, args.runs, mode=args.mode)
    except (PermissionError, ValueError) as error:
        print(f"not run: {error}", file=sys.stderr)
        return 1
    print("\n".join(lines(report)) + f"\nAnswers and report: {out}")
    return 0


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
