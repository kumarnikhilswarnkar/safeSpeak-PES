# SafeSpeak PES - one-command local start (Windows PowerShell 5.1+).
#
#   powershell -ExecutionPolicy Bypass -File .\start-safespeak.ps1
#   (or double-click start-safespeak.cmd)
#
# Starts the FastAPI backend (port 8001) and the React frontend (port 5173) together,
# opens http://localhost:5173, and stops BOTH when you press Ctrl+C in this window
# (or when you run stop-safespeak.ps1 / stop-safespeak.cmd from another window).
#
# Database safety: the existing database is never reset or recreated. If (and only if)
# a schema migration is pending, the SQLite database is backed up first
# (scripts/backup_sqlite.ps1 -> backups/) and then migrated with "alembic upgrade head".
#
# For the containerised deployment (PostgreSQL, one URL behind nginx) use Docker Compose
# instead: see docs/docker.md.
param(
    [int]$BackendPort = 8001,
    [int]$FrontendPort = 5173,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$python = Join-Path $backend '.venv\Scripts\python.exe'

# Windows PowerShell 5.1 turns any stderr output of a native program into an error record,
# which "Stop" would make fatal (alembic logs INFO lines to stderr). Run native tools with
# "Continue" and judge success by the exit code instead.
function Invoke-Native([scriptblock]$Block) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Block } finally { $ErrorActionPreference = $previous }
}

function Test-PortInUse([int]$port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
}

Write-Host 'SafeSpeak PES - starting...' -ForegroundColor Cyan

# 1. Prerequisites
if (-not (Test-Path $python)) {
    throw "Backend virtual environment not found. Run once:`n  cd backend; python -m venv .venv; .venv\Scripts\python -m pip install -r requirements.txt"
}
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    throw "Frontend dependencies not installed. Run once:`n  cd frontend; npm install"
}
foreach ($port in @($BackendPort, $FrontendPort)) {
    if (Test-PortInUse $port) {
        throw "Port $port is already in use (SafeSpeak may already be running). Close that window or stop the process, then try again."
    }
}

# 2. Database: migrate only when needed, with a backup first. Never reset.
Push-Location $backend
try {
    $current = Invoke-Native { & $python -m alembic current 2>$null } | Select-String -Pattern '^[0-9a-f]{12}' | Select-Object -First 1
    $head = Invoke-Native { & $python -m alembic heads 2>$null } | Select-String -Pattern '^[0-9a-f]{12}' | Select-Object -First 1
    $currentRev = if ($current) { $current.ToString().Split(' ')[0] } else { '' }
    $headRev = if ($head) { $head.ToString().Split(' ')[0] } else { '' }
    if ($headRev -and $currentRev -ne $headRev) {
        Write-Host "Database schema update needed ($currentRev -> $headRev). Backing up first..." -ForegroundColor Yellow
        Invoke-Native { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'scripts\backup_sqlite.ps1') }
        if ($LASTEXITCODE -ne 0) { throw 'Database backup failed; the schema was not changed and nothing was started.' }
        Invoke-Native { & $python -m alembic upgrade head 2>&1 | ForEach-Object { "$_" } }
        if ($LASTEXITCODE -ne 0) { throw 'Database migration failed; nothing was started. The backup is in backups/.' }
    } else {
        Write-Host "Database schema is up to date ($currentRev)."
    }
} finally {
    Pop-Location
}

# 3. Backend (background process, logs to backend/logs/backend.log)
$logDir = Join-Path $backend 'logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$backendLog = Join-Path $logDir 'backend.log'
$backendErr = Join-Path $logDir 'backend.err.log'
# The processes this script starts are recorded here, so stop-safespeak.ps1 can stop exactly
# them (and nothing else, e.g. servers you started by hand).
$pidFile = Join-Path $logDir 'safespeak.pids.json'
$backendProc = Start-Process -FilePath $python -WorkingDirectory $backend -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $backendLog -RedirectStandardError $backendErr `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$BackendPort")
$frontendProc = $null

function Stop-Tree($proc, [string]$label) {
    if ($proc -and -not $proc.HasExited) {
        Write-Host "Stopping the $label..." -ForegroundColor Cyan
        Invoke-Native { & taskkill /PID $proc.Id /T /F 2>$null | Out-Null }
    }
}

function Save-Pids {
    $state = @{ backend = $backendProc.Id; frontend = if ($frontendProc) { $frontendProc.Id } else { $null };
                backend_port = $BackendPort; frontend_port = $FrontendPort; started = (Get-Date).ToString('o') }
    $state | ConvertTo-Json | Set-Content -Path $pidFile -Encoding UTF8
}

try {
    Save-Pids
    # Wait for the API to answer (up to 60 s).
    $healthUrl = "http://127.0.0.1:$BackendPort/api/v1/health"
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        if ($backendProc.HasExited) { break }
        try {
            $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
            $ready = $true
            break
        } catch { Start-Sleep -Seconds 1 }
    }
    if (-not $ready) {
        Write-Host "The backend did not start. Last lines of $backendErr :" -ForegroundColor Red
        if (Test-Path $backendErr) { Get-Content $backendErr -Tail 20 }
        throw 'Backend failed to start.'
    }
    Write-Host ("Backend ready on port {0}: database {1}, AI model {2}" -f $BackendPort, $health.database, $health.triage_model) -ForegroundColor Green

    # 4. Frontend in this console (so Ctrl+C reaches it); its dev proxy forwards /api to the backend.
    $env:SAFESPEAK_API_URL = "http://127.0.0.1:$BackendPort"
    $frontendProc = Start-Process -FilePath $env:ComSpec -WorkingDirectory $frontend -PassThru -NoNewWindow `
        -ArgumentList @('/c', 'npm', 'run', 'dev', '--', '--port', "$FrontendPort", '--strictPort')
    Save-Pids
    if (-not $NoBrowser) {
        Start-Job -ScriptBlock { param($url) Start-Sleep -Seconds 4; Start-Process $url } -ArgumentList "http://localhost:$FrontendPort" | Out-Null
    }
    Write-Host "Opening http://localhost:$FrontendPort  -  press Ctrl+C here (or run stop-safespeak.cmd) to stop SafeSpeak." -ForegroundColor Cyan
    # Wait until either server exits (Ctrl+C, stop-safespeak, or a crash), then stop the other.
    while (-not $frontendProc.HasExited -and -not $backendProc.HasExited) { Start-Sleep -Milliseconds 500 }
    if ($backendProc.HasExited) { Write-Host "The backend stopped (see $backendErr)." -ForegroundColor Yellow }
} finally {
    # Stop both servers (and their child processes) whatever happened above.
    Stop-Tree $frontendProc 'frontend'
    Stop-Tree $backendProc 'backend'
    Remove-Item $pidFile -ErrorAction SilentlyContinue
    Get-Job | Remove-Job -Force -ErrorAction SilentlyContinue
    Write-Host 'SafeSpeak stopped. Your data is kept in the database.' -ForegroundColor Cyan
}
