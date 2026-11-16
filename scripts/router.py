#!/usr/bin/env python3
"""Router: turn one request in plain words into a decision about the repository, the goal and the tools.

A program decides, no model does. It reads what the request asks (an order, a question, a review, a setup,
a publication), asks scripts/repo_fingerprint.py what the folder is, picks a recipe of settings/recipes.yml
and, for every capability of that recipe, the first provider this client and this machine really have.
The decision names the evidence of each choice, what leaves the machine, the permission the request needs
and how the result is verified. It never edits a file and never starts a tool.

A work order opens one task. A follow-up updates that task instead of opening another. The task has a key
and a state in ~/.standards/router/tasks, so a new session finds the work an old one left.

Usage: python scripts/router.py route "REQUEST" [--cwd DIR] [--client claude|opencode|coordinator] [--json]
       python scripts/router.py tasks [--cwd DIR]
       python scripts/router.py done KEY
       python scripts/router.py check
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import repo_fingerprint  # noqa: E402

SCHEMA = "standards/route-decision/v1"
CLIENTS = ("claude", "opencode", "coordinator")
INTENTS = ("work", "query", "review", "setup", "publish", "other")
DEFAULTS = {"owner": "session", "task_ttl_h": 12, "max_context_chars": 1800}
# Words that open a question. A request that starts with one asks for an answer, whatever verb follows.
QUESTION = re.compile(r"^(qué|que|por qué|porque|cómo|como|cuál|cual|cuáles|cuándo|dónde|quién|what|why|how|which|when|where|who|"
                      r"is|are|does|do|should|would|will|es|son|hay|debería|conviene)\b")
ASK = re.compile(r"^(explica\w*|explíca\w*|explain|describe\w*|cuéntame|dime|tell me|muéstrame|show me|resume|resúme\w*|summari[sz]e|"
                 r"analiza\w*|analy[sz]e|compara\w*|compare|lista\w*|list)\b")
POLITE = re.compile(r"^(por favor,?|please,?|puedes|podrías|podrias|can you|could you|necesito que|quiero que|i need you to|"
                    r"i want you to|ahora|now|ok,?|vale,?|bien,?)\s+")
CLITICS = "(lo|la|los|las|le|les|me|nos)?"


def verbs(spanish: str, english: str) -> re.Pattern:
    """A pattern for orders. Each Spanish verb is given as `imperative/accented/infinitive/formal`, so a noun
    that shares its stem, such as "cambios", never reads as an order. An English verb counts only as the first
    word, because "build", "change" or "release" are nouns everywhere else."""
    forms = []
    for entry in spanish.split():
        plain, accented, infinitive, formal = entry.split("/")
        forms += [plain + CLITICS, accented + CLITICS, infinitive + CLITICS, formal + "s?" + CLITICS]
    return re.compile(r"\b(" + "|".join(forms) + r")\b|^(" + "|".join(english.split()) + r")\b")


CHANGE = verbs(
    "corrige/corríge/corregir/corrija arregla/arrégla/arreglar/arregle mejora/mejóra/mejorar/mejore "
    "agrega/agréga/agregar/agregue añade/añáde/añadir/añada implementa/impleménta/implementar/implemente "
    "crea/créa/crear/cree cambia/cámbia/cambiar/cambie modifica/modifíca/modificar/modifique "
    "actualiza/actualíza/actualizar/actualice refactoriza/refactoríza/refactorizar/refactorice "
    "elimina/elimína/eliminar/elimine borra/bórra/borrar/borre quita/quíta/quitar/quite "
    "optimiza/optimíza/optimizar/optimice reescribe/reescríbe/reescribir/reescriba migra/mígra/migrar/migre "
    "convierte/conviérte/convertir/convierta termina/termína/terminar/termine completa/compléta/completar/complete "
    "integra/intégra/integrar/integre renombra/renómbra/renombrar/renombre mueve/muéve/mover/mueva "
    "traduce/tradúce/traducir/traduzca haz/haz/hacer/haga pon/pon/poner/ponga ajusta/ajústa/ajustar/ajuste "
    "simplifica/simplifíca/simplificar/simplifique repara/repára/reparar/repare "
    "soluciona/solucióna/solucionar/solucione resuelve/resuélve/resolver/resuelva escribe/escríbe/escribir/escriba "
    "limpia/límpia/limpiar/limpie ordena/ordéna/ordenar/ordene busca/búsca/buscar/busque encuentra/encuéntra/encontrar/encuentre "
    "genera/génera/generar/genere dibuja/dibúja/dibujar/dibuje diseña/diséña/diseñar/diseñe ilustra/ilústra/ilustrar/ilustre "
    "documenta/documénta/documentar/documente redacta/redácta/redactar/redacte graba/grába/grabar/grabe anima/ánima/animar/anime "
    "incluye/inclúye/incluir/incluya adjunta/adjúnta/adjuntar/adjunte sustituye/sustitúye/sustituir/sustituya "
    "reemplaza/reempláza/reemplazar/reemplace acelera/aceléra/acelerar/acelere reduce/redúce/reducir/reduzca",
    "fix add improve implement create change update refactor remove delete optimi[sz]e rewrite migrate convert make "
    "build write rename move translate finish integrate simplify repair solve clean find search draw design generate "
    "illustrate document include attach replace reduce speed")
PUBLISH = verbs("sube/súbe/subir/suba publica/publíca/publicar/publique despliega/despliéga/desplegar/despliegue "
                "fusiona/fusióna/fusionar/fusione lanza/lánza/lanzar/lance", "push deploy merge release publish ship")
REVIEW = verbs("revisa/revísa/revisar/revise audita/audíta/auditar/audite critica/critíca/criticar/critique", "review audit critique")
SETUP = verbs("incorpora/incorpóra/incorporar/incorpore adopta/adópta/adoptar/adopte organiza/organíza/organizar/organice "
              "reorganiza/reorganíza/reorganizar/reorganice estructura/estructúra/estructurar/estructure "
              "inicializa/inicialíza/inicializar/inicialice", r"onboard setup set\sup scaffold")
SETUP_OBJECT = re.compile(r"\b(repositorio|repo|repository|estándar|estandar|standard|proyecto|project|carpetas|folders)\b")
CONTINUE = re.compile(r"^(también|tambien|además|ademas|y |pero |mejor |en vez|no,|sí,|si,|also|and |but |instead|actually|wait)\b")
THIRD_PARTY = ("remote",)


def home() -> Path:
    return repo_fingerprint.home()


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def first_sentence(prompt: str) -> str:
    text = re.sub(r"\s+", " ", str(prompt or "")).strip().lower().lstrip("¿¡ ")
    return re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]


def classify(prompt: str) -> tuple[str, str]:
    """(intent, why). An order starts with what to do. A question starts with a question word or asks to explain."""
    text = first_sentence(prompt)
    if not text or text.startswith("/"):
        return "other", "no request text, or a command of the client"
    polite = False
    while True:
        found = POLITE.match(text)
        if not found:
            break
        text, polite = text[found.end():], True
    if not polite and QUESTION.match(text):
        return "query", f"starts with the question word '{QUESTION.match(text).group(1)}'"
    if ASK.match(text):
        return "query", f"asks to '{ASK.match(text).group(1)}'"
    lead = " ".join(text.split()[:5])
    if SETUP.search(lead) and SETUP_OBJECT.search(text):
        return "setup", f"asks to '{SETUP.search(lead).group(0)}' a repository"
    change = CHANGE.search(lead)
    if change:
        return "work", f"starts with the verb '{change.group(0)}'"
    # An order after a description: "la ventana tarda en cargar, mejora el rendimiento".
    for clause in re.split(r"[,;:]\s+|\s+(?:y|and|pero|but|entonces|so)\s+", text)[1:]:
        found = CHANGE.match(clause.strip()) or CHANGE.search(" ".join(clause.split()[:2]))
        if found and not QUESTION.match(clause.strip()):
            return "work", f"a clause starts with the verb '{found.group(0)}'"
    # Without a change verb, the first of the two decides: "review it before pushing" is a review.
    found = sorted((m.start(), name, m.group(0)) for name, m in (("publish", PUBLISH.search(lead)), ("review", REVIEW.search(lead))) if m)
    if found:
        return found[0][1], f"asks to '{found[0][2]}'"
    if text.endswith("?"):
        return "query", "ends with a question mark"
    return "other", "no order, question or review was recognized"


def load_yaml(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_recipes(path: Path | None = None) -> dict:
    return load_yaml(path or ROOT / "settings" / "recipes.yml")


def statuses() -> dict:
    """Status of every tool the radar and the MCP catalog know, by name."""
    found: dict[str, str] = {}
    try:
        for entry in load_yaml(ROOT / "radar" / "radar.yml").get("entries") or []:
            found["radar:" + str(entry.get("name"))] = entry.get("status")
        for server in load_yaml(ROOT / "settings" / "mcp" / "catalog.yml").get("servers") or []:
            found["mcp:" + str(server.get("name"))] = server.get("status")
    except Exception:  # noqa: BLE001 (a bundle without the radar still routes, with the status written in the recipe)
        pass
    return found


def provider_status(provider: dict, known: dict) -> str:
    return (known.get("radar:" + str(provider.get("radar"))) or known.get("mcp:" + str(provider.get("mcp")))
            or provider.get("status") or "assess")


def owner_limits(root: Path) -> dict:
    """What the owner's policy says about this folder: local only or not, and who runs a work order."""
    out = {**DEFAULTS, "local_only": True, "privacy": "unknown", "cost_mode": "unknown",
           "why_local": "the owner's policy could not be read, so nothing is sent to a third party"}
    try:
        import orchestrate
        conf, local = orchestrate.policy(), orchestrate.local_config()
        mode = orchestrate.cost_mode(conf, local)[0]
        cls = orchestrate.privacy_class(root, conf, local)[0]
        strict = conf["privacy"]["classes"][cls].get("remote_free") == "deny"
        out.update({**(conf.get("routing") or {}), **(local.get("router") or {})})
        out.update(privacy=cls, cost_mode=mode, local_only=mode == "local-only" or strict,
                   why_local=f"cost mode {mode}" if mode == "local-only" else f"a {cls} folder" if strict else "")
    except Exception:  # noqa: BLE001 (fail closed: keep the task local)
        pass
    return out


