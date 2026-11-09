---
name: repo-improve
description: Improve an existing repository as a whole. Find out what "better" means for this particular repository from its goals and evidence, agree on the full list with the owner once, then apply every improvement in order. It runs the standard's check and move plan, audits structure, documentation, build, tests and CI, security and privacy, dependencies and size, licensing, the profile's own practices and presentation, and hands each topic to repo-setup, code-review, web-improve or docs-review. Use this whenever the user asks to improve, clean up, professionalize, modernize, audit or fix a repository or project, or asks what a repository needs, even when the request is vague, such as "mejora este repo".
---

# repo-improve

"Improve this repository" means something different for every repository. Decide what it means here from evidence and from the owner's goals, agree on it, then work in small steps that each leave the repository better and passing its check.

## Ground rules

- Talk to the owner in their language. Write repository artifacts in English.
- The owner's goals decide what "better" means. Without confirmed goals there is no list: step 1 is mandatory.
- One improvement per pull request. Moving or deleting files, changing public URLs and rewriting history are yellow changes: propose them and wait.
- Never invent measurements, results or a passing check.

## 1. Understand and confirm, before anything else

1. Read `README.md`, `docs/goals.md`, `AGENTS.md`, `.standard.yml`, the main source files, the recent commits and, if available, the open issues. For a website, also read the page itself: what it says, what the visitor does, step by step.
2. Write an Understanding block in plain words: what the repository is for, who uses it, the main task step by step, how it works (for example where the processing runs), and anything that looked contradictory. Ask the owner to confirm or correct it. Every later decision rests on this, so do not continue until the owner confirms.
3. Interview the owner for whatever is missing or marked `TODO(owner)`: `docs/goals.md` (vision, users, objectives, non-goals, success criteria, priorities, constraints), `DESIGN.md` for the web profile (identity, audience, personality, palette, typography, motion, references), and the status line of `README.md`. Ask one short round at a time, with choices when they help, using the tool's question interface if it has one.
4. Transcribe the answers into those files in English, keeping the owner's meaning, and show the result for confirmation. Never invent an answer. Leave `TODO(owner)` only for questions the owner chose to skip.

Identify the profile and its parts the way repo-setup does. If the repository does not follow the standard yet, adopting it is the first improvement: hand it to repo-setup, which plans and applies the move.

## 2. Diagnose with the standard

Get the pinned standard the way repo-setup describes, then run:

```bash
python <standard>/scripts/standard.py check .
```

Every error is a finding. When the check reports layout errors, generate the move plan with `migrate` (it moves nothing) and use it as evidence.

## 3. Audit the dimensions that apply

Follow `references/audit-dimensions.md`. Skip the dimensions that do not apply to the profile. For each finding, keep the evidence: a file and line, a command and its output, or a measurement.

## 4. Agree on the full list once

List every finding, not only the top ones. Order them for execution: structure first, because the other findings depend on where files end up, then security and privacy, then build and tests, then the rest. Mark each one green, yellow or red with the traffic light in `AGENTS.md`.

Write the list to `docs/improvement-plan.md` as a Markdown task list, so any later session continues where the last one stopped:

- `- [ ] text` pending
- `- [x] text` done
- `- [x] SKIPPED: reason` skipped
- `- [ ] BLOCKED: question` waiting for the owner

Keep each item to one line of at most 240 characters, so the plan stays cheap to reread. The check enforces the format.

Before the owner approves, have the `deep-reviewer` subagent review the plan when it is available. It answers BUILD, BUILD WITH CUTS or REFUSE for every item. Apply the cuts, drop the refusals, and show the owner the list with the verdicts.

The owner approves the list once. After that, do not ask again for approved items.

## Hand-off and autopilot

By default, hand the green items to another executor to save Claude usage, and keep verifying them yourself. For each item:

1. Ask the router: `python <standard>/scripts/orchestrate.py route <task-type> --repo . --files <n> --risk <green|yellow|red>`. Task types are in `settings/orchestration.yml`. It answers tools, ollama, opencode, claude or blocked, with the reason. It never sends client or work code to a free model, and only uses free models the owner checked recently.
2. When it says tools, use the program. When it says claude, do the item yourself.
3. When it says opencode, delegate for real: `python <standard>/scripts/orchestrate.py delegate opencode --task "<item>" --allow <files> --test "<check and tests>"`. It runs OpenCode in its own worktree, then checks the diff, the protected files, the scope and the tests itself, and commits on a `delegate/<id>` branch only when everything passed. Integrate a verified run with `git cherry-pick <commit>` and run the check again. A failed run leaves its worktree for you to read: fix it yourself or mark the item BLOCKED.
4. When it says ollama, use `delegate ollama` for short local work such as classifying or summarizing, and check the answer.
5. Never take an executor's own summary as evidence. The run record (`orchestrate.py runs <id>`) holds the exit code, the diff and the test output.

