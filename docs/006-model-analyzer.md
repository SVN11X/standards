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

## What is found, and what the files add

Nothing is counted against a fixed list. The analyzer finds models in three places:

- The local Ollama. It reads `/api/tags` and `/api/show` and takes every installed model, in the catalog or not. From what Ollama reports it tells a chat model from an embedding model, and whether it takes images and tools. A model that runs on Ollama's servers (a cloud tag, or one with a remote host) is listed as remote and never treated as local. A model whose size, with room for its context, does not fit in the graphics memory plus a share of the RAM is not tested.
- OpenCode, for the free models it serves as a coding agent. A model that `opencode models` no longer lists is reported as retired.
- Each provider of `settings/providers.yml` that has an adapter, a free offer and a key in the environment. The adapter asks the provider for its models.

`settings/models.yml` no longer decides which models exist. It adds what discovery cannot know: data use, a daily limit, a note, or `blocked: <reason>` to keep a model out. `settings/providers.yml` holds one entry per provider: address, the name of the environment variable with the key, cost category, how a model counts as free, what the adapter may send, data use, limits and sources. Measured results live in neither. They go to `~/.standards/bench.jsonl`, the same history `orchestrate.py bench` writes and the router reads.

## Providers by API

One transport in `scripts/providers.py` speaks the OpenAI-compatible protocol: list models, check the account, send a chat request with text, images and tools, and name every failure (no key, wrong key, payment asked, limit reached, feature not supported, not found, outage, network, bad reply). A provider is a few lines of settings, not new code. A command line tool is not an API, so it gets no adapter.

| Provider | State | How a model counts as free |
| --- | --- | --- |
| OpenRouter | adapter | its own listing prices everything at 0, and the account reports free requests left |
| Groq, Mistral, Google Gemini API, Cloudflare Workers AI | adapter | the free plan covers it, and you confirm the account has no billing attached |
| Cerebras, NVIDIA API catalog | never called | a trial with credits is not a free offer |
| GitHub Models | retired | the service ended on 2026-07-30 |
| OpenCode Zen by API, Ollama cloud, Antigravity CLI | no adapter | see `settings/providers.yml` |

What was confirmed for each one, and where, is in `settings/providers.yml`. It came from a search of each provider's own site on 2026-11-10. No page was opened directly, no endpoint was called and no adapter was tested against its service. Every adapter was tested against a fake server only.

Before any request to a provider model, all of this holds:

1. The cost mode and the privacy class allow remote models. Work and restricted code never go. Private code goes only to a provider that keeps nothing.
2. The provider has an adapter and a free offer. Trial, paid and unknown cost are refused, also after your check.
3. You checked the provider in the last 30 days: `python scripts/orchestrate.py consent --free-provider <id>`. It records that you read its page, the account is on the free plan and no billing is attached.
4. Where the provider lists prices, the model is in a list fetched in the last 24 hours with every price at 0. A name ending in `:free` proves nothing by itself.
5. The key is in the environment. Without it the provider is pending and nothing is sent. Keys are never stored, printed or written to a report.
6. Where an endpoint reports the account, it still has free requests today.

A reply that reports a charge, a payment request or a reached limit stops that provider for the night. A reply from another model fails the run. The adapter never follows a redirect, so a key cannot travel to another host. A redirect, a limit or an outage is not a result of the model, so that run is not kept.

The router may send a real short task to a provider model (`api` in `settings/orchestration.yml`) only after that model passed the bench class of the task.

## Coverage

`python scripts/analyze.py prepare` lists every model found, by provider, model and endpoint, with one state and its reason: eligible, not installed, not reachable, not a chat model, not enough resources, blocked in the catalog, waiting for your check, no key, no adapter, retired, cost unknown, not free, privacy does not allow it, outside the cost mode, or could not be listed. `--all` prints one line per model and `--json` prints the data.

A task a model was not run on is "not evaluated", with the reason, never a score of zero: the model does not report that capability, Ollama does not report capabilities at all, the adapter does not send that feature, or the provider refused the request as unsupported. A vision test always sends a real image. A model that takes no image is not given the vision test.

