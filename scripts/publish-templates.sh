#!/usr/bin/env bash
# Builds one template repository per profile and pushes it to GitHub as a template repository.
# Template repositories are generated output, so each run replaces their history.
# Usage: scripts/publish-templates.sh [owner]
set -euo pipefail

owner="${1:-SVN11X}"
root="$(cd "$(dirname "$0")/.." && pwd)"
out="$(mktemp -d)"

python "$root/scripts/standard.py" templates "$out"

for dir in "$out"/template-*; do
  name="$(basename "$dir")"
  (
    cd "$dir"
    git init -q -b main
    git add -A
    git commit -q -m "chore: generate $name from standards"
    if gh repo view "$owner/$name" >/dev/null 2>&1; then
      git remote add origin "https://github.com/$owner/$name.git"
      git push -q --force origin main
    else
      gh repo create "$owner/$name" --public --source=. --push \
        --description "Template for the $name profile of $owner/standards"
    fi
    gh repo edit "$owner/$name" --template
  )
  echo "published $owner/$name"
done
