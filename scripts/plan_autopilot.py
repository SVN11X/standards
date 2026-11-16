#!/usr/bin/env python3
"""Natural-language planning and gated GitHub publication for standards.

plan    -> a planner model drafts JSON -> one contract fixes, repairs and validates it (NO code executed)
go      -> plan + the executor loop with a ready queue; publication is an explicit opt-in
publish -> verify a completed execution, run final regression, create PR, watch its checks, fix a
           failed check inside the attempt budget, optionally request GitHub-native auto-merge
           (never bypass checks).

The planner is the smallest one that is enough (scripts/planner.py): Claude Haiku, Sonnet or Opus through
one `claude -p` call, or the local Ollama model when cost or privacy keep Claude out. `go --detach` leaves
the run in its own process, so nothing waits on a Claude session.

This file intentionally adds a thin orchestrator instead of duplicating
workplan.py, execute.py, or the owner's privacy/cost policies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import execute  # noqa: E402
import orchestrate  # noqa: E402
import plan_contract as contract  # noqa: E402
import planner  # noqa: E402
import workplan  # noqa: E402
from plan_contract import MAX_UNITS, Blocked, high_risk, safe_path  # noqa: E402,F401

# Immutable test command catalogue. Model output cannot inject shell commands.
TESTS = {
    "python -m unittest discover -s tests": [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
    "python -m pytest -q": [sys.executable, "-m", "pytest", "-q"],
    "python scripts/verify.py --level standard": [sys.executable, "scripts/verify.py", "--level", "standard"],
    "npm test": ["npm", "test"],
    "go test ./...": ["go", "test", "./..."],
    "cargo test --quiet": ["cargo", "test", "--quiet"],
}
MAX_TRACKED_IN_PROMPT = 180
CI_FIX = "ci-fix-"


def checked_command(command: str) -> list[str]:
    if command not in TESTS:
        raise Blocked("Test is not allowlisted. Choose one of: " + "; ".join(TESTS))
    return TESTS[command]


def default_test(repo: Path) -> str:
    if (repo / "scripts" / "verify.py").is_file() and (repo / "tests").is_dir():
        return "python scripts/verify.py --level standard"
    if (repo / "pytest.ini").exists() or (repo / "pyproject.toml").exists():
        return "python -m pytest -q"
    if (repo / "tests").is_dir() and any((repo / "tests").glob("test*.py")):
        return "python -m unittest discover -s tests"
    if (repo / "package.json").is_file():
        try:
            obj = json.loads((repo / "package.json").read_text(encoding="utf-8"))
            if (obj.get("scripts") or {}).get("test"):
                return "npm test"
        except (OSError, ValueError):
            pass
    if (repo / "go.mod").is_file():
        return "go test ./..."
    if (repo / "Cargo.toml").is_file():
        return "cargo test --quiet"
    raise Blocked("Cannot discover a safe regression command; use --test with an allowlisted command")


def plan_id_of(repo: Path, base: str, instruction: str) -> str:
    return "auto-" + hashlib.sha256((str(repo.resolve()) + base + instruction).encode()).hexdigest()[:14]


def assemble(units: list[dict], instruction: str, repo: Path, test: str, base: str, policy: dict) -> dict:
    """The work plan around normalized units. Budgets and the test come from here, never from a model."""
    for unit in units:
        unit["acceptance"]["test"] = test
    plan = {"plan_id": plan_id_of(repo, base, instruction), "repo": str(repo.resolve()), "base": base,
            "goal": instruction, "defaults": {"risk": "green", "test": test},
            "budgets": {"max_attempts_per_unit": 2, "max_total_attempts": MAX_UNITS * 2,
                        "max_wall_s": 7200, "max_remote_sessions": MAX_UNITS * 2,
                        "max_split_depth": 1, "max_units_after_split": MAX_UNITS * 2,
                        "max_ci_fix_attempts": 1},
            "final_regression": [test], "units": units}
    errors = workplan.validate(plan, policy)
    if errors:
        raise Blocked("Plan does not pass the repository policy: " + "; ".join(errors))
    return plan


def to_workplan(raw: dict, instruction: str, repo: Path, test: str, base: str, policy: dict) -> dict:
    """Convert untrusted model JSON into the existing workplan contract, fail closed."""
    checked_command(test)
    units, _, issues = contract.normalize(raw, instruction, repo, policy)
    if issues:
        raise Blocked(contract.describe(issues))
    return assemble(units, instruction, repo, test, base, policy)


def select_inventory(paths: list[str], instruction: str) -> list[str]:
    """Prioritize matching paths and represent each directory in a bounded inventory."""
    words = {w for w in re.findall(r"[a-z0-9]{3,}", instruction.lower())
             if w not in {"para", "with", "from", "this", "that", "como", "hacer", "añade"}}
    def rank(path: str) -> tuple[int, str]:
        label = path.lower().replace("_", "-")
        return (-sum(3 if w in label else 0 for w in words), path)
    groups: dict[str, list[str]] = {}
    for path in paths:
        groups.setdefault(path.split("/", 1)[0] if "/" in path else "(root)", []).append(path)
    for group in groups.values():
        group.sort(key=rank)
    selected = []
    while len(selected) < MAX_TRACKED_IN_PROMPT and any(groups.values()):
        # Round-robin stops alphabetical truncation from hiding scripts/ in large repos.
        for name in sorted(groups, key=lambda n: (rank(groups[n][0])[0] if groups[n] else 0, n)):
            if groups[name] and len(selected) < MAX_TRACKED_IN_PROMPT:
                selected.append(groups[name].pop(0))
    return selected


def planner_prompt(instruction: str, tracked: list[str], policy: dict) -> str:
    return contract.prompt(instruction, tracked, policy)


def build_plan(instruction: str, repo: Path, test: str, base: str, policy: dict, ask, repair=None) -> tuple[dict, dict]:
    """Draft, fix what is safe here, repair the rest with one model call, validate. Returns (plan, record).

    `ask(messages)` and `repair(messages)` return the model's text. Every problem of the draft goes into
    one repair message. A draft with an unsafe path or an oversized scope is refused before any repair.
    """
    checked_command(test)
    # File inventory only; no source, secrets or environment are transferred.
    inventory = select_inventory([p for p in workplan.tracked_files(repo) if not p.startswith(".git/")], instruction)
    messages = [{"role": "user", "content": contract.prompt(instruction, inventory, policy)}]
    reply = ask(messages)
    raw, syntax, problem = contract.parse(reply)
    record = {"fixes": list(syntax), "repair_calls": 0, "repaired": []}
    units, issues = [], [{"unit": 0, "field": "json", "problem": problem, "fatal": False}] if problem else []
    if raw is not None:
        units, fixes, issues = contract.normalize(raw, instruction, repo, policy)
        record["fixes"] += fixes
    if issues:
        if any(i["fatal"] for i in issues):
            raise Blocked(contract.describe(issues))
        record.update(repair_calls=1, repaired=[f"unit {i['unit']} {i['field']}" for i in issues])
        again = [*messages, {"role": "assistant", "content": reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)},
                 {"role": "user", "content": contract.repair_prompt(issues)}]
        fixed, syntax, problem = contract.parse((repair or ask)(again))
        if problem:
            raise contract.Unrepaired("Planner repair failed: " + problem)
        if raw is not None:
            contract.guard(raw, fixed, issues)
        units, fixes, issues = contract.normalize(fixed, instruction, repo, policy)
        record["fixes"] += syntax + fixes
        if issues:
            raise contract.Unrepaired(contract.describe(issues))
    return assemble(units, instruction, repo, test, base, policy), record


def ollama_asker(model: str, policy: dict, request=None):
    """A callable that sends messages to the local Ollama model and returns its text."""
    url = policy["executors"]["ollama"]["url"].rstrip("/") + "/api/chat"
    if request is None:
        def request(url, payload):
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as response:
                return json.load(response)

    def ask(messages: list[dict]) -> str:
        payload = {"model": model, "stream": False, "format": "json", "think": False,
                   "options": {"num_ctx": 8192, "num_predict": 2400, "temperature": 0}, "messages": messages}
        try:
            return request(url, payload)["message"]["content"]
        except (KeyError, TypeError, ValueError, urllib.error.URLError, TimeoutError) as exc:
            raise Blocked(f"Local planner failed to return valid structured JSON: {exc}") from exc
    return ask


def local_plan(instruction: str, repo: Path, model: str, test: str, *,
               request=None, policy=None, local=None, record: dict | None = None) -> dict:
    policy = policy if policy is not None else orchestrate.policy()
    local = local if local is not None else orchestrate.local_config()
    base = orchestrate.git(repo, "rev-parse", "HEAD").strip()
    if not orchestrate.is_loopback(policy["executors"]["ollama"].get("url", "")):
        raise Blocked("Planning requires a local Ollama loopback URL")
    caps = {"ollama": orchestrate.detect_ollama(policy["executors"]["ollama"])}
    if model not in caps["ollama"].get("models", []) or model in caps["ollama"].get("remote", []):
        raise Blocked(f"Ollama model {model!r} is missing or remote")
    ok, reason = orchestrate.gate("ollama", model, repo, policy, local, mode="local-only", caps=caps)
    if not ok:
        raise Blocked("Local model rejected by privacy/cost gate: " + reason)
    plan, notes = build_plan(instruction, repo, test, base, policy, ollama_asker(model, policy, request))
    if record is not None:
        record.update(notes)
    return plan


def make_plan(instruction: str, repo: Path, test: str, *, asked: str | None = None, model: str | None = None,
              opus_reason: str | None = None, policy=None, local=None, ask_claude=None, request=None) -> dict:
    """Pick the planner, draft and validate. The plan names who drafted it, why, and what was fixed or repaired."""
    policy = policy if policy is not None else orchestrate.policy()
    local = local if local is not None else orchestrate.local_config()
    choice = planner.select(instruction, repo, policy, local, asked, workplan.tracked_files(repo), opus_reason=opus_reason,
                            cli="injected" if ask_claude else None)
    ask_claude = ask_claude or planner.ask_claude
    record: dict = {}
    calls: list[dict] = []

    def asker(who: dict):
        def ask(messages):
            try:
                reply = ask_claude(messages, who["model"], policy)
            except planner.PlannerError as error:
                raise Blocked(str(error)) from error
            calls.append({k: reply.get(k) for k in ("model", "seconds", "input_tokens", "output_tokens", "reported_cost_usd")})
            return reply["text"]
        return ask

    used = 0
    while True:
        if choice["backend"] != "claude":
            plan = local_plan(instruction, repo, model or choice["model"], test, request=request, policy=policy,
                              local=local, record=record)
            break
        base = orchestrate.git(repo, "rev-parse", "HEAD").strip()
        try:
            plan, record = build_plan(instruction, repo, test, base, policy, asker(choice),
                                      asker(planner.repairer(choice, policy)))
            break
        except contract.Unrepaired:
            # Only a draft that stayed invalid moves up. A refused scope or path is the policy's answer.
            higher = planner.escalate(choice, policy, used)
            if higher is None:
                raise
            choice, used = higher, used + 1
    plan["planner"] = {**choice, "fixes": record.get("fixes", []), "repaired": record.get("repaired", []),
                       "repair_calls": record.get("repair_calls", 0), "calls": calls, "escalations": used}
    plan["route"] = route_of(instruction, repo)
    return plan


def route_of(instruction: str, repo: Path) -> dict | None:
    """What the router says about the request, kept in the plan so a run can show why its tools were chosen."""
    try:
        import router
        found = router.decide(instruction, repo, "coordinator", save=False)
    except Exception:  # noqa: BLE001 (a plan is valid without a route)
        return None
    return {"recipe": found["recipe"], "recipe_why": found["recipe_why"], "folder": found["folder"], "profile": found["profile"],
            "verification": found["verification"], "leaves_machine": found["leaves_machine"],
            "capabilities": [{"capability": c["capability"], "provider": c["provider"]} for c in found["capabilities"]]}


def resolve_plan(path: Path, repo: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if str(repo.resolve()) != plan.get("repo"):
        raise Blocked("This plan was generated for a different repository")
    if not re.fullmatch(r"auto-[0-9a-f]{14}", str(plan.get("plan_id", ""))):
        raise Blocked("Only auto-generated plan IDs are accepted by this publishing workflow")
    if not re.fullmatch(r"[0-9a-f]{40}", str(plan.get("base", ""))):
        raise Blocked("The plan does not pin a Git base commit")
    if len(plan.get("final_regression", [])) != 1:
        raise Blocked("The plan needs one trusted final-regression command")
    test = plan["final_regression"][0]
    checked_command(test)
    errors = workplan.validate(plan)
    if errors:
        raise Blocked("Invalid workplan: " + "; ".join(errors))
    if any(unit.get("acceptance", {}).get("test") != test for unit in plan["units"]):
        raise Blocked("Unit test commands differ from the trusted final regression")
    return plan


def save_plan(plan: dict, output: Path | None = None) -> Path:
    path = output or (orchestrate.home() / "plans" / f"{plan['plan_id']}.json")
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if old != plan:
            raise Blocked("Existing plan differs; refusing to overwrite " + str(path))
        return path
    orchestrate.write_json(path, plan)
    return path


def ensure_base(plan: dict, repo: Path) -> None:
    if orchestrate.git(repo, "rev-parse", "HEAD").strip() != plan["base"]:
        raise Blocked("HEAD moved since planning. Generate a new plan; never silently reset the repository")
    if orchestrate.git(repo, "status", "--porcelain", "--untracked-files=all").strip():
        raise Blocked("Worktree is dirty. Commit or stash your changes before running this plan")


def execute_plan(path: Path, plan: dict, repo: Path, reviewer: str, parallel: int | None = None) -> None:
    ensure_base(plan, repo)
    status = execute.check(plan, repo)
    if status["errors"] or not all(r.get("ready") for r in status["routes"].values()):
        raise Blocked("Routing is not ready. Use execute.py check: " + json.dumps(status, ensure_ascii=False))
    prior = execute.load_state(plan["plan_id"])
    command = "resume" if prior.get("units") else "run"
    args = [command, str(path), "--repo", str(repo), "--reviewer", reviewer]
    result = execute.main(args + (["--parallel", str(parallel)] if parallel else []))
    if result != 0:
        raise Blocked("Executor has failed/blocked units; inspect execute.py report. PR not created")


def regression(repo: Path, command: str) -> None:
    args = checked_command(command)
    result = orchestrate.run(args, cwd=repo, timeout=1200)
    if result["exit"] != 0:
        raise Blocked("Final regression failed: " + orchestrate.tail(result["stdout"] + result["stderr"], 1500))


def integration_ready(plan: dict, repo: Path, *, auto_merge: bool) -> tuple[Path, str, str]:
    state = execute.load_state(plan["plan_id"])
    units = state.get("units") or {}
    # A unit that fixed a failed check works inside the files the plan already declared.
    extra = set(units) - {u["id"] for u in plan["units"]}
    if {u["id"] for u in plan["units"]} - set(units) or any(not name.startswith(CI_FIX) for name in extra) or any(
        entry.get("status") != execute.DONE for entry in units.values()
    ):
        raise Blocked("Not all units have passed. Cannot publish")
    if auto_merge and any(u.get("risk") != "green" for u in plan["units"]):
        raise Blocked("Yellow/red work requires owner review; automatic merge is refused")
    if auto_merge and any((entry.get("review") or {}).get("verdict") != "pass" for entry in units.values()):
        raise Blocked("All units need an explicit 'pass' independent review for automatic merge")
    integ = state.get("integration") or {}
    expected_branch = "execute/" + plan["plan_id"]
    if integ.get("branch") != expected_branch or integ.get("base") != plan["base"]:
        raise Blocked("Integration metadata disagrees with the pinned plan base/branch")
    path = Path(integ.get("worktree") or "")
    expected_path = orchestrate.home() / "worktrees" / f"execute-{plan['plan_id']}"
    if path.resolve() != expected_path.resolve():
        raise Blocked("Integration worktree path is not the expected owned worktree")
    if not path.is_dir() or not (path / ".git").exists():
        raise Blocked("Integration worktree is missing")
    if orchestrate.git(path, "branch", "--show-current") != expected_branch:
        raise Blocked("Integration branch has changed")
    if orchestrate.git(path, "status", "--porcelain", "--untracked-files=all"):
        raise Blocked("Integration tree is dirty")
    if orchestrate.git(path, "merge-base", plan["base"], "HEAD") != plan["base"]:
        raise Blocked("Integration branch is not descended from the planned base")
    head = orchestrate.git(path, "rev-parse", "HEAD")
    if head == plan["base"]:
        raise Blocked("No commits to publish")
    paths = orchestrate.git(path, "diff", "--name-only", plan["base"], "HEAD").splitlines()
    protected = orchestrate.policy().get("protected", [])
    if any(any(workplan.matches(p, pattern) for pattern in protected) for p in paths):
        raise Blocked("Integration diff touches protected files")
    declared = {p for u in plan["units"] for p in u["allowed"] + u.get("new_files", [])}
    if any(p not in declared for p in paths):
        raise Blocked("Integrated files exceed the approved file scope")
    return path, expected_branch, head


def checked_run(args: list[str], *, cwd: Path, timeout: int = 120) -> str:
    result = orchestrate.run(args, cwd=cwd, timeout=timeout)
    if result["exit"] != 0:
        raise Blocked(f"{args[0]} {args[1] if len(args)>1 else ''} failed: " +
                      orchestrate.tail(result["stderr"] + result["stdout"], 1200))
    return result["stdout"].strip()


def gh_repo(path: Path) -> tuple[str, str]:
    obj = json.loads(checked_run(["gh", "repo", "view", "--json", "nameWithOwner,defaultBranchRef"], cwd=path))
    name = obj.get("nameWithOwner")
    default = (obj.get("defaultBranchRef") or {}).get("name")
    if not name or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name) or not default:
        raise Blocked("Unable to identify GitHub repository and base branch")
    origin = checked_run(["git", "remote", "get-url", "origin"], cwd=path)
    if not (re.search(r"(?:github\.com[:/])" + re.escape(name) + r"(?:\.git)?$", origin, flags=re.I)):
        raise Blocked("Remote origin does not match the GitHub repository")
    return name, default


def required_checks(path: Path, name: str, base: str) -> None:
    """Fail closed: never request GitHub's own auto-merge without required checks it waits for.

    Classic branch protection needs strict checks. A ruleset (what settings/ruleset-main.json applies) needs a
    required_status_checks rule with at least one check, as the owner set it."""
    try:
        rules = json.loads(checked_run(["gh", "api", f"repos/{name}/rules/branches/{base}"], cwd=path) or "[]")
    except (Blocked, ValueError):
        rules = []
    required = [r for r in rules if isinstance(r, dict) and r.get("type") == "required_status_checks"]
    if any((r.get("parameters") or {}).get("required_status_checks") for r in required):
        return
    endpoint = f"repos/{name}/branches/{base}/protection"
    obj = json.loads(checked_run(["gh", "api", endpoint], cwd=path))
    status = obj.get("required_status_checks") or {}
    checks = status.get("checks") or status.get("contexts") or []
    if not checks or status.get("strict") is not True:
        raise Blocked("Auto-merge requires mandatory status checks and up-to-date branches (strict protection)")


def base_moved(worktree: Path, base_branch: str, plan: dict) -> bool:
    """True when origin's base branch no longer points at the commit the plan was made on."""
    try:
        checked_run(["git", "fetch", "--quiet", "origin", base_branch], cwd=worktree, timeout=180)
        tip = checked_run(["git", "rev-parse", f"origin/{base_branch}"], cwd=worktree)
    except Blocked:
        return False
    return bool(tip) and tip != plan["base"]


