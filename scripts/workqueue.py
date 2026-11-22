#!/usr/bin/env python3
"""A queue of work between the owner's machines: the remote VM runs CPU work, the notebook takes the work for its GPU.

The queue is one SQLite file on the remote VM. The notebook reaches it over SSH, an authenticated private channel, with
`--via HOST`. A task holds its id, repository, commit, the capability it needs (cpu or gpu), the command and its state.
A worker claims one task for a limited time and gets a token. Only the holder of that token can finish it, and a task
finishes once: a second result for the same id is refused. A lease that ran out is not given to another worker by
itself: someone checks the result and the diff first, then `retry --checked` puts it back.

What may enter: the cost mode is not local-only and the privacy class of the repository is in
`remote_node.allow_classes` of settings/orchestration.yml. A local-only task stays on the notebook and never enters.
Ollama and Colibri stay on loopback: the queue carries commands and short results, never a model port.

Commands:
  add      put a task in the queue: --repo PATH --commit SHA --needs cpu|gpu --command "..."
  claim    take the oldest pending task this worker can do: --worker NAME --can cpu [gpu] [--via HOST]
  done     finish a claimed task with its token and a short result: ID --token T --result TEXT [--failed] [--via HOST]
  retry    put an expired task back after its result and diff were checked: ID --checked
  list     the tasks and their state
  export   every task as JSON lines, to keep a backup off the VM
  restore  read a backup. A task the queue already finished keeps its one result
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "hooks"))

NEEDS = ("cpu", "gpu")
STATES = ("pending", "claimed", "expired", "done", "failed")
FINAL = ("done", "failed")
MAX_RESULT_CHARS = 4000
SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, repo TEXT NOT NULL, commit_sha TEXT NOT NULL, needs TEXT NOT NULL, command TEXT NOT NULL,
  privacy TEXT NOT NULL, state TEXT NOT NULL, worker TEXT, token TEXT, lease_until TEXT, attempts INTEGER NOT NULL DEFAULT 0,
  result TEXT, created TEXT NOT NULL, updated TEXT NOT NULL, finished TEXT);
"""


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def stamp(at: dt.datetime | None = None) -> str:
    return (at or now()).isoformat(timespec="seconds")


def db_path() -> Path:
    root = Path(os.environ.get("STANDARDS_HOME") or Path.home() / ".standards")
    root.mkdir(parents=True, exist_ok=True)
    return root / "workqueue.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    db = sqlite3.connect(path or db_path(), isolation_level=None)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def settings() -> dict:
    import orchestrate
    conf = orchestrate.policy()
    return {"allow_classes": ["personal-public"], "lease_s": 1800, **(conf.get("remote_node") or {})}


def may_enter(repo: Path, mode: str | None = None) -> tuple[bool, str, str]:
    """(ok, why, privacy class). The VM is another machine, so the cost mode and the privacy class both decide."""
    import orchestrate
    conf, local = orchestrate.policy(), orchestrate.local_config()
    name, source = orchestrate.cost_mode(conf, local, mode)
    cls, cls_source = orchestrate.privacy_class(repo, conf, local)
    if name == "local-only":
        return False, f"cost mode local-only ({source}): the task stays on this machine and never enters the queue", cls
    allowed = settings()["allow_classes"]
    if cls not in allowed:
        return False, (f"a {cls} repository ({cls_source}) does not go to the remote node. remote_node.allow_classes "
                       f"allows {', '.join(allowed) or 'nothing'}"), cls
    return True, f"a {cls} repository may go to the remote node", cls


def add(db, repo: str, commit: str, needs: str, command: str, privacy: str, task_id: str | None = None) -> str:
    if needs not in NEEDS:
        raise ValueError(f"needs must be one of {NEEDS}")
    task_id = task_id or uuid.uuid4().hex[:12]
    db.execute("INSERT INTO tasks(id, repo, commit_sha, needs, command, privacy, state, created, updated) "
               "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)", (task_id, repo, commit, needs, command, privacy, stamp(), stamp()))
    return task_id


def expire(db, at: dt.datetime | None = None) -> int:
    """Claims whose lease ran out become expired. They wait for a check, they are never handed out again by themselves."""
    cursor = db.execute("UPDATE tasks SET state = 'expired', token = NULL, updated = ? WHERE state = 'claimed' AND lease_until < ?",
                        (stamp(at), stamp(at)))
    return cursor.rowcount


