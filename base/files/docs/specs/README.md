# specs

A specification is only for large changes, such as a new feature or a migration. Small tasks do not need one.

Create one folder per change, named with the month and a short title, for example `2026-11-sensor-ingestion/`, with three files:

- `requirements.md`: what must be true when the change is done. Start each requirement with an id and mark the ones that must never break: `R1 (critical): WHEN <condition> THE SYSTEM SHALL <behavior>` (EARS notation), or Given, When, Then. A test covers a requirement when it names it, for example `# covers 2026-11-sensor-ingestion/R1`.
- `plan.md`: how it will be built, and the decisions it needs.
- `tasks.md`: small tasks in order, each with its own Done when.

The owner approves `requirements.md` before any code is written. `python .standards/scripts/readiness.py <folder> --ci green` then says READY, NEEDS_DECISION or BLOCKED. A critical requirement no test names blocks the change even with green CI.
