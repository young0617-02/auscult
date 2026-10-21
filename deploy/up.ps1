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

# ---------------------------------------------------------------- 端口占用预检（ISS-057）
# 2026-10-21 实测：宿主 mosquitto.exe 占用 1883 时，compose 的 MQTT 端口映射会**静默失败**
# （`docker port` 仅见 9001），灌数链路实际连到宿主 broker（默认 max_queued_messages=1000）
# → 单轮 10804 报文仅落 ~1250 行（约 12%），而 `up -d` 全程零报错。
# compose 本身不上报该冲突（冲突只体现在容器内 broker 层），故在此 fail-fast。
function Get-ListeningPids {
    param([int]$Port)
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        return @($conns | Select-Object -ExpandProperty OwningProcess -Unique)
    } catch {
        # 回退 netstat（Get-NetTCPConnection 不可用或权限受限），取 LISTENING 行的 PID 列
        $rows = netstat -ano | Select-String -Pattern ":$Port\s" | Select-String -Pattern "LISTENING"
        return @($rows | ForEach-Object { ($_.ToString().Trim() -split '\s+')[-1] } |
                 Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ } |
                 Select-Object -Unique)
    }
}

$MqttPort = 1883
$holderPids = Get-ListeningPids -Port $MqttPort
if ($holderPids.Count -gt 0) {
    # 本栈已起时 1883 由 docker 代理进程持有（com.docker.backend / vpnkit / wslrelay），
    # 属正常映射 → 放行；宿主其它进程（典型：mosquitto.exe）一律拒绝起栈。
    $foreign = @()
    foreach ($hp in $holderPids) {
        $proc = Get-Process -Id $hp -ErrorAction SilentlyContinue
        $procName = if ($proc) { $proc.ProcessName } else { "<pid $hp>" }
        if ($procName -notmatch '^(com\.docker|docker|vpnkit|wslrelay|dockerd)') {
            $foreign += "$procName($hp)"
        }
    }
    if ($foreign.Count -gt 0) {
        Write-Host "[FAIL] 端口 1883 已被非 docker 进程占用：$($foreign -join ', ')" -ForegroundColor Red
        Write-Host "       compose 的 MQTT 端口映射会**静默失败**（ISS-057）→ 灌数走宿主 broker，数据只落 ~12%。" -ForegroundColor Red
        Write-Host "       处置：停止占用进程后重试（例：Stop-Process -Id <PID> -Force），或改用其它端口。" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "[INFO] 1883 由本栈 docker 映射持有，跳过占用预检" -ForegroundColor DarkGray
} else {
    Write-Host "[OK] 端口 1883 空闲（MQTT 映射可正常建立）" -ForegroundColor Green
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
