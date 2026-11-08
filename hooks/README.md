# hooks

Claude Code hooks published with the skills plugin. Hooks are scripts that Claude Code runs at fixed moments, so these rules hold even when the agent forgets them.

- `guard.py` (before every shell command): asks the owner before merging, deploying, force pushing, rewriting history, mass deletions, publishing packages or changing secrets. Blocks `git commit` while the standard check of the repository fails.
- `secret_scan.py` (after every file write): stops the agent when the file now contains a credential, so it moves it to an environment variable.
- `reinject.py` (after a compaction): puts the key rules of `AGENTS.md` and the plan status back in context.
- `notify.py` (when Claude Code needs the owner): plays a short sound.
- `autopilot.py` (when the agent is about to stop): while `.git/standard-autopilot` exists, keeps the session working through `docs/improvement-plan.md`. Delete the file to turn autopilot off.