def ci_status(number: int, name: str, cwd: Path, run=None) -> dict:
    """The checks of a pull request as GitHub reports them: {state: pass|fail|pending|none, failed: [...], checks: n}."""
    result = (run or orchestrate.run)(["gh", "pr", "checks", str(number), "--repo", name, "--json", "name,bucket,link"],
                                      cwd=cwd, timeout=120)
    try:
        rows = json.loads(result.get("stdout") or "[]")
    except ValueError:
        rows = None
    if not isinstance(rows, list):
        return {"state": "unknown", "failed": [], "checks": 0, "note": orchestrate.tail(result.get("stderr") or "", 300)}
    failed = [r for r in rows if r.get("bucket") in ("fail", "cancel")]
    state = "none" if not rows else "fail" if failed else "pending" if any(r.get("bucket") == "pending" for r in rows) else "pass"
    return {"state": state, "failed": [{"name": r.get("name"), "link": r.get("link")} for r in failed], "checks": len(rows)}


def watch_ci(number: int, name: str, cwd: Path, *, timeout_s: int = 1800, poll_s: int = 30, run=None,
             sleep=time.sleep, clock=time.monotonic) -> dict:
    """Wait for the checks of a pull request to end. A check still running at the limit is reported as pending."""
    began = clock()
    while True:
        status = ci_status(number, name, cwd, run)
        # GitHub lists no check for a few seconds after a push, so "none" is final only once the limit passed.
        if status["state"] in ("pass", "fail") or clock() - began >= timeout_s:
            return {**status, "waited_s": round(clock() - began, 1)}
        sleep(poll_s)


