# Tests the allowed model candidates on the bench tasks and writes the report. It installs and downloads nothing.
# Works in Windows PowerShell 5.1 and PowerShell 7.
# Usage, from the standards folder:  .\scripts\analyze-models.ps1 prepare
#                                    .\scripts\analyze-models.ps1 plan
#                                    .\scripts\analyze-models.ps1 run
#                                    .\scripts\analyze-models.ps1 report
$root = Split-Path -Parent $PSScriptRoot
$analyze = Join-Path $root "scripts\analyze.py"

# Some tools look for powershell.exe on the PATH. Add its folder for this window only, never globally.
if ($env:WINDIR) {
    $shellDir = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0"
    if ((Test-Path (Join-Path $shellDir "powershell.exe")) -and -not (Get-Command powershell.exe -ErrorAction SilentlyContinue)) {
        $env:PATH = "$env:PATH;$shellDir"
    }
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw "Python is not on the PATH." }
python -c "import yaml" 2>$null
if ($LASTEXITCODE -ne 0) { throw "PyYAML is missing. Install it with: python -m pip install pyyaml" }

python $analyze @args
exit $LASTEXITCODE
