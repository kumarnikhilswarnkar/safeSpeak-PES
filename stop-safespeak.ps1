# Stop SafeSpeak PES started by start-safespeak.ps1 (Windows PowerShell 5.1+).
#
#   powershell -ExecutionPolicy Bypass -File .\stop-safespeak.ps1
#   (or double-click stop-safespeak.cmd)
#
# Stops ONLY the backend and frontend processes recorded by start-safespeak.ps1 in
# backend/logs/safespeak.pids.json (and their child processes). Each recorded PID is checked
# first: it must still be a SafeSpeak uvicorn / npm process, so a reused PID is never touched.
# Servers you started by hand (e.g. your own uvicorn/npm windows) are not affected.
$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot 'backend\logs\safespeak.pids.json'

if (-not (Test-Path $pidFile)) {
    Write-Host 'SafeSpeak is not running from start-safespeak.ps1 (no PID file). Nothing to stop.' -ForegroundColor Cyan
    exit 0
}
$state = Get-Content $pidFile -Raw | ConvertFrom-Json
$expected = @{ backend = 'uvicorn app.main:app'; frontend = 'npm run dev' }
foreach ($name in @('frontend', 'backend')) {
    $id = $state.$name
    if (-not $id) { continue }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
    if (-not $proc) {
        Write-Host "The $name (PID $id) has already stopped."
        continue
    }
    if ($proc.CommandLine -notlike "*$($expected[$name])*") {
        Write-Host "PID $id is no longer the SafeSpeak $name; leaving it alone." -ForegroundColor Yellow
        continue
    }
    Write-Host "Stopping the $name (PID $id)..." -ForegroundColor Cyan
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & taskkill /PID $id /T /F 2>$null | Out-Null } finally { $ErrorActionPreference = $previous }
}
Remove-Item $pidFile -ErrorAction SilentlyContinue
Write-Host 'SafeSpeak stopped. Your data is kept in the database.' -ForegroundColor Cyan
