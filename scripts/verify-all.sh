#!/usr/bin/env bash
# Checks everything in one run: selftest, unit tests, the adversarial suite, the linters it finds, and the
# executors of this machine. It installs nothing and changes no setting.
# Usage: scripts/verify-all.sh [repository] [--offline]
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
repo="${1:-$root}"
if [ "${2:-}" = "--offline" ] || [ "${1:-}" = "--offline" ]; then
  [ "${1:-}" = "--offline" ] && repo="$root"
  exec python3 "$root/scripts/verify.py" --level standard --repo "$repo"
fi
exec python3 "$root/scripts/verify.py" --level deep --live --repo "$repo"
