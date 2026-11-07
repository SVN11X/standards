# skills

Skills for Claude and for other tools that read the SKILL.md format.

- `repo-setup`: create a repository or adopt the standard in an existing one.
- `code-review`: review code or a pull request against the standard.

Do not upload these folders directly. Run `python scripts/standard.py package-skills dist/skills`, which bundles each skill with a copy of the standard pinned to the current version. A skill never downloads the standard at run time.
