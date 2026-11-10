# Improvement plan

Progress of the free routing, model analyzer and web design work of November 2026. Details are in `CHANGELOG.md` and `docs/006-model-analyzer.md`.

- [x] Cost modes, data use per privacy class and one gate for every model call
- [x] Model catalog in `settings/models.yml` with the candidates from the owner's notes
- [x] Bench classes with deterministic graders, and the night analyzer with prepare, plan, run and report
- [x] Table of task, agent and model in `route --all` and `doctor`
- [x] `docs/how-it-works.md` template, check and the standard's own file
- [x] Web sub-profiles, interaction patterns, gallery, layered design judgment and browser measurement
- [x] Radar entries at assess for the tools the owner named
- [ ] BLOCKED: run `analyze.py` on the owner's machine with real models. It needs Ollama, OpenCode and the owner's checks
- [ ] BLOCKED: parse and run `analyze-models.ps1` in Windows PowerShell 5.1. No PowerShell in the cloud session
- [ ] BLOCKED: read the official pages again and set `checked` in `settings/models.yml`. The session had no access to them
- [ ] BLOCKED: owner provides pairs of screens in `~/.standards/design-pairs/` for the design judge
- [ ] BLOCKED: owner decides whether a free model may plan or do deep review, and with which bench class
- [ ] BLOCKED: owner decides whether to publish the gallery with GitHub Pages. The workflow needs pinned action commits
- [x] Discovery of every installed Ollama model, with kind, capabilities, cloud or local and a memory check
- [x] Transport for OpenAI-compatible providers with settings per provider, and coverage with one state per model
- [ ] BLOCKED: run each provider adapter against its real service with the owner's key. Only a fake server was used
- [ ] BLOCKED: open each provider's pages and confirm what `settings/providers.yml` says. It came from a search of their sites
- [ ] Confirm that `opencode run --file` sends an image, then test vision models served only through OpenCode
- [ ] Adapter for a gateway such as FreeLLMAPI, after the trial checks in the radar pass with a fake server
- [ ] Locate the official repository and license of the impeccable detector before adding it to the radar
- [ ] Second web change: site performance budget, chart palette for color blindness, form pattern, link preview