def claim(db, worker: str, can: list[str], lease_s: int | None = None, at: dt.datetime | None = None) -> dict | None:
    """The oldest pending task this worker can do, with a token valid until the lease ends. None when there is none."""
    at = at or now()
    lease_s = lease_s or int(settings()["lease_s"])
    db.execute("BEGIN IMMEDIATE")
    try:
        expire(db, at)
        marks = ",".join("?" for _ in can) or "''"
        row = db.execute(f"SELECT * FROM tasks WHERE state = 'pending' AND needs IN ({marks}) ORDER BY created, id LIMIT 1",
                         list(can)).fetchone()
        if row is None:
            db.execute("COMMIT")
            return None
        token = uuid.uuid4().hex
        until = stamp(at + dt.timedelta(seconds=lease_s))
        db.execute("UPDATE tasks SET state = 'claimed', worker = ?, token = ?, lease_until = ?, attempts = attempts + 1, updated = ? "
                   "WHERE id = ?", (worker, token, until, stamp(at), row["id"]))
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    return {**dict(row), "state": "claimed", "worker": worker, "token": token, "lease_until": until, "attempts": row["attempts"] + 1}


def clean_result(text: str) -> str:
    from secret_scan import scan
    found = scan(text)
    if found:
        raise ValueError(f"refused: the result looks like it holds {', '.join(found)}")
    return text.strip()[:MAX_RESULT_CHARS]


def finish(db, task_id: str, token: str, result: str, ok: bool = True, at: dt.datetime | None = None) -> tuple[bool, str]:
    """Record the one result of a task. Only the token of a claim whose lease still runs may do it, and only once."""
    result = clean_result(result)
    expire(db, at)
    cursor = db.execute("UPDATE tasks SET state = ?, result = ?, finished = ?, updated = ?, token = NULL "
                        "WHERE id = ? AND state = 'claimed' AND token = ?",
                        ("done" if ok else "failed", result, stamp(at), stamp(at), task_id, token))
    if cursor.rowcount == 1:
        return True, f"{task_id} {'done' if ok else 'failed'}"
    row = db.execute("SELECT state FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return False, f"no task {task_id}"
    if row["state"] in FINAL:
        return False, f"{task_id} already has its result ({row['state']}). A task finishes once"
    return False, f"{task_id} is {row['state']} and this token no longer holds it. Check its result and diff, then retry --checked"


def retry(db, task_id: str, checked: bool) -> tuple[bool, str]:
    if not checked:
        return False, "check the result and the diff of the expired run first, then pass --checked"
    cursor = db.execute("UPDATE tasks SET state = 'pending', worker = NULL, lease_until = NULL, updated = ? "
                        "WHERE id = ? AND state = 'expired'", (stamp(), task_id))
    return (True, f"{task_id} is pending again") if cursor.rowcount else (False, f"{task_id} is not expired")


def export(db) -> list[dict]:
    return [{key: row[key] for key in row.keys() if key != "token"} for row in db.execute("SELECT * FROM tasks ORDER BY created, id")]


def restore(db, rows: list[dict]) -> dict:
    """Bring back a backup. A finished task keeps the result it has. A claim from before the loss comes back expired."""
    counts = {"added": 0, "kept": 0}
    for row in rows:
        if db.execute("SELECT 1 FROM tasks WHERE id = ?", (row["id"],)).fetchone():
            counts["kept"] += 1
            continue
        state = "expired" if row["state"] == "claimed" else row["state"]
        db.execute("INSERT INTO tasks(id, repo, commit_sha, needs, command, privacy, state, worker, lease_until, attempts, result, "
                   "created, updated, finished) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (row["id"], row["repo"], row["commit_sha"], row["needs"], row["command"], row["privacy"], state, row.get("worker"),
                    row.get("lease_until"), row.get("attempts", 0), row.get("result"), row["created"], stamp(), row.get("finished")))
        counts["added"] += 1
    return counts


def remote(host: str, path: str, args: list[str]) -> dict:
    """Run this script on the remote VM over SSH and read its JSON answer."""
    command = " ".join(shlex.quote(part) for part in ["python3", path, *args, "--json"])
    done = subprocess.run(["ssh", "-o", "BatchMode=yes", host, command], capture_output=True, text=True, timeout=120)
    if done.returncode not in (0, 1):
        raise RuntimeError((done.stderr or done.stdout)[-300:] or f"ssh exited with {done.returncode}")
    return json.loads(done.stdout or "{}")


