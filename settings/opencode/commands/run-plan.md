---
description: Check a work plan, then run it with the executor loop when the check passes
agent: build
---
Run the work plan: $ARGUMENTS
The argument is the path of a plan that follows `schemas/work-plan.schema.json`, and optionally `--reviewer <ollama model>`.

1. Find the standard: the folder that `~/.agents/skills/repo-improve` links to, two levels up. Call it `<standard>`.
2. Run `python <standard>/scripts/execute.py check <plan> --repo .` and print the result as it is. If it exits with 1, print the errors and the units with no coding agent, change nothing and stop.
3. Without `--reviewer`, stop and ask the owner for the Ollama model that reviews. Review is required, a unit without it is blocked.
4. Run `python <standard>/scripts/execute.py run <plan> --reviewer <model> --repo .`.
5. Run `python <standard>/scripts/execute.py report <plan>` and summarize: units passed, blocked, failed or skipped, and the branch `execute/<plan_id>`.
6. Do not push, merge, edit the plan or pick another model. `execute.py resume` continues an interrupted run and `execute.py clean` removes its worktrees.
