# =============================================================
# Phase 6 deploy/down.ps1 - Stop and optionally destroy services
#
# Usage:
#   .\deploy\down.ps1              # stop services, keep volumes
#   .\deploy\down.ps1 -Volumes     # stop + destroy volumes (data loss!)
# =============================================================

param(
    [switch]$Volumes
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
$ComposeFile = "$ProjectRoot\deploy\docker-compose.yml"

Write-Host "=== auscult deploy: down ===" -ForegroundColor Cyan

if ($Volumes) {
    Write-Host "[WARN] Destroying volumes - ALL DATA WILL BE LOST" -ForegroundColor Red
    $confirm = Read-Host "Type 'yes' to confirm"
    if ($confirm -ne "yes") {
        Write-Host "[ABORT] User cancelled" -ForegroundColor Yellow
        exit 0
    }
    Write-Host "[STEP] Stopping services + destroying volumes..." -ForegroundColor Cyan
    docker compose -f $ComposeFile down -v
} else {
    Write-Host "[STEP] Stopping services (volumes preserved)..." -ForegroundColor Cyan
    docker compose -f $ComposeFile down
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Services stopped." -ForegroundColor Green
} else {
    Write-Host "[FAIL] docker compose down failed (exit $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}
