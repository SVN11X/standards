#!/usr/bin/env bash
# Sets up OpenCode for every repository: global config, global rules, commands and the standard's skills.
# Run it again after pulling the standard. It merges into an existing global config, after a backup.
# Usage: scripts/setup-opencode.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
source_dir="$root/settings/opencode"
config="$HOME/.config/opencode"
skills="$HOME/.agents/skills"

mkdir -p "$config/commands" "$skills"

# Merge instead of replacing: your own keys stay, and for each rule the stricter one wins.
python3 "$root/scripts/orchestrate.py" merge-opencode --target "$config"

grep -qx -- '---' "$root/prompts/global-instructions.md" || { echo "prompts/global-instructions.md has no '---' line." >&2; exit 1; }
{
  awk 'found { print } $0 == "---" && !found { found = 1 }' "$root/prompts/global-instructions.md" | sed '/./,$!d'
  echo
  cat "$source_dir/small-model-rules.md"
} > "$config/AGENTS.md"

cp "$source_dir"/commands/*.md "$config/commands/"

for dir in "$root"/skills/*/; do
  name="$(basename "$dir")"
  [ -f "$dir/SKILL.md" ] || continue
  link="$skills/$name"
  if [ -e "$link" ] || [ -L "$link" ]; then
    if [ ! -L "$link" ]; then
      echo "skipped skill $name: $link is a folder, not a link, so it was left as it is."
      continue
    fi
    [ "$(readlink "$link")" = "${dir%/}" ] && continue
    rm "$link"
  fi
  ln -s "${dir%/}" "$link"
  echo "linked skill $name"
done

echo "OpenCode is set up in $config. Open a repository, run opencode, then /connect and /models once."