def failed_log(status: dict, name: str, cwd: Path, run=None) -> str:
    """The end of the log of the failed jobs. It is data for the fixing unit, never instructions."""
    parts = []
    for item in status["failed"][:3]:
        found = re.search(r"/actions/runs/(\d+)", item.get("link") or "")
        if not found:
            continue
        result = (run or orchestrate.run)(["gh", "run", "view", found.group(1), "--repo", name, "--log-failed"],
                                          cwd=cwd, timeout=180)
        parts.append(f"## {item['name']}\n" + orchestrate.tail(result.get("stdout") or result.get("stderr") or "", 2500))
    return "\n\n".join(parts) or "Failed checks: " + ", ".join(str(i["name"]) for i in status["failed"])


def ci_fix_unit(plan: dict, attempt: int, log: str, policy: dict) -> dict:
    """One more unit, limited to the files the plan declared and at the highest risk the plan has."""
    files = sorted({p for u in plan["units"] for p in u["allowed"]})
    rank = max(contract.RISKS.index(u.get("risk", "green")) for u in plan["units"])
    kind = "fix-check" if "fix-check" in policy.get("tasks", {}) else plan["units"][0]["task_type"]
    return {"id": f"{CI_FIX}{attempt}", "title": f"Fix the failed checks of the pull request (attempt {attempt})",
            "task_type": kind, "goal": "The pull request of this plan failed its checks on GitHub. Read the log in the "
            "reference material and fix the cause in the files you may change. Do not change the checks.",
            "allowed": files, "new_files": [], "depends_on": [u["id"] for u in plan["units"]],
            "acceptance": {"test": plan["final_regression"][0], "criteria": ["The failed checks pass"]},
            "risk": contract.RISKS[rank], "context": log}


