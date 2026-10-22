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

# ---------------------------------------------------------------- docker 调用辅助
# ⚠️ 陷阱（同 ISS-044 根因，2026-10-15 修复）：`docker compose down` 停止容器时的
#   进度/警告走 stderr，PS 5.1 将其包装为 ErrorRecord；脚本顶部 EAP="Stop" 会在
#   下方退出码判定**之前**直接终止脚本（用户看到红色异常、收不到 [OK]/[FAIL]
#   反馈）。修复：调用期间临时 SilentlyContinue（Continue 只不终止、仍打印噪音），
#   结束后恢复 EAP，并以显式退出码为唯一判定依据。
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

# ⚠️ 陷阱（ISS-063，2026-10-22 干净环境演练实测）：up.ps1 自 2026-10-14 起默认带
#   `--profile tdengine` 起栈，而 down 原先**不带 profile** → `down` 后 auscult-tdengine
#   仍在运行，并持续占用 auscult-net（`docker compose down` 只打一行
#   "Network ... Resource is still in use" 的非致命提示，脚本仍 exit 0 报 [OK]，
#   属静默"半停"）。故两条路径都必须带同一 profile，与 up 口径对齐。
if ($Volumes) {
    Write-Host "[WARN] Destroying volumes - ALL DATA WILL BE LOST" -ForegroundColor Red
    $confirm = Read-Host "Type 'yes' to confirm"
    if ($confirm -ne "yes") {
        Write-Host "[ABORT] User cancelled" -ForegroundColor Yellow
        exit 0
    }
    Write-Host "[STEP] Stopping services + destroying volumes..." -ForegroundColor Cyan
    $downExit = Invoke-DockerQuiet @("compose", "-f", $ComposeFile, "--profile", "tdengine", "down", "-v")
} else {
    Write-Host "[STEP] Stopping services (volumes preserved)..." -ForegroundColor Cyan
    $downExit = Invoke-DockerQuiet @("compose", "-f", $ComposeFile, "--profile", "tdengine", "down")
}

if ($downExit -eq 0) {
    Write-Host "[OK] Services stopped." -ForegroundColor Green
} else {
    Write-Host "[FAIL] docker compose down failed (exit $downExit)" -ForegroundColor Red
    exit 1
}
