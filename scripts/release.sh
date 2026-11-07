#!/usr/bin/env bash
# Releases the standard in one step: selftest, commit, version tag from base/base.yml, major tag, push,
# then publishes the skills and the templates.
# Usage: scripts/release.sh [-m "feat: short description"] [-f]
set -euo pipefail

message=""
force=0
while getopts "m:f" option; do
  case "$option" in
    m) message="$OPTARG" ;;
    f) force=1 ;;
    *) echo "Usage: scripts/release.sh [-m message] [-f]" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
version="$(python -c "import yaml; print(yaml.safe_load(open('base/base.yml', encoding='utf-8'))['version'])")"
tag="v$version"
major="v${version%%.*}"

python scripts/standard.py selftest

git add -A
if [ -n "$(git status --porcelain)" ]; then
  git commit -q -m "${message:-chore: release $tag}"
fi
git push -q

head="$(git rev-parse HEAD)"
if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
  tagged="$(git rev-parse "$tag^{commit}")"
  if [ "$tagged" != "$head" ]; then
    if [ "$force" -ne 1 ]; then
      echo "Tag $tag already points to $tagged, not to HEAD $head. Raise the version in base/base.yml, or run with -f." >&2
      exit 1
    fi
    git tag -f "$tag" >/dev/null
  fi
else
  git tag "$tag"
fi
git tag -f "$major" >/dev/null
git push -q -f origin "$tag" "$major"

scripts/publish-skills.sh
scripts/publish-templates.sh
echo "released $tag ($major now points to $head)"
