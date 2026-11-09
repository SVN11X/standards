# scripts

- `release.ps1` and `release.sh`: release the standard in one step (selftest, commit, tags, push, publish skills and templates).
- `standard.py`: the engine of the standard. Run `python scripts/standard.py --help` for the commands. Needs PyYAML (`pip install pyyaml`).
- `publish-templates.sh` (bash) and `publish-templates.ps1` (Windows PowerShell): build one template repository per profile and push them to GitHub as template repositories. They need Python with PyYAML and the GitHub CLI (`gh`), logged in.
- `publish-skills.sh` and `publish-skills.ps1`: build the public `skills` repository from `skills/` and publish it with a release that holds the ZIP files.
- `setup-opencode.sh` and `setup-opencode.ps1`: set up OpenCode for every repository from `settings/opencode/`. They back up an existing global config before replacing it.
- `protect-repo.sh` and `protect-repo.ps1`: apply `settings/ruleset-main.json` to a repository, so changes need a pull request that passes the standard check.
- On Windows, run the PowerShell versions in a window where you first ran `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force`, because Windows blocks unsigned scripts by default.
