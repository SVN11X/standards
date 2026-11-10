# 006. Cost modes and the model analyzer

Free here means no extra charge for software, an API, a subscription or infrastructure. A local model still uses electricity and a machine you own. The router checks cost, it does not trust a label.

## Cost modes

| Mode | What may run |
| --- | --- |
| `local-only` | Programs and models on this machine. Nothing is sent to a provider. |
| `free-strict` | The above, plus free remote models you checked yourself. No subscription and no paid fallback. |
| `existing-subscription` | The above, plus Claude Code, which you already pay for. This is the default. |

Set yours once with `python scripts/orchestrate.py consent --cost-mode free-strict`. One run can ask for a stricter mode with `--mode` or the `STANDARDS_COST_MODE` variable. Nothing can ask for a looser one.

A remote model is used only when all of this holds, and the request is refused before anything is sent:

1. The cost mode allows remote models.
2. The privacy class of the folder allows them (see `005-verification-and-orchestration.md`).
3. You checked the model as free in the last 30 days (`consent --free-model <id>`).
4. `settings/models.yml` does not list it as paid, trial or unknown cost, and its promotion has not passed its review date.
5. Somebody recorded what the provider does with the data, and the folder allows it. Public code may go to a model that trains. Private code goes only to a model that keeps nothing. A model with no data policy goes nowhere.

When no executor passes, the answer is `blocked` with the reason. The task is then reduced, done with tools or taken to the owner. Nothing paid is used on its own.

Risk decides who reviews, not which brand works. Yellow and red work always needs the owner before integration. A model other than the planner may take it only after it passed the bench class of that task.

Listening on `localhost` is not proof of being local. An Ollama cloud tag, a model served from a remote host, an Ollama URL on another machine and any gateway count as remote.

## Who does what

```
python scripts/orchestrate.py route --all --repo .
```

prints every task type with the agent, the exact model on this machine and the reason, including why a task is blocked or moved to another agent. `doctor` prints the same table after the list of tools, and names the catalog entries, owner checks and measurements that are due again with the page to read. It confirms nothing by itself: you confirm that a model is still free.

## The catalog

`settings/models.yml` holds one entry per provider, model and endpoint: cost category, data use, stated capabilities, daily limit, source, date and evidence level (`declared` when read on the provider's page, `candidate` when a guide named it). An entry enables nothing. Measured results never live there. They go to `~/.standards/bench.jsonl`, the same history `orchestrate.py bench` writes and the router reads.

## Bench classes

| Class | Runs on | A program checks |
| --- | --- | --- |
| `classify`, `extract` | a program, Ollama | exact labels and fields |
| `summarize` | Ollama | required facts, and that every command in the summary exists in the source |
| `web-subprofile` | a program, Ollama | the sub-profile of a labeled request |
| `tool-call` | Ollama | the right tools, in order, with valid arguments, and no made-up content after a tool error |
| `vision` | Ollama, models that report vision | facts that only the image holds |
| `design-judge` | Ollama, models that report vision | agreement with your choice between two screens, asked in both orders |
| `fix-bug`, `fix-multi`, `docs-small` | OpenCode | acceptance tests the agent never saw, the allowed files and the protected files |

Every fixture is synthetic. No model grades another. A model enters a real task only after 3 runs with a pass rate of 0.8 in the class that measures it. Three runs are a first signal on one machine, not strong statistics.

The design judge needs your choices. Put pairs of screenshots in `~/.standards/design-pairs/` with a `pairs.yml`:

```yaml
pairs:
  - {id: home-hero, a: home-a.png, b: home-b.png, choice: b, why: one clear action}
```

Without your pairs the test runs on a made-up sample, recorded as `design-judge-sample`, which never counts for routing.

## Night guide

Run everything from `C:\my_drive\Portafolio\standards` in Windows PowerShell, one command per line. The same commands work in bash with `python3` and `/`.

By day, look at what is ready. This changes nothing and downloads nothing:

```
python scripts\analyze.py prepare
```

It lists the models ready to test, the ones left out, and the exact command for each one you may want to add. You decide which to run. Typical ones:

```
ollama pull granite4.1:3b
python scripts\orchestrate.py doctor --full
python scripts\orchestrate.py consent --free-model opencode/glm-5.3-flash-free
```

`ollama pull` downloads a model, so check its size and license on its page first. `consent --free-model` records that you read the provider's page today and the model is still free. Use the exact name `doctor --full` prints under OpenCode.

Preview the night. Nothing runs:

```
python scripts\analyze.py plan
```

It prints the steps, the longest the run can take and the remote sessions it would open. One run stops by itself after 8 hours at most (`analysis.night_budget_s`). Set Windows not to sleep for the night, because a sleeping machine pauses the run.

Start it and leave:

```
python scripts\analyze.py run
```

It tests local models one at a time and frees the card between them, records cold and warm load and the share on the GPU, and gives each remote model a limited number of sessions. A model that answers that its limit was reached is not used again that night. One failing model never stops the rest. If the run is interrupted, the same command continues where it stopped.

In the morning:

```
python scripts\analyze.py report
```

It writes `model-analysis-<date>.md` in `%USERPROFILE%\.standards\reports\` and prints the path. Read the proposed split, the models below the threshold with their most common failure, and what was not tested and why.

The router already uses the history: among the models you allowed, it takes the one that passed and is fastest. Two things stay your decision. A new local model is used for real tasks only after you add it to `executors.ollama.prefer` in `settings/orchestration.yml`. A remote model is used only while your own check is fresh.

`scripts\analyze-models.ps1` and `scripts/analyze-models.sh` run the same commands, for example `.\scripts\analyze-models.ps1 prepare`.

## Limits

- The analyzer cannot send an image through OpenCode, so remote vision models are not tested on `vision` or `design-judge`.
- Planning, deep review and visual direction have no bench class. In a free mode they are blocked, and whether a free model may ever do them is the owner's decision.
- An agent session makes several requests. The session budget per remote model is an estimate (`analysis.requests_per_agent_run`), not a count of requests.
- OpenCode does not report which model answered, so that field is empty for agent runs. Ollama does, and a different name fails the run.
- The services listed under `services` in `settings/models.yml` (OpenRouter, GitHub Models and others) have no adapter. They are notes to check, not integrations.