def mcp_servers(root: Path, folder: str) -> set[str]:
    """Names of the MCP servers the project already configures, for either client."""
    names: set[str] = set()
    for base in {root, root / folder}:
        for name, key in ((".mcp.json", "mcpServers"), ("opencode.json", "mcp")):
            try:
                data = json.loads((base / name).read_text(encoding="utf-8"))
                names |= set((data.get(key) or {}).keys())
            except (OSError, ValueError, AttributeError):
                continue
    return names


def skill_present(name: str) -> bool:
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT")
    places = [ROOT / "skills" / name, HERE.parents[2] / name if len(HERE.parents) > 2 else ROOT]
    if plugin:
        places.append(Path(plugin) / "skills" / name)
    return any((place / "SKILL.md").is_file() for place in places)


def is_available(provider: dict, signals: set[str], servers: set[str]) -> bool | None:
    """True when the provider is seen, False when it is not there, None when it cannot be seen from here."""
    detect = provider.get("detect")
    if detect == "always":
        return True
    if not isinstance(detect, dict):
        return None
    if "signal" in detect:
        return detect["signal"] in signals
    if "which" in detect:
        return any(shutil.which(program) for program in detect["which"])
    if "mcp" in detect:
        return detect["mcp"] in servers
    if "skill" in detect:
        return skill_present(detect["skill"])
    if "platform" in detect:
        return (os.name == "nt") == (detect["platform"] == "windows")
    return None


