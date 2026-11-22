# Improvement plan

Progress of the free routing, model analyzer and web design work of November 2026. Details are in `CHANGELOG.md` and `docs/006-model-analyzer.md`.

- [x] Cost modes, data use per privacy class and one gate for every model call
- [x] Model catalog in `settings/models.yml` with the candidates from the owner's notes
- [x] Bench classes with deterministic graders, and the night analyzer with prepare, plan, run and report
- [x] Table of task, agent and model in `route --all` and `doctor`
- [x] `docs/how-it-works.md` template, check and the standard's own file
- [x] Web sub-profiles, interaction patterns, gallery, layered design judgment and browser measurement
- [x] Radar entries at assess for the tools the owner named
- [x] Run `analyze.py` on the owner's machine with real models. 139 runs on 2026-11-10 and 2026-11-11, reports in `~/.standards/reports`
- [x] Parse and run `analyze-models.ps1` in Windows PowerShell 5.1. On 2026-11-18 all eight `.ps1` scripts parse with no error, and `prepare`, `plan` and `run` work under the RemoteSigned policy
- [x] Read the official pages again and set `checked` in `settings/models.yml`. On 2026-11-18 for the ten local candidates, from `ollama show`, the registry manifest and license of each tag and its tags page, and for the free OpenCode models on the models page
- [ ] BLOCKED: owner provides pairs of screens in `~/.standards/design-pairs/` for the design judge
- [x] The owner decided on 2026-11-18 that no free model plans or does deep review for now. No model passed `review-diff`, the best got 2 of 3, and only `qwen2.5-coder:7b` and `gpt-oss:20b` passed `decompose`. Planning and deep review stay with Claude. Ask again once a model passes `review-diff`
- [x] The owner decided on 2026-11-18 not to publish the gallery with GitHub Pages for now. The repository is already public, and a Pages workflow would need the owner for every change
- [x] The owner approved `opencode/hy4-flash-free` on 2026-11-18 with `orchestrate.py consent`. It gets real tasks only after 3 bench runs at a pass rate of 0.8
- [x] The owner kept `longcat-2.5-free` on the strict data policy on 2026-11-18. What it stores is unknown and it is hosted in China
- [x] Discovery of every installed Ollama model, with kind, capabilities, cloud or local and a memory check
- [x] Transport for OpenAI-compatible providers with settings per provider, and coverage with one state per model
- [ ] BLOCKED: run each provider adapter against its real service with the owner's key. Only a fake server was used. On 2026-11-18 the owner chose not to add provider keys for now, since OpenCode's free models and Ollama cover the work
- [x] Open each provider's pages and confirm what `settings/providers.yml` says. On 2026-11-18 all 24 sources were read: 47 claims confirmed, 3 corrected and every unconfirmed data claim kept strict. Groq training is now unknown and Ollama cloud is paid
- [x] Confirm that `opencode run --file` sends an image. On 2026-11-18 a local stub recorded the request of OpenCode 1.19.5: the PNG arrives byte for byte as an `image_url` data URL when the model declares `modalities.input` with `image`, and as a text saying the model cannot read it otherwise. The earlier runs failed on the speed of the local 9B, not on the transport
- [x] Adapter for a gateway such as FreeLLMAPI, after the trial checks in the radar pass with a fake server
- [x] Locate the official repository and license of the impeccable detector. It is pbakaus/impeccable, Apache-2.0, and the radar lists it at assess
- [x] Second web change: site performance budget, chart palette for color blindness, form pattern, link preview
- [x] Remove Claude from routing. Drop `claude` from every `tasks` list, add `planner_tasks`, remove the risk reorder and the proof exemption, update the five tests
- [x] Proof and tiers in policy. Move `ROUTE_BENCH` and `LARGE_BENCH` into `orchestration.yml` so `fix-multi` never qualifies for `refactor`
- [x] Evidence expiry and identity. Bench rows older than `bench_recheck_days` or from another OpenCode minor or GPU do not count
- [x] Model lifecycle command. `orchestrate.py models` prints discovered, tested and authorized states per task type with the expiry date
- [x] Bench class `refactor-module`. A 6 to 8 file fixture that extracts a duplicated function into a module with hidden tests and an `ast` check
- [x] Bench class `review-diff`. Six synthetic diffs with seeded defects, graded on recall of file and line range and false high findings
- [x] Bench class `decompose`. Three task specs graded with `workplan.validate` on coverage, acyclicity and disjoint parallel sets
- [x] Health and failover. Failure codes, `~/.standards/health.json`, cooldowns, candidate switch and `fallbacks` in `route()`
- [x] Work plan contract. `schemas/work-plan.schema.json` plus `scripts/workplan.py` with validate, DAG, glob expansion, conflicts and parallel batches
- [x] Review. `scripts/review.py` with a cross-model JSON verdict, finding validation and one fix round on a high finding
- [x] Decomposition. `split_unit` in `workplan.py`: deterministic by files, by criteria, then model proposal, each validated
- [x] Executor loop. `scripts/execute.py` with check, run, status, resume and clean, under 600 lines by reusing `orchestrate`, `workplan` and `review`
- [x] Adversarial scenarios. New cases in `adversarial.py` for planner types, claude calls, overlap, budget stops and invented review lines
- [x] Report. `schemas/execution-report.schema.json` and the `report` command, one consolidated report per plan
- [x] Docs and agent texts. `docs/007`, `docs/005`, `docs/006`, `skills/repo-improve/SKILL.md` and a new `run-plan` OpenCode command
- [x] Run the three new bench classes `refactor-module`, `review-diff` and `decompose` against real models. On 2026-11-18, 3 runs per model: `refactor-module` passed with `deepseek-v4.1-flash-free` and `mimo-v2.6-flash-free`, `review-diff` with both `gpt-oss` 20B, `decompose` with `qwen2.5-coder:7b` and both `gpt-oss` 20B. A `fix-multi` run of the two free models also passed, so `edit-large` and `refactor` route to OpenCode again. Report in `~/.standards/reports/model-analysis-20261118-1030.md`
- [x] Fix: a timeout kills the whole process tree of the executor, so a stuck OpenCode no longer hangs the run
- [x] Fix: a command run in a folder gets PWD set to that folder, so OpenCode launched from a Bash session works in its own worktree
- [x] Executor loop calls `split_unit` when a unit is too large, instead of only failing it
- [x] Executor loop enforces every budget declared in the work plan, not only `max_attempts_per_unit` and `final_regression`
- [x] Pilot plan of 3 green units with `execute.py` and a real `review.py` run, local-only. Two units passed with their tests and a review by `qwen2.5:7b` with no findings, and one failed `inside_scope` on a stale integration base, which the loop now refuses
- [ ] BLOCKED: map the gateway adapter to FreeLLMAPI's real request and reply fields and prove the four radar conditions against the real service at trial. The adapter was proven only against a fake server with its own field names. On 2026-11-18 the owner chose not to install it for now
- [x] Per task type p90 ceiling and evidence refresh. `limits.max_p90_s` as a ceiling on the p90 seconds to an accepted result per route task type, and `refresh_before_days` so the night run measures again the evidence that expires soon. An earlier delegated run wrote it on an old base and it was never integrated. The patch is at `~/.standards/backups/df2d69-uncommitted-p90-and-refresh.patch`, 139 added lines in `analyze.py`, `orchestrate.py`, `orchestration.yml` and two test files. It conflicts with the current `orchestrate.py`, so redo it on top of `fresh_rows` and `model_states` and do not apply it as it is
- [x] Fix: the router skips a free OpenCode model that `opencode models` no longer lists. OpenCode retired `glm-5.3-flash-free` on 2026-11-18 and every edit task was still routed to it
- [x] Fix: `review-diff` and `decompose` get a reply budget of 1500 tokens and a model with only thinking levels gets the lowest one. At 400 tokens every `decompose` reply of the first real run was cut, so the class measured the budget, not the model

