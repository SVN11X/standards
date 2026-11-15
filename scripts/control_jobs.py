#!/usr/bin/env python3
"""Bounded jobs for Standards AI Control: local benchmarks and Autopilot plans.

No shell, model installation, arbitrary command or automatic start.
Users start/cancel jobs explicitly from the loopback dashboard. A benchmark uses the existing
analyzer and its resume logic. An Autopilot job runs scripts/plan_autopilot.py as its own process,
under the owner's cost and privacy policy, and goes on after the dashboard or a Claude session ends.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

TASKS = ("refactor-module", "review-diff", "decompose")
MODEL = "qwen3.5-9b-ctx16k"
KINDS = ("bench-plan", "bench-run")


def command(kind: str, repo: Path) -> list[str]:
    if kind not in KINDS:
        raise ValueError("unsupported operation")
    script = Path(repo).resolve() / "scripts" / "analyze.py"
    if not script.is_file():
        raise FileNotFoundError(f"Analyzer missing: {script}")
    cmd = [sys.executable, str(script), "plan" if kind == "bench-plan" else "run",
           "--mode", "local-only", "--models", MODEL, "--tasks", *TASKS,
           "--local-agents", "--runs", "3"]
    if kind == "bench-run":
        cmd += ["--hours", "2"]
    return cmd


def read_tail(path: Path | None, max_bytes: int = 16000) -> str:
    if not path or not path.is_file():
        return ""
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(stream.tell() - max_bytes, 0))
        return stream.read().decode("utf-8", errors="replace")


class JobManager:
    """One local benchmark at a time. Never kill or claim ownership of other processes."""
    def __init__(self, repo: Path, data_dir: Path | None = None, popen=None):
        self.repo = Path(repo).resolve()
        self.data_dir = Path(data_dir or (Path.home() / ".standards" / "control-jobs"))
        self.popen = popen or subprocess.Popen
        self.lock = threading.Lock()
        self.process = None
        self.job: dict | None = None

    def snapshot(self) -> dict:
        with self.lock:
            if self.job is None:
                return {"active": False, "job": None, "log": ""}
            row = self.job.copy()
            exit_code = self.process.poll() if self.process is not None else None
            if row["state"] in {"running", "cancelling"} and exit_code is not None:
                row["state"] = ("cancelled" if row["state"] == "cancelling" else
                                "passed" if exit_code == 0 else "failed")
                row["exit_code"] = exit_code
                row["finished_at"] = datetime.now(timezone.utc).isoformat()
                self.job = row
            return {"active": row["state"] in {"running", "cancelling"}, "job": row,
                    "log": read_tail(self.data_dir / f"{row['id']}.log")}

    def start(self, kind: str) -> dict:
        argv = command(kind, self.repo)
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise RuntimeError("a benchmark is already running")
            self.data_dir.mkdir(parents=True, exist_ok=True)
            job_id = uuid.uuid4().hex
            log_path = self.data_dir / f"{job_id}.log"
            env = os.environ.copy()
            # Fail closed even if the owner's defaults are more permissive.
            env["STANDARDS_COST_MODE"] = "local-only"
            env["PYTHONUTF8"] = "1"
            with log_path.open("wb") as output:
                proc = self.popen(argv, cwd=str(self.repo), stdin=subprocess.DEVNULL,
                                  stdout=output, stderr=subprocess.STDOUT, env=env)
            self.process = proc
            self.job = {"id": job_id, "kind": kind, "state": "running", "pid": proc.pid,
                        "started_at": datetime.now(timezone.utc).isoformat(), "exit_code": None,
                        "mode": "local-only", "model": MODEL, "tasks": list(TASKS),
                        "command": " ".join(argv)}
            # Persist just metadata to recover evidence after dashboard restarts.
            (self.data_dir / f"{job_id}.json").write_text(json.dumps(self.job, indent=2), encoding="utf-8")
        return self.snapshot()

    def cancel(self, job_id: str) -> dict:
        with self.lock:
            if not self.job or self.job["id"] != job_id:
                raise ValueError("unknown job")
            if self.process is None or self.process.poll() is not None:
                raise RuntimeError("job is not running")
            self.process.terminate()
            self.job["state"] = "cancelling"
            # A successful terminate() call does not prove that child processes stopped.
        return self.snapshot()


PLAN_ID = re.compile(r"auto-[0-9a-f]{14}")
PLANNERS = ("auto", "local", "haiku", "sonnet", "opus")
PUBLISH = ("none", "pr")


def autopilot_command(kind: str, repo: Path, *, instruction: str = "", planner: str = "auto", plan: Path | None = None,
                      publish: str = "none") -> list[str]:
    """The exact argv of an Autopilot job. Auto-merge is never offered here: it stays an explicit terminal command.

    The script is the one next to this file. `repo` is the repository the plan changes, which is rarely this one.
    """
    script = Path(__file__).resolve().parent / "plan_autopilot.py"
    if not script.is_file():
        raise FileNotFoundError(f"Autopilot missing: {script}")
    if kind == "plan":
        if not instruction.strip() or len(instruction) > 6000 or planner not in PLANNERS:
            raise ValueError("an instruction of 1 to 6000 characters and a known planner are required")
        return [sys.executable, str(script), "plan", "--instruction", instruction.strip(), "--planner", planner,
                "--repo", str(Path(repo).resolve())]
    if kind == "run":
        if plan is None or not PLAN_ID.fullmatch(plan.stem) or not plan.is_file() or publish not in PUBLISH:
            raise ValueError("a saved plan and a publish mode of none or pr are required")
        return [sys.executable, str(script), "run", str(plan), "--repo", str(Path(repo).resolve()), "--publish", publish]
    raise ValueError("unsupported operation")


class AutopilotManager:
    """Plans and runs started from the dashboard. One job per plan at a time. It never kills a process it did not start."""

    def __init__(self, repo: Path, data_dir: Path, plans_dir: Path, popen=None):
        self.repo, self.data_dir, self.plans_dir = Path(repo).resolve(), Path(data_dir), Path(plans_dir)
        self.popen = popen or subprocess.Popen
        self.lock = threading.Lock()
        self.jobs: dict[str, dict] = {}
        self.procs: dict[str, object] = {}

    def refresh(self, row: dict) -> dict:
        proc = self.procs.get(row["id"])
        code = proc.poll() if proc is not None else None
        if row["state"] == "running" and code is not None:
            # The exit code is the evidence. A process that only went quiet is still running.
            row.update(state="passed" if code == 0 else "failed", exit_code=code,
                       finished_at=datetime.now(timezone.utc).isoformat())
        return row

    def snapshot(self) -> list[dict]:
        with self.lock:
            rows = [self.refresh(row).copy() for row in self.jobs.values()]
        for row in rows:
            row["log"] = read_tail(self.data_dir / f"{row['id']}.log", 6000)
        return sorted(rows, key=lambda r: r["started_at"], reverse=True)[:12]

    def launch(self, kind: str, key: str, argv: list[str], cwd: Path | None = None) -> dict:
        with self.lock:
            if any(self.refresh(r)["state"] == "running" and r["key"] == key for r in self.jobs.values()):
                raise RuntimeError("this plan already has a job running")
            self.data_dir.mkdir(parents=True, exist_ok=True)
            job_id = uuid.uuid4().hex
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            flags = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True})
            with (self.data_dir / f"{job_id}.log").open("wb") as output:
                proc = self.popen(argv, cwd=str(cwd or self.repo), stdin=subprocess.DEVNULL, stdout=output,
                                  stderr=subprocess.STDOUT, env=env, **flags)
            self.procs[job_id] = proc
            self.jobs[job_id] = {"id": job_id, "kind": kind, "key": key, "state": "running", "pid": proc.pid,
                                 "started_at": datetime.now(timezone.utc).isoformat(), "exit_code": None}
            return self.jobs[job_id].copy()

    def plan(self, instruction: str, planner: str = "auto") -> dict:
        argv = autopilot_command("plan", self.repo, instruction=instruction, planner=planner)
        return self.launch("plan", "plan:" + instruction.strip()[:80], argv)

    def start(self, plan_id: str, publish: str = "none") -> dict:
        if not PLAN_ID.fullmatch(str(plan_id)):
            raise ValueError("unknown plan")
        path = self.plans_dir / f"{plan_id}.json"
        try:
            # A plan runs in the repository it was made for, whatever folder the dashboard was started in.
            repo = Path(str(json.loads(path.read_text(encoding="utf-8")).get("repo") or self.repo))
        except (OSError, ValueError):
            raise ValueError("unknown plan") from None
        if not repo.is_dir():
            raise ValueError("the repository of this plan is not on this machine")
        return self.launch("run", plan_id, autopilot_command("run", repo, plan=path, publish=publish), repo)
