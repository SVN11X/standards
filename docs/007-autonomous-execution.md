# 007. Autonomous execution

Claude stops being an automatic executor. It writes a work plan, the owner invokes it by hand, and free or local executors do the work under the existing gate. This document is the design and the contracts. The implementation order is in `docs/improvement-plan.md`.

## Goal

Claude acts as an exceptional architect, not as a regular worker. The orchestrator never routes implement, review, refactor or split work to Claude. Free and local executors (OpenCode with free models, Ollama, free API providers, programs without AI) do the work. One script, `scripts/execute.py`, takes a validated plan, splits it, routes each unit to a model whose evidence is current, classifies failures, switches candidates, requests cross-model review, runs the regression and hands back one report. If no valid route exists, the unit stays BLOCKED with the reason. Nothing is pushed, merged or opened as a PR by the loop.

## Why Claude still got work (audit)

Evidence from `~/.standards/bench.jsonl` (139 runs, report `model-analysis-20261111-1041.md`, RTX 2060 6 GB, OpenCode 1.19.5):

- `opencode/glm-5.3-flash-free`: fix-bug 6/6 (p50 18 s), fix-multi 3/3 (25 s), docs-small 3/3. Keeps nothing, does not train.
- `opencode/deepseek-v4.1-flash-free`: fix-bug 5/6, fix-multi 2/3. `mimo-v2.6-flash-free`: passes but may train, so private code never goes there.
- `ollama qwen3.5:4b`: passes classify, extract, summarize, tool-call, vision, web-subprofile, all local. design-judge-sample 0/3.
- No provider key is set. OpenRouter has one classify run.

Root causes, with locations:

1. `settings/orchestration.yml:57-62`: `edit-large` and `refactor` list `claude` first. `plan`, `review-deep`, `web-direction` and `unknown_task` list only `claude`. Under the default mode `existing-subscription`, Claude wins before OpenCode is even tried.
2. `scripts/orchestrate.py:826-828` (`route`): risk yellow or red moves `claude` to the front. This contradicts the policy text that risk decides who reviews, not which brand works.
3. `scripts/orchestrate.py:833` (`route`): `needs_proof = proven and candidate != "claude"`. Claude is the only unproven candidate, so it is the silent fallback whenever proof is missing or `files > edit_small_max_files`.
4. No decomposition. A task that is too large is either `blocked` or Claude's.
5. Evidence never expires in routing. `bench_recheck_days` is only a warning in `stale_notes` (`orchestrate.py:897-905`). `measured_models` (`:605`) counts runs of any age and any OpenCode version.
6. Tier gap. `fix-multi` is one 3-file synthetic fixture. Passing it currently qualifies a model for `refactor` (`ROUTE_BENCH`, `:62-65`). A model that only passed simple tests must not get complex refactors.
7. `delegate_opencode` (`:985-987`) takes `models[0]` when no model is given, ignoring the bench. No failure classification, no retry, no switch to another candidate, no cooldown after a rate limit (only a boolean `rate_limited`).
8. No independent review step, no plan contract, no closed loop, no consolidated report across tasks.
9. Text that keeps Claude as worker: `skills/repo-improve/SKILL.md:67` ("Mark the items that need judgment yellow or red, so they stay with Claude"), the `docs/005` flow chart ("Claude fixes it"), `docs/006:183`, `docs/improvement-plan.md:16`.
10. Tests that encode the old behavior: `tests/test_scripts.py` `test_risk_and_size_keep_it_with_claude` (:124), `test_unknown_task_never_reaches_claude_in_a_free_mode` (:154), `test_planner_only_tasks_are_blocked_without_a_subscription` (:161), `test_risk_needs_the_owner_and_a_proven_model_not_a_brand` (:190), `test_private_needs_explicit_consent` (:129).

What works and stays: `gate()`/`explain()` (cost mode, privacy, owner check, catalog, data use), worktree delegation with scope, protected and test checks, run records in `~/.standards/runs`, bench history with grader versions, `analyze.py` discovery and night runs, provider transport, `adversarial.py`, OpenCode permissions in `settings/opencode/opencode.json`.

## Architecture and responsibilities

