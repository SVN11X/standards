#!/usr/bin/env python3
"""Install, diagnose, repair, update and verify the local AI ecosystem of the standard.

Modes: doctor (reads only), status (one line per component), install (adds what is missing),
repair (install, then restart what does not answer), update (pulls the Colibri tag), verify (real requests).
Every step is idempotent. Nothing here deletes a model or overwrites a config without a backup.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import colibri  # noqa: E402
import orchestrate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / "settings" / "ecosystem.yml"


def spec() -> dict:
    return orchestrate.load_yaml(SETTINGS)


def expand(path: str) -> Path:
    return Path(path.replace("~", str(Path.home()), 1))


def component(name: str, ok: bool, detail: str, fix: str | None = None) -> dict:
    return {"name": name, "ok": ok, "detail": detail, "fix": None if ok else fix}


def check_tools(conf: dict) -> list[dict]:
    rows = []
    for tool in conf["tools"]["required"]:
        found = shutil.which(tool)
        version = orchestrate.version_of([tool, "--version"]) if found else None
        rows.append(component(tool, bool(found), version or "not found", f"install {tool}"))
    return rows


def check_ollama(conf: dict) -> list[dict]:
    info = orchestrate.detect_ollama({"url": "http://127.0.0.1:11434"})
    if not info["up"]:
        return [component("ollama-server", False, info.get("error", "not answering"), "start Ollama")]
    rows = [component("ollama-server", True, f"version {info.get('version')}, {len(info['models'])} models")]
    for name in conf["ollama"]["keep"] + conf["ollama"]["install"]:
        have = name in info["models"]
        rows.append(component(f"ollama:{name}", have, f"{(info['sizes'].get(name) or 0) / 1e9:.1f} GB" if have else "missing",
                              f"ollama pull {name}"))
    return rows


def check_colibri(conf: dict) -> list[dict]:
    wanted = conf["colibri"]
    home = colibri.settings()["home"]
    engine = home / "c" / "qwen36.exe"
    model_dir = expand(wanted["models_dir"]) / wanted["model"]
    marker = model_dir / ".colibri-download.json"
    api = colibri.probe()
    return [
        component("colibri-clone", (home / "c" / "coli").exists(), str(home), "git clone the tag from settings/ecosystem.yml"),
        component("colibri-engine", engine.exists() or (home / "c" / "qwen36").exists(), f"{wanted['backend']} build", "coli setup"),
        component("colibri-model", marker.exists() and not list(model_dir.glob("*.part")), str(model_dir), "coli setup resumes the download"),
        component("colibri-api", api["up"] and bool(api["models"]), ", ".join(api["models"]) or api.get("error", "down"),
                  "python scripts/colibri.py ensure"),
    ]


def check_opencode_link() -> list[dict]:
    path = Path.home() / ".config" / "opencode" / "opencode.json"
    try:
        providers = json.loads(path.read_text(encoding="utf-8")).get("provider", {})
    except (OSError, ValueError):
        providers = {}
    return [component("opencode-ollama", "ollama" in providers, "provider in opencode.json", "scripts/setup-opencode.ps1"),
            component("opencode-colibri", "colibri" in providers, "provider in opencode.json", "python scripts/colibri.py register")]


def diagnose() -> list[dict]:
    conf = spec()
    return check_tools(conf) + check_ollama(conf) + check_colibri(conf) + check_opencode_link()


def install() -> list[dict]:
    """Adds what is missing. Downloads only models listed in settings/ecosystem.yml, and only when absent."""
    conf, steps = spec(), []
    have = orchestrate.detect_ollama({"url": "http://127.0.0.1:11434"}).get("models", [])
    for name in conf["ollama"]["install"]:
        if name not in have:
            result = orchestrate.run(["ollama", "pull", name], timeout=7200)
            steps.append({"step": f"ollama pull {name}", "ok": result["exit"] == 0})
    home = colibri.settings()["home"]
    if not (home / "c" / "coli").exists():
        home.parent.mkdir(parents=True, exist_ok=True)
        result = orchestrate.run(["git", "clone", "--depth", "1", "--branch", conf["colibri"]["tag"], conf["colibri"]["repo"], str(home)],
                                 timeout=600)
        steps.append({"step": "clone colibri", "ok": result["exit"] == 0})
    wanted = conf["colibri"]
    if (home / "c" / "coli").exists():
        result = colibri.coli("setup", "--yes", "--model", wanted["model"], "--backend", wanted["backend"], "--dir",
                              str(expand(wanted["models_dir"])), "--no-start", "--no-browser", timeout=86400)
        steps.append({"step": "coli setup", "ok": result["exit"] == 0, "tail": (result["stdout"] or result["stderr"])[-300:]})
    started = colibri.ensure()
    steps.append({"step": "colibri ensure", "ok": started["ok"]})
    if started["ok"]:
        steps.append({"step": "register colibri in opencode", "ok": colibri.register()["ok"]})
    return steps


def update() -> list[dict]:
    home = colibri.settings()["home"]
    tag = spec()["colibri"]["tag"]
    fetched = orchestrate.run(["git", "-C", str(home), "fetch", "--depth", "1", "origin", "tag", tag], timeout=300)
    return [{"step": f"fetch colibri {tag}", "ok": fetched["exit"] == 0}, *install()]


def verify() -> list[dict]:
    """Real requests, not exit codes: Ollama answers a prompt and Colibri answers through its API."""
    rows = []
    reply = orchestrate.delegate_ollama("Reply with the single word: ready", model=spec()["ollama"]["install"][0])
    rows.append({"step": "ollama answers", "ok": reply.get("state") == "verified" or bool(reply.get("reply")),
                 "model": reply.get("model")})
    chat = colibri.chat("Reply with the single word: ready")
    rows.append({"step": "colibri answers", "ok": chat["ok"], **{k: chat.get(k) for k in ("model", "seconds", "completion_tokens", "tokens_per_second")}})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["doctor", "status", "install", "repair", "update", "verify"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.mode in {"doctor", "status"}:
        rows = diagnose()
    elif args.mode == "install":
        rows = install()
    elif args.mode == "repair":
        rows = install() + diagnose()
    elif args.mode == "update":
        rows = update()
    else:
        rows = verify()
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            mark = "OK  " if row["ok"] else "FAIL"
            text = row.get("detail") or row.get("step")
            print(f"{mark} {row.get('name') or row.get('step')}: {text}" + (f"  -> {row['fix']}" if row.get("fix") else ""))
    return 0 if all(row["ok"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