def choose_provider(name: str, capability: dict, client: str, signals: set[str], servers: set[str], limits: dict,
                    known: dict) -> dict:
    """The first provider of a capability that this client and machine have. The rest are named with the reason."""
    seen, missing, passed = [], [], []
    for provider in capability.get("providers") or []:
        status = provider_status(provider, known)
        row = {"provider": provider["id"], "status": status, "runs": provider.get("runs"),
               "leaves_machine": provider.get("leaves_machine", "nothing")}
        if status == "hold":
            passed.append({**row, "why_not": "on hold in the radar"})
        elif client not in (provider.get("clients") or CLIENTS):
            passed.append({**row, "why_not": f"not offered in {client}"})
        elif provider.get("needs_signal") and provider["needs_signal"] not in signals:
            passed.append({**row, "why_not": f"the folder has no {provider['needs_signal']} files"})
        elif provider.get("runs") in THIRD_PARTY and limits["local_only"]:
            passed.append({**row, "why_not": f"it sends data out and {limits['why_local']} keeps the task on this machine"})
        else:
            available = is_available(provider, signals, servers)
            (seen if available else missing if available is False else seen).append({**row, "available": available})
    ready = [r for r in seen if r["available"]] or [r for r in seen if r["available"] is None]
    if ready:
        chosen = ready[0]
        others = [{"provider": r["provider"], "why_not": "a provider earlier in the list is available"}
                  for r in seen + missing if r is not chosen]
        why = ("seen in the project or on this machine" if chosen["available"] else "cannot be seen from here, so not checked")
        note = "" if chosen["status"] in ("adopt", "trial") else ". In assessment: not proven in this standard yet"
        return {"capability": name, **chosen, "why": why + note, "requirement": None,
                "alternatives": others + [{"provider": p["provider"], "why_not": p["why_not"]} for p in passed]}
    first = missing[0] if missing else None
    need = None
    if first:
        spec = next(p for p in capability["providers"] if p["id"] == first["provider"])
        detect = spec.get("detect") if isinstance(spec.get("detect"), dict) else {}
        need = (f"Add it with: python scripts/orchestrate.py mcp config {detect['mcp']} --client {client if client != 'coordinator' else 'claude'}"
                if "mcp" in detect else f"{detect['which'][0]} is not installed" if "which" in detect
                else f"The folder shows no {detect['signal']}" if "signal" in detect
                else f"It needs a {detect['platform']} machine and this one is not" if "platform" in detect
                else f"It needs {first['provider']}")
    return {"capability": name, "provider": None, "available": False, "status": None, "runs": None, "leaves_machine": "nothing",
            "why": "no provider of this capability is available here", "requirement": need,
            "alternatives": [{"provider": r["provider"], "why_not": "not found in the project or on this machine"} for r in missing]
            + [{"provider": p["provider"], "why_not": p["why_not"]} for p in passed]}