```
Owner ──asks──> Claude Opus (planner, manual only)
                   │ writes work-plan.json (schema-validated)
                   ▼
           scripts/execute.py  (orchestrator loop, no AI)
   ┌───────────────┼───────────────────────────────┐
   │ workplan.py   │ orchestrate.route() + gate()  │ review.py
   │ DAG, split,   │ tiers, fresh evidence,        │ cross-model review,
   │ conflicts     │ health, fallbacks             │ JSON findings
   ▼               ▼                               ▼
 tools (tests, lint, verify.py)   OpenCode (code)   Ollama (classify, summarize,
                                  free API models    split proposals, local review)
                   │
                   ▼
   integration branch work/<plan-id>  ──>  final regression  ──>  report.md + report.json
   (never pushed, never merged by the loop)
```

| Role | Does | Never does |
| --- | --- | --- |
| Claude Opus | Writes `work-plan.json` and architecture decisions when the owner asks. Rewrites a plan that came back BLOCKED. | Gets routed any task. Acts as fallback. |
| Orchestrator (`execute.py` + `orchestrate.py`) | Validates the plan, routes, authorizes via `gate()`, splits, schedules, retries, switches candidates, integrates, reports. | Uses a model to decide privacy or cost. Pushes, merges, uses keys not in the environment. |
| OpenCode | Code units: edit, fix, refactor, tests, docs. | Touches protected files or files outside the unit. |
| Ollama | Classify, summarize, extract, failure triage, split proposals, local review for work and restricted code. | Code edits (no bench class for that yet). |
| Free API providers | Review and short text tasks after they pass the class, within quota. | Anything in work or restricted folders. |
| Tools | Tests, lint, `standard.py selftest`, `verify.py`, diff, scope and hash checks, deterministic splits. | n/a |

## Routing rules

- `claude` appears in no `tasks:` list. New key `planner_tasks: [plan, web-direction]`. `route()` answers `executor: planner` with `reasons: ["planner work: the owner asks Claude directly"]`. It is never auto-run. `execute.py` stops a unit of a planner type as BLOCKED.
- `unknown_task: []`. An unknown type is `blocked` with "classify the task type or ask the planner".
- Risk yellow or red: `review: owner`, `needs: proven` at the unit's tier. No reordering.
- `executors.claude` stays only for `bench` comparisons, behind an explicit `--executor claude` flag.

## Capability tiers and proof

`ROUTE_BENCH` and `LARGE_BENCH` move from `orchestrate.py` into `orchestration.yml` as `proof:`, so qualification is policy, not code:

```yaml
proof:
  edit-small: [fix-bug]
  fix-test: [fix-bug]
  fix-check: [fix-bug]
  docs-small: [docs-small, fix-bug]
  edit-large: [fix-multi]
  refactor: [refactor-module]        # new class. fix-multi alone never qualifies
  review-deep: [review-diff]         # new class
  decompose: [decompose]             # new class
  classify: [classify]
  ...                                # the rest as today
size_tiers:                          # file count raises the class, never lowers it
  - {max_files: 5, classes: null}    # the task's own class
  - {max_files: 12, classes: [fix-multi]}
  - {max_files: 999, classes: [refactor-module]}
```

A unit above the largest tier any authorized model passed is split before it is routed.

## Model lifecycle

Three states, computed (never stored by hand), printed by `orchestrate.py models`:

- discovered: listed by Ollama, `opencode models` or a provider adapter (existing `analyze.coverage`).
- tested: has current-grader bench rows for a class.
- authorized for task type T: passes `gate()` now, owner check fresh, and for each class in `proof[T]` has at least `bench_min_runs` runs with pass rate at least `bench_min_pass_rate`, all within `bench_recheck_days`, on the same OpenCode major.minor (agent classes) and the same GPU name (local classes), and p90 at most `limits.max_p90_s[T]` when set.

Expired evidence drops the model to tested. `stale_notes` keeps naming what to re-run. Re-evaluation: the existing night run (`analyze.py run`) re-measures every model whose evidence ends within 7 days (new `analysis.refresh_before_days: 7`).

## Health and failover

`~/.standards/health.json`, written with an atomic replace (reuse `write_json`):

```json
{"opencode/glm-5.3-flash-free": {"consecutive_failures": 0, "cooldown_until": null, "last_code": null}}
```

Failure codes, set by the caller from evidence only, with the action:

