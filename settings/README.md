# settings

Repository settings kept as code.

- `repository.yml`: what every repository gets on GitHub besides its files. Features that are on or off, merge settings, security features and labels. Each repository writes its About panel (description, website, topics) in `.standard.yml` under `github`, and can override features there.
- `ruleset-main.json`: protects the default branch. Changes reach it only through a pull request whose `check / standard` job passed, and nobody can force-push or delete it.

Apply both with `python scripts/standard.py github <repo> --apply --protect`, which uses the GitHub CLI with your login. Without `--apply` it only shows what it would change.

Rulesets and some security features work on public repositories with GitHub Free, and on private ones only with a paid plan. Do not apply the ruleset to generated repositories (standards, skills, template-*), because their publish scripts push directly to the default branch.

Two things have no API and are set by hand once per repository: the social preview image (Settings) and which sections the home page shows (the gear next to About: Releases, Packages, Deployments).
