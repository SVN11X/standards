# 014. Token use

Spending fewer tokens is worth something only if the result stays as good. This file says how the standard measures what each task costs, where it saves tokens and how a change is proven not to lower quality. The owner asked for it on 2026-11-22.

## What one task costs

Every call to a model appends one row to `telemetry.jsonl` under `STANDARDS_HOME`. `scripts/usage.py` gives the row one shape for every executor:

| Field | Meaning |
| --- | --- |
| `input_tokens` | Prompt tokens the cache did not hold |
| `cache_read_tokens` | Prompt tokens read from the cache |
| `cache_write_tokens` | Prompt tokens written to the cache |
| `output_tokens` | Every generated token, reasoning included |
| `reasoning_tokens` | The reasoning part of the output, when the tool reports it apart |

A row also names its task, its plan, its kind (`plan`, `execute`, `review`, `bench`) and its attempt. A value the tool did not report is null. It is never estimated from characters, and `usage_source` says where the numbers came from. When a unit of a plan ends, the executor loop appends one outcome row: accepted or not, attempts, tests, review and duration. `python scripts/usage.py tasks --plan ID` joins both, so the cost of a task includes its failed attempts, its reviews and the planning calls of its plan (task `<plan id>/plan`).

| Executor | Where the numbers come from |
| --- | --- |
| Claude Code (`claude -p --output-format json`) | `modelUsage`, which also counts subagents and background calls, then `usage` ([cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking)) |
| OpenCode | the `step_finish` events of `opencode run --format json`, summed over the steps of the run. The flag is added only when `opencode run --help` lists it |
| Ollama | `prompt_eval_count` and `eval_count`. Ollama reports no cache |
| Providers with an OpenAI-compatible API | `usage`, with `prompt_tokens_details.cached_tokens` taken out of the new input |

Two costs stay apart. `reported_cost_usd` is the price a tool prints, such as the API price Claude Code shows for a call on a subscription. Claude Code itself calls it a client-side estimate. `extra_charge_usd` is money charged beyond what is already paid: 0 for a local model and for a Claude Code call (the planner removes every API key, so the call goes to the subscription), the provider's own figure when it reports a charge, and null when nothing says. Electricity is not counted.

Bench rows carry the same usage block, so two models can be compared by the tokens they need for a verified result, not only by their pass rate.

## Not covered yet

- The OpenCode event fields were read from projects that parse them, not from an OpenCode release note. Check one real run with `usage.py tasks` before trusting the numbers.
- Calls made inside a Claude Code session, outside the scripts, are not in the telemetry. `hooks/cache_notice.py` reads their cache misses from the transcript.
