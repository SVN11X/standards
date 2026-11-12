# 007. Autonomous execution

Claude is the planner, not an automatic executor. It writes a work plan, the owner starts it by hand, and free or local executors do the work under the same gate as every other delegation. This chapter describes what the code does today. The history of the change is in `docs/improvement-plan.md` and `CHANGELOG.md`.

## What runs

```
Owner asks Claude (planner) for a plan  ->  work-plan.json
        |
        v
scripts/execute.py   check | run | status | resume | clean | report
        |  workplan.py: validate, order, find conflicts, batch, split
        |  orchestrate.py: route() and gate() per unit, health, fallbacks
        |  review.py: a different model reviews the diff
        v
one worktree per unit  ->  cherry-pick into branch execute/<plan_id>
```

Nothing is pushed, merged or opened as a pull request by the loop. Claude is listed in no `tasks:` entry of `settings/orchestration.yml`. `plan` and `web-direction` are `planner_tasks`: `route()` answers `planner`, and a plan with a unit of that type is invalid. `claude` stays only as a bench executor behind an explicit flag. An unknown task type is blocked until it is classified.

## Work plan

`schemas/work-plan.schema.json` is the contract. `python scripts/workplan.py validate PLAN.json` checks it and `batches PLAN.json` prints the groups of units that may run together. A plan holds `plan_id`, `goal`, optional `defaults` (`risk`, `test`), optional `budgets`, optional `final_regression` and `units`. A unit holds `id`, `title`, `task_type`, `goal`, `allowed` and `acceptance` (`test`, `criteria`), and may hold `read`, `new_files`, `protect`, `depends_on`, `risk` and `max_input_chars`.

`validate` returns a problem for each of these:

- a duplicate id, an unknown dependency, a unit that depends on itself or a cycle
- a `task_type` that is unknown or a planner type
- a protected file of `settings/orchestration.yml` in `allowed` or `new_files`
- no `acceptance.test` and no `defaults.test` when the type is not a tools type

Two units share a batch only when neither depends on the other, their expanded `allowed` files (globs expanded against `git ls-files`) are disjoint and neither touches a serial file (`package.json`, `package-lock.json`, `pyproject.toml`, `requirements*.txt`, `.standard.yml`). `execute.py run --parallel N` caps the batch size.

`split_unit` splits a unit by files, then by acceptance criteria, then with a proposal from a model passed in as a callable. Each candidate is validated with the plan rules and must stay inside the parent's files. The first valid one wins, else the result is `none`. The loop calls it for a unit whose input (task text plus the files it may touch) is larger than its `max_input_chars`. The parts run in order, each in its own worktree. The parent passes only when every part passed, and a failed part fails the parent while independent units go on. A part is split again only while `budgets.max_split_depth` allows it (default 1, so never), and nothing valid to split blocks the unit. A Colibri unit is blocked instead of split, because its parts could route to another model.

## Routing and proof

Risk decides who reviews, not which brand works. Yellow and red units need the owner's review and a proven model. Proof is policy, in `settings/orchestration.yml`:

- `proof:` maps each task type to the bench classes that qualify a model, for example `edit-large: [fix-multi]` and `refactor: [refactor-module]`.
- `size_tiers:` raises the class with the file count and never lowers it. Up to 5 files the task's own class counts, up to 12 files `fix-multi`, above that `refactor-module`.
- `proven_only:` lists the types where a model must have passed before it takes the task.

`route()` skips a model that is in cooldown and lists the next candidates in `fallbacks`.

## Evidence expiry and the `models` command

A bench row counts only while it is within `limits.bench_recheck_days` (30), was measured with the same OpenCode minor (agent classes) or the same GPU (local classes), and belongs to the current grader version. An expired model drops from authorized to tested, and `stale_notes` names what to run again.

```
python scripts/orchestrate.py models [--mode MODE] [--json]
```

prints one row per task type and model with the columns `discovered` (the analyzer coverage lists it), `tested` (fresh passing evidence and its class), `authorized` (cost, privacy and the task list allow it) and `expires` (the date the evidence stops counting, `no date` or `-`). The states are computed on each call and never stored by hand.

## Health and failover

`~/.standards/health.json` keeps one entry per `executor|model` with `code`, `at`, `until` and `count`. A failure starts a cooldown taken from `health.cooldown_s` in the policy: `rate_limit` 3600, `timeout` 900, `unavailable` 600, `auth` 86400 seconds. A success clears the entry. OpenCode and Colibri runs, Ollama calls and API calls all record it. A reply the model got wrong says nothing about its health and records nothing. A timeout kills the whole process tree of the executor, so a stuck agent does not hang the run.

