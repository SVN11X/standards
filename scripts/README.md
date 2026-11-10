# scripts

- `release.ps1` and `release.sh`: release the standard in one step (selftest, commit, tags, push, publish skills and templates).
- `verify.py`: the independent verifier. `python scripts/verify.py --level deep --live` checks everything in one run and writes a JSON and Markdown report. `verify-all.ps1` and `verify-all.sh` run it from Windows PowerShell or bash.
- `adversarial.py`: tries to break the standard's controls with fake executors and synthetic data, in quick, standard and deep levels.
- `orchestrate.py`: finds the executors of the machine, chooses one per task under the cost and privacy rules, delegates to OpenCode or Ollama and verifies the result, runs benchmarks, records consent and the cost mode, merges the OpenCode config and prints MCP configs.
- `bench_tasks.py`: the synthetic bench tasks and the code that grades them. No model grades another.
- `analyze.py`: finds the models of the machine and of each provider, tests the allowed ones overnight and writes the report (`prepare`, `plan`, `run`, `report`). `analyze-models.ps1` and `analyze-models.sh` run it. It never downloads a model.
- `providers.py`: the transport for providers with an OpenAI-compatible API (`status`, `models`, `check`). Keys come from the environment and are never stored or printed.
- `preserve.py`: snapshots and compares protected data, and lists what an extraction still misses.
- `safe_patch.py`: builds a patch for git am and proves it applies and passes the tests on its base.
- `memory.py`: local technical memory in SQLite FTS5, outside every repository, with export and expiry of agent hints.
- `evidence.py`: the result format and the report writer the other scripts share.
- `standard.py`: the engine of the standard. Run `python scripts/standard.py --help` for the commands. Needs PyYAML (`pip install pyyaml`).
- `publish-templates.sh` (bash) and `publish-templates.ps1` (Windows PowerShell): build one template repository per profile and push them to GitHub as template repositories. They need Python with PyYAML and the GitHub CLI (`gh`), logged in.
- `publish-skills.sh` and `publish-skills.ps1`: build the public `skills` repository from `skills/` and publish it with a release that holds the ZIP files.
- `setup-opencode.sh` and `setup-opencode.ps1`: set up OpenCode for every repository from `settings/opencode/`. They merge the standard's rules into an existing global config after a backup: your keys stay and the stricter rule wins.
- `protect-repo.sh` and `protect-repo.ps1`: apply `settings/ruleset-main.json` to a repository, so changes need a pull request that passes the standard check.
- On Windows, run the PowerShell versions in a window where you first ran `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force`, because Windows blocks unsigned scripts by default.