## Plan of 2026-11-21: models per task on the RTX 2060, public sites and a remote node

From the owner's "Plan de mejoras para STANDARDS". One branch with one commit per delivery, instead of seven pull requests, because this session pushes to one branch. Details are in `CHANGELOG.md` 1.23.0.

- [x] PR 1. Colibri in the analyzer coverage, one record per executor, id and kind, a pinned executor that is used or blocked with the reason and the bench evidence, usage with `n/a`, and `models` authorizing edit tasks through their bench class
- [x] PR 2. `executors.ollama.prefer_by_task` with `prefer` as the fallback, failed local models refused, `rejected_models` in `route`, and non-chat kinds in the catalog
- [x] PR 3. Recall by words and by meaning with references, repository filter first, vectors per model revision, rebuild of only the affected vectors, and `memory.py eval`
- [x] Night run plans only the missing evidence and does not repeat a failure with nothing changed
- [x] Radar entries for the engines, the options on hold and the services of the plan, with `not verified` where nobody read the license
- [x] Specialists per job in `settings/models.yml`, routed to nothing
- [x] Recipes `web-visitor-ai`, `static-search`, `visitor-ai`, `3d-preview`, `isolated-test` and `remote-node`, and the STL check
- [x] `scripts/workqueue.py` with privacy checks, expiring claims, one result per task, backup and restore
- [x] Released 1.23.0 and 1.24.0 on 2026-11-21, and opened one pull request with the regenerated `AGENTS.md` in each of the five repositories that use the standard
- [ ] BLOCKED: OpenTutor, Fieldnotes and transcribe fail the standard check on decision records with Status proposed and a name in Accepted by. The owner confirms each acceptance
- [x] First notebook session on 2026-11-21 at 1.24.0: `ollama list`, `ollama ps`, `doctor`, `models` and `bench --report` with `--mode local-only`, and `colibri.py status` and `models`. The table was compared with `bench.jsonl`
- [ ] BLOCKED: `orchestrate.py consent --cost-mode local-only` stays with the owner. The session passed `--mode local-only` to each command instead
- [x] The proposed split of `analyze.py report` leaves out models the last run found retired. It named `opencode/glm-5.3-flash-free` first for the edit tasks
- [x] A blocked OpenCode route names every distinct refusal. In local-only `doctor` blamed only the retired glm model, while the cost mode refused deepseek and mimo
- [x] On the notebook on 2026-11-21: `route extract-short` gives ollama `qwen3.5:4b` at p50 5.81 s. `route edit-small --executor colibri` answers blocked with exit 3, because Colibri was not running
- [x] Recall measured on 2026-11-21 with `qwen3-embedding:0.6b` on OpenTutor and Fieldnotes, 8 questions: words alone 5 of 7 in the first 3, words and meaning 7 of 7, and the unanswerable one returned nothing
- [x] `memory.min_similarity` stays at 0.5. Right fragments scored 0.506 to 0.722 and the unanswerable question at most 0.394. Revisit with more Spanish paraphrases
- [ ] BLOCKED: `memory.py index --repo .` finds nothing in this repository, which has no memory entries and no `docs/decisions/`. The owner decides whether recall reads its numbered docs
- [x] Bench of `qwen3.5-9b-ctx16k` on 2026-11-21 in local-only: 3 of 3 on classify, extract, summarize, web-subprofile and vision, 2 of 3 on tool-call, 0 of 3 on the sample design judge
- [x] Engine pilot on 2026-11-21, `qwen2.5:7b` Q4_K_M on classify: llama.cpp b12613 Vulkan median 2.69 s, Ollama 0.40.17 with all layers on the card 2.23 s, both 12 of 12. Not integrated
- [x] The owner chose on 2026-11-21 that every Ollama call fixes temperature, seed and GPU layers. Ollama had put 18 % of `qwen2.5:7b` on the CPU and took 6.45 s instead of 2.23 s
- [ ] BLOCKED: the owner picks one consumer project and one pending task for the first specialist. Granite 4.1 3B if Spanish extraction fails, PaddleOCR-VL-1.5 if a table of the notes extractor is misread
- [ ] BLOCKED: Fieldnotes and tesis_explain adopt `web-visitor-ai` in their own repositories, with the owner's Cloudflare account on Workers Free. The acceptance test needs a browser with an empty cache and the notebook off
- [ ] BLOCKED: the Raspberry Pi 4 case adopts `3d-preview` in the prototype's repository
- [ ] BLOCKED: OpenSandbox QA pilot, which needs Docker or WSL2 on the notebook
- [ ] BLOCKED: the Oracle A1 node and T3 Code on the owner's personal account, then the acceptance test of `docs/005-verification-and-orchestration.md` with the notebook off. `workqueue.py --via` was tested here without SSH

