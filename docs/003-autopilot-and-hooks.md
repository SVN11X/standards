# 003. Autopilot, hooks and models

`repo-improve` lists every finding in `docs/improvement-plan.md` as a short task list, has the plan reviewed (build, build with cuts or refuse), and gets one approval from the owner. With autopilot on, each item goes to a subagent with a clean context, and the session keeps going until nothing is pending. Items that need the owner are marked BLOCKED and collected for the end. The run closes by updating assumptions, decisions and goals, and by proposing preference changes from the owner's corrections.

Hooks enforce what text cannot: asking before merges, deploys and deletions, blocking commits while the check fails, stopping on written secrets, restoring the rules after a compaction, and notifying the owner.

Models by task: plan on Opus and execute on Sonnet (`opusplan`, made the default by `settings/claude-managed-settings.json`), mechanical steps on Haiku (`standard-runner`), deep reviews on Opus (`deep-reviewer`).

By default `repo-improve` routes each approved item with `scripts/orchestrate.py route` and delegates green ones to OpenCode or Ollama with `orchestrate.py delegate`, which runs the executor in its own worktree and checks the result itself (see `005-verification-and-orchestration.md`). The `/next-item` and `/fix-check` commands that `scripts/setup-opencode.ps1` installs still work by hand. Autopilot in Claude Code runs only when the owner asks, or in repositories with work or client code. No hook runs in OpenCode, so its config asks before commits and pushes instead. Free models keep what you send, so use them only in personal repositories.

Habits that save tokens:

- When an answer goes wrong, go back and rewrite the message (Esc twice in Claude Code) instead of correcting it in a new one.
- Show a screenshot instead of describing a visual problem.
- Use `/clear` between unrelated tasks.
- Keep the concise output style from `settings/output-style-concise.md` active.

## Why an agent asks, and what the owner can change

Three different things stop an agent, and only the first one lives in this standard.

1. The guard hook of this standard (`hooks/guard.py`). It asks before a force push, `git reset --hard`, `git clean`, `git branch -D`, a recursive deletion, a deploy, a package publish, a secret, cloud or cluster deletions, `ollama pull` and `orchestrate.py consent`. A hook that answers "ask" still asks when a settings rule allows the command, so these prompts change only here. It asks nothing for a deletion inside a temporary folder or a delegation's worktree, for a `delegate/<run>` branch it made, for `git worktree remove` or for `git branch -d`, which refuses an unmerged branch. A commit is blocked only for check errors about the files that commit holds, so a loose file the owner adds meanwhile no longer blocks an unrelated commit. `gh pr merge` goes to `merge_when_green.py` once the owner allowed merges.
2. Claude Code's auto mode classifier, which reviews actions such as a merge into a public `main` or a change of the Pages source. A narrow allow rule in the user settings (`%USERPROFILE%\.claude\settings.json` on Windows) resolves before the classifier. A broad one such as `Bash(python*)` is dropped in auto mode. Copy the exact command the agent ran, for example the `merge_when_green.py` path the guard prints, into one rule. `autoMode.allow` in the same file loosens a routine pattern the classifier keeps flagging. The `/permissions` dialog lists the rules and the file each one comes from, and its recently blocked tab approves one action once.
3. The owner's own instructions, such as "before moving, renaming or deleting files, show me the plan and wait". Only the owner changes them. A version that keeps the safety: files that existed before the task need the plan first, and files the task created are removed and reported.

What stays with the owner on purpose: deploys and secrets, force pushes, recursive deletions outside scratch folders, and workflow changes. `python scripts/orchestrate.py consent --merge-workflows when-green` lets `merge_when_green.py` merge a workflow change once every check passed, unless the change adds a line that reaches secrets, write permissions or the triggers that run with them, which still waits. Deploy and secret files always wait. Sources: https://code.claude.com/docs/en/permissions and https://code.claude.com/docs/en/auto-mode-config.
