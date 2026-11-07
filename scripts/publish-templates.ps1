# Builds one template repository per profile and pushes it to GitHub as a template repository.
# Template repositories are generated output, so each run replaces their history.
# Usage: powershell -ExecutionPolicy Bypass -File .\scripts\publish-templates.ps1 [-Owner SVN11X]
param([string]$Owner = "SVN11X")

function Assert-Ok([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE." }
}

$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path ([System.IO.Path]::GetTempPath()) ("templates-" + [guid]::NewGuid().ToString())

# The python command on Windows can be a Microsoft Store shortcut, so prefer the py launcher.
$python = $null
foreach ($candidate in @("py", "python")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        & $candidate -c "import yaml" *> $null
        if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
    }
}
if (-not $python) { throw "Python with PyYAML not found. Install Python, then run: py -m pip install pyyaml" }

& $python (Join-Path $root "scripts\standard.py") templates $out
Assert-Ok "Building the templates"

foreach ($dir in Get-ChildItem $out -Directory -Filter "template-*") {
    $name = $dir.Name
    Push-Location $dir.FullName
    try {
        git init -q -b main
        Assert-Ok "git init"
        git add -A
        Assert-Ok "git add"
        git commit -q -m "chore: generate $name from standards"
        Assert-Ok "git commit (if git asks who you are, set git config --global user.name and user.email)"
        gh repo view "$Owner/$name" *> $null
        if ($LASTEXITCODE -eq 0) {
            git remote add origin "https://github.com/$Owner/$name.git"
            git push -q --force origin main
            Assert-Ok "git push"
        } else {
            gh repo create "$Owner/$name" --public --source=. --push --description "Template for the $name profile of $Owner/standards"
            Assert-Ok "gh repo create"
        }
        $kind = $name.Substring("template-".Length)
        gh repo edit "$Owner/$name" --template --description "Template for the $kind profile of $Owner/standards. Use this template, then answer the setup questions." --enable-wiki=false --enable-projects=false --add-topic template --add-topic repository-template --add-topic $kind
        Assert-Ok "gh repo edit"
        Write-Host "published $Owner/$name"
    } finally {
        Pop-Location
    }
}
