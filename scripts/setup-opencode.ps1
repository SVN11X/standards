# Sets up OpenCode for every repository: global config, global rules, commands and the standard's skills.
# Run it again after pulling the standard. It backs up an existing global config before replacing it.
# Usage: .\scripts\setup-opencode.ps1

$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root "settings\opencode"
$config = Join-Path $HOME ".config\opencode"
$skills = Join-Path $HOME ".agents\skills"
$stamp = Get-Date -Format "yyyyMMddHHmmss"
$utf8 = New-Object System.Text.UTF8Encoding $false

New-Item -ItemType Directory -Force -Path (Join-Path $config "commands") | Out-Null
New-Item -ItemType Directory -Force -Path $skills | Out-Null

$ours = (Get-FileHash (Join-Path $source "opencode.json")).Hash
foreach ($name in @("opencode.json", "opencode.jsonc")) {
    $existing = Join-Path $config $name
    if ((Test-Path $existing) -and (Get-FileHash $existing).Hash -ne $ours) {
        Move-Item $existing "$existing.bak-$stamp"
        Write-Host "backed up $existing to $name.bak-$stamp. Copy your own keys, such as model, into the new opencode.json."
    }
}
Copy-Item (Join-Path $source "opencode.json") (Join-Path $config "opencode.json")

$lines = Get-Content (Join-Path $root "prompts\global-instructions.md") -Encoding UTF8
$start = [array]::IndexOf($lines, "---")
if ($start -lt 0) { throw "prompts\global-instructions.md has no '---' line." }
$global = ($lines[($start + 1)..($lines.Count - 1)] -join "`n").Trim()
$limits = (Get-Content (Join-Path $source "small-model-rules.md") -Raw -Encoding UTF8).Trim()
[System.IO.File]::WriteAllText((Join-Path $config "AGENTS.md"), "$global`n`n$limits`n", $utf8)

Copy-Item (Join-Path $source "commands\*.md") (Join-Path $config "commands") -Force

foreach ($dir in Get-ChildItem (Join-Path $root "skills") -Directory) {
    if (-not (Test-Path (Join-Path $dir.FullName "SKILL.md"))) { continue }
    $link = Join-Path $skills $dir.Name
    if (Test-Path $link) {
        $item = Get-Item $link -Force
        if ($item.LinkType -ne "Junction") {
            Write-Host "skipped skill $($dir.Name): $link is a folder, not a link, so it was left as it is."
            continue
        }
        if (@($item.Target) -contains $dir.FullName) { continue }
        [System.IO.Directory]::Delete($link)
    }
    New-Item -ItemType Junction -Path $link -Target $dir.FullName | Out-Null
    Write-Host "linked skill $($dir.Name)"
}

Write-Host "OpenCode is set up in $config. Open a repository, run opencode, then /connect and /models once."
