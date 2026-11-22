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

## What the hooks add to a session

`hooks/route_prompt.py` adds the router's decision and the recalled notes to every work request. The router already shortens a follow-up of the same task to one line. The recalled notes came back whole on every message. Each message also stays in the conversation, so every later turn reads it again, from the cache at best.

`hooks/context_log.py` now keeps, per session, a fingerprint of each block it added. A routing the session already holds is replaced by one line that says so, and a recalled note the session has seen is left out, so a follow-up adds only what is new. Anthropic's guide asks for "the smallest possible set of high-signal tokens" in the context and for loading the rest when it is needed ([context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)). Leaving out is safe only while the earlier copy is still in the context, so:

- a compaction (`reinject.py`) forgets the session and the next message gets everything again,
- a cleared conversation has another transcript and starts empty,
- an entry older than six hours is sent again,
- the style line, the peerbox messages and the supervisor notice are always sent.

Every injection is logged in `context.jsonl` with the size of each block and the characters left out. `python scripts/usage.py context` sums it. The log counts characters, because a hook sees no tokens. Planner calls record the characters of their prompt next to the tokens the CLI reported.

## Reviews in parts

A local reviewer runs with `num_ctx` 4096. Ollama cuts a longer prompt instead of failing, so a long diff was judged on what was left of it. `scripts/review.py` now sends one part of at most `review.part_chars` characters per call (6000 by default). A part holds whole files when they fit and cuts a file only between hunks, or inside a hunk longer than a part. A cut hunk gets its own `@@` line with the file's line numbers, so a finding is still checked against the lines it cites. Every part of a long diff names all the files of the change. Models use what sits at the start or the end of a long context better than what sits in the middle ([Liu et al.](https://arxiv.org/abs/2307.03172)), which is one more reason to keep each part short.

- An error in any part ends the review as an error. A diff with a part nobody judged cannot pass.
- A diff over `review.max_diff_chars` (100000 by default) is refused before any call. The unit is blocked with the way out: split it.
- A part whose prompt was already judged in the same review is not sent again. The reviewer runs at temperature 0 with a fixed seed, so the same prompt gets the same answer. A fix that changes nothing keeps its failed verdict without a new call.
- The real reviewer now gets the reply budget of the `review-diff` bench class, 1500 tokens. It ran with 400, where the bench had measured that most replies were cut.
- A plan with more than one passed unit gets one more review, of its whole integrated diff. Each unit's review saw only its own diff. Publishing refuses a plan whose integrated review did not pass at the current commit, and automatic merge needs an explicit pass. A plan of one unit is not reviewed twice.

## Who does a task, per accepted result

Among the models that passed the bench class of a task type, the router used to pick the one with the lowest median time. A model that fails one run in five needs more tries for the same result. The bench summary now has `seconds_per_accepted`, the median of the accepted runs divided by the pass rate, and `tokens_per_accepted`, counted the same way when every run reported its tokens. Routing ranks by the first and breaks a tie with the second. With every run passing the order is the same as before, and one odd run still cannot decide, because both come from a median. `analyze.py report` shows both columns.

## Proving that quality held

A saving counts only if the work is still delivered. `python scripts/usage.py compare BASELINE CANDIDATE` compares two runs of the same plans, one without a change (A) and one with it (B).

1. Pick real tasks from the repositories that use the standard, not only bench tasks.
2. Run each task in arm A with its own `STANDARDS_HOME`, reset the repository folder to the same base commit, and run it again in arm B with another `STANDARDS_HOME`. The same folder, base and instruction give the same plan id, which is how the plans are paired.
3. Keep the models, the reviewer and the acceptance criteria the same in both arms. Note the version of the standard and of each tool.
4. Run `usage.py compare <home A> <home B>`.

A plan counts as accepted only when every unit passed its tests and review and the review of its whole diff, where one was needed, passed too. Its cost is every call of the plan: planning, attempts that failed, reviews and fixes. The comparison reports per arm the plans accepted, new input, cache read and output tokens, tokens per kind of call, attempts and the p90 time of an accepted plan.

The pilot thresholds were proposed on 2026-11-22. They are evaluation criteria, not a measured saving:

| Criterion | Pilot value |
| --- | --- |
| Saving per accepted plan | at least 15 % |
| Plans the baseline delivered and the candidate did not | 0 |
| Paired plans | at least 30 |
| Calls that reported no usage | 0 |

The saving is measured in the reported cost when every call of both arms reported one, else in new tokens: new input, cache writes and output, leaving out cache reads because they are reused. `--metric` picks another. Thirty pairs show a difference worth a larger run. They do not prove that quality is equal, and a regression in a task the bench does not cover is still possible. The command exits with 1 until every criterion holds.

## Not covered yet

- The OpenCode event fields were read from projects that parse them, not from an OpenCode release note. Check one real run with `usage.py tasks` before trusting the numbers.
- Calls made inside a Claude Code session, outside the scripts, are not in the telemetry. `hooks/cache_notice.py` reads their cache misses from the transcript.
