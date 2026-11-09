---
name: safe-patch
description: Deliver a change as one patch for git am that is proven to apply on its base commit and to pass the tests there, without touching the owner's working tree, with a written rollback. Also checks a patch someone else made, and audits a release (inventory, versions, artifacts, regressions) before it is published. Use it whenever the owner asks for a patch, a .patch file, changes to apply with git am, a delivery from a chat without repository access, or a pre-release check, even if they only say "give me the changes".
---

# safe-patch

A patch is done when it applies and its tests pass on the commit the owner has, not when it was written.

## Make a patch

1. Find the base commit the owner has. Ask for `git rev-parse HEAD` when you cannot see it. Never guess it.
2. Work on a branch from that base, in a worktree when the owner's folder has uncommitted work: `git worktree add ../<repo>-patch -b patch/<topic> <base>`. Never overwrite local changes.
3. Make the change in Conventional Commits. Run the check, the tests and adversarial-testing at the level the risk needs.
4. Build and prove the patch in one step, writing it outside the repository:

   ```bash
   python <standard>/scripts/safe_patch.py create --base <base> --out ../<topic>.patch --test "<test command>"
   ```

   It applies the patch with `git am` in a temporary worktree at the base, compares the result with your branch and runs the tests there. Deliver only on PASS.

## Check a patch you received

`python <standard>/scripts/safe_patch.py check --patch <file> --base <base> --test "<test command>"`

## Before a release

Run `python <standard>/scripts/verify.py --level deep`, compare the CHANGELOG section with the commits since the last tag, list the artifacts and their checksums, and check that the version in every file agrees. Report what is missing before anyone tags.

## Tell the owner

One line per step, with the folder for each command and no chained commands:

```
git am <path to the patch>
```

Rollback while `git am` stops on a conflict: `git am --abort`. Right after it finished: `git reset --keep ORIG_HEAD`.