def record_publication(plan: dict, **fields) -> None:
    state = execute.load_state(plan["plan_id"])
    state["publication"] = {**(state.get("publication") or {}), **fields, "at": orchestrate.now()}
    orchestrate.write_json(execute.state_file(plan["plan_id"]), state)


def publish(plan: dict, repo: Path, *, auto_merge: bool = False, watch: bool = False, reviewer: str | None = None,
            fixer=None, policy: dict | None = None) -> dict:
    """Push the integration branch, open one pull request and, with `watch`, follow its checks to the end.

    A failed check gets up to budgets.max_ci_fix_attempts fixing units, pushed to the same pull request.
    Auto-merge without `watch` is GitHub's own: it merges when the required checks pass. With `watch` the merge happens
    here, once every check on the head passed, through merge_when_green, which keeps workflow, deploy and secret changes
    for the owner. Neither ever uses --admin.
    """
    ensure_base(plan, repo)
    worktree, branch, head = integration_ready(plan, repo, auto_merge=auto_merge)
    if orchestrate.git(repo, "branch", "--show-current") != "main":
        raise Blocked("Publish only from a clean main checkout, to avoid including unrelated feature commits")
    name, base = gh_repo(worktree)
    # Only the default branch is eligible: no auto-merging into a random target.
    if base != "main":
        raise Blocked("Default branch is not main; adapt this restriction explicitly before publishing")
    behind = base_moved(worktree, base, plan)
    regression(worktree, plan["final_regression"][0])
    checked_run(["git", "push", "--set-upstream", "origin", branch], cwd=worktree, timeout=180)
    opened = json.loads(checked_run(["gh", "pr", "list", "--repo", name,
                                    "--head", branch, "--state", "open",
                                    "--json", "number,url,headRefOid"], cwd=worktree))
    if len(opened) > 1:
        raise Blocked("More than one open PR for this branch")
    if opened:
        pr = opened[0]
    else:
        checked_run(["gh", "pr", "create", "--repo", name, "--base", base, "--head", branch,
                     "--title", "feat: " + plan["goal"].splitlines()[0][:65], "--body", pr_body(plan)], cwd=worktree)
        opened = json.loads(checked_run(["gh", "pr", "list", "--repo", name, "--head", branch,
                                        "--state", "open", "--json", "number,url,headRefOid"], cwd=worktree))
        if len(opened) != 1:
            raise Blocked("PR was submitted but cannot be uniquely confirmed; inspect GitHub")
        pr = opened[0]
    if pr.get("headRefOid") != head:
        raise Blocked("PR head differs from the tested commit; refusing auto-merge")
    out = {"pr": pr["url"], "head": head, "auto_merge_requested": False, "base_moved": behind,
           "note": "auto-merge is a GitHub request, not a guarantee: required checks/reviews must pass"}
    record_publication(plan, pr=pr["url"], head=head, base_moved=behind)
    if auto_merge and behind:
        raise Blocked(f"PR created at {pr['url']}, but auto-merge is blocked: origin/{base} moved since the plan was made. "
                      "Make a new plan on the new base")
    if auto_merge and not watch:
        try:
            required_checks(worktree, name, base)
        except Blocked as error:
            raise Blocked(f"PR created at {pr['url']}, but auto-merge is blocked: {error}") from error
        # Never use --admin, --force, delete-branch, or merge outside GitHub's required checks.
        checked_run(["gh", "pr", "merge", str(pr["number"]), "--repo", name,
                     "--auto", "--squash", "--match-head-commit", head], cwd=worktree)
        out["auto_merge_requested"] = True
        record_publication(plan, auto_merge_requested=True)
    if watch:
        out["ci"] = follow_ci(plan, repo, worktree, branch, name, pr, reviewer=reviewer, fixer=fixer, policy=policy)
        if auto_merge:
            if out["ci"].get("state") != "pass":
                raise Blocked(f"The checks on {pr['url']} ended {out['ci'].get('state')}, not pass, so it was not merged")
            # Every check on the head passed, so merge that head now, through the same gate a session uses.
            import merge_when_green
            try:
                merged = merge_when_green.merge(str(pr["number"]), name, wait=0, setting="when-green", run=gh_runner(worktree))
            except merge_when_green.Refused as error:
                raise Blocked(f"Checks passed on {pr['url']}, but it was not merged: {error}") from error
            out.update(merged=merged["merged"], auto_merge_requested=True)
            record_publication(plan, merged=merged["merged"], auto_merge_requested=True)
    return out


