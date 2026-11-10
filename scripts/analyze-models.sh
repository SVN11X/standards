#!/usr/bin/env bash
# Tests the allowed model candidates on the bench tasks and writes the report. It installs and downloads nothing.
# Usage: scripts/analyze-models.sh prepare|plan|run|report [options]
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$root/scripts/analyze.py" "$@"
