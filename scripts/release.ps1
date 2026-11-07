# Releases the standard in one step: selftest, commit, version tag from base/base.yml, major tag, push,
# then publishes the skills and the templates.
# Usage: .\scripts\release.ps1 [-Message "feat: short description"] [-Force]
param([string]$Message = "", [switch]$Force)

function Assert-Ok([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE." }
}

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $python = $null
    foreach ($candidate in @("py", "python")) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            & $candidate -c "import yaml" *> $null
            if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
        }
    }
    if (-not $python) { throw "Python with PyYAML not found. Run: python -m pip install pyyaml" }

    $version = (& $python -c "import yaml; print(yaml.safe_load(open('base/base.yml', encoding='utf-8'))['version'])").Trim()
    Assert-Ok "Reading the version"
    $tag = "v$version"
    $major = "v" + $version.Split(".")[0]

    & $python scripts\standard.py selftest
    Assert-Ok "Selftest"

    git add -A
    if (git status --porcelain) {
        if (-not $Message) { $Message = "chore: release $tag" }
        git commit -q -m $Message
        Assert-Ok "git commit"
    }
    git push -q
    Assert-Ok "git push"

    $head = (git rev-parse HEAD).Trim()
    $existing = git rev-parse -q --verify "refs/tags/$tag"
    if ($existing) {
        $tagged = (git rev-parse "$tag^{commit}").Trim()
        if ($tagged -ne $head) {
            if (-not $Force) {
                throw "Tag $tag already points to $tagged, not to HEAD $head. Raise the version in base/base.yml, or run again with -Force to move the tag."
            }
            git tag -f $tag | Out-Null
        }
    } else {
        git tag $tag
    }
    git tag -f $major | Out-Null
    git push -q -f origin $tag $major
    Assert-Ok "Pushing the tags"

    & (Join-Path $PSScriptRoot "publish-skills.ps1")
    & (Join-Path $PSScriptRoot "publish-templates.ps1")
    Write-Host "released $tag ($major now points to $head)"
} finally {
    Pop-Location
}