def gh_runner(cwd: Path):
    """gh with the cwd of the integration worktree, for merge_when_green."""
    return lambda args: checked_run(["gh", *args], cwd=cwd, timeout=180)


def pr_body(plan: dict) -> str:
    """The sections of the standard's pull request contract (PR_SECTIONS in standard.py), filled from the saved state only."""
    report = execute.report(plan, execute.load_state(plan["plan_id"]))
    metrics = report.get("metrics") or {}
    rows = "\n".join(f"- `{u['id']}` {u['status']}, model `{u['model']}`, review {u['review']}, tests {u['tests']}"
                     for u in report["units"])
    risks = ", ".join(sorted({u.get("risk", "green") for u in plan["units"]}))
    return ("## Task\n\nNone. Automated execution of a validated standards work plan.\n\n"
            f"## What I understood\n\n{plan['goal'].splitlines()[0][:300]}\n\n"
            f"Plan `{plan['plan_id']}` on base `{plan['base'][:12]}`, drafted by "
            f"`{(plan.get('planner') or {}).get('model', 'unknown')}`.\n\n"
            "## Assumptions\n\nNone beyond the plan. Each unit changed only the files the plan declared.\n\n"
            f"## Decisions\n\n{rows}\n\nRisk of the units: {risks}. Yellow and red units need the owner before a merge.\n\n"
            "## Not done\n\nNone. Every unit of the plan passed.\n\n"
            f"## How to verify\n\nRun `{plan['final_regression'][0]}`. It passed on the integration branch, and every unit "
            "passed its tests and a review by a model other than its author.\n"
            f"Total {metrics.get('total_s')} s, peak of {metrics.get('peak_parallel')} units at once, "
            f"{metrics.get('collisions')} integration conflicts, {metrics.get('retries')} retries.\n"
            + readiness_section(plan))


