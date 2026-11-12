# Local benchmark controls and pending decisions

This patch extends Standards AI Control without replacing the analyzer, executor,
model registry or privacy gate. It does **not** unblock all 11 legacy decisions
and it does not turn the dashboard into an unrestricted command shell.

## Safe capabilities

- Dashboard **Operations** view: inspect 11 documented blockers grouped into
  technical, human, credential, or review. Classification is advisory only;
  changing a blocker to "done" still requires evidence and plan maintenance.
- Preview three new benches through the existing `scripts/analyze.py plan`.
- Explicitly start one local-only benchmark batch through the existing analyzer
  (`refactor-module`, `review-diff`, `decompose`). The model is restricted to
  `qwen3.5-9b-ctx16k`; runs are bounded to 2 hours and 3 repetitions per task.
- Cancel the job **started by this dashboard process** (not arbitrary processes).
- View the captured command output, task, model, status and exit code.

The control server continues to bind only to 127.0.0.1. Mutating endpoints
require an unpredictable per-session token, matching browser origin, loopback
Host, JSON content type and an explicit click/confirmation. Only whitelisted
commands are accepted; there is no shell. Running a local bench never installs
models, uses remote inference, touches keys or changes approvals.

## Windows use

```powershell
cd C:\my_drive\Portafolio\standards
python -m unittest discover -s tests -p "test_control_jobs.py"
python -m unittest discover -s tests -p "test_next_actions.py"
python scripts\verify.py --level standard
python scripts\control.py serve --repo .
```

Open `http://127.0.0.1:8765` and select **Operations**.
The first operation is **Plan only**, which does not execute benchmarks. Run
benchmarks only after checking the GPU is free and the estimated time is
acceptable. Prior benchmarks retain their existing history and resume logic;
this patch never calls `--restart`.

## Explicit limitations

- Token and throughput values still depend on each engine's real telemetry.
- Other MCP providers, publication, cloud keys, vision validation and consent
  decisions are **not** automatically approved by this patch.
- The cancel action requests termination of its direct child process. On Windows
  subprocess descendants may continue; use the existing executor process-tree
  cleanup if a process survives.
- Work-plan execution remains governed by `execute.py` and existing Git
  approvals; this patch does not auto-merge, push or erase branches/worktrees.
- Real hardware/integration verification must be run on the owner's Windows
  computer; offline unit tests cover the new safe-control behavior.
