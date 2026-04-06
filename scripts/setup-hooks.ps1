$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$hooksDir = "$repoRoot\.githooks"

if (-not (Test-Path $hooksDir)) {
    Write-Host "Creating .githooks directory..."
    New-Item -ItemType Directory -Path $hooksDir -Force | Out-Null
}

Write-Host "Setting git core.hooksPath to .githooks..."
Push-Location $repoRoot
try {
    git config core.hooksPath .githooks
    Write-Host "Git hooks configured successfully." -ForegroundColor Green
    Write-Host "Hooks directory: $hooksDir"
} finally {
    Pop-Location
}
