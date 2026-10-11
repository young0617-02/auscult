# =============================================================
# Phase 6 deploy/up.ps1 - Start all infrastructure services
#
# Usage:
#   .\deploy\up.ps1                 # start base stack (no tdengine)
#   .\deploy\up.ps1 -IncludeTDengine  # start with tdengine profile
#
# Prerequisites:
#   - Docker Desktop running
#   - .wslconfig applied (20GB / 10 vCPU)
#   - deploy/.env created from deploy/.env.example (optional)
# =============================================================

param(
    [switch]$IncludeTDengine
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
$ComposeFile = "$ProjectRoot\deploy\docker-compose.yml"

Write-Host "=== auscult deploy: up ===" -ForegroundColor Cyan

# Load .env if exists
$EnvFile = "$PSScriptRoot\.env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line.Split("=", 2)
            if ($parts.Length -eq 2) {
                $key = $parts[0].Trim()
                $val = $parts[1].Trim()
                Set-Item -Path "Env:$key" -Value $val
            }
        }
    }
    Write-Host "[OK] Loaded deploy/.env" -ForegroundColor Green
} else {
    Write-Host "[INFO] No .env found; using code defaults (app/api/config.py)" -ForegroundColor Yellow
}

# Build compose args
$composeArgs = @("compose", "-f", $ComposeFile, "up", "-d")
if ($IncludeTDengine) {
    $composeArgs = @("compose", "-f", $ComposeFile, "--profile", "tdengine", "up", "-d")
    Write-Host "[INFO] Starting with tdengine profile" -ForegroundColor Yellow
}

Write-Host "[STEP 1/2] Pulling images (if missing)..." -ForegroundColor Cyan
# ⚠️ 陷阱（2026-10-11 实测修复）：docker 的拉取进度输出到 **stderr**。原写法
#   `docker compose ... pull 2>&1 | Out-Null` 会把 stderr 并进 pipeline，PowerShell
#   将其包装为 ErrorRecord；配合脚本顶部 $ErrorActionPreference="Stop"，会在执行
#   `up -d` **之前**直接终止脚本 —— 干净环境（必然触发 pull 输出）100% 复现，
#   一键启动完全不可用。故：①不做 stderr 合并；②调用 native 命令期间临时放宽 EAP。
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
docker compose -f $ComposeFile pull | Out-Null

Write-Host "[STEP 2/2] Starting services..." -ForegroundColor Cyan
& docker @composeArgs
$composeExit = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($composeExit -ne 0) {
    Write-Host "[FAIL] docker compose up failed (exit $composeExit)" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[OK] Services started. Waiting for healthchecks..." -ForegroundColor Green
Write-Host "  PG:       localhost:5433" -ForegroundColor Gray
Write-Host "  Milvus:   localhost:19531" -ForegroundColor Gray
Write-Host "  Redis:    localhost:6379" -ForegroundColor Gray
Write-Host "  Neo4j:    localhost:7474 / 7687" -ForegroundColor Gray
Write-Host "  MQTT:     localhost:1883" -ForegroundColor Gray
Write-Host "  Nginx:    localhost:9763" -ForegroundColor Gray
if ($IncludeTDengine) {
    Write-Host "  TDengine: localhost:6030 / 6041" -ForegroundColor Gray
}
Write-Host ""
Write-Host "Next: .\deploy\init.ps1  (idempotent initialization)" -ForegroundColor Cyan