def readiness_section(plan: dict) -> str:
    """When the plan implements a spec, the computed verdict goes in the pull request. CI is not known yet here."""
    if not plan.get("spec"):
        return ""
    import readiness
    return "\n## Readiness\n\n" + readiness.markdown(readiness.assess(Path(plan["repo"]), plan["spec"], "unknown")) + "\n"


def follow_ci(plan: dict, repo: Path, worktree: Path, branch: str, name: str, pr: dict, *, reviewer: str | None = None,
              fixer=None, policy: dict | None = None, **watch_options) -> dict:
    """Watch the checks. On a failure run a fixing unit, push it to the same pull request and watch again."""
    policy = policy if policy is not None else orchestrate.policy()
    budget = (plan.get("budgets") or {}).get("max_ci_fix_attempts", 1)
    attempt = 0
    while True:
        status = watch_ci(pr["number"], name, worktree, **watch_options)
        record_publication(plan, ci=status, ci_fix_attempts=attempt)
        if status["state"] != "fail":
            return {**status, "fix_attempts": attempt}
        if attempt >= budget:
            raise Blocked(f"Checks failed on {pr['url']} and the fix budget ({budget}) is used: "
                          + ", ".join(str(i["name"]) for i in status["failed"]) + ". The PR stays open and is not merged")
        attempt += 1
        unit = ci_fix_unit(plan, attempt, failed_log(status, name, worktree, watch_options.get("run")), policy)
        fixed = (fixer or run_fix)(plan, unit, repo, reviewer)
        if not fixed:
            raise Blocked(f"Checks failed on {pr['url']} and the fixing unit did not pass. The PR stays open and is not merged")
        regression(worktree, plan["final_regression"][0])
        checked_run(["git", "push", "origin", branch], cwd=worktree, timeout=180)


