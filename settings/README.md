# settings

Repository settings kept as code.

- `ruleset-main.json`: protects the default branch. Changes reach it only through a pull request whose `check / standard` job passed, and nobody can force-push or delete it. Apply it with `scripts/protect-repo.ps1` or `scripts/protect-repo.sh`.

Rulesets work on public repositories with GitHub Free, and on private ones with GitHub Pro. Do not apply this ruleset to generated repositories (standards, skills, template-*), because their publish scripts push directly to the default branch.
