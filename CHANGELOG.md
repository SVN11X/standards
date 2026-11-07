# Changelog

All notable changes to this standard are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/2.0.0/) and versions follow [Semantic Versioning](https://semver.org/).

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
