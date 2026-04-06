$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host '=== rFactor2 Engineer — Local Tests ==='

# Go backend tests
Write-Host "`n--- Go Backend Tests ---"
Push-Location "$repoRoot\services\backend_go"
try {
    Write-Host 'Running go vet...'
    go vet ./...
    Write-Host 'Running go test...'
    go test ./... -v -count=1
    Write-Host 'Go tests PASSED'
} catch {
    Write-Host "Go tests FAILED: $_" -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
}

# Expo app tests (if node_modules exist)
$expoDir = "$repoRoot\apps\expo_app"
if (Test-Path "$expoDir\node_modules") {
    Write-Host "`n--- Expo App Tests ---"
    Push-Location $expoDir
    try {
        Write-Host 'Running jest...'
        npx jest --passWithNoTests
        Write-Host 'Expo tests PASSED'
    } catch {
        Write-Host "Expo tests FAILED: $_" -ForegroundColor Red
        exit 1
    } finally {
        Pop-Location
    }
} else {
    Write-Host "`nSkipping Expo tests (node_modules not found). Run 'npm install' in apps/expo_app/ first."
}

Write-Host "`n=== All tests PASSED ===" -ForegroundColor Green
