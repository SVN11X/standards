# Protects the default branch of a repository with the standard's ruleset.
# After this, changes reach it only through a pull request whose standard check passed.
# Do not use it on generated repositories (standards, skills, template-*): their scripts push directly.
# Usage: .\scripts\protect-repo.ps1 -Repo SVN11X/my-repo
param([Parameter(Mandatory = $true)][string]$Repo)

$root = Split-Path -Parent $PSScriptRoot
$file = Join-Path $root "settings\ruleset-main.json"
$name = (Get-Content $file -Raw | ConvertFrom-Json).name

$existing = gh api "repos/$Repo/rulesets" | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Could not read the rulesets of $Repo. Private repositories need GitHub Pro for rulesets." }
$match = @($existing | Where-Object { $_.name -eq $name }) | Select-Object -First 1
if ($match) {
    gh api --method PUT "repos/$Repo/rulesets/$($match.id)" --input $file | Out-Null
} else {
    gh api --method POST "repos/$Repo/rulesets" --input $file | Out-Null
}
if ($LASTEXITCODE -ne 0) { throw "Could not apply the ruleset to $Repo. Private repositories need GitHub Pro for rulesets." }
Write-Host "protected $Repo with ruleset '$name'"