def words_in(text: str, words: list[str]) -> list[str]:
    low = " " + re.sub(r"[^\w\sáéíóúñ./-]", " ", text.lower()) + " "
    return [w for w in words or [] if f" {w} " in low]


def pick_recipe(intent: str, signals: set[str], prompt: str, recipes: list[dict]) -> tuple[dict | None, list[dict], str, int]:
    """(recipe, the others that matched, why, subject score). The subject score counts only the words that
    name what the request is about, so it can tell two folders apart."""
    scored = []
    for order, recipe in enumerate(recipes):
        if intent not in recipe.get("intents", []):
            continue
        hits = [s for s in recipe.get("signals_any") or [] if s in signals]
        if recipe.get("signals_any") and not hits:
            continue
        words = words_in(prompt, recipe.get("words") or [])
        verbs = words_in(prompt, recipe.get("verbs") or [])
        scored.append((len(hits) * 2 + (len(words) + len(verbs)) * 3, -order, recipe, hits, words + verbs, len(words) * 3))
    if not scored:
        return None, [], "no recipe matches this request in this folder", 0
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, _, best, hits, words, subject = scored[0]
    why = "; ".join(part for part in (f"the folder shows {', '.join(hits)}" if hits else "",
                                      f"the request says {', '.join(words)}" if words else "") if part) or "the kind of request"
    return best, [{"recipe": item[2]["id"], "score": item[0]} for item in scored[1:]], why, subject


def find_focus(fp: dict, cwd: Path, prompt: str, intent: str, recipes: list[dict]) -> tuple[str, str, list[str]]:
    """(folder, why, candidates). The folder the request is about, or the folders it could be about.

    Order: the folder the session is in, the folder the request names, the only project that could take the
    request, the project whose subject words the request uses. Anything else is a question, never a guess."""
    root = Path(fp["root"])
    try:
        inside = cwd.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        inside = "."
    subs = fp.get("subprojects") or []
    for sub in sorted(subs, key=lambda s: -len(s["path"])):
        if inside == sub["path"] or inside.startswith(sub["path"] + "/"):
            return sub["path"], "the session is inside this folder", []
    low = prompt.lower().replace("\\", "/")
    named = [s["path"] for s in subs if re.search(r"(?<![\w/])" + re.escape(s["path"].lower()) + r"(?![\w-])", low)
             or re.search(r"(?<![\w/-])" + re.escape(s["path"].rsplit("/", 1)[-1].lower()) + r"(?![\w-])", low)]
    if len(named) == 1:
        return named[0], "the request names this folder", []
    fits = []
    for sub in subs:
        if named and sub["path"] not in named:
            continue
        recipe, _, _, subject = pick_recipe(intent, {x["id"] for x in sub["signals"]}, prompt, recipes)
        if recipe:
            fits.append((subject, sub["path"]))
    if len(fits) == 1:
        return fits[0][1], "the only folder of the repository that could take this request", []
    if len(fits) > 1:
        fits.sort(reverse=True)
        if fits[0][0] > fits[1][0]:
            return fits[0][1], "the request uses the words of this folder's kind of project", []
        return ".", "several folders could be meant", sorted(path for _, path in fits)[:8]
    return ".", "the repository has one project", []


