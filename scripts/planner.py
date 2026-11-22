#!/usr/bin/env python3
"""Planning agent: picks the smallest planner that is enough for a request and asks it for one draft.

A program scores the request, no model does. The score picks a tier of `planning.tiers` in
settings/orchestration.yml: light (Claude Haiku), medium (Claude Sonnet) or advanced (Claude Opus).
Claude is reached with `claude -p`, one call that ends when the draft is back, so no Claude session
stays open while the plan runs. When the cost mode or the privacy class of the folder does not allow the
Claude subscription, or the Claude Code CLI is missing, the local Ollama planner drafts the plan.

The Claude Code subscription is not an API key. This module removes ANTHROPIC_API_KEY from the call, so a
key in the environment is never billed by a plan.

Usage: python scripts/planner.py select --instruction TEXT [--planner auto|local|haiku|sonnet|opus] [--repo DIR]
       python scripts/planner.py doctor
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import orchestrate  # noqa: E402
import plan_contract as contract  # noqa: E402
import usage  # noqa: E402

TIERS = ("light", "medium", "advanced")
CHOICES = ("auto", "local", "haiku", "sonnet", "opus")
DEFAULTS = {
    "default": "auto", "local_model": "qwen3.5:9b", "repair_tier": "light", "max_escalations": 1,
    "opus_on_block": False, "opus_max_concurrent": 1,
    "tiers": {"light": {"model": "haiku", "timeout_s": 180}, "medium": {"model": "sonnet", "timeout_s": 300},
              "advanced": {"model": "opus", "timeout_s": 600}},
    "complexity": {"medium_at": 3, "advanced_at": 6},
    "command": ["claude", "-p", "--model", "{model}", "--output-format", "json"],
}
# Flags added to the command only when `claude --help` of the installed version lists them.
OPTIONAL_FLAGS = [("--max-turns", ["--max-turns", "1"]), ("--no-session-persistence", ["--no-session-persistence"]),
                  ("--tools", ["--tools", ""])]
DESIGN_TERMS = re.compile(
    r"\b(architect|arquitect|redesign|rediseñ|migrat|migra|rewrite|reescrib|orchestrat|orquest|protocol|protocolo|"
    r"multi-?agent|multiagente|concurren|schema|esquema|pipeline|framework|end.to.end|extremo a extremo)", re.IGNORECASE)
SYSTEM = ("Answer with one JSON object and nothing else. Do not use tools, do not read files and do not ask "
          "questions. Everything you need is in the message.")


class PlannerError(RuntimeError):
    """The planner could not be reached or did not answer."""


def settings(conf: dict) -> dict:
    mine = conf.get("planning") or {}
    return {**DEFAULTS, **mine, "tiers": {**DEFAULTS["tiers"], **(mine.get("tiers") or {})},
            "complexity": {**DEFAULTS["complexity"], **(mine.get("complexity") or {})}}


def complexity(instruction: str, paths: list[str], conf: dict) -> tuple[str, int, list[str]]:
    """(tier, score, reasons). Counted by a program: length, folders named, design words, risk words, listed items.

    A folder counts when the request names one of its files by path or by file name, or names the folder itself.
    Words inside a file path never count as design words.
    """
    text = instruction.lower()
    words = re.findall(r"\w+", text)
    prose = re.sub(r"\S*[/\\]\S*|\S+\.\w{1,5}\b", " ", instruction)
    score, reasons = 0, []
    if len(words) > 200:
        score, reasons = score + 2, [f"{len(words)} words"]
    elif len(words) > 60:
        score, reasons = score + 1, [f"{len(words)} words"]
    tops = {p.split("/", 1)[0] for p in paths if "/" in p}
    names = [p.rsplit("/", 1)[-1].lower() for p in paths]
    # A bare file name points at a folder only when one tracked file has that name.
    named = {p for p in paths if "/" in p and (p.lower() in text or (names.count(p.rsplit("/", 1)[1].lower()) == 1 and re.search(
        r"(?<![\w./-])" + re.escape(p.rsplit("/", 1)[1].lower()) + r"(?![\w-])", text)))}
    folders = {p.split("/", 1)[0] for p in named} | {t for t in tops if len(t) >= 4 and re.search(rf"\b{re.escape(t.lower())}\b", text)}
    if len(folders) >= 3:
        score += 2 if len(folders) >= 6 else 1
        reasons.append(f"names files in {len(folders)} folders")
    design = sorted({m.lower() for m in DESIGN_TERMS.findall(prose)})
    if design:
        score += min(3, len(design) + 1)
        reasons.append("design words: " + ", ".join(design[:4]))
    if contract.RISK_TERMS.search(instruction):
        score += 1
        reasons.append("names a risky area")
    items = len(re.findall(r"(?m)^\s*(?:[-*]|\d+[.)])\s+\S", instruction))
    if items >= 5:
        score += 1
        reasons.append(f"lists {items} items")
    limits = settings(conf)["complexity"]
    tier = "advanced" if score >= limits["advanced_at"] else "medium" if score >= limits["medium_at"] else "light"
    return tier, score, reasons or ["short request about few files"]


def select(instruction: str, repo: Path, conf: dict, local: dict, asked: str | None = None, paths: list[str] | None = None,
           mode: str | None = None, opus_reason: str | None = None, cli=None) -> dict:
    """Who drafts the plan: {backend, model, tier, score, reasons}. Cost and privacy go through orchestrate.gate()."""
    conf_plan = settings(conf)
    asked = asked or conf_plan["default"]
    if asked not in CHOICES:
        raise ValueError(f"unknown planner {asked!r}. Use one of: {', '.join(CHOICES)}")
    tier, score, reasons = complexity(instruction, paths or [], conf)
    choice = {"backend": "ollama", "model": conf_plan["local_model"], "tier": tier, "score": score, "asked": asked,
              "reasons": [f"complexity {tier} (score {score}): " + ", ".join(reasons)]}
    if asked == "local":
        choice["reasons"].append("the owner asked for the local planner")
        return choice
    ok, why = orchestrate.gate("claude", None, repo, conf, local, mode)
    if not ok:
        choice["reasons"].append(f"Claude is not used: {why}. The local planner drafts the plan")
        return choice
    cli = shutil.which("claude") if cli is None else cli
    if not cli:
        choice["reasons"].append("the Claude Code CLI is not installed. The local planner drafts the plan")
        return choice
    by_model = {spec["model"]: name for name, spec in conf_plan["tiers"].items()}
    if asked != "auto":
        wanted = by_model.get(asked, tier)
        if TIERS.index(wanted) > TIERS.index(tier) and wanted == "advanced" and not opus_reason:
            choice["reasons"].append(f"Opus was asked but the request scores {tier}. Opus is kept for advanced "
                                     "planning, so the tier of the score is used. Pass a reason to insist")
        else:
            if wanted != tier:
                choice["reasons"].append(f"the owner asked for {asked}" + (f": {opus_reason}" if opus_reason else ""))
            tier = wanted
    choice.update(backend="claude", model=conf_plan["tiers"][tier]["model"], tier=tier)
    choice["reasons"].append(why)
    return choice


def escalate(choice: dict, conf: dict, used: int) -> dict | None:
    """The next tier after a draft that stayed invalid, or None. Opus is reached this way only when the policy says so."""
    conf_plan = settings(conf)
    if choice["backend"] != "claude" or used >= conf_plan["max_escalations"] or choice["tier"] == "advanced":
        return None
    tier = TIERS[TIERS.index(choice["tier"]) + 1]
    if tier == "advanced" and not conf_plan["opus_on_block"]:
        return None
    return {**choice, "tier": tier, "model": conf_plan["tiers"][tier]["model"],
            "reasons": [*choice["reasons"], f"the {choice['tier']} draft stayed invalid after one repair, so {tier} drafts it"]}


def repairer(choice: dict, conf: dict) -> dict:
    """Who repairs a draft. Never above the repair tier: a structure error is not worth an Opus call."""
    conf_plan = settings(conf)
    if choice["backend"] != "claude":
        return choice
    tier = conf_plan["repair_tier"] if conf_plan["repair_tier"] in TIERS[:2] else "light"
    return {**choice, "tier": tier, "model": conf_plan["tiers"][tier]["model"]}


def claude_env() -> dict:
    """The subscription login only. A paid API key in the environment is never passed on."""
    env = orchestrate.child_env()
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENCODE_API_KEY", "OPENROUTER_API_KEY"):
        env.pop(name, None)
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    return env


def cli_flags(run=None) -> list[str]:
    """Flags the installed Claude Code lists in its help. An older version simply gets a shorter command."""
    result = (run or orchestrate.run)(["claude", "--help"], timeout=30)
    text = (result.get("stdout") or "") + (result.get("stderr") or "")
    return [name for name, _ in OPTIONAL_FLAGS if re.search(r"(?m)^\s+(?:-\w, )?" + re.escape(name) + r"\b", text)]


def opus_slot(conf: dict):
    """A lock file so one Opus planning call runs at a time. Returns the path to remove, or raises."""
    conf_plan = settings(conf)
    path = orchestrate.home() / "planner-opus.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    limit = conf_plan["tiers"]["advanced"]["timeout_s"] * 2
    if path.exists() and time.time() - path.stat().st_mtime > limit:
        path.unlink(missing_ok=True)
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise PlannerError("another Opus planning call is running and the policy allows one at a time") from None
    os.write(handle, str(os.getpid()).encode())
    os.close(handle)
    return path


def ask_claude(messages: list[dict], model: str, conf: dict, run=None, flags: list[str] | None = None) -> dict:
    """One `claude -p` call. Returns {text, seconds, input_tokens, output_tokens, reported_cost_usd, model}."""
    conf_plan = settings(conf)
    spec = next((s for s in conf_plan["tiers"].values() if s["model"] == model), {"timeout_s": 300})
    flags = cli_flags(run) if flags is None else flags
    command = orchestrate.fill(conf_plan["command"], model=model)
    for name, extra in OPTIONAL_FLAGS:
        if name in flags and name not in command:
            command += extra
    command += ["--append-system-prompt", SYSTEM]
    text = "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages) if len(messages) > 1 else messages[0]["content"]
    folder = orchestrate.home() / "planner"
    folder.mkdir(parents=True, exist_ok=True)
    lock = opus_slot(conf) if model == conf_plan["tiers"]["advanced"]["model"] else None
    try:
        # An empty folder: the planner reads the request, never a repository or its CLAUDE.md.
        result = (run or orchestrate.run)(command, cwd=folder, timeout=spec.get("timeout_s", 300), env=claude_env(), stdin=text)
    finally:
        if lock:
            lock.unlink(missing_ok=True)
    if result.get("timeout"):
        raise PlannerError(f"claude -p --model {model} gave no answer in {spec.get('timeout_s', 300)}s")
    if result.get("exit") != 0:
        raise PlannerError(f"claude -p --model {model} failed: " + orchestrate.tail(result.get("stderr") or result.get("stdout") or "", 300))
    out = {"text": result["stdout"], "seconds": result.get("seconds"), "input_tokens": None, "output_tokens": None,
           "reported_cost_usd": None, "model": model, "usage": usage.empty()}
    try:
        reply = json.loads(result["stdout"])
    except ValueError:
        reply = None
    if isinstance(reply, dict) and "result" in reply:
        if reply.get("is_error"):
            raise PlannerError(f"claude -p --model {model} reported an error: " + str(reply.get("result"))[:300])
        counted = usage.from_claude(reply)
        # input_tokens stays the whole prompt the model read. `usage` keeps the cached parts apart.
        out.update(text=str(reply["result"]), input_tokens=usage.prompt_tokens(counted), output_tokens=counted["output_tokens"],
                   reported_cost_usd=reply.get("total_cost_usd"), usage=counted)
    # reported_cost_usd is what the CLI prints as the API price of the call. On a subscription nothing is charged for it.
    with usage.scope(kind=usage.current().get("kind") or "plan"):
        usage.record("claude", model, out["usage"], "claude-json", out["seconds"], reported_cost_usd=out["reported_cost_usd"])
    return out


def doctor() -> dict:
    path = shutil.which("claude")
    if not path:
        return {"claude": None, "note": "the Claude Code CLI is not installed. The local planner is used"}
    version = orchestrate.version_of(["claude", "--version"])
    return {"claude": path, "version": version, "optional_flags": cli_flags(),
            "api_key_in_environment": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "note": "an API key in the environment is removed from every planning call"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    pick = sub.add_parser("select")
    pick.add_argument("--instruction", required=True)
    pick.add_argument("--planner", choices=CHOICES)
    pick.add_argument("--opus-reason")
    pick.add_argument("--repo", default=".")
    sub.add_parser("doctor")
    args = parser.parse_args(argv)
    if args.command == "doctor":
        print(json.dumps(doctor(), indent=2))
        return 0
    import workplan
    repo = orchestrate.repo_root(Path(args.repo))
    print(json.dumps(select(args.instruction, repo, orchestrate.policy(), orchestrate.local_config(), args.planner,
                            workplan.tracked_files(repo), opus_reason=args.opus_reason), indent=2))
    return 0


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
