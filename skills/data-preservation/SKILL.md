---
name: data-preservation
description: Protect data a repository already holds (question banks, images, transcripts, JSON, extracted pages) from accidental loss during changes, and check that an extraction is complete, without duplicates and able to resume after an interruption. Uses inventories, checksums, id checks and declared exceptions. Use it before any change that touches data folders, migrations, regenerated files or extraction scripts, and whenever the owner asks whether something was lost, how many items there are, or how to resume a scrape or download, even if they never say "preservation".
---

# data-preservation

Content that was added on purpose stays unless the owner declared its removal.

## Set it up once

Write `docs/preservation.yml` with the owner:

```yaml
protect: ["data/**", "assets/img/**"]
json_ids:
  - {file: data/questions.json, path: questions, id: id, min_count: 349}
allow: []
```

Every exception needs a path, a change (delete, modify, delete-ids or any), a reason and an end date. Show the file to the owner, since it is their decision what counts as protected.

## Around every change

1. Before: `python <standard>/scripts/preserve.py snapshot`. The snapshot goes inside the git folder and is never committed.
2. After: `python <standard>/scripts/preserve.py compare`. It fails on deleted or changed protected files, repeated or lost ids, broken JSON and counts under the minimum.
3. A legitimate removal gets an `allow` entry in the same commit, so the reason is reviewed with the change.

`verify.py` runs the comparison by itself when the file and a snapshot exist, and reports NOT_RUN when the snapshot is missing.

## Extractions

- Keep a list of what should exist (ids, URLs or file names) next to the output.
- `python <standard>/scripts/preserve.py coverage --expected expected.txt --found data/items.json --path items --id id --resume-out missing.txt` lists missing, duplicated and extra items and writes the missing ones for the next run.
- Resume from `missing.txt`. Write each item atomically (a temporary file, then a rename) so an interruption never leaves half a file.
- Only extract what the owner is allowed to download. Never bypass CAPTCHA, logins or rate limits.

Fixtures for tests are synthetic. Never copy real data from another repository into tests.
