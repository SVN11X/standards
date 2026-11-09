# Checks everything in one run: selftest, unit tests, the adversarial suite, the linters it finds, and the
# executors of this machine (Ollama, OpenCode with the free models you checked, MCP servers in trial).
# It installs nothing and changes no setting. Works in Windows PowerShell 5.1 and PowerShell 7.
# Usage, from the standards folder:  .\scripts\verify-all.ps1
#        another repository:          .\scripts\verify-all.ps1 -Repo C:\path\to\repo
#        without the live executors:  .\scripts\verify-all.ps1 -Offline
param(
    [string]$Repo = (Split-Path -Parent $PSScriptRoot),
    [switch]$Offline
)

$root = Split-Path -Parent $PSScriptRoot
$verify = Join-Path $root "scripts\verify.py"

# Some tools look for powershell.exe on the PATH. Add its folder for this window only, never globally.
if ($env:WINDIR) {
    $shellDir = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0"
    if ((Test-Path (Join-Path $shellDir "powershell.exe")) -and -not (Get-Command powershell.exe -ErrorAction SilentlyContinue)) {
        $env:PATH = "$env:PATH;$shellDir"
        Write-Host "Added $shellDir to the PATH of this window only."
    }
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw "Python is not on the PATH." }
python -c "import yaml" 2>$null
if ($LASTEXITCODE -ne 0) { throw "PyYAML is missing. Install it with: python -m pip install pyyaml" }

if ($Offline) {
    python $verify --level standard --repo $Repo
} else {
    python $verify --level deep --live --repo $Repo
}
exit $LASTEXITCODE
