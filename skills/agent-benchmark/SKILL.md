---
name: agent-benchmark
description: Measure which executor does a kind of task best on this machine (Claude Code, OpenCode with a free model, a local Ollama model, or a program without AI) by time to correct and verified code, with repeated runs, percentiles, hardware and versions, and use the history to route future work. Also checks claims about model speed, memory, VRAM or energy. Use it when the owner asks which model or agent to use, why OpenCode or Ollama feels slow, whether delegating is worth it, or wants to compare models, even if they only ask "which one is faster".
---

# agent-benchmark

The best executor is the one that reaches verified, correct code soonest, including retries. First-token latency and model size are not the measure.

## Look before measuring

`python <standard>/scripts/orchestrate.py doctor --full` shows OpenCode, its models, Ollama, the models loaded and their share on the GPU, the VRAM in use and the shells. A model split between GPU and CPU is slow on its own, so check `ollama ps` before blaming anything else. Never pull a model or change a timeout without the owner.

## Measure

- Fixing code: `python <standard>/scripts/orchestrate.py bench --task fix-bug --executors opencode:<model> opencode:<other> --runs 3`. Each run starts from an identical synthetic repository, the executor works in its own worktree, and hidden acceptance tests it never saw decide whether the result counts.
- Short local work: `python <standard>/scripts/orchestrate.py bench --task classify --executors tools ollama:qwen3.5:4b --runs 3`. The keyword baseline without AI is always in the comparison.
- Report: `python <standard>/scripts/orchestrate.py bench --report` prints runs, pass rate, p50 and p90 per task, executor and model.

Use only models the owner checked as free on the day (`orchestrate.py consent --free-model <id>`). Never switch to a paid model on your own.

## Interpret

- Three runs are the minimum before the router uses a result. One run is a hint.
- Compare like with like: a direct Ollama call and a full agent session are different tasks.
- Record cold and warm runs apart. The first call loads the model.
- Accuracy counts as much as time. A wrong explanation that arrived fast is a failure.
- Results belong to one machine. Say which one, and never turn them into general percentages.

The router (`orchestrate.py route`) reads this history and prefers executors with enough passing runs. When nothing was measured, it follows the order in `settings/orchestration.yml`, and it can always answer that a program without AI, or doing it yourself, is the better choice.
