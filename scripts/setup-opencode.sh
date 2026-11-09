#!/usr/bin/env bash
# Sets up OpenCode for every repository: global config, global rules, commands and the standard's skills.
# Run it again after pulling the standard. It backs up an existing global config before replacing it.
# Usage: scripts/setup-opencode.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
source_dir="$root/settings/opencode"
config="$HOME/.config/opencode"
skills="$HOME/.agents/skills"
stamp="$(date +%Y%m%d%H%M%S)"

mkdir -p "$config/commands" "$skills"

for name in opencode.json opencode.jsonc; do
  if [ -e "$config/$name" ] && ! cmp -s "$config/$name" "$source_dir/opencode.json"; then
    mv "$config/$name" "$config/$name.bak-$stamp"
    echo "backed up $config/$name to $name.bak-$stamp. Copy your own keys, such as model, into the new opencode.json."
  fi
done
cp "$source_dir/opencode.json" "$config/opencode.json"

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
