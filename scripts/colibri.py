#!/usr/bin/env python3
"""Manage the local Colibri server: status, ensure, start, stop, models and a measured test request.

Colibri is a local inference engine with an OpenAI-compatible API. It runs from a clone under
~/.standards/tools/colibri (executors.colibri.home in settings/orchestration.yml). Nothing here
installs or downloads: that is `coli setup`, run by scripts/standards.ps1.
A stopped server is reported, never replaced by another model.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orchestrate  # noqa: E402


def settings() -> dict:
    conf = orchestrate.policy()["executors"]["colibri"]
    return {**conf, "home": Path(str(conf["home"]).replace("~", str(Path.home()), 1))}


def coli(*args: str, timeout: int = 60) -> dict:
    script = settings()["home"] / "c" / "coli"
    return orchestrate.run([sys.executable, str(script), *args], timeout=timeout)


def server_status() -> dict:
    """The `coli status --json` fields, or an error. The server block says state, urls and the model id."""
    result = coli("status", "--json", timeout=30)
    try:
        return json.loads(result["stdout"])
    except ValueError:
        return {"error": (result["stderr"] or result["stdout"])[-300:] or "coli status gave no JSON"}


def probe(conf: dict | None = None) -> dict:
    """What the API itself answers. It is the proof that the server is up, whatever the launcher says."""
    return orchestrate.detect_colibri(conf or settings())


def stop() -> dict:
    return coli("stop", timeout=60)


def start() -> dict:
    return coli("start", "--background", "--no-browser", timeout=60)


def ensure(timeout_s: int | None = None, restarts: int = 1) -> dict:
    """Make the server answer. It starts a stopped server and restarts a broken one at most `restarts` times."""
    conf = settings()
    limit = timeout_s or conf.get("ready_timeout_s", 300)
    for attempt in range(restarts + 1):
        info = probe(conf)
        if info["up"] and info["models"]:
            return {"ok": True, "attempts": attempt, **info}
        if attempt:
            stop()
        started = start()
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            info = probe(conf)
            if info["up"] and info["models"]:
                return {"ok": True, "attempts": attempt + 1, **info}
            state = (server_status().get("server") or {}).get("state")
            if state in {"error", "stopped"}:
                break
            time.sleep(5)
    log = coli("logs", "-n", "20", timeout=30)
    return {"ok": False, "error": "Colibri did not answer", "start_exit": started["exit"],
            "log_tail": (log["stdout"] or log["stderr"])[-1500:], **info}


def chat(prompt: str, max_tokens: int = 64) -> dict:
    """One real request. Tokens and latency come from the server's own usage block and are appended to telemetry."""
    conf = settings()
    info = probe(conf)
    if not info["up"]:
        return {"ok": False, "error": "Colibri is not running"}
    model = info["models"][0]
    began = time.monotonic()
    try:
        reply = orchestrate.http_json(f"{conf['url'].rstrip('/')}/v1/chat/completions",
                                      {"model": model, "messages": [{"role": "user", "content": prompt}],
                                       "max_tokens": max_tokens}, timeout=conf.get("chat_timeout_s", 600))
    except (OSError, ValueError, urllib.error.URLError) as error:
        return {"ok": False, "model": model, "error": str(error)[:300]}
    seconds = round(time.monotonic() - began, 2)
    usage = reply.get("usage") or {}
    out = usage.get("completion_tokens")
    row = {"date": orchestrate.now(), "provider": "colibri", "model": model, "seconds": seconds,
           "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": out,
           "tokens_per_second": round(out / seconds, 2) if out and seconds else None}
    orchestrate.append_telemetry(row)
    text = ((reply.get("choices") or [{}])[0].get("message") or {}).get("content")
    return {"ok": bool(text), "reply": (text or "")[:300], **row}


# The MCP server of Colibri can install a model of tens of gigabytes and stop the server a task is using.
# An agent may read the state, never change it. The orchestrator starts and stops Colibri itself.
DENIED_MCP_TOOLS = ("colibri_install", "colibri_start", "colibri_stop")


def apply_mcp(data: dict, conf: dict) -> dict:
    """Add Colibri's own MCP server to an OpenCode config and deny its tools that change the machine. Other keys stay."""
    coli = Path(str(conf["home"])) / "c" / "coli"
    data.setdefault("mcp", {})["colibri"] = {"type": "local", "command": [sys.executable, str(coli), "mcp"],
                                             "enabled": True, "timeout": 20000}
    tools = data.setdefault("tools", {})
    for name in DENIED_MCP_TOOLS:
        tools[name] = False
    return data


def register(target: Path | None = None) -> dict:
    """Add Colibri as an OpenCode provider and MCP server in the global config, after a backup. Other keys stay as they are."""
    conf = settings()
    info = probe(conf)
    if not info["up"] or not info["models"]:
        return {"ok": False, "error": "Colibri is not running, so its model id is unknown (python scripts/colibri.py ensure)"}
    path = (target or Path.home() / ".config" / "opencode") / "opencode.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"$schema": "https://opencode.ai/config.json"}
    if path.exists():
        backup = path.with_name(f"opencode.json.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    block = {"npm": "@ai-sdk/openai-compatible", "name": "Colibri (local)",
             "options": {"baseURL": f"{conf['url'].rstrip('/')}/v1"},
             "models": {name: {"name": f"{name} (Colibri)"} for name in info["models"]}}
    data.setdefault("provider", {})["colibri"] = block
    apply_mcp(data, conf)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "config": str(path), "models": info["models"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "start", "stop", "models", "register"):
        sub.add_parser(name)
    p = sub.add_parser("ensure")
    p.add_argument("--timeout", type=int)
    p = sub.add_parser("chat")
    p.add_argument("--prompt", default="Reply with the single word: ready")
    args = parser.parse_args(argv)
    if args.command == "status":
        result = {"api": probe(), "launcher": server_status()}
    elif args.command == "models":
        result = probe()
    elif args.command == "ensure":
        result = ensure(args.timeout)
    elif args.command == "register":
        result = register()
    elif args.command == "chat":
        result = chat(args.prompt)
    else:
        result = (start if args.command == "start" else stop)()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok", result.get("up", result.get("exit", 0) == 0)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
