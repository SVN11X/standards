# 010. Multi-agent Autopilot

One instruction in plain words becomes a validated plan, several agents work on it at once in separate worktrees, and one pull request comes out. `standards` does the coordination as a plain process. Claude is asked once, for the plan, and no Claude session stays open while the work runs.

This extends `docs/007-autonomous-execution.md` and `docs/009-natural-language-autopilot.md`. Every cost, privacy, review and merge rule of those documents still applies.

## Two levels

| Level | Who | What it does | What it never does |
| --- | --- | --- | --- |
| Planning | Claude Haiku, Sonnet or Opus through one `claude -p` call, or the local Ollama planner | Drafts the plan as JSON | Edits code, runs commands, reviews units, polls status |
| Execution | OpenCode with the free models the owner checked, local Ollama models through OpenCode, Colibri | Edits files in its own worktree | Chooses its test command, commits, pushes, merges |

Between the two sits code with no model: the plan contract, the scheduler, the resource pools, the checks, the integration queue and the monitor.

## Roles and what plays them

No role got a new model where a program or an existing tool already did the job.

| Role | Played by | Uses a model |
| --- | --- | --- |
| Planning agent | `scripts/planner.py` picks the tier, `scripts/plan_autopilot.py` asks for the draft | One call per plan |
| Repository explorer | `select_inventory` in `scripts/plan_autopilot.py` (a ranked file list), `agents/repo-scout.md` for a question inside Claude Code | No. The subagent runs on Haiku |
| Implementation agents | `orchestrate.delegate_opencode`, one worktree and branch per unit | Yes, free or local |
| Test agent | The caller runs the allowlisted test command in the unit's worktree | No |
| Review agent | `scripts/review.py`, a model other than the author | Yes, local |
| Security agent | Scope, protected files and `hooks/secret_scan.py` patterns on the lines a unit added | No |
| Integration agent | `Executor.take` (one cherry-pick at a time) and `publish` in `scripts/plan_autopilot.py` | No |
| Monitoring agent | The event log and state file of each plan, read by `scripts/control.py` | No |

## Choosing the planner

`scripts/planner.py` scores the request with a program: its length, how many folders it names (by a file path, by a file name only one tracked file has, or by the folder name), design words outside file paths, risk words and listed items. The size of the repository does not change the score. The score picks a tier of `planning.tiers` in `settings/orchestration.yml`.

| Tier | Model | Picked when |
| --- | --- | --- |
| light | Haiku | Score below `complexity.medium_at` (3) |
| medium | Sonnet | Score from 3 to 5 |
| advanced | Opus | Score of `complexity.advanced_at` (6) or more |

- A request never passes through all three. One tier drafts it.
- `--planner haiku`, `sonnet` or `local` is always honored. `--planner opus` on a request that scores lower falls to the tier of the score, unless `--opus-reason "..."` gives the reason, which is saved in the plan.
- A draft that is still invalid after its repair moves up one tier, once (`max_escalations`). That climb reaches Opus only when `opus_on_block` is true. It is false.
- One Opus planning call runs at a time (`opus_max_concurrent`, a lock file in `~/.standards`).
- Claude passes the same gate as every other request. A `work` folder needs the owner's consent, a `restricted` folder and the `local-only` and `free-strict` cost modes never reach Claude. Then the local Ollama planner drafts the plan.
- The call uses the Claude Code subscription. `ANTHROPIC_API_KEY` is removed from its environment, so a key that happens to be set is never billed. The cost the CLI prints is recorded as `reported_cost_usd`: the API price of the call, not a charge.

`python scripts/planner.py doctor` prints the installed Claude Code version and which optional flags it lists. Only listed flags are used.

## One contract for the plan

`scripts/plan_contract.py` is the single source for the prompt, the parser, the normalizer, the validator and the repair guard. The prompt lists the task types, the limits and the protected paths the validator enforces.

1. `parse` fixes syntax only: a code fence, text around the object, trailing commas. A reply that was cut off is a problem, never a guess.
2. `normalize` checks every field of every unit in one pass and reports all problems together.
3. Fixes that cannot widen anything are applied by the program, with no model call:

