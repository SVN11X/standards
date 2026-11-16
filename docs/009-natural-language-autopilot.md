# 009. Natural language autopilot and guarded GitHub publication

This is an additive extension to `workplan.py` and `execute.py`. It does not change the existing permission policy, existing task/benchmark evidence, default cost mode or repository protections.

## What it does

- `plan`: turns an instruction into an exact-file, policy-validated `schemas/work-plan.schema.json`. The planner is the smallest one that is enough: Claude Haiku, Sonnet or Opus through one `claude -p` call, or **local Ollama** (default `qwen3.5:9b`) when the cost mode or the privacy class keeps Claude out, or with `--planner local`. Saves the plan **outside Git** in `~/.standards/plans/`. No code edits. See `docs/010-multiagent-autopilot.md`.
- `go`: creates the plan, checks routing and runs the units through the **existing** `execute.py` (isolated worktrees, checks, second-model review, state/resume). Independent units run at the same time, up to `concurrency.max_parallel`. `--detach` leaves the run in its own process. Publishing is optional.
- `run`: runs or resumes a saved plan.
- `publish`: checks that all original plan units passed, that the integration worktree is clean and has changed only approved files, runs the predefined final regression, pushes the integration branch, creates or reuses a GitHub PR and follows its checks. A failed check gets one fixing unit inside the plan's files (`budgets.max_ci_fix_attempts`).
- `--publish auto-merge`: additionally asks GitHub to merge the PR **once its required checks and reviews pass**. It uses `gh pr merge --auto --squash --match-head-commit`. Never uses `--admin`, `--force`, deletes a branch, or ignores branch protection.

## On Windows (PowerShell)

From the target Git repository, with a clean working tree:

```powershell
# Inspect the generated JSON first (recommended)
python C:\my_drive\Portafolio\standards\scripts\plan_autopilot.py plan --repo . --instruction "Corrige la validación de fechas en src/dates.py y agrega pruebas"

# Single-step autonomous execution with local planning, using the existing routing policies
python C:\my_drive\Portafolio\standards\scripts\plan_autopilot.py go --repo . --instruction "Corrige la validación de fechas en src/dates.py y agrega pruebas" --reviewer qwen2.5:7b --publish pr

# Once execution is complete, publish an existing plan; GitHub-native auto-merge is explicit
python C:\my_drive\Portafolio\standards\scripts\plan_autopilot.py publish "$HOME\.standards\plans\auto-EXAMPLE.json" --repo . --publish auto-merge
```

`go` with no `--publish` changes **only local worktrees**; it doesn't push anything. `go --publish pr` creates a PR but leaves merging to the owner. `go --publish auto-merge` attempts both after all checks have passed. A reviewer with compatible capabilities must be installed, and the underlying route must authorize the executors. Do not use the same author/reviewer model.

Plans intentionally contain **exact filenames**, not globs or arbitrary shell commands. A model cannot choose its own test command. Supported regression commands (`--test`) are limited to:

```
python -m unittest discover -s tests
python -m pytest -q
python scripts/verify.py --level standard
npm test
go test ./...
cargo test --quiet
```

For another test runner, extend the trusted command catalog with tests in a separate PR. A complex request involving many unrelated files may be refused so it can be split. Security-sensitive requests are automatically classified red and cannot auto-merge.

## Auto-merge prerequisites

GitHub must have these conditions before a merge can be scheduled. If protection cannot be verified, the command may still create the PR, but will stop **without enabling auto-merge**:

1. Authenticated `gh` with write permission to the repository.
2. Base branch `main` with **required status checks**: a ruleset with a required status checks rule (what `settings/ruleset-main.json` applies), or classic branch protection with `strict=true`. The command refuses to weaken or create protection itself. This applies to GitHub's own auto-merge, used when checks are not followed.
3. GitHub repository setting **Allow auto-merge** enabled, or compatible merge-queue behavior.
4. Green-risk units, each with an independent `pass` review; no failed, blocked or incomplete unit; final regression passing in the integration worktree.
5. Existing **Claude Code/Git/standards permissions** must permit the actual push/PR/merge operations. This script does not silently change those rules. If `gh pr merge` is denied, run the approved operation yourself; it will not override a denial. With the owner's setting below, merges go through `scripts/merge_when_green.py`, which the guard hook lets through.

GitHub's auto-merge may remain pending until required reviews and checks finish. The CLI returning success **does not prove the PR is already merged**; check its final state with `gh pr view <number>`.

If neither a ruleset nor classic protection with required checks can be read, the command fails closed for the merge step and leaves the PR open for the owner. Use `--publish pr` to publish without requesting a merge.

## Merging without the owner

The owner decides once, on their machine:

```
python scripts/orchestrate.py consent --merge when-green
```

From then on an agent merges with `python scripts/merge_when_green.py <PR> --wait 1800`. It merges only when the pull request is open, has no conflict, changes no workflow, deploy or secret file, and every check on its head passed. The merge names that head with `--match-head-commit`, so a later push cannot slip in, and never uses `--admin`, so every rule of the repository still applies. A direct `gh pr merge` is answered by the guard hook with that command. `plan_autopilot.py --publish pr` merges the same way once the checks it follows pass. `consent --merge ask` turns it off. Deploys, secrets and history rewrites always wait for the owner.

## Important limitations

- The model drafts a plan; its quality is not guaranteed. `workplan.validate`, path gates, security classification and `execute.check` reject invalid/unsafe/unauthorized requests. A green classification is **not** a guarantee that a task is safe.
- A local Ollama plan does not depend on Claude, and a Claude plan needs Claude for one call only. Changes are implemented only by the existing authenticated OpenCode/Colibri routes. Colibri can be too slow for large prompts, and the router's previous evidence continues to apply.
- `execute.py` can return a failed unit, or a blocked route: publishing will then stop without pushing anything. A plan may require attention to acceptance tests or scope.
- Publication requires the target checkout to be on `main`, at the pinned planning commit and clean. Planning and local execution can run on another clean branch, but automatic publication is intentionally blocked there. If the branch moves, generate a new plan rather than resetting files or forcing a push.
- The final regression is deliberately run once again **on the integrated branch** before publishing. Earlier passing tests per unit do not establish the final combined tree is correct.
- Standards AI Control has an Autopilot view that creates a plan from text, starts or resumes it, pauses assignments and cancels a unit. Each request needs the page token and a loopback origin. Auto-merge is not offered there.
- Offline unit tests mock GitHub/Ollama; a live end-to-end coding and merge test on the user's Windows computer is still required.

## Checks

```powershell
python -m unittest tests.test_autopilot
python -m unittest discover -s tests
python scripts\verify.py --level standard
```

If the repository uses other `tests/` layout, invoke `python -m unittest discover -s tests -p test_autopilot.py`.