A Colibri task never gets a fallback and never moves to another model. If Colibri is stopped the unit is blocked.

## Executor loop

```
python scripts/execute.py check PLAN.json [--repo DIR]
python scripts/execute.py run PLAN.json --reviewer MODEL [--repo DIR] [--parallel N]
python scripts/execute.py status PLAN.json
python scripts/execute.py resume PLAN.json --reviewer MODEL [--repo DIR]
python scripts/execute.py clean PLAN.json [--repo DIR]
python scripts/execute.py report PLAN.json
```

- `check` validates the plan, prints the batches and the route of each unit. It exits 1 on an invalid plan or when a unit has no coding agent.
- `run` starts from empty state. It creates the worktree `~/.standards/worktrees/execute-<plan_id>` on branch `execute/<plan_id>`, then runs batch by batch. Each unit runs through `delegate_opencode` in its own worktree, with its allowed files, protected files and test command. The unit passes only when the caller's checks pass (a change exists, scope, protected files, tests) and the review has no high finding. A passed unit is cherry-picked into the integration branch, so dependents build on it. A conflict aborts the pick and fails the unit.
- A unit tries its route and then its fallbacks, at most `budgets.max_attempts_per_unit` choices (default 1). A blocked result or a Colibri unit stops the tries.
- A unit that waits on one that did not pass is `skipped`. A failure or exception in one unit never stops the independent ones.
- Review is required. `--reviewer` names an Ollama model. Without it, or with the author's own model, the unit is blocked before any call. Findings that cite files or lines outside the diff are dropped. The reviewer must be a different model than the author.
- `resume` keeps the units that passed and runs the rest. `status` prints the saved state, kept in `~/.standards/executions/<plan_id>.json` and written after every unit.
- `clean` removes the unit worktrees, the integration worktree and the state file. Branches stay.
- `report` prints one consolidated JSON report built only from the saved state (`schemas/execution-report.schema.json`): per unit the status, commit, tests, review verdict and findings, retries, executor and model. A value the state does not hold is null.

Budgets of the plan, all checked before an attempt starts or a split is made. A unit stopped by a budget is `blocked` with the budget in its note, and independent units go on. A Colibri unit is never moved to another model by a budget.

- `max_attempts_per_unit`: choices tried for one unit (default 1).
- `max_total_attempts`: attempts across the whole run. Counters are per `run` or `resume` call and start at zero.
- `max_wall_s`: seconds since the call started. It is checked before each attempt and cannot interrupt one that is running, so the last attempt may end after the limit.
- `max_remote_sessions`: attempts whose channel is not local. A remote choice over the limit is skipped and a local fallback may still run. The channel comes from the model name and the policy only, so a remote Ollama host that the name does not show counts as local.
- `max_split_depth`: how deep a split may go (default 1). `max_units_after_split`: the cap on units after a split, parts counted and split parents not. A split over either limit blocks the unit.

`final_regression` is accepted by the schema and the loop does not run it yet.

## Bench classes for the loop

Three classes measure what the loop needs. A program grades each one and records the grader version.

- `refactor-module`: an 8 file fixture where `slugify` is copied into three modules and must move to `app/text.py`. Hidden tests check the behavior and, with `ast`, that the function is defined once. It is the proof class of `refactor`.
- `review-diff`: six synthetic diffs with one seeded defect each. A diff passes when a finding names the file and overlaps the defect lines, a finding over ten lines does not count, and no high finding sits elsewhere.
- `decompose`: three specs where a model returns work units. `workplan.validate` rejects a bad plan, then the grader checks the unit count, that every file to change is covered and that units able to run together share no file.

## Measured limit of Colibri

Colibri on the RTX 2060 (6 GiB) with `qwen3-coder-30b` prefills about 6 tokens per second (1009 tokens in 177 s, 3011 in 451 s). The 12000 token OpenCode prompt needs about 30 minutes, and `fix-bug` timed out at 600 s. Every model Colibri supports is a 27B or larger MoE. On this machine Colibri answers short prompts and is not a coding agent. A route that reaches it will time out, and the loop records the timeout and never replaces the model.

## Controls that did not change

`gate()` still decides cost mode, privacy and data use. Worktrees, the scope and protected checks, the UNTRUSTED fence around task material, the OpenCode permissions in `settings/opencode/opencode.json` and the run records in `~/.standards/runs` are the same. `scripts/adversarial.py` has seven `X.` scenarios for the loop: planner types, Claude as a unit executor, overlapping units, attempt budgets, invented review lines, the privacy class of worktrees and a stopped Colibri with no fallback.

## Not tested live

The loop and the bench classes were tested with fakes and fixtures. A pilot plan of three units and the three new bench classes have not run on the owner's machine with real models.