| Code | Detected by | Action |
| --- | --- | --- |
| `rate-limit` | `RATE_LIMIT` regex, provider error kind | cooldown `limits.cooldown_rate_limit_s` (3600), next candidate |
| `timeout` | `run()["timeout"]` | retry once with same model, then next candidate |
| `executor-error` | nonzero exit, no change | next candidate |
| `no-change` | `changed_something` FAIL | retry once with failure note, then split |
| `scope` | `inside_scope` FAIL | next candidate, never retry same model on the same unit |
| `protected` | `protected_untouched` FAIL | next candidate, counts double toward cooldown |
| `tests` | tests FAIL | fix loop (see closing loop) |
| `review` | review high finding | one fix round with the findings |
| `context` | input over the executor's limit | split |
| `gate` | `gate()` refused | next candidate, never retried in this run |
| `no-route` | no candidate left | split if splittable, else BLOCKED |

Three consecutive failures (any code) give a cooldown of `limits.cooldown_failures_s` (1800). `route()` skips models in cooldown and returns `fallbacks`: the ordered list of other authorized candidates with their models.

## Decomposition

`workplan.split_unit(unit, reason)` tries, in order, and validates every result with the same schema and conflict checks:

1. Deterministic by files: one subunit per allowed file or file group, ordered by an import graph built with `ast` for Python and a plain regex for JS/TS imports. The unit's test command stays the acceptance of the last subunit. Earlier subunits get `python -m py_compile` or the repo lint as acceptance.
2. By acceptance criteria: one subunit per criterion when the plan lists several.
3. Model proposal: `route("decompose")` (Ollama or OpenCode that passed the `decompose` class). The proposal is data. It must reference only files inside the parent's `allowed`, form an acyclic graph, and cover every parent file. Otherwise it is discarded.

Limits: `budgets.max_split_depth` (2), at most `budgets.max_units_after_split` (12) per parent. A unit that cannot be split further and has no route is BLOCKED with the attempts list.

## Parallel execution

Two units run in parallel only when all hold: no dependency path between them, expanded `allowed` file sets (globs expanded against `git ls-files` plus declared new files) are disjoint, neither touches a lockfile or shared config listed in `limits.serial_files` (`package.json`, `package-lock.json`, `pyproject.toml`, `requirements*.txt`, `.standard.yml`), and resource slots are free: `ollama: 1` (one model on a 6 GB card), `opencode: limits.parallel_opencode` (2), per provider its `requests_per_minute`. Integration is always serial in topological order.

## Contracts

All JSON, all validated with `jsonschema` if installed, else with the same minimal validator `verify.py` already uses for `verify-report.schema.json` (check and reuse it).

### 1. Work plan (Claude to orchestrator): `schemas/work-plan.schema.json`

```json
{
  "plan_id": "2026-11-12-routing",
  "repo": ".",
  "base": "<commit sha or branch>",
  "goal": "one sentence",
  "defaults": {"risk": "green", "test": "python -m unittest discover -s tests"},
  "budgets": {"max_attempts_per_unit": 3, "max_total_attempts": 40, "max_wall_s": 14400,
              "max_remote_sessions": 30, "max_split_depth": 2, "max_units_after_split": 12},
  "final_regression": ["python scripts/standard.py selftest", "python -m unittest discover -s tests"],
  "units": [{
    "id": "u1",
    "title": "short",
    "task_type": "edit-small",
    "goal": "what must be true after",
    "read": ["scripts/orchestrate.py#route"],
    "allowed": ["scripts/orchestrate.py", "tests/test_scripts.py"],
    "new_files": [],
    "protect": [],
    "acceptance": {"test": "python -m unittest tests.test_scripts.Route", "criteria": ["route never returns claude"]},
    "depends_on": [],
    "risk": "green",
    "max_input_chars": 20000
  }]
}
```

Rules checked by `workplan.validate`: unique ids, acyclic `depends_on`, every `task_type` known and not a planner type, `allowed` non-empty, no protected file from `orchestration.yml` in `allowed`, `acceptance.test` present unless `task_type` is a tools type.

### 2. Task packet (orchestrator to executor)

Extend `build_packet` (`orchestrate.py:930`) with `criteria` and `previous_failure` (failure code, test tail, review findings), both inside the existing UNTRUSTED fence when they contain executor or test output.

### 3. Unit record

Existing run record plus `unit_id`, `plan_id`, `attempt`, `failure_code`, `parent_unit` (after a split). States extend `STATES` with `split` and `reviewed`.

### 4. Review request and response: `review.py`

Input: diff of the unit (capped at `limits.review_max_diff_chars`, 30000, else split review per file), unit goal and criteria. Output the reviewer must return:

```json
{"verdict": "pass|changes", "findings": [{"severity": "high|medium|low", "file": "x.py", "line": 12, "claim": "..."}]}
```

