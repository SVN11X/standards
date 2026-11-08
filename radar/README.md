# radar

Tools, libraries and skills evaluated for the standard, inspired by the Thoughtworks Technology Radar. Skills check this list before adding a third-party tool to a repository. A tool that is not here is evaluated first with the `tool-radar` skill.

## Status

- `adopt`: use it when the problem appears. Still record the decision in the repository.
- `trial`: use it in one repository, measure, then move it to adopt or hold.
- `assess`: read and learn from it. Do not install it yet.
- `hold`: do not use it in new work.

## Fields

Every entry in `radar.yml` has: `name`, `url`, `status`, `profiles`, `kind` (library, skill, plugin, tool, app, reference), `license`, `cost`, `privacy` (what leaves the machine), `expression` (for interface tools: the `DESIGN.md` expression levels it fits, sober, balanced or expressive), `notes` and `evaluated` (date).

## Criteria

An entry needs evidence, not hype: the repository exists, its README says what it does, the license allows the use, the cost fits "free tools" when a repository requires it, and it serves a goal in the repository's `docs/goals.md`. Prototypes and single-maintainer projects start at `assess` or `trial`.