| Problem | Fix |
| --- | --- |
| `risk` is not green, yellow or red | A known word maps to its level (`low`, `medium`, `high`). Anything else becomes `red` |
| A string where a list belongs (`allowed`, `criteria`, `depends_on`) | A list of one |
| `criteria` under `acceptance`, empty entries, entries over 500 characters | Lifted, dropped, cut |
| `task_type` in another case or with `_` | Normalized. `fix` and `docs` map to `fix-test` and `docs-small` |
| Path with `\` or a leading `./`, a repeated path | Rewritten, dropped |
| `new_files` entry missing from `allowed` | Added. The scope of a unit is both lists, so no boundary moves |
| Missing `title` | First line of the goal |
| `depends_on` names itself or an unknown unit | Dropped |
| `depends_on` missing | The unit waits for the one before it |
| A cycle | Its edge to a later unit is dropped. Plan order wins |
| Keys the contract does not know (`test`, `budgets`) | Never copied. The test and budgets come from the program |

4. What is left goes to a model once, in one message that names every problem. Haiku repairs a Claude draft, the local model repairs its own. Opus never repairs a structure.
5. `guard` refuses the repaired draft when a field that was not named changed, a path was added or the unit count changed.
6. An unsafe path (`..`, absolute, `.git`, hidden, a glob), more than 8 units or more than 5 files per unit refuses the draft before any repair.
7. A plan that is still invalid runs nothing.

`python scripts/plan_contract.py check DRAFT.json` prints the fixes and the remaining problems of a draft.

## Scheduling

`scripts/scheduler.py` keeps a ready queue instead of batches.

- A unit starts when its own dependencies passed, a slot of its pool is free and no running unit shares a file with it. It does not wait for the rest of a batch.
- A unit whose dependency did not pass is skipped. Independent units go on.
- `concurrency` in `settings/orchestration.yml` holds the limits: `max_parallel` (3), `pools.remote_free` (2), `pools.local` (1) and `tests` (1). `--parallel N` changes the first for one run.
- A pool loses one slot when a unit hits a rate limit and gets it back after `grow_after` units passed in a row.
- A ready unit that gets no slot within `stall_s` is blocked with that reason.

## This machine

The limits fit a 4 core CPU, 64 GiB of RAM and one 6 GiB graphics card.

- One local model at a time (`pools.local: 1`), so two models never compete for the card.
- Before a local unit starts, `scripts/resources.py` reads the free graphics memory. Below `local_min_free_vram_mib`, and unless Ollama already holds that model, the unit waits.
- A waiting unit moves to a free remote model only when `route()` listed one as a fallback. `route()` lists only what passed the cost and privacy gate, and `delegate_opencode` asks the gate again. Work and restricted code stay local and wait.
- One test suite at a time (`tests: 1`), so a heavy suite does not fight a local model for the CPU.
- A Colibri unit never moves to another model and nothing is downloaded.

## Worktrees, conflicts and recovery

- Each unit works on its own branch and worktree. The integration branch `execute/<plan_id>` takes one cherry-pick at a time.
- Only the files the agent changed are committed. Files the tests leave behind are not.
- A cherry-pick conflict fails that unit, is counted in `metrics.collisions` and keeps its branch and worktree.
- State is saved after every transition. A unit that was reviewed and committed is saved as `reviewed` before integration, so a restart integrates it without running the agent again. A unit left `running` is run again and its old worktree is listed under `orphans`.
- `execute.py clean` removes a worktree only when it is clean and its commit is integrated, and never with `--force`. Anything else is kept and named. No `reset --hard`, `git clean` or force push exists in this code.
- `execute.py pause` stops new assignments and lets running units end. `unpause` and `resume` continue. `cancel --unit ID` stops one unit and keeps its worktree.

## Pull request and checks

`publish --publish pr` pushes the integration branch and opens one pull request with the sections of the pull request contract. Then it follows the checks with `gh pr checks`.

- A failed check gets up to `budgets.max_ci_fix_attempts` (1) fixing units. A fixing unit may change only the files the plan declared, at the highest risk of the plan, and reads the failed log as untrusted data. Its commit goes to the same pull request.
- Checks that still fail leave the pull request open and unmerged.
- `--publish auto-merge` is GitHub's own auto-merge. It needs green units, a `pass` review of each, strict required checks and a base branch that did not move. It never uses `--admin`.
- `--no-watch-ci` returns right after the pull request exists.

## Standards AI Control

`python scripts/control.py serve` has an Autopilot view.

- Shown: active agents, the model and provider of each unit, its state, elapsed time, what it depends on and waits on, pool limits, done and pending work, metrics, the pull request with its checks, and what needs the owner.
- Controls: create a plan from text with a chosen planner, start or resume a plan, start and open a pull request, pause and allow new assignments, cancel a unit. Auto-merge is not offered in the page.
- Logs and events are folded by default.
- A unit counts as done only when its state says `passed`. An agent that went quiet is still `running`.
- Reading the page asks no model. It reads `~/.standards/plans`, `~/.standards/executions/<plan_id>.json` and `<plan_id>.events.jsonl`.

## Commands on Windows PowerShell

Run them in the target repository, on a clean `main`.

```powershell
python C:\my_drive\Portafolio\standards\scripts\plan_autopilot.py plan --repo . --instruction "Add a median function to mathutil.py with a test"
```

```powershell
python C:\my_drive\Portafolio\standards\scripts\plan_autopilot.py go --repo . --instruction "Add a median function to mathutil.py with a test" --publish pr --detach
```

```powershell
python C:\my_drive\Portafolio\standards\scripts\execute.py status "$HOME\.standards\plans\auto-EXAMPLE.json"
```

```powershell
python C:\my_drive\Portafolio\standards\scripts\plan_autopilot.py run "$HOME\.standards\plans\auto-EXAMPLE.json" --repo . --publish pr
```

`go --detach` returns at once with the process id and the log path. The same request on the same commit reuses the saved plan and asks no planner again.

## What is recorded

Per unit, in the state and in `execute.py report`: model, executor, channel, status, attempts, failure code, seconds, agent seconds, test seconds, seconds waiting for the test slot, checks, review and commit.

Per plan, under `metrics`: total seconds, units at once (limit and peak), pool peaks and changes, seconds waiting for slots, integration seconds, conflicts, retries, and RAM and graphics memory before and after.

Per planning call, in the plan and in `~/.standards/telemetry.jsonl`: model, seconds, tokens in and out, tokens per second and the reported cost.

A value nobody reported is null. Prefill time and tokens of a coding agent are not reported by OpenCode, so they are not recorded.

## Measured

Both runs were made on 2026-11-15 in a Linux cloud container with 4 CPUs, Python 3.13 and Claude Code 2.1.325. Repeat them on your machine with the commands shown.

### Scheduler, sequential against parallel

`python scripts/bench_parallel.py --units 6 --latency 2.0 --test-s 0.3 --levels 1 2 3 4`

Six units, five independent and one that waits for the first. The agents are simulated: a process that waits 2 s and edits its file. The worktrees, checks, test command, review step and integration are the real code path.

| Units at once | Total s | Speedup | Failed | Conflicts | Retries | Waiting for the test slot s |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 15.37 | 1.00 | 0 | 0 | 0 | 0.00 |
| 2 | 8.05 | 1.91 | 0 | 0 | 0 | 0.31 |
| 3 | 5.86 | 2.62 | 0 | 0 | 0 | 0.95 |
| 4 | 5.51 | 2.79 | 0 | 0 | 0 | 1.92 |

The fourth slot adds little: the time waiting for the single test slot doubles. This measures the scheduler for a fixed agent latency. It says nothing about the speed of a model, a provider's quota or a real graphics card.

### End to end with a real planner

1. `plan_autopilot.py plan` on a small repository with two modules, two tests and one document. `auto` scored the request light and made one Haiku call: 8.05 s, 836 output tokens, 103.85 tokens per second, no fix and no repair needed. The plan had three units: two independent code units and one documentation unit that depends on both.
2. `bench_parallel.py --plan PLAN.json --repo DIR --levels 1 2` ran that plan with simulated agents of 2 s.

| Units at once | Total s | Speedup | Passed | Conflicts |
| --- | --- | --- | --- | --- |
| 1 | 6.93 | 1.00 | 3 of 3 | 0 |
| 2 | 4.74 | 1.46 | 3 of 3 | 0 |

The first parallel run of this plan failed one unit with a cherry-pick conflict: both units had committed the same `__pycache__` file their tests created. `delegate_opencode` now commits only the files the agent changed, and a test keeps it that way.

A second request, on a clone of this repository, named files in four folders and a schema. It scored medium and made one Sonnet call: 14.05 s, 1387 output tokens, 98.72 tokens per second, four units with their dependencies, no fix and no repair needed. That run showed two defects, both fixed with a test: every word of a request that appeared in any path counted its folder, so a large repository raised every score, and the input tokens left out the cached part of the prompt.

### Dashboard in a browser

`node tests/web/control.test.mjs` starts the real server on seeded state and drives the Autopilot view in Chromium through Playwright. Twelve checks pass: units with state, model, provider and dependencies, active agents, the pull request and its checks, text shown as text, folded events, pause and allow, cancel, a plan and a run started from the page, the page token, every view without a script error and no sideways scroll at 360 px. `verify.py` runs it as `S.control-page` where Node and Playwright exist.

Its first run found three defects, now fixed: the page looked for `plan_autopilot.py` inside the repository a plan changes, an opened log stopped the view from following the state, and the plan table made the page scroll sideways on a narrow screen.

## Not tested here

- Real coding agents. The container has no OpenCode, Ollama or Colibri, so units ran with simulated agents. A run with the owner's free and local models on Windows is still needed.
- The real `gh` calls of `publish`. Pull request creation, check reading and the fixing unit are tested against a fake `gh`.
- Windows. Process groups, `taskkill` and `.cmd` launchers follow the existing code paths but were run on Linux only.
- An Opus call. Its selection is tested, and only Haiku and Sonnet were called.
- The dashboard on a live plan. The browser test drives it on seeded state, and its start buttons were followed only to a refused run.

## Claude Code features looked at

| Feature | Used | Why |
| --- | --- | --- |
| `claude -p` with `--model` and `--output-format json` | Yes | One call, structured reply with usage, ends on its own |
| `--tools ""`, `--no-session-persistence` | When the installed version lists them | The planner needs no tool and leaves no session |
| `--max-turns`, `--max-budget-usd`, `--json-schema` | Only `--max-turns`, when listed | Version 2.1.325 lists the last two. A subscription call has no budget to cap, and the contract already validates the JSON |
| Custom subagents | `agents/repo-scout.md` on Haiku, next to the existing ones | For a question inside a Claude Code session. Autopilot does not need it |
| Background subagents and sessions (`--bg`) | No | The executor loop is already its own process |
| Agent Teams | No | Experimental, and it would keep Claude sessions open as workers |

## Checks

```powershell
python -m unittest discover -s tests
```

```powershell
python scripts\verify.py --level standard
```
