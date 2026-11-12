#!/usr/bin/env python3
"""Bounded local benchmark jobs for Standards AI Control.

No shell, remote provider, model installation, arbitrary command or automatic start.
Users start/cancel jobs explicitly from the loopback dashboard. This is intentionally
narrower than the work-plan executor; it uses the existing analyzer and its resume logic.
"""
from __future__ import annotations

import json
import os
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