def run_fix(plan: dict, unit: dict, repo: Path, reviewer: str | None) -> bool:
    """Run one fixing unit through the executor loop: its own worktree, the tests and a cross-model review."""
    import review as review_mod
    work = {**plan, "units": [*plan["units"], unit]}
    judge = review_mod.ollama_reviewer(repo, reviewer) if reviewer else None
    state = execute.Executor(work, repo, reviewer, judge, parallel=1).run()
    return state["units"].get(unit["id"], {}).get("status") == execute.DONE


def detach(args: list[str], repo: Path, plan_id: str) -> dict:
    """Start this script as its own process, so the run goes on after the caller (a Claude session, a terminal) ends."""
    log = orchestrate.home() / "autopilot" / f"{plan_id}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    import supervisor
    running = supervisor.read_pid(log.parent / f"{plan_id}.pid")
    if supervisor.alive(running):
        # A second session with the same request finds the same plan: it joins the run instead of starting another.
        return {"detached": False, "already_running": running, "log": str(log), "plan_id": plan_id}
    flags = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)}
             if os.name == "nt" else {"start_new_session": True})
    with log.open("ab") as out:
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *args], cwd=str(repo),
                                stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, **flags)
    (log.parent / f"{plan_id}.pid").write_text(str(proc.pid), encoding="utf-8")
    return {"detached": True, "pid": proc.pid, "log": str(log), "plan_id": plan_id}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    plan_cmd = commands.add_parser("plan", help="Create and validate a plan; no code changes")
    go_cmd = commands.add_parser("go", help="Plan, run with the executor loop, optionally publish")
    run_cmd = commands.add_parser("run", help="Run or resume a saved plan, optionally publish")
    publish_cmd = commands.add_parser("publish", help="Publish a completed execution as a PR")
    for p in (plan_cmd, go_cmd):
        p.add_argument("--instruction", required=True)
        p.add_argument("--planner", choices=planner.CHOICES, help="default: planning.default in the policy")
        p.add_argument("--opus-reason", help="why Opus is needed when the request scores below advanced")
        p.add_argument("--model", help="local Ollama model when the local planner drafts the plan")
        p.add_argument("--test", choices=tuple(TESTS))
        p.add_argument("--output", type=Path)
    for p in (go_cmd, run_cmd, publish_cmd):
        p.add_argument("--reviewer", default="qwen2.5:7b")
        p.add_argument("--publish", choices=("none", "pr", "auto-merge"), default="none")
        p.add_argument("--no-watch-ci", action="store_true", help="do not wait for the checks of the pull request")
    for p in (go_cmd, run_cmd):
        p.add_argument("--parallel", type=int, help="units at once. Default: concurrency.max_parallel")
        p.add_argument("--detach", action="store_true", help="run in its own process and return at once")
    for p in (run_cmd, publish_cmd):
        p.add_argument("plan", type=Path)
    for p in (plan_cmd, go_cmd, run_cmd, publish_cmd):
        p.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        repo = orchestrate.repo_root(args.repo).resolve()
        if args.command in ("plan", "go"):
            if not args.instruction.strip() or len(args.instruction) > 6000:
                raise Blocked("Provide an instruction between 1 and 6000 characters")
            if orchestrate.git(repo, "status", "--porcelain", "--untracked-files=all"):
                raise Blocked("Repository has changes; commit/stash them before automatic planning")
            test = args.test or default_test(repo)
            instruction = args.instruction.strip()
            saved = args.output or (orchestrate.home() / "plans" /
                                    f"{plan_id_of(repo, orchestrate.git(repo, 'rev-parse', 'HEAD').strip(), instruction)}.json")
            reused = saved.exists()
            if reused:
                # Same request on the same commit: the saved plan is the answer and no planner is asked again.
                plan, path = resolve_plan(saved, repo), saved
            else:
                plan = make_plan(instruction, repo, test, asked=args.planner, model=args.model, opus_reason=args.opus_reason)
                path = save_plan(plan, args.output)
            print(json.dumps({"plan": str(path), "units": len(plan["units"]), "reused": reused,
                              "risk": [u["risk"] for u in plan["units"]],
                              "depends_on": {u["id"]: u["depends_on"] for u in plan["units"]},
                              "planner": {k: (plan.get("planner") or {}).get(k) for k in ("backend", "model", "tier", "reasons")}},
                             ensure_ascii=False))
            if args.command == "plan":
                return 0
        else:
            path = args.plan
            plan = resolve_plan(path, repo)
            # 'publish' is an explicit operation; --publish none means create only.
            if args.command == "publish" and args.publish == "none":
                args.publish = "pr"
        if args.command in ("go", "run"):
            if args.detach:
                again = ["run", str(path), "--repo", str(repo), "--reviewer", args.reviewer, "--publish", args.publish]
                again += (["--parallel", str(args.parallel)] if args.parallel else []) + (["--no-watch-ci"] if args.no_watch_ci else [])
                print(json.dumps(detach(again, repo, plan["plan_id"]), ensure_ascii=False))
                return 0
            execute_plan(path, plan, repo, args.reviewer, args.parallel)
        if args.publish != "none":
            import merge_when_green
            # With the owner's setting when-green, a published pull request is merged once its checks pass.
            auto = args.publish == "auto-merge" or (args.publish == "pr" and merge_when_green.owner_setting() == "when-green")
            print(json.dumps(publish(plan, repo, auto_merge=auto, watch=not args.no_watch_ci,
                                     reviewer=args.reviewer), ensure_ascii=False))
        return 0
    except (Blocked, ValueError, OSError) as error:
        print("BLOCKED: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
