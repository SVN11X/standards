#!/usr/bin/env bash
# Protects the default branch of a repository with the standard's ruleset.
# After this, changes reach it only through a pull request whose standard check passed.
# Do not use it on generated repositories (standards, skills, template-*): their scripts push directly.
# Usage: scripts/protect-repo.sh OWNER/REPO
set -euo pipefail

repo="${1:?Usage: scripts/protect-repo.sh OWNER/REPO}"
root="$(cd "$(dirname "$0")/.." && pwd)"
file="$root/settings/ruleset-main.json"
name="$(python -c 'import json, sys; print(json.load(open(sys.argv[1]))["name"])' "$file")"

id="$(gh api "repos/$repo/rulesets" --jq ".[] | select(.name == \"$name\") | .id" | head -n 1)"
if [ -n "$id" ]; then
  gh api --method PUT "repos/$repo/rulesets/$id" --input "$file" >/dev/null
else
  gh api --method POST "repos/$repo/rulesets" --input "$file" >/dev/null
fi
echo "protected $repo with ruleset '$name'"
