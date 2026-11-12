# Delivery report, 12 November 2026

State of the local AI ecosystem of this repository after the implementation session. Every number comes from a command run on the owner's machine in that session. What was not proven is listed as such.

## Summary

- The standard now orchestrates Ollama, OpenCode, Colibri and free cloud models behind one policy, with a loop that plans, executes, tests and reviews work units.
- A real pilot on a throwaway repository, local models only, passed 2 of 3 units with their tests and a review by a second model. The third failed on a stale base and the loop now refuses that case.
- Colibri is installed, serving and connected as a provider and an MCP server, but it is **not usable as a coding agent on this GPU**. Measured, not assumed.
- Pull request 18 holds all the work. The CI is green (`selftest` and `verify`). Nothing is merged.

## Environment and versions

| Component | Version or state |
|---|---|
| Machine | Windows 11, i5-10300H, 64 GiB RAM, RTX 2060 with 6 GiB VRAM |
| Python | 3.11.0 |
| Ollama | 0.40.16 at `127.0.0.1:11434` |
| OpenCode | 1.19.5 |
| Colibri | v2.1.0, Vulkan engine, API at `127.0.0.1:8000`, model `qwen3-coder-30b` (19 GB) |
| Dashboard | `python scripts/control.py serve` at `127.0.0.1:8765`, loopback only |

## Models in Ollama

The four original models are untouched: `qwen3.5:4b`, `qwen3.5:9b`, `qwen2.5:7b`, `qwen3-embedding:0.6b`.

Added: `qwen2.5-coder:7b` (4.7 GB) and `gpt-oss:20b` (13 GB). Three variants with a 16K context, `qwen3.5-9b-ctx16k`, `qwen2.5-coder-7b-ctx16k` and `gpt-oss-20b-ctx16k`, download nothing and exist because OpenCode sends about 12000 tokens and Ollama cut them to 2050 by default.

## Measurements

| Subject | Result |
|---|---|
| `qwen3.5-9b-ctx16k` through OpenCode, `fix-bug` | 3 of 3 passed, p50 334 s, p90 470 s |
| `qwen2.5-coder:7b` through OpenCode | fails, prints the tool call as text |
| Free OpenCode models, `fix-bug` | glm 6 of 6 and mimo 6 of 6, about 20 to 45 s per run |
| Colibri prefill with the GPU shared | about 5.7 tokens per second |
| Colibri prefill with the GPU free | about 8.6 tokens per second, 1000 tokens in 116 s |
| Colibri prompt reuse | none, the same prompt took 115 s three times |
| Colibri through OpenCode, `fix-bug` | 0 passes, one run timed out at 600 s |

A 12000 token OpenCode prompt would take about 23 minutes to read on Colibri. Colibri stays installed for short prompts and the router refuses it for coding. `coli tune` measures generation speed on short prompts and failed on a long one, so it does not help here.

## Pilot of the executor loop

Plan of 3 independent bug fixes on a throwaway repository, cost mode `local-only`, one unit at a time.

| Unit | Result |
|---|---|
| `u1` clamp | passed, tests PASS, review by `qwen2.5:7b` with no findings |
| `u3` word count | passed, tests PASS, review with no findings |
| `u2` last n | failed `inside_scope`, tests PASS |

The first attempt also showed a 15 minute cooldown after a timeout and a blocked message that hid the cause. Both are fixed. The integration branch was checked by hand: the fixes of `u1` and `u3` are real and their tests pass.

## Endpoints and commands

```powershell
.\scripts\standards.ps1 doctor      # reads only, 21 checks OK
.\scripts\standards.ps1 install     # adds what is missing, idempotent
.\scripts\standards.ps1 repair      # install, then restart what does not answer
.\scripts\standards.ps1 update
.\scripts\standards.ps1 verify      # real requests to Ollama and Colibri
python scripts\colibri.py ensure    # also start, stop, status, register
python scripts\control.py serve     # dashboard
python scripts\orchestrate.py models
python scripts\execute.py check|run|status|resume|clean|report PLAN.json --reviewer MODEL
```

## Acceptance criteria

| Criterion | State |
|---|---|
| Colibri installed and serving a real local model | Met |
| Ollama keeps the four original models | Met |
| New approved models installed and tested | Installed and tested. Neither passes `fix-bug` through OpenCode, `gpt-oss:20b` failed its run after 229 s |
| OpenCode uses both local engines | Ollama met. Colibri connects but times out as an agent |
| Free providers configured | Not proven here. No adapter ran with a real key |
| Needed MCP installed and tested | Only Colibri's own MCP. The other four in the catalog are not installed |
| Automatic model selection | Met, checked in normal and `local-only` modes |
| Dashboard with real metrics | Met, unavailable metrics show as null |
| Claude kept out of ordinary implementation | Met, removed from routing and covered by tests |
| 16 original items recovered | Met, 32 plan items done and none open without a block |
| Pending items done or blocked with a cause | Met, 12 blocked |
| Privacy, cost and approval policies kept | Met, and a path that downgraded the privacy class was closed, see below |
| Reproducible install, diagnosis and repair | Met through `standards.ps1` |
| Integration and regression passed | Met, 220 unit tests, `verify` 53 pass and 0 fail, CI green |
| Evidence and consolidated report | This file |

## Defects found and fixed during the session

- A worktree of a `work` or `restricted` repository fell to the default privacy class and could reach a free remote model. It now inherits the owner's class.
- A model with failed runs counted as not measured, so `local-only` routed a coding task to Colibri. A failed model is now refused.
- The CI `verify` did not know Colibri as an executor and two imports were unused. It failed on every pull request run checked, and the local checks of the session did not include `verify.py`.
- A blocked route hid its cause. It now names why each candidate was refused.
- The loop reused an integration worktree built on an old commit. It now refuses and says to clean.
- Colibri's MCP exposes `install`, `start` and `stop`. They are denied in OpenCode, checked with `opencode debug agent`.

## Blocked, needs the owner

1. Real keys to run each provider adapter and the pages to confirm `providers.yml`.
2. A free vision model checked in `local.yml` to prove `opencode run --file`. Two runs with the local 9B returned nothing.
3. Pairs of screens for the design judge.
4. Decision on whether a free model may plan or review deeply.
5. Decision on publishing the gallery with GitHub Pages.
6. Installing FreeLLMAPI to map the adapter to its real API. It was proven only against a fake server.
7. Running the three new bench classes against real models. Their graders are tested with fakes.
8. Running `analyze.py` and `analyze-models.ps1` on the machine for the night analysis.
9. Re-reading the official provider pages to set `checked` in `settings/models.yml`.

## Recovery

- Colibri stopped or slow: `python scripts\colibri.py ensure`. A stopped Colibri blocks its tasks, they never move to another model.
- A unit failed: `python scripts\execute.py resume PLAN.json`. If the repository moved, run `clean` and start again.
- OpenCode config: every change makes `opencode.json.bak-<date>`. The last one is `opencode.json.bak-20261112-141231`.
- Stuck worktrees: `git worktree list`, then `git worktree remove` on the ones under `~/.standards/worktrees`.
- Cooldowns live in `~/.standards/health.json` and expire by themselves.

## Limits to keep in mind

- The pilot used a throwaway repository and one local model. It is not evidence for large refactors.
- The reviewer ran on 2 diffs. That is too few to measure its false negatives.
- Auto-continue runs through a local Stop hook and a deny list in `.claude/settings.local.json`. It is not part of the repository.
