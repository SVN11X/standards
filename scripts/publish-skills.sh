#!/usr/bin/env bash
# Builds the public skills repository from this standard and publishes it, with a release that holds the ZIP files.
# The skills repository is generated output, so each run replaces its history.
# Usage: scripts/publish-skills.sh [owner]
set -euo pipefail

owner="${1:-SVN11X}"
root="$(cd "$(dirname "$0")/.." && pwd)"
out="$(mktemp -d)/skills"

python "$root/scripts/standard.py" skills-repo "$out"
version="$(tr -d '[:space:]' < "$out/VERSION")"

(
  cd "$out/repo"
  git init -q -b main
  git add -A
  git commit -q -m "chore: publish skills $version from standards"
  if gh repo view "$owner/skills" >/dev/null 2>&1; then
    git remote add origin "https://github.com/$owner/skills.git"
    git push -q --force origin main
  else
    gh repo create "$owner/skills" --public --source=. --push --description "Agent skills for $owner/standards"
  fi
)

if gh release view "v$version" --repo "$owner/skills" >/dev/null 2>&1; then
  gh release upload "v$version" "$out"/release/*.zip --repo "$owner/skills" --clobber
else
  gh release create "v$version" "$out"/release/*.zip --repo "$owner/skills" --title "v$version" \
    --notes "Skills generated from $owner/standards $version."
fi
echo "published $owner/skills v$version"