Validation: each finding's file and line must exist in the diff's new side, else dropped and counted. Reviewer must be a different model from the executor, and a different provider when one is authorized. Review never proves correctness. Only tests and checks do. A high finding triggers one fix round.

### 5. Consolidated report: `schemas/execution-report.schema.json`

`~/.standards/plans/<plan_id>/report.json` and `report.md`: plan id, base, integration branch, per unit (state, executor, model, attempts with failure codes, review verdict, tests), splits made, models put in cooldown, budgets used against limits, final regression results, BLOCKED list with the reason and what the owner can do, and what was not tested. A copy of `report.md` is the only output printed at the end.

## Autonomous closing loop (`scripts/execute.py`)

Commands: `check <plan.json>`, `run <plan.json> [--mode] [--parallel N]`, `status <plan_id>`, `resume <plan_id>`, `report <plan_id>`, `clean <plan_id>` (removes worktrees of that plan only).

Per run:

1. Load and validate the plan. Refuse a dirty base. Create `work/<plan_id>` branch from `base` in its own worktree under `~/.standards/worktrees`.
2. Build the DAG. Mark planner-type units BLOCKED.
3. Loop while ready units exist and budgets allow:
   1. Route the unit with its tier (file count, risk). `no-route` goes to split.
   2. Delegate (`delegate_opencode` from the integration branch head, or `delegate_ollama` for text units).
   3. Classify the outcome into a failure code. Update health.
   4. `tests` failure: next attempt on the same model with the test tail, then the next candidate, then split. At most `max_attempts_per_unit` per unit and per subunit.
   5. On verified: review (green: optional when no reviewer is authorized, recorded as `not-run` with the reason. Yellow and red: owner review always, plus model review when available).
   6. Integrate: cherry-pick onto `work/<plan_id>`, run the unit's test and `limits.integration_check` there. A conflict or failure reverts the cherry-pick and the unit goes back with code `integration`.
4. Final regression: every `final_regression` command on `work/<plan_id>`. A failure: triage with Ollama (summarize the failure, suggest the unit), one targeted fix unit, then report.
5. Write the report. Never push, never merge, never open a PR. Print the branch and the command the owner can run.

Budgets enforced: attempts per unit, total attempts, wall clock, remote sessions (counted per OpenCode run and per API request using `analysis.requests_per_agent_run`), provider daily limits from `settings/providers.yml`. Hitting any budget stops scheduling new units, finishes running ones and writes the report with `stopped: <budget>`. State is written after each step so `resume` continues.

## Risks and recovery

| Risk | Control |
| --- | --- |
| Free model quality on real code is lower than on synthetic fixtures | Tiers, hidden tests, review, small units, split on failure, owner review for yellow and red |
| Free offer ends or a model is withdrawn | `review_by`, owner checks, `opencode models` retired detection, cooldown, fallbacks |
| Rate limits cascade | Cooldown per model, provider budgets, `max_remote_sessions`, stop with report |
| Infinite retry or split loops | Per-unit and total attempts, split depth, wall clock |
| Parallel units corrupt each other | Disjoint expanded file sets, serial files, separate worktrees, serial integration with tests after each |
| Prompt injection via repo files or test output | Existing UNTRUSTED fence, scope and protected checks, executor summary never counts |
| Stale or biased evidence | Expiry by age, OpenCode version and GPU, grader versions, night refresh |
| Small context of local models | `max_input_chars`, `context` failure code leads to split |
| Interrupted run | State after every step, `resume`, `clean` |
| Executor edits the orchestrator itself (this repo) | Work happens in worktrees on `delegate/*` and `work/*`. The running `execute.py` is the one on `main`, not the one being edited |

Rollback: every item is one commit on its own branch. The loop never touches `main`. Deleting `work/<plan_id>` and running `execute.py clean` removes a run completely.

## Acceptance criteria

- `python scripts/orchestrate.py route --all --repo .` lists no `claude`. `plan` and `web-direction` show `planner`.
- With the owner's current evidence, `edit-large` routes to `glm-5.3-flash-free`, and `refactor` is `blocked` until a model passes `refactor-module`.
- `execute.py run` on a fixture plan with 4 units (2 parallel, 1 that fails and is split, 1 yellow) ends with one report, the yellow unit marked for owner review, no push, and no Claude call.
- All unit tests, `standard.py selftest`, and the new adversarial scenarios pass.
- Nothing in `local.yml`, privacy classes, cost modes or OpenCode permissions became looser (diff of `settings/` reviewed).