# Test tooling a workspace often keeps at its root for every package below it.
SHARED_TOOLING = {"tests", "playwright", "axe", "vitest", "jest", "pytest", "unittest", "storybook", "ci"}


def scope_signals(fp: dict, folder: str) -> tuple[list[dict], dict, str]:
    """(signals, commands, where the commands run). A folder keeps the test tooling and the test command of the
    repository root when it has none of its own, as in a workspace that runs every test from the root."""
    root_signals, root_commands = fp.get("signals") or [], fp.get("commands") or {}
    sub = next((s for s in fp.get("subprojects") or [] if s["path"] == folder), None) if folder != "." else None
    if sub is None:
        return root_signals, root_commands, "."
    have = {s["id"] for s in sub["signals"]}
    signals = sub["signals"] + [s for s in root_signals if s["id"] in SHARED_TOOLING and s["id"] not in have]
    if sub["commands"].get("test"):
        return signals, {**({"install": root_commands["install"]} if root_commands.get("install") and not sub["commands"].get("install") else {}),
                         **sub["commands"]}, folder
    inherited = {key: root_commands[key] for key in ("test", "install") if root_commands.get(key)} if root_commands.get("test") else {}
    return signals, {**sub["commands"], **inherited}, "." if root_commands.get("test") else folder


def merge_setting() -> str:
    try:
        import merge_when_green
        return merge_when_green.owner_setting()
    except Exception:  # noqa: BLE001 (a bundle without it keeps every merge with the owner)
        return "ask"


def experience_for(prompt: str, root: Path) -> dict | None:
    try:
        import standard
        choice = standard.choose_subprofile(prompt, root)
        return {"subprofile": choice["subprofile"], "why": choice["why"]}
    except Exception:  # noqa: BLE001 (a bundle without the profiles routes without naming an experience)
        return None


# Tasks


