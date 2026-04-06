$ErrorActionPreference = 'SilentlyContinue'

Write-Host 'Stopping local test processes...'

# Stop Go backend (if running on port 8080)
$goProc = Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty OwningProcess
if ($goProc) {
    Stop-Process -Id $goProc -Force
    Write-Host "Stopped process on port 8080 (PID: $goProc)"
}

# Stop Expo dev server (if running on port 8081)
$expoProc = Get-NetTCPConnection -LocalPort 8081 -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty OwningProcess
if ($expoProc) {
    Stop-Process -Id $expoProc -Force
    Write-Host "Stopped process on port 8081 (PID: $expoProc)"
}

Write-Host 'Done.'
