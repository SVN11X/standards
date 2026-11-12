# One entry point for the local AI ecosystem. Run from the repository folder.
# Usage: .\scripts\standards.ps1 doctor|status|install|repair|update|verify
param([Parameter(Mandatory = $true)][ValidateSet("doctor", "status", "install", "repair", "update", "verify")][string]$Mode)
python (Join-Path $PSScriptRoot "ecosystem.py") $Mode
exit $LASTEXITCODE