def tasks_dir() -> Path:
    path = home() / "router" / "tasks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_tasks(root: str | None = None) -> list[dict]:
    rows = []
    for path in tasks_dir().glob("*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if root is None or row.get("root") == root:
            rows.append(row)
    return sorted(rows, key=lambda r: r.get("updated", ""), reverse=True)


def write_task(row: dict) -> None:
    path = tasks_dir() / f"{row['key']}.json"
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(row, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def fresh(row: dict, ttl_h: float) -> bool:
    try:
        age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(row["updated"])
    except (KeyError, ValueError):
        return False
    return age.total_seconds() <= ttl_h * 3600


def track(decision: dict, prompt: str, session: str | None, ttl_h: float) -> dict:
    """Open one task for a work order, or add a follow-up to the task this session already has in this repository."""
    root = decision["repository"]["root"]
    active = [t for t in read_tasks(root) if t.get("state") == "active" and fresh(t, ttl_h)]
    mine = next((t for t in active if session and t.get("session") == session), None)
    text = str(prompt).strip()[:2000]
    follow = mine and (CONTINUE.match(first_sentence(prompt)) or (decision["intent"] == "other" and len(text) < 200))
    if follow:
        mine["updates"] = [*(mine.get("updates") or []), {"at": now(), "text": text}][-20:]
        mine["updated"] = now()
        write_task(mine)
        return {"key": mine["key"], "state": "updated", "prompt": mine["prompt"], "updates": len(mine["updates"])}
    if decision["intent"] not in ("work", "setup", "review", "publish") or decision["questions"]:
        left = next((t for t in active if t is not mine), None) or mine
        return {"key": None, "state": "none", "unfinished": {"key": left["key"], "prompt": left["prompt"][:200]} if left else None}
    for old in active:
        if session and old.get("session") == session:
            old.update(state="superseded", updated=now())
            write_task(old)
    key = hashlib.sha256(f"{root}|{session}|{text}|{now()}".encode()).hexdigest()[:12]
    left = next((t for t in active if not session or t.get("session") != session), None)
    write_task({"key": key, "root": root, "folder": decision["folder"], "session": session, "intent": decision["intent"],
                "recipe": decision["recipe"], "owner": decision["owner"], "prompt": text, "updates": [], "state": "active",
                "created": now(), "updated": now()})
    return {"key": key, "state": "new", "prompt": text[:200],
            "unfinished": {"key": left["key"], "prompt": left["prompt"][:200]} if left else None}


def finish(key: str) -> bool:
    for row in read_tasks():
        if row.get("key") == key:
            row.update(state="done", updated=now())
            write_task(row)
            return True
    return False


# Decision


def decide(prompt: str, cwd: Path, client: str = "claude", session: str | None = None, permission_mode: str | None = None,
           recipes: dict | None = None, limits: dict | None = None, fingerprint: dict | None = None, save: bool = True) -> dict:
    """The whole decision for one request. `save` opens or updates the task. Everything else only reads."""
    if client not in CLIENTS:
        raise ValueError(f"unknown client {client!r}. Use one of: {', '.join(CLIENTS)}")
    fp = fingerprint or repo_fingerprint.fingerprint(Path(cwd))
    root = Path(fp["root"])
    recipes = recipes or load_recipes()
    limits = limits or owner_limits(root)
    intent, intent_why = classify(prompt)
    known = statuses()
    folder, folder_why, candidates = find_focus(fp, Path(cwd), prompt, intent, recipes.get("recipes") or [])
    signal_rows, commands, where = scope_signals(fp, folder)
    signals = {s["id"] for s in signal_rows}
    recipe, alternatives, recipe_why, _ = pick_recipe(intent, signals, prompt, recipes.get("recipes") or [])
    questions = []
    if candidates and intent in ("work", "review", "publish"):
        questions.append("Which folder is this about: " + ", ".join(candidates) + "?")
    standard = fp.get("standard") or {}
    profile = standard.get("profile") or (recipe or {}).get("profile")
    profile_why = ("declared in .standard.yml" if standard.get("profile") else
                   f"the recipe {recipe['id']} suggests it. The repository has no .standard.yml" if recipe and recipe.get("profile")
                   else "not declared and no recipe names one")
    names = list((recipe or {}).get("capabilities") or [])
    notes = [recipe["notes"]] if recipe and recipe.get("notes") else []
    for extra in recipes.get("additions") or []:
        hit = words_in(prompt, extra.get("words") or [])
        if recipe and hit and extra["capability"] not in names:
            names.append(extra["capability"])
            notes.append(f"{extra['capability']} added: {extra['why']} (the request says {', '.join(hit)})")
    servers = mcp_servers(root, folder)
    chosen = [choose_provider(name, recipes["capabilities"][name], client, signals, servers, limits, known)
              for name in names if name in (recipes.get("capabilities") or {})]
    leaves = sorted({f"{c['provider']}: {c['leaves_machine']}" for c in chosen
                     if c["provider"] and c["leaves_machine"] not in ("nothing", None)})
    writes = intent in ("work", "setup")
    permission = {"work": "edits inside the repository. Pushing, merging and deploying follow the owner's rules",
                  "setup": "edits inside the repository. Moving or deleting files needs the owner's yes to the plan first",
                  "publish": "pushing, merging or deploying: the owner's configured permission decides, and the client may ask",
                  "review": "reads only", "query": "reads only", "other": "nothing asked"}[intent]
    merges = merge_setting()
    if merges == "when-green" and intent in ("work", "publish", "setup"):
        permission = (permission.replace("Pushing, merging and deploying follow the owner's rules",
                                         "Pushing follows the owner's rules. Deploying waits for the owner")
                      .replace("pushing, merging or deploying: the owner's configured permission decides, and the client may ask",
                               "pushing follows the owner's rules and deploying waits for the owner"))
        permission += (f". Merging: the owner allows it once every check passed. Merge with python \"{HERE / 'merge_when_green.py'}\" "
                       "<PR> --wait 1800, never with gh pr merge")
    if intent == "work" and PUBLISH.search(first_sentence(prompt)):
        permission += ". The request also asks to publish: that part waits for the owner's configured permission"
    if not fp["standard"]["present"] and intent in ("work", "setup"):
        notes.append("no .standard.yml in the repository: its rules are unknown, so check the README and local rules first")
    owner = limits.get("owner", "session") if intent == "work" and client == "claude" and not questions else "session"
    handoff = None
    if owner == "coordinator":
        script = HERE / "plan_autopilot.py"
        handoff = f'python "{script}" go --repo "{root}" --instruction "<the request>" --detach'
    decision = {
        "schema": SCHEMA, "at": now(), "client": client, "permission_mode": permission_mode,
        "intent": intent, "intent_why": intent_why,
        "repository": {"name": fp["name"], "root": str(root), "revision": fp.get("revision"), "standard": bool(standard.get("present"))},
        "folder": folder, "folder_why": folder_why, "profile": profile, "profile_why": profile_why,
        "experience": experience_for(prompt, root) if recipe and recipe.get("experience") and signals & {"web", "static-web"} else None,
        "signals": signal_rows, "recipe": recipe["id"] if recipe else None, "recipe_why": recipe_why, "alternatives": alternatives,
        "capabilities": chosen,
        "verification": {"command": commands.get("test"), "where": where, "proof": (recipe or {}).get("proof"),
                         "install": commands.get("install") if commands.get("test") else None},
        "permission": permission, "writes": writes, "leaves_machine": leaves,
        "privacy": limits.get("privacy"), "cost_mode": limits.get("cost_mode"),
        "reused": ["the fingerprint saved for this commit"] if fp.get("cached") else [],
        "questions": questions, "notes": notes, "owner": owner, "handoff": handoff,
        "task": {"key": None, "state": "none"},
    }
    if save:
        decision["task"] = track(decision, prompt, session, float(limits.get("task_ttl_h", DEFAULTS["task_ttl_h"])))
        if decision["task"]["state"] == "updated":
            decision["notes"].append("a follow-up of the task this session already has here. No new task was opened")
    return decision


def render(decision: dict, limit: int = DEFAULTS["max_context_chars"]) -> str:
    """The decision as short facts for the client. Facts only: the client decides what to do with them."""
    task = decision["task"]
    if task["state"] == "updated":
        return (f"standards router: follow-up of task {task['key']} in {decision['repository']['name']} "
                f"(\"{task['prompt'][:120]}\"). The task keeps its folder, recipe and verification.")
    if decision["intent"] in ("query", "other"):
        return ""
    repo = decision["repository"]
    lines = [f"standards router: {decision['intent']} request ({decision['intent_why']}) for repository {repo['name']}, "
             f"folder {decision['folder']} ({decision['folder_why']}), revision {(repo['revision'] or 'none')[:7]}."]
    if decision["profile"]:
        exp = decision.get("experience") or {}
        lines.append(f"Profile {decision['profile']} ({decision['profile_why']})"
                     + (f", experience {exp['subprofile']} ({exp['why']})." if exp.get("subprofile") else "."))
    if decision["recipe"]:
        lines.append(f"Recipe {decision['recipe']}: {decision['recipe_why']}.")
    for item in decision["capabilities"]:
        if item["provider"]:
            lines.append(f"- {item['capability']}: {item['provider']} ({item['why']}).")
        else:
            lines.append(f"- {item['capability']}: none available here. {item['requirement'] or ''}".rstrip())
    check = decision["verification"]
    if check["command"] or check["proof"]:
        place = "at the repository root" if check["where"] == "." else f"in {check['where']}"
        setup = check.get("install")
        if setup:
            steps = setup if isinstance(setup, list) else [setup]
            lines.append("Before the tests, install: " + ", then ".join(f"`{step}`" for step in steps) + ".")
        lines.append("Verification: " + (f"`{check['command']}` {place}. " if check["command"] else "")
                     + (f"Done means: {check['proof']}." if check["proof"] else ""))
    lines.append(f"Permission: {decision['permission']}.")
    if decision["leaves_machine"]:
        lines.append("Leaves the machine: " + "; ".join(decision["leaves_machine"]) + ".")
    for note in decision["notes"]:
        lines.append("Note: " + note + ".")
    for question in decision["questions"]:
        lines.append("Open question before any edit: " + question)
    if decision["owner"] == "coordinator":
        lines.append(f"Owner of this task: the standards coordinator, so the session edits no file. It starts with: {decision['handoff']}")
    if task.get("key"):
        lines.append(f"Task {task['key']} opened. `python \"{HERE / 'router.py'}\" done {task['key']}` closes it.")
    if task.get("unfinished"):
        lines.append(f"Unfinished task {task['unfinished']['key']} in this repository: \"{task['unfinished']['prompt'][:120]}\".")
    text = "\n".join(lines)
    return text if len(text) <= limit else text[:limit - 20].rsplit("\n", 1)[0] + "\n(shortened)"


def check(recipes: dict | None = None) -> list[str]:
    """Problems in settings/recipes.yml: a recipe that names no known capability, a provider with no status source."""
    recipes = recipes or load_recipes()
    known = statuses()
    capabilities = recipes.get("capabilities") or {}
    problems = []
    ids = [r.get("id") for r in recipes.get("recipes") or []]
    problems += [f"recipe id {i} is listed twice" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for recipe in recipes.get("recipes") or []:
        problems += [f"recipe {recipe.get('id')}: unknown capability {c}" for c in recipe.get("capabilities") or []
                     if c not in capabilities]
        problems += [f"recipe {recipe.get('id')}: unknown intent {i}" for i in recipe.get("intents") or [] if i not in INTENTS]
        if not recipe.get("proof"):
            problems.append(f"recipe {recipe.get('id')}: no proof of done")
    for extra in recipes.get("additions") or []:
        if extra.get("capability") not in capabilities:
            problems.append(f"addition: unknown capability {extra.get('capability')}")
    for name, capability in capabilities.items():
        for provider in capability.get("providers") or []:
            where = f"{name}/{provider.get('id')}"
            if provider.get("radar") and "radar:" + provider["radar"] not in known:
                problems.append(f"{where}: radar entry {provider['radar']!r} does not exist")
            if provider.get("mcp") and "mcp:" + provider["mcp"] not in known:
                problems.append(f"{where}: MCP server {provider['mcp']!r} is not in settings/mcp/catalog.yml")
            if not (provider.get("radar") or provider.get("mcp") or provider.get("status") in ("adopt", "trial", "assess", "hold")):
                problems.append(f"{where}: no status and no radar or MCP entry to read it from")
            if set(provider.get("clients") or []) - set(CLIENTS) or not provider.get("clients"):
                problems.append(f"{where}: clients must be a list of {', '.join(CLIENTS)}")
            if provider.get("runs") not in ("client", "local", "remote", "plugin"):
                problems.append(f"{where}: runs must be client, local, remote or plugin")
            if provider.get("runs") == "remote" and provider.get("leaves_machine") in (None, "nothing"):
                problems.append(f"{where}: a remote provider must say what leaves the machine")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    route = sub.add_parser("route")
    route.add_argument("request")
    route.add_argument("--cwd", default=".")
    route.add_argument("--client", choices=CLIENTS, default="claude")
    route.add_argument("--json", action="store_true")
    route.add_argument("--dry", action="store_true", help="decide without opening or updating a task")
    listed = sub.add_parser("tasks")
    listed.add_argument("--cwd", default=".")
    done = sub.add_parser("done")
    done.add_argument("key")
    sub.add_parser("check")
    args = parser.parse_args(argv)
    if args.command == "check":
        problems = check()
        print("\n".join(problems) or "recipes are consistent")
        return 1 if problems else 0
    if args.command == "done":
        print("closed" if finish(args.key) else "no task with that key")
        return 0
    if args.command == "tasks":
        root = repo_fingerprint.fingerprint(Path(args.cwd))["root"]
        print(json.dumps([{k: t.get(k) for k in ("key", "state", "intent", "recipe", "folder", "prompt", "updated")}
                          for t in read_tasks(root)], indent=2, ensure_ascii=False))
        return 0
    decision = decide(args.request, Path(args.cwd), args.client, save=not args.dry)
    print(json.dumps(decision, indent=2, ensure_ascii=False) if args.json else (render(decision) or
          f"{decision['intent']} request ({decision['intent_why']}): no task, the answer is an explanation."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