## Bench classes

| Class | Runs on | A program checks |
| --- | --- | --- |
| `classify`, `extract` | a program, Ollama, a provider API | exact labels and fields |
| `summarize` | Ollama, a provider API | required facts, and that every command in the summary exists in the source |
| `web-subprofile` | a program, Ollama, a provider API | the sub-profile of a labeled request |
| `tool-call` | Ollama, a provider API | the right tools, in order, with valid arguments, and no made-up content after a tool error |
| `vision` | models that take images, on Ollama or a provider API | facts that only the image holds |
| `design-judge` | models that take images, on Ollama or a provider API | agreement with your choice between two screens, asked in both orders |
| `fix-bug`, `fix-multi`, `docs-small` | OpenCode | acceptance tests the agent never saw, the allowed files and the protected files |

The first six rows are inference by API: one request per item, straight to the model. The last row is a full agent working in a repository. The report keeps the two apart, because they measure different things.

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

It lists every model found with its state, and the exact command for each one you may want to add. You decide which to run. Typical ones:

```
ollama pull granite4.1:3b
python scripts\orchestrate.py doctor --full
python scripts\orchestrate.py consent --free-model opencode/glm-5.3-flash-free
```

`ollama pull` downloads a model, so check its size and license on its page first. A model you install appears in `prepare` by itself, with no edit to any file. `consent --free-model` records that you read the provider's page today and the model is still free. Use the exact name `doctor --full` prints under OpenCode.

To add a provider by API, put its key in the environment of that window only, so it is in no file and not in the command history, then record your check of the account:

```
$env:OPENROUTER_API_KEY = Read-Host "OpenRouter key"
python scripts\providers.py status
python scripts\providers.py models openrouter
python scripts\providers.py check openrouter
python scripts\orchestrate.py consent --free-provider openrouter
```

`status` shows which providers have their key, never the key. `models` asks the provider for its list. `check` asks about the account where an endpoint reports it. The other variables are `GROQ_API_KEY`, `MISTRAL_API_KEY`, `GEMINI_API_KEY`, and `CLOUDFLARE_API_TOKEN` with `CLOUDFLARE_ACCOUNT_ID`. A provider without its key stays pending and the rest runs.

A free account gives few requests a day, so the plan cuts the runs that do not fit and says so. Pick what matters with `--models` and `--tasks`, for example `python scripts\analyze.py plan --models openrouter/ --tasks classify vision`.

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

## Gateways and boards, not connected

No gateway or agent board is integrated. Two candidates are in the radar at `assess`, with the checks that decide a trial: FreeLLMAPI (one endpoint in front of several free providers) and Paperclip (a board for several agents). The rules for any of them are already in the code and the policy:

- The router of the standard stays the only authority on cost and privacy. A gateway chooses only inside the list of providers and models it was given.
- Any executor that is not a program, the local Ollama or Claude counts as remote, wherever it listens.
- A gateway is usable for a class of data only if it can refuse a provider before sending. A check after the answer finds a detour, it does not undo it.
- The model that answered is recorded. A different one fails the run.
- Everything works with the adapter off or down.

## Limits

- No adapter was tested against its real service. Until you run one with your key, its state is "pending a real test".
- Sending an image through `opencode run` is not confirmed, so a vision model served only through OpenCode is not evaluated on `vision` or `design-judge`.
- The reply of a provider may name the model with or without a suffix. A name that only adds or drops a suffix counts as the same model, another name fails the run. The first real run shows whether a provider needs a stricter rule.
- The memory check of a local model uses the file size with a fixed overhead. It is a rough fit, not a measurement.
- Planning, deep review and visual direction have no bench class. In a free mode they are blocked, and whether a free model may ever do them is the owner's decision.
- An agent session makes several requests. The session budget per remote model is an estimate (`analysis.requests_per_agent_run`), not a count of requests.
- OpenCode does not report which model answered, so that field is empty for agent runs. Ollama does, and a different name fails the run.
- Groq, Mistral, Gemini and Cloudflare report no account state to the adapter, so the only evidence that the account cannot be billed is your own check.
