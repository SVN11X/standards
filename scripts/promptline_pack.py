#!/usr/bin/env python3
"""Write a Promptline pack with the requests this standard understands, so the owner pastes them with one key.

Each prompt is a request the router already classifies, in the words the owner uses. The pack is one JSON file that Promptline imports.
Promptline (MIT, https://github.com/bekalpaslan/promptline) is the Windows tray app that pastes saved prompts into Claude Code, Codex or a browser.
Run: python scripts/promptline_pack.py [--out FILE] [--name NAME]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PROMPTS = [
    {"group": "Control", "title": "Estado", "tags": ["control"], "text": "muéstrame el estado"},
    {"group": "Control", "title": "Pausa", "tags": ["control"], "text": "Pausa"},
    {"group": "Control", "title": "Reanuda", "tags": ["control"], "text": "reanuda"},
    {"group": "Control", "title": "Cancela el plan", "tags": ["control"], "text": "cancela el plan"},
    {"group": "Control", "title": "Por qué se detuvo", "tags": ["control"], "text": "¿por qué no puedes hacerlo?"},
    {"group": "Control", "title": "Continúa", "tags": ["control"],
     "text": "continúa con lo pendiente y avísame cuando termines"},
    {"group": "Repository", "title": "Mejora este repo", "tags": ["repo"], "text": "mejora este repo"},
    {"group": "Repository", "title": "Revisa el PR", "tags": ["repo"], "text": "revisa el PR {pr}"},
    {"group": "Repository", "title": "Revisa este cambio", "tags": ["repo"], "text": "revisa esto:\n\n{clipboard}"},
    {"group": "Repository", "title": "Prepara el repo", "tags": ["repo"],
     "text": "organiza este repositorio según el estándar"},
    {"group": "Debug", "title": "Causa raíz primero", "tags": ["debug"],
     "text": "Este es el error:\n\n{clipboard}\n\nEncuentra la causa raíz antes de proponer un arreglo."},
    {"group": "Debug", "title": "Arregla el check", "tags": ["debug"],
     "text": "El check falló con esto:\n\n{clipboard}\n\nArréglalo en la misma rama."},
]

FIXED = re.compile(r"\{(?:clipboard|date|time)\}")
ASKED = re.compile(r"\{[a-z_]+\}")
ONCE = re.compile(r"\{\{[a-z_]+\}\}")
BRACES = re.compile(r"\{\{[^{}]*\}\}|\{[^{}]*\}")
TAG = re.compile(r"^[a-z0-9_-]+$")


def pack(name: str = "SVN11X standards") -> dict:
    return {"name": name, "prompts": [{key: dict(p)[key] for key in ("title", "tags", "group", "text")} for p in PROMPTS]}


def problems(data: dict) -> list[str]:
    found = []
    if not data.get("name"):
        found.append("the pack has no name")
    prompts = data.get("prompts")
    if not isinstance(prompts, list) or not prompts:
        return found + ["the pack has no prompts"]
    seen = set()
    for item in prompts:
        title = item.get("title") or ""
        label = title or "(no title)"
        if not title:
            found.append("a prompt has no title")
        elif title in seen:
            found.append(f"{label}: duplicate title")
        seen.add(title)
        if not item.get("text"):
            found.append(f"{label}: no text")
        tags = item.get("tags")
        if not isinstance(tags, list) or not 1 <= len(tags) <= 3:
            found.append(f"{label}: needs 1 to 3 tags")
        elif not all(isinstance(t, str) and TAG.match(t) for t in tags):
            found.append(f"{label}: tags must be lowercase")
        for token in BRACES.findall(item.get("text") or ""):
            if not (FIXED.fullmatch(token) or ASKED.fullmatch(token) or ONCE.fullmatch(token)):
                found.append(f"{label}: unknown placeholder {token}")
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Write a Promptline pack with the requests the standard understands.")
    parser.add_argument("--out", help="file to write, default is stdout")
    parser.add_argument("--name", default="SVN11X standards")
    args = parser.parse_args(argv)
    data = pack(args.name)
    bad = problems(data)
    if bad:
        for line in bad:
            print(f"problem: {line}", file=sys.stderr)
        return 1
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if not args.out:
        sys.stdout.write(text)
        return 0
    out = Path(args.out)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(out)
    return 0


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
