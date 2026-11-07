# skills

Source of the skills for Claude and for every tool that reads the open Agent Skills format.

- `repo-setup`: create a repository or adopt the standard in an existing one.
- `code-review`: review code or a pull request against the standard, with a deep mode.
- `web-improve`: audit and improve a website, for the web profile.
- `docs-review`: review documents and documentation, for the docs profile.
- `published-readme.md.tmpl`: README of the public skills repository.

Do not install these folders directly. `scripts/publish-skills.ps1` (or `publish-skills.sh`) bundles each skill with a copy of the standard pinned to the current version, publishes them to the `skills` repository, and attaches the ZIP files to a release there. A skill never downloads the standard at run time.
