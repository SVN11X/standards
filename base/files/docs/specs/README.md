# specs

A specification is only for large changes, such as a new feature or a migration. Small tasks do not need one.

Create one folder per change, named with the month and a short title, for example `2026-11-sensor-ingestion/`, with three files:

- `requirements.md`: what must be true when the change is done. Write each requirement as "WHEN <condition> THE SYSTEM SHALL <behavior>" (EARS notation) or as Given, When, Then.
- `plan.md`: how it will be built, and the decisions it needs.
- `tasks.md`: small tasks in order, each with its own Done when.

The owner approves `requirements.md` before any code is written.
