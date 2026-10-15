# =============================================================
# Phase 6 deploy/up.ps1 - Start all infrastructure services
#
# Usage:
#   .\deploy\up.ps1                 # start full stack (tdengine included by default)
#   .\deploy\up.ps1 -IncludeTDengine  # accepted for compatibility; tdengine is
#                                     # already enabled by default since 2026-10-14
#
# Prerequisites:
#   - Docker Desktop running
#   - .wslconfig applied (20GB / 10 vCPU)
#   - deploy/.env created from deploy/.env.example (optional)
#   - No leftover auscult-ingest-* containers holding ports 6030/6041/1883
#     (legacy ingest stack, superseded by local self_decoder.py; see ISS-046)
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
# 2026-10-14：**默认即启用 tdengine profile** —— 诊断主场景的 analyze_sensor 依赖
# iot.st_pump_metrics 时序数据，原先默认不带 TDengine 使主场景必现
# E_TD_TIMEOUT / sensor_report=None（审计实证）。-IncludeTDengine 保留为兼容参数。
$composeArgs = @("compose", "-f", $ComposeFile, "--profile", "tdengine", "up", "-d")
if ($IncludeTDengine) {
    Write-Host "[INFO] Starting with tdengine profile (default since 2026-10-14)" -ForegroundColor Yellow
} else {
    Write-Host "[INFO] tdengine profile 默认启用（诊断主场景 analyze_sensor 依赖时序数据）" -ForegroundColor Yellow
}

# ---------------------------------------------------------------- docker 调用辅助
# ⚠️ 陷阱（ISS-044，2026-10-11 实测修复；2026-10-15 补全剩余调用点）：
#   docker compose 的进度/警告输出到 **stderr**，PS 5.1 会把 native stderr 包装为
#   ErrorRecord。原 `pull 2>&1 | Out-Null` 写法把 stderr 并进 pipeline，配合顶部
#   $ErrorActionPreference="Stop" 会在 `up -d` 之前直接终止脚本（干净环境 100%
#   复现，一键启动完全不可用）。
#   2026-10-15 补充：仅把 EAP 放宽到 "Continue" 并不够 —— Continue 只保证**不终止**，
#   ErrorRecord 仍会以红色噪音打印（`up -d` 的 stderr 进度行即此现象，功能不受影响
#   但观感与排障体验差）；须 "SilentlyContinue" 才静默。故统一收敛到本辅助函数：
#   静默 stderr + 显式退出码判定（调用方不得依赖 stdout/stderr 输出，以退出码为准）。
function Invoke-DockerQuiet {
    param([Parameter(Mandatory)][string[]]$Command)
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        & docker @Command
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEap
    }
}

Write-Host "[STEP 1/2] Pulling images (if missing)..." -ForegroundColor Cyan
$pullExit = Invoke-DockerQuiet @("compose", "-f", $ComposeFile, "pull")
if ($pullExit -ne 0) {
    Write-Host "[FAIL] docker compose pull failed (exit $pullExit)" -ForegroundColor Red
    exit 1
}

Write-Host "[STEP 2/2] Starting services..." -ForegroundColor Cyan
$composeExit = Invoke-DockerQuiet $composeArgs
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
Write-Host "  TDengine: localhost:6030 / 6041 (默认启用；schema 由 init.ps1 初始化)" -ForegroundColor Gray
Write-Host ""
Write-Host "Next: .\deploy\init.ps1  (idempotent initialization)" -ForegroundColor Cyan
