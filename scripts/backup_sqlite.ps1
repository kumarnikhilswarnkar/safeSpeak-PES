# Back up the local SQLite development database before schema changes.
# Usage (repository root):  powershell -File scripts/backup_sqlite.ps1
# Writes backups/safespeak_dev-<timestamp>.db and prints its SHA-256.
# backups/ is git-ignored: it contains personal and complaint data.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root 'backend\safespeak_dev.db'
if (-not (Test-Path $source)) { Write-Output "No SQLite database at $source; nothing to back up."; exit 0 }
$dir = Join-Path $root 'backups'
New-Item -ItemType Directory -Force $dir | Out-Null
$target = Join-Path $dir ("safespeak_dev-{0}.db" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
Copy-Item $source $target
$hash = (Get-FileHash $target -Algorithm SHA256).Hash.ToLower()
Write-Output "Backup: $target"
Write-Output "SHA-256: $hash"