The owner can still run `/next-item` in OpenCode by hand, one item at a time. Keep every item green, small and concrete, so a small model can do it. Mark the items that need judgment yellow or red, so they stay with Claude.

Before closing a run, use adversarial-testing at the level the risk needs, and data-preservation when the repository protects data.

Turn autopilot on only when the owner asks for it, or when the repository holds work or client code that must not reach a free model. To turn it on, create the empty file at the path `git rev-parse --git-path standard-autopilot` prints (`.git/standard-autopilot` in a normal clone, a folder under `.git/worktrees/` in a linked worktree). It lives inside the git folder, so it is never committed. While it exists, the plugin's Stop hook keeps the session working until no item is pending.

When the owner comes back after a hand-off, review the branch with code-review, take the BLOCKED items, and close the run as the last steps below describe.

- Work through the list without pausing between items. Hand each item to the `item-worker` subagent when it is available, so every item starts with a clean context and the main session only keeps the list. After each item: the check passes, the commit is pushed, the pull request is updated, and the item is marked done.
- If the owner wants to keep working in the same folder, run the autopilot in a separate worktree: `git worktree add ../<repository>-autopilot -b improve/<topic>`.
- When an item needs the owner (a red change or a decision the list left open), mark it `- [ ] BLOCKED: <question>` and continue with the next one. Do not stop to ask.
- Never merge, deploy, publish secrets or rewrite history during autopilot. Those always wait for the owner.
- When nothing is pending, close the run in three steps. Reconcile: reread the commits and the pull request, and update `docs/assumptions.md`, `docs/decisions/` and `docs/goals.md` where the work changed them. Retrospective: list what the owner had to correct during the run and propose the matching lines for `preferences.md` or `AGENTS.md`, for the owner to approve. Then delete the autopilot file and give one final summary with every BLOCKED question together.
- If the owner asks to pause or stop, delete the autopilot file at once.

## 5. Apply everything, in order

Hand each topic to the skill that owns it:

- Layout, standard files, migration: repo-setup.
- Code quality and security: code-review, in its deep mode for a full audit.
- Website UX, interactive explanations, GitHub Pages: web-improve.
- Theses, reports and documentation: docs-review.
- Interface slop, accessibility, mobile layout and copy: the antislop skills, when installed.
- A new tool, library or skill: check the radar of the standard first. If it is not there, evaluate it with tool-radar before using it.

Each improvement is its own commit, verified with the check before the next one starts, so any of them can be reverted alone. Open the pull request with a Conventional Commits title (for example `refactor: adopt the repository standard`) and a body that copies `.github/pull_request_template.md` with every section filled: Task, What I understood, Assumptions, Decisions, Not done, How to verify. Write the body to a file outside the repository and use `gh pr create --title "..." --body-file <file>`. Then wait for the check and fix it if it fails. Group them in one pull request, or one per improvement if the owner prefers. In a chat without repository access, deliver one patch for `git am` instead, and a ZIP only when the owner asks. Never paste whole files or logs in the reply. Record decisions in `docs/decisions/` and surviving assumptions in `docs/assumptions.md`. Update the task list in `docs/improvement-plan.md` as you go.

## Models in Claude Code

- Plan with the strongest model and execute with a balanced one: the owner can set the model to `opusplan`, which uses Opus in plan mode and Sonnet after the plan is approved. Do the diagnosis and the list in plan mode.
- Delegate mechanical steps (the check, move plans, regenerating `AGENTS.md`, tests, builds) to the `standard-runner` subagent, which runs on Haiku, when it is available.
- Delegate deep code audits to the `deep-reviewer` subagent, which runs on Opus, when it is available.

## 6. Leave a trail

After each improvement, run the check again, update `CHANGELOG.md` when the change is visible to users, and update `docs/improvement-plan.md`, so the next session starts from evidence instead of from scratch.