def gpu_ready(can: list[str]) -> tuple[list[str], str | None]:
    """Drop gpu from what this worker can do while the local card is busy, so a GPU task waits instead of failing."""
    if "gpu" not in can:
        return can, None
    import orchestrate
    import resources
    busy = resources.local_busy(None, orchestrate.policy())
    return ([need for need in can if need != "gpu"], busy) if busy else (can, None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, help="the queue file (default: STANDARDS_HOME/workqueue.db)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("add")
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--commit", required=True)
    p.add_argument("--needs", choices=NEEDS, required=True)
    p.add_argument("--command", dest="task_command", required=True)
    p.add_argument("--id")
    p.add_argument("--mode", choices=["local-only", "free-strict", "existing-subscription"])
    for name in ("claim", "done"):
        p = sub.add_parser(name)
        p.add_argument("--via", help="the remote VM as an SSH host. Without it the queue is the local file")
        p.add_argument("--remote-path", default="standards/scripts/workqueue.py", help="this script on the remote VM")
        p.add_argument("--json", action="store_true")
        if name == "claim":
            p.add_argument("--worker", required=True)
            p.add_argument("--can", nargs="+", choices=NEEDS, required=True)
            p.add_argument("--lease", type=int, help="seconds the claim holds (default remote_node.lease_s)")
        else:
            p.add_argument("id")
            p.add_argument("--token", required=True)
            p.add_argument("--result", required=True)
            p.add_argument("--failed", action="store_true")
    p = sub.add_parser("retry")
    p.add_argument("id")
    p.add_argument("--checked", action="store_true")
    p = sub.add_parser("list")
    p.add_argument("--state", choices=STATES)
    sub.add_parser("export")
    p = sub.add_parser("restore")
    p.add_argument("file", type=Path)
    args = parser.parse_args(argv)

    can = None
    if args.command == "claim":
        can, busy = gpu_ready(list(args.can))
        if not can:
            print(json.dumps({"task": None, "why": busy}) if args.json else f"nothing claimed: {busy}")
            return 0
    if args.command in ("claim", "done") and args.via:
        if args.command == "claim":
            forward = ["claim", "--worker", args.worker, *(["--lease", str(args.lease)] if args.lease else []), "--can", *can]
        else:
            forward = ["done", args.id, "--token", args.token, "--result", args.result] + (["--failed"] if args.failed else [])
        print(json.dumps(remote(args.via, args.remote_path, forward), ensure_ascii=False))
        return 0
    if args.command == "add":
        repo = args.repo.resolve()
        ok, why, cls = may_enter(repo, args.mode)
        if not ok:
            print(f"not queued: {why}", file=sys.stderr)
            return 1
    db = connect(args.db)
    if args.command == "add":
        print(add(db, repo.name, args.commit, args.needs, args.task_command, cls, args.id))
        return 0
    if args.command == "claim":
        task = claim(db, args.worker, can, args.lease)
        print(json.dumps({"task": task}, ensure_ascii=False) if args.json else (f"{task['id']} {task['repo']}@{task['commit_sha'][:12]} "
              f"{task['needs']}: {task['command']} (token {task['token']}, until {task['lease_until']})" if task else "nothing to do"))
        return 0
    if args.command == "done":
        try:
            ok, why = finish(db, args.id, args.token, args.result, not args.failed)
        except ValueError as error:
            ok, why = False, str(error)
        print(json.dumps({"ok": ok, "why": why}) if args.json else why)
        return 0 if ok else 1
    if args.command == "retry":
        ok, why = retry(db, args.id, args.checked)
        print(why)
        return 0 if ok else 1
    if args.command == "export":
        for row in export(db):
            print(json.dumps(row, ensure_ascii=False))
        return 0
    if args.command == "restore":
        rows = [json.loads(line) for line in args.file.read_text(encoding="utf-8").splitlines() if line.strip()]
        print(json.dumps(restore(db, rows)))
        return 0
    expire(db)
    for row in db.execute("SELECT * FROM tasks" + (" WHERE state = ?" if args.state else "") + " ORDER BY created, id",
                          (args.state,) if args.state else ()):
        print(f"{row['id']}  {row['state']:<8} {row['needs']}  {row['repo']}@{row['commit_sha'][:12]}  {row['command'][:60]!r}"
              + (f"  {row['worker']}" if row["worker"] else "") + (f"  {row['result'][:80]!r}" if row["result"] else ""))
    return 0


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
