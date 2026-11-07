# Changelog

All notable changes to this standard are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/2.0.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [1.3.0] - 2026-11-07

### Added

- The skills repository is a plugin marketplace (`.claude-plugin/`), so claude.ai and Claude Code can install the skills once and sync updates automatically.

### Changed

- The skills read the rules from SVN11X/standards at the version the repository pins, the same source the check uses. The bundled copy is only a fallback without network access.
- Generated files are always written with LF line endings, also on Windows.
- A new standard version alone no longer flags `AGENTS.md`. Only a change in its content does.

## [1.2.0] - 2026-11-07

### Added

- `migrate` command: writes a move plan for a messy repository, then applies it with `git mv` and lists the lines that need fixing.
- `settings/ruleset-main.json` and `protect-repo` scripts that require a pull request with a passing standard check.

### Changed

- Loose files at the repository root are errors, not warnings. Only standard files and tool manifests may stay there.
- Undeclared hidden folders are errors.
- Official actions moved to their Node 24 versions (`actions/checkout@v5`, `actions/setup-python@v6`, `actions/setup-node@v5`).

## [1.1.0] - 2026-11-07

### Added

- `skills-repo` command and `publish-skills` scripts that publish the skills to SVN11X/skills, with a release holding the ZIP files.
- `prompts/global-instructions.md` so every tool knows the standard outside a repository.
- Every repository lists the `code-review` skill, and `AGENTS.md` says where the standard's skills are published.

## [1.0.0] - 2026-11-07

### Added

- Six profiles: web, software, data-ai, hardware, docs and infra. Each has fixed rules, techniques that need a written reason, and setup questions.
- Generated `AGENTS.md` with a goal summary, the traffic light, source priority, language rules and anti-slop rules.
- Intent files for every repository: goals, glossary, assumptions, decisions and specs.
- Reusable check workflow covering structure, intent, slop, the pull request contract, secrets and links.
- Ten pattern cards and an index.
- Skills `repo-setup` and `code-review`, and prompts for tools without skills.
- Template publishers for bash (`publish-templates.sh`) and Windows PowerShell (`publish-templates.ps1`).
- `.gitattributes` that keeps line endings as LF on every system.
