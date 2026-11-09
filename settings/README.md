# settings

Repository settings kept as code.

- `repository.yml`: what every repository gets on GitHub besides its files. Features that are on or off, merge settings, security features and labels. Each repository writes its About panel (description, website, topics) in `.standard.yml` under `github`, and can override features there.
- `ruleset-main.json`: protects the default branch. Changes reach it only through a pull request whose `check / standard` job passed, and nobody can force-push or delete it.

Apply both with `python scripts/standard.py github <repo> --apply --protect`, which uses the GitHub CLI with your login. Without `--apply` it only shows what it would change.

Rulesets and some security features work on public repositories with GitHub Free, and on private ones only with a paid plan. Do not apply the ruleset to generated repositories (standards, skills, template-*), because their publish scripts push directly to the default branch.

Two things have no API and are set by hand once per repository: the social preview image (Settings) and which sections the home page shows (the gear next to About: Releases, Packages, Deployments).

- `opencode/`: OpenCode as a second agent for small work on free models, so Claude usage goes to planning and reviews. `scripts/setup-opencode.ps1` (or `.sh`) merges `opencode.json` into yours, keeping your keys and the stricter rule (asks before commits, pushes, merges, deploys and deletions, and blocks edits to `AGENTS.md`), the global rules, the `/next-item` and `/fix-check` commands, and links the skills. Run it again after pulling the standard. Never run `/init` in a repository, because it rewrites the generated `AGENTS.md`. Never sign in with a Claude subscription there, because Anthropic allows it only in Claude Code and claude.ai. Free models keep what you send, so use them only in personal repositories.
- `claude-managed-settings.json`: makes `opusplan` the model of every Claude Code session on the machine. Copy it as administrator to `C:\Program Files\ClaudeCode\managed-settings.json` on Windows, `/Library/Application Support/ClaudeCode/managed-settings.json` on macOS or `/etc/claude-code/managed-settings.json` on Linux. Managed settings win over user and project settings, so a repository cannot switch the default to Opus. `/model` still changes one session on purpose.
- `output-style-concise.md`: a Claude Code output style that keeps answers short. Copy it to `~/.claude/output-styles/` and choose it in `/config`.
- `orchestration.yml`: who may do which task, what may leave the machine for each privacy class, and the limits of each executor. Read by `scripts/orchestrate.py`. Measurements are not kept here.
- `mcp/catalog.yml`: MCP servers the standard knows, at exact versions, all off by default. `orchestrate.py mcp config <name>` prints the config to turn one on for a task.
