# Builds the public skills repository from this standard and publishes it, with a release that holds the ZIP files.
# The skills repository is generated output, so each run replaces its history.
# Usage: .\scripts\publish-skills.ps1 [-Owner SVN11X]
param([string]$Owner = "SVN11X")

function Assert-Ok([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE." }
}

$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path ([System.IO.Path]::GetTempPath()) ("skills-" + [guid]::NewGuid().ToString())

# The python command on Windows can be a Microsoft Store shortcut, so prefer the py launcher.
$python = $null
foreach ($candidate in @("py", "python")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        & $candidate -c "import yaml" *> $null
        if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
    }
}
if (-not $python) { throw "Python with PyYAML not found. Install Python, then run: python -m pip install pyyaml" }

& $python (Join-Path $root "scripts\standard.py") skills-repo $out
Assert-Ok "Building the skills repository"
$version = (Get-Content (Join-Path $out "VERSION") -Raw).Trim()

Push-Location (Join-Path $out "repo")
try {
    git init -q -b main
    Assert-Ok "git init"
    git add -A
    Assert-Ok "git add"
    git commit -q -m "chore: publish skills $version from standards"
    Assert-Ok "git commit"
    gh repo view "$Owner/skills" *> $null
    if ($LASTEXITCODE -eq 0) {
        git remote add origin "https://github.com/$Owner/skills.git"
        git push -q --force origin main
        Assert-Ok "git push"
    } else {
        gh repo create "$Owner/skills" --public --source=. --push --description "Agent skills for $Owner/standards"
        Assert-Ok "gh repo create"
    }
} finally {
    Pop-Location
}

$zips = @(Get-ChildItem (Join-Path $out "release") -Filter "*.zip" | ForEach-Object { $_.FullName })
gh release view "v$version" --repo "$Owner/skills" *> $null
if ($LASTEXITCODE -eq 0) {
    gh release upload "v$version" $zips --repo "$Owner/skills" --clobber
} else {
    gh release create "v$version" $zips --repo "$Owner/skills" --title "v$version" --notes "Skills generated from $Owner/standards $version."
}
Assert-Ok "gh release"
Write-Host "published $Owner/skills v$version"
