#!/usr/bin/env python3
"""Independent verifier: runs every check that applies and writes one report, JSON and Markdown.

  python scripts/verify.py                          standard level, offline
  python scripts/verify.py --level deep --live      everything, including the real Ollama and OpenCode

Levels: quick (seconds), standard (adds fake executors in real worktrees, unit tests, linters when
installed), deep (adds live probes). --live adds the executors of this machine. --ci makes the
linters required. The verdict is PASS only when every required check passed or was skipped with a
reason. A check that could not run is NOT_RUN, never PASS.

In the standards repository it checks the standard itself. In any other repository it runs the
standard check, the tests it finds, the data snapshot comparison and the controls of the standard.
The report goes inside the git folder (standards/reports), so it is never committed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import py_compile
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import adversarial  # noqa: E402
import evidence  # noqa: E402
import orchestrate  # noqa: E402
import preserve  # noqa: E402

R = evidence.result

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required. Install it with: pip install pyyaml")


def sh(cmd, cwd: Path, timeout: int = 900, shell: bool = False) -> dict:
    return orchestrate.run(cmd, cwd=cwd, timeout=timeout, shell=shell)


def is_standards_repo(repo: Path) -> bool:
    return (repo / "scripts" / "standard.py").exists() and (repo / "base" / "base.yml").exists()


# Checks of the standards repository


def check_compile(repo: Path) -> dict:
    broken = []
    files = [p for folder in ("scripts", "hooks", "skills", "tests") for p in (repo / folder).rglob("*.py")]
    with tempfile.TemporaryDirectory() as tmp:
        for index, path in enumerate(files):
            try:
                py_compile.compile(str(path), doraise=True, cfile=str(Path(tmp) / f"{index}.pyc"))
            except py_compile.PyCompileError as error:
                broken.append(f"{path.relative_to(repo)}: {error.msg.strip()[:120]}")
    return R("S.python-compiles", "build", "FAIL" if broken else "PASS", severity="critical",
             evidence="; ".join(broken) or f"{len(files)} Python files compile", repro="python -m py_compile <file>")


def check_command(check_id: str, category: str, cmd, repo: Path, expected: str, timeout: int = 900, shell=False) -> dict:
    ran = sh(cmd, repo, timeout, shell)
    text = (ran["stdout"] + ran["stderr"]).strip()
    status = "PASS" if ran["exit"] == 0 else ("ERROR" if ran["exit"] is None else "FAIL")
    return R(check_id, category, status, severity="critical", evidence=f"{ran['seconds']}s. " + text[-1500:],
             repro=cmd if isinstance(cmd, str) else " ".join(map(str, cmd)), expected=expected)


def frontmatter(text: str) -> dict | None:
    match = re.match(r"^---\n(.*?)\n---\n", text.replace("\r\n", "\n"), re.DOTALL)
    return yaml.safe_load(match.group(1)) if match else None


def check_skills(repo: Path) -> dict:
    problems, names = [], []
    for skill in sorted((repo / "skills").glob("*/SKILL.md")):
        try:
            meta = frontmatter(skill.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            problems.append(f"{skill.parent.name}: YAML does not parse: {error}")
            continue
        if not meta:
            problems.append(f"{skill.parent.name}: no frontmatter")
            continue
        names.append(meta.get("name"))
        if meta.get("name") != skill.parent.name:
            problems.append(f"{skill.parent.name}: name is {meta.get('name')!r}")
        description = str(meta.get("description") or "")
        if not 40 <= len(description) <= 1024:
            problems.append(f"{skill.parent.name}: description has {len(description)} characters")
        for ref in re.findall(r"`(references/[\w./-]+)`", skill.read_text(encoding="utf-8")):
            bundled = ref.startswith("references/patterns") and (repo / "patterns").is_dir()
            if not (skill.parent / ref).exists() and not bundled:
                problems.append(f"{skill.parent.name}: {ref} does not exist")
    return R("S.skills", "contract", "FAIL" if problems else "PASS", severity="high",
             evidence="; ".join(problems) or f"{len(names)} skills parse: {', '.join(names)}",
             expected="every SKILL.md parses, its name matches its folder, its references exist")


def check_settings(repo: Path) -> list[dict]:
    results = []
    conf = yaml.safe_load((repo / "settings" / "orchestration.yml").read_text(encoding="utf-8"))
    problems = [key for key in ("privacy", "tasks", "limits", "executors", "protected") if key not in conf]
    for task, candidates in (conf.get("tasks") or {}).items():
        unknown = set(candidates) - {"tools", "ollama", "opencode", "claude"}
        if unknown:
            problems.append(f"task {task}: unknown executors {sorted(unknown)}")
    classes = conf.get("privacy", {}).get("classes", {})
    if set(classes) != set(conf.get("privacy", {}).get("order", [])):
        problems.append("privacy order and classes differ")
    if classes.get("work", {}).get("remote_free") != "deny" or classes.get("restricted", {}).get("remote_claude") != "deny":
        problems.append("work or restricted code could reach a remote model")
    results.append(R("S.orchestration-policy", "security", "FAIL" if problems else "PASS", severity="critical",
                     evidence="; ".join(problems) or "policy loads, client code never reaches free models",
                     expected="every task names known executors and work code stays local"))
    opencode = json.loads((repo / "settings" / "opencode" / "opencode.json").read_text(encoding="utf-8"))
    bash, edit = opencode["permission"]["bash"], opencode["permission"]["edit"]
    lost = [rule for rule, want in (("git push --force*", "deny"), ("gh pr merge*", "deny"), ("git filter-*", "deny"),
                                    ("git commit*", "ask"), ("rm *", "ask")) if bash.get(rule) != want]
    lost += ["*AGENTS.md" for _ in [0] if edit.get("*AGENTS.md") != "deny"]
    if opencode.get("share") != "disabled":
        lost.append("share")
    results.append(R("S.opencode-rules-kept", "security", "FAIL" if lost else "PASS", severity="critical",
                     evidence=f"weakened: {lost}" if lost else "share disabled, force push and merge denied, AGENTS.md protected",
                     expected="the OpenCode config never loses a protective rule"))
    catalog = yaml.safe_load((repo / "settings" / "mcp" / "catalog.yml").read_text(encoding="utf-8"))
    radar_status = {"adopt", "trial", "assess", "hold"}
    bad = []
    for server in catalog.get("servers", []):
        launch = " ".join(server.get("launch", []))
        if server.get("status") not in radar_status:
            bad.append(f"{server.get('name')}: status")
        pinned = re.search(r"@\d+\.\d+\.\d+|==\d+\.\d+\.\d+", launch)
        if server.get("status") in {"adopt", "trial"} and not pinned:
            bad.append(f"{server.get('name')}: not pinned")
        if "latest" in launch:
            bad.append(f"{server.get('name')}: uses latest")
        if server.get("status") in {"adopt", "trial"} and not server.get("leaves_machine"):
            bad.append(f"{server.get('name')}: does not say what leaves the machine")
    results.append(R("S.mcp-catalog", "security", "FAIL" if bad else "PASS", severity="high",
                     evidence="; ".join(bad) or f"{len(catalog.get('servers', []))} servers, trial ones pinned, none on by default",
                     expected="exact versions and a privacy note for every server in use"))
    return results


def check_ruff(repo: Path, required: bool) -> dict:
    if not shutil.which("ruff"):
        status = "NOT_RUN" if required else "SKIP"
        return R("S.ruff-critical", "build", status, severity="medium", required=required,
                 evidence="ruff is not installed" + ("" if required else ". CI runs it."))
    ran = sh(["ruff", "check", "--isolated", "--select", "E9,F63,F7,F82,F401,F841", "scripts", "hooks", "tests"], repo, 120)
    return R("S.ruff-critical", "build", "PASS" if ran["exit"] == 0 else "FAIL", severity="medium", required=required,
             evidence=(ran["stdout"] + ran["stderr"]).strip()[-1500:] or "no syntax errors, undefined names or unused imports",
             repro="ruff check --isolated --select E9,F63,F7,F82,F401,F841 scripts hooks tests")


def check_powershell(repo: Path) -> dict:
    """Parse every .ps1 with the real parser. On Windows this is Windows PowerShell 5.1."""
    builtin = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    shell = shutil.which("powershell") or (str(builtin) if os.name == "nt" and builtin.exists() else None) or shutil.which("pwsh")
    files = sorted((repo / "scripts").glob("*.ps1"))
    if not shell or not files:
        return R("S.powershell-parse", "build", "SKIP", severity="medium", required=False,
                 evidence="no PowerShell here" if files else "no .ps1 files")
    listed = ", ".join("'" + str(f).replace("'", "''") + "'" for f in files)
    script = (f"$bad = @(); foreach ($f in @({listed})) {{ $e = $null; "
              "[System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$null, [ref]$e) | Out-Null; "
              "if ($e.Count) { $bad += ($f + ': ' + $e[0].Message) } }; "
              "Write-Output (($PSVersionTable.PSVersion.ToString()) + ' ' + ($bad -join ' | ')); exit $bad.Count")
    ran = sh([shell, "-NoProfile", "-NonInteractive", "-Command", script], repo, 120)
    return R("S.powershell-parse", "build", "PASS" if ran["exit"] == 0 else "FAIL", severity="medium", required=False,
             evidence=f"PowerShell {(ran['stdout'] or ran['stderr']).strip()[:600]}, {len(files)} scripts")


# Checks of any repository that follows the standard


def standard_script(repo: Path) -> Path:
    return repo / "scripts" / "standard.py" if is_standards_repo(repo) else HERE / "standard.py"


def detect_tests(repo: Path) -> tuple[str | None, str]:
    package = repo / "package.json"
    if package.exists():
        scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
        if "test" in scripts:
            return ("npm test" if shutil.which("npm") else None), "package.json has a test script"
    tests = repo / "tests"
    if tests.is_dir() and any(tests.rglob("test_*.py")):
        if (repo / "pytest.ini").exists() or (repo / "pyproject.toml").exists() and "pytest" in (repo / "pyproject.toml").read_text(encoding="utf-8"):
            return (f'"{sys.executable}" -m pytest -q' if shutil.which("pytest") else None), "pytest tests"
        return f'"{sys.executable}" -m unittest discover -s tests -t .', "unittest tests"
    return None, "no tests found"


def check_repository(repo: Path) -> list[dict]:
    results = []
    if (repo / ".standard.yml").exists():
        results.append(check_command("R.standard-check", "contract", [sys.executable, str(standard_script(repo)), "check", str(repo)],
                                     repo, "the repository follows its profile"))
    else:
        results.append(R("R.standard-check", "contract", "SKIP", severity="info", evidence="no .standard.yml here"))
    command, why = detect_tests(repo)
    if command:
        results.append(check_command("R.tests", "regression", command, repo, "the repository's tests pass", 1800, shell=True))
    elif why == "no tests found":
        results.append(R("R.tests", "regression", "SKIP", severity="medium", evidence="no tests found. Add them."))
    else:
        results.append(R("R.tests", "regression", "NOT_RUN", severity="high", evidence=f"{why}, but the runner is not installed"))
    config = preserve.load_config(repo, None)
    if config.get("protect") or config.get("json_ids"):
        baseline = preserve.default_baseline(repo)
        if baseline.exists():
            results += preserve.compare(repo, config, json.loads(baseline.read_text(encoding="utf-8")))
        else:
            results.append(R("R.preservation", "data", "NOT_RUN", severity="high", evidence="docs/preservation.yml exists but no snapshot",
                             fix="run python <standard>/scripts/preserve.py snapshot before the change"))
    return results


# Live checks on this machine


def live_checks(repo: Path) -> list[dict]:
    results = []
    caps = orchestrate.doctor(full=True)
    found = [f"Python {caps['python']}", caps.get("git") or "no git",
             f"OpenCode {caps['opencode'].get('version')}" if caps["opencode"].get("path") else "no OpenCode",
             f"Ollama with {len(caps['ollama']['models'])} models" if caps["ollama"]["up"] else "Ollama off",
             f"GPU {caps['gpu']['name']} {caps['gpu']['vram_used_mib']}/{caps['gpu']['vram_total_mib']} MiB" if caps.get("gpu") else "no NVIDIA GPU seen",
             f"FTS5 {'yes' if caps['sqlite_fts5'] else 'no'}"]
    results.append(R("L.doctor", "environment", "PASS", severity="info", evidence=", ".join(found)))
    if not caps["sqlite_fts5"]:
        results.append(R("L.fts5", "environment", "FAIL", severity="medium", evidence="this Python has no SQLite FTS5, memory.py cannot work"))
    shells = caps.get("shells")
    if shells:
        ok = shells["powershell_on_path"] or not shells["powershell_exists"]
        results.append(R("L.windows-shell", "environment", "PASS" if ok else "FAIL", severity="low", required=False,
                         evidence=f"powershell.exe on PATH: {shells['powershell_on_path']}, exists: {shells['powershell_exists']}, pwsh: {shells['pwsh']}. "
                                  "orchestrate.py adds its folder to the PATH of every executor it starts",
                         fix="add %WINDIR%\\System32\\WindowsPowerShell\\v1.0 to your user PATH so other tools find it too"))
    conf = orchestrate.policy()
    if caps["ollama"]["up"]:
        model, note = orchestrate.pick_ollama_model(conf["executors"]["ollama"], caps["ollama"])
        reply = orchestrate.delegate_ollama('Answer with JSON {"ok": true} and nothing else.', want_json=True, conf=conf,
                                            caps=caps["ollama"]) if model else {"state": "blocked", "checks": {}}
        metrics = reply.get("metrics") or {}
        results.append(R("L.ollama-direct", "executor", "PASS" if reply["state"] == "verified" else "FAIL", severity="medium",
                         evidence=f"{model or note}: {reply['state']} in {reply.get('seconds')}s, "
                                  f"{metrics.get('tokens_per_s')} tokens/s, load {round((metrics.get('load_duration') or 0) / 1e9, 2)}s",
                         repro="python scripts/orchestrate.py delegate ollama --task \"Say OK\""))
        row = orchestrate.bench_classify("ollama", model) if model else None
        base = orchestrate.bench_classify("tools", None)
        for item in filter(None, [row, base]):
            orchestrate.append_bench(item)
        results.append(R("L.bench-classify", "benchmark", "PASS", severity="info", required=False,
                         evidence=f"keywords without AI: accuracy {base['accuracy']} in {base['seconds']}s. "
                                  + (f"{model}: accuracy {row['accuracy']} in {row['seconds']}s." if row else "no Ollama model")))
    else:
        results.append(R("L.ollama-direct", "executor", "SKIP", severity="info", evidence="Ollama is not running. The suite already checks the fallback."))
    local = orchestrate.local_config()
    models = orchestrate.checked_free_models(local, conf)
    if not caps["opencode"].get("path"):
        results.append(R("L.opencode-delegation", "executor", "SKIP", severity="info", evidence="OpenCode is not installed"))
    elif not models:
        results.append(R("L.opencode-delegation", "executor", "SKIP", severity="info",
                         evidence="no free model checked today. Record one with: python scripts/orchestrate.py consent "
                                  "--path <your repositories folder> --class personal-public --free-model <id from opencode models>"))
    else:
        for model in models:
            row = orchestrate.bench_fix("opencode", model)
            orchestrate.append_bench(row)
            results.append(R(f"L.opencode-delegation:{model}", "executor", "PASS" if row["verified"] else "FAIL", severity="medium",
                             evidence=f"{row['state']}, hidden tests {row['hidden_tests']}, {row['seconds']}s, checks {row['checks']}, note {row['error']}",
                             repro=f"python scripts/orchestrate.py bench --executors opencode:{model}"))
    servers = [s for s in orchestrate.mcp_catalog() if s.get("status") in {"adopt", "trial"}]
    for server in servers:
        inspected = orchestrate.mcp_inspect(server["name"])
        detail = inspected.get("error") or f"{len(inspected.get('tools', []))} tools, write tools: {inspected.get('write_tools')}"
        results.append(R(f"L.mcp:{server['name']}", "mcp", inspected["status"], severity="low", required=False,
                         evidence=detail, repro=f"python scripts/orchestrate.py mcp inspect {server['name']}"))
    return results


def default_out(repo: Path) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        rel = orchestrate.git(repo, "rev-parse", "--git-path", f"standards/reports/{stamp}")
        path = Path(rel)
        return path if path.is_absolute() else repo / path
    except RuntimeError:
        return orchestrate.home() / "reports" / stamp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--level", choices=["quick", "standard", "deep"], default="standard")
    parser.add_argument("--live", action="store_true", help="also check the executors of this machine")
    parser.add_argument("--ci", action="store_true", help="linters are required")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    started = time.monotonic()
    results: list[dict] = []
    print(f"verify {args.level}{' live' if args.live else ''} in {repo}", flush=True)
    if is_standards_repo(repo):
        results.append(check_compile(repo))
        results.append(check_command("S.selftest", "regression", [sys.executable, "scripts/standard.py", "selftest"], repo,
                                     "every profile passes init and check, hooks behave"))
        results.append(check_skills(repo))
        results += check_settings(repo)
        if args.level != "quick":
            results.append(check_command("S.unit-tests", "regression",
                                         [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                                         repo, "the unit tests of the scripts pass"))
            results.append(check_ruff(repo, args.ci))
            results.append(check_powershell(repo))
    else:
        results += check_repository(repo)
    suite = adversarial.run_suite(args.level, repo)
    if args.ci:
        for item in suite:
            if item["id"] in {"G.actionlint", "G.zizmor"}:
                item["required"] = True
                if item["status"] == "SKIP":
                    item["status"] = "NOT_RUN"
    results += suite
    if args.live:
        try:
            results += live_checks(repo)
        except Exception as error:  # noqa: BLE001 (a broken probe is reported as ERROR)
            results.append(R("L.live", "environment", "ERROR", error=f"{type(error).__name__}: {error}"))
    report = evidence.build_report("verify", args.level, results, {"seconds": round(time.monotonic() - started, 1),
                                                                  "repository": str(repo), "live": args.live})
    json_path, md_path = evidence.write_report(report, args.out or default_out(repo))
    width = max(len(r["id"]) for r in results)
    for item in sorted(results, key=lambda r: ({"FAIL": 0, "ERROR": 1, "NOT_RUN": 2, "SKIP": 3, "PASS": 4}[r["status"]], r["id"])):
        flag = "" if item["required"] else " (optional)"
        print(f"{item['status']:<7} {item['id']:<{width}} {(item['error'] or item['evidence']).splitlines()[0][:110] if (item['error'] or item['evidence']) else ''}{flag}")
    counts = report["counts"]
    print(f"\n{report['verdict']} in {report['seconds']}s. PASS {counts['PASS']}, FAIL {counts['FAIL']}, ERROR {counts['ERROR']}, "
          f"NOT_RUN {counts['NOT_RUN']}, SKIP {counts['SKIP']}")
    print(f"Report: {md_path}\nData:   {json_path}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
