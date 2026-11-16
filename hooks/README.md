# hooks

Claude Code hooks published with the skills plugin. Hooks are scripts that Claude Code runs at fixed moments, so these rules hold even when the agent forgets them.

- `guard.py` (before every shell command): asks the owner before merging (or, when the owner allowed merges with `orchestrate.py consent --merge when-green`, sends the agent to `scripts/merge_when_green.py`, which merges only after every check passed), deploying, force pushing, rewriting history, mass deletions, publishing packages, changing secrets, pulling or deleting local models, global installs, or changing which folders may use remote models. Blocks `git commit` while the standard check of the repository fails.
- `secret_scan.py` (after every file write): stops the agent when the file now contains a credential, so it moves it to an environment variable.
- `session_probe.py` (when a session starts in a repository with `.standard.yml`): says which executors this machine has and how to route and delegate. It only looks, in about a second.
- `route_prompt.py` (on every prompt): adds the router's decision to a work, review, setup or publish request inside a git repository: the folder, the recipe, the provider of each capability, the verification and the permission it needs. A question gets nothing and a prompt is never blocked. See `docs/011-request-router.md`.
- `reinject.py` (after a compaction): puts the key rules of `AGENTS.md` and the plan status back in context.
- `notify.py` (when Claude Code needs the owner): plays a short sound.
- `autopilot.py` (when the agent is about to stop): while `standard-autopilot` exists in the git folder (`git rev-parse --git-path standard-autopilot`, also in linked worktrees), keeps the session working through `docs/improvement-plan.md`. Delete the file to turn autopilot off.