## The ConquerAI video and the owner's agent reports of 2026-11-21

- [x] Guardrails in `.standard.yml` enforced by the check, skill evals with several runs, the feedback loop and `docs/feature-map.md`, and the size of each change in the reports
- [x] Commit gate scoped to the commit, `git branch -d` without a prompt, the PR template and `check --pr --title --body-file`, the Pages artifact per attempt, doubling cooldowns and `no_change`
- [x] Base rules for UTF-8 and LF, a look at media before publishing, and files that parallel changes edit
- [ ] BLOCKED: the owner decides whether to run `orchestrate.py consent --merge-workflows when-green`. Workflow changes keep waiting for the owner until then
- [ ] BLOCKED: the owner adds narrow allow rules in `%USERPROFILE%\.claude\settings.json` for the commands the auto mode classifier stops, such as the exact `merge_when_green.py` command, as `docs/003-autopilot-and-hooks.md` explains. Nothing in a repository can change that file
- [ ] BLOCKED: the owner chooses whether to soften "show me the plan before deleting files" for files the task itself created. It lives in the owner's own instructions
- [x] `skill_eval.py run code-review --executor claude --runs 3` on 2026-11-21: 32 of 33 criteria met. One run wrote the severity labels in Spanish, so no step was skipped by half of the runs

