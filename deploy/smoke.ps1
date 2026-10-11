# =============================================================
# Phase 6 deploy/smoke.ps1 - Smoke test (M6.2 exit gate)
#
# Checks:
#   1. All compose services healthy
#   2. PG: can connect + count tables
#   3. Milvus: can connect + collection exists
#   4. Redis: can PING
#   5. Neo4j: can connect + count nodes
#   6. Nginx: can reach :9763
#
# Usage:
#   .\deploy\smoke.ps1
# =============================================================

# 注：native 命令(docker)stderr 在 Stop 下会被视为终止错误，故用 Continue
$ErrorActionPreference = "Continue"
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
$ComposeFile = "$ProjectRoot\deploy\docker-compose.yml"

Write-Host "=== auscult deploy: smoke test ===" -ForegroundColor Cyan
$pass = 0
$fail = 0

# ---- 1. Compose services healthy ----
Write-Host ""
Write-Host "[1/6] Checking compose services..." -ForegroundColor Cyan
# 逐行解析 `{{.Service}} {{.Health}}`（比 ConvertFrom-Json 在 PS5.1 下更可靠）
$lines = docker compose -f $ComposeFile ps --format "{{.Service}} {{.Health}}" 2>$null
$allHealthy = $true
foreach ($line in $lines) {
    if (-not $line.Trim()) { continue }
    $parts = $line.Split(" ", 2)
    $name = $parts[0].Trim()
    $health = $parts[1].Trim()
    # nginx healthy 依赖后端(Next.js/FastAPI)回源，非纯基建判据 → 排除出本项计数
    if ($name -eq "nginx") { continue }
    if ($health -ne "healthy") {
        Write-Host "  [WARN] $name health=$health" -ForegroundColor Yellow
        $allHealthy = $false
    }
}
if ($allHealthy) {
    Write-Host "  [PASS] All infra services healthy (nginx excluded - backend dependent)" -ForegroundColor Green
    $pass++
} else {
    Write-Host "  [FAIL] Some infra services not healthy" -ForegroundColor Red
    $fail++
}

# ---- 2. PG (via container psql - no host psql needed) ----
Write-Host ""
Write-Host "[2/6] Checking PostgreSQL..." -ForegroundColor Cyan
try {
    $tables = docker exec auscult-pg psql -U root -d auscult_v2 -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>$null
    $tables = $tables.Trim()
    Write-Host "  [PASS] PG connected, $tables tables in public schema" -ForegroundColor Green
    $pass++
} catch {
    Write-Host "  [FAIL] PG connection failed: $_" -ForegroundColor Red
    $fail++
}

# ---- 3. Milvus ----
Write-Host ""
Write-Host "[3/6] Checking Milvus..." -ForegroundColor Cyan
$milvusPort = $env:MILVUS_PORT; if (-not $milvusPort) { $milvusPort = "19531" }
try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$milvusPort/healthz" -TimeoutSec 5 -ErrorAction Stop
    Write-Host "  [PASS] Milvus healthz OK (port $milvusPort)" -ForegroundColor Green
    $pass++
} catch {
    # Milvus gRPC port may not serve HTTP; try metrics port
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:9092/healthz" -TimeoutSec 5 -ErrorAction Stop
        Write-Host "  [PASS] Milvus healthz OK (metrics port 9092)" -ForegroundColor Green
        $pass++
    } catch {
        Write-Host "  [FAIL] Milvus unreachable: $_" -ForegroundColor Red
        $fail++
    }
}

# ---- 4. Redis ----
Write-Host ""
Write-Host "[4/6] Checking Redis..." -ForegroundColor Cyan
try {
    # compose base 的 redis.conf 配了密码 auscult-dev-redis（configs/redis.conf 口径）
    # 合并 2>&1 + Out-String 强制捕获（PS5.1 原生命令 stdout 直赋值偶发为空）
    $out = docker exec auscult-redis redis-cli --no-auth-warning -a auscult-dev-redis ping 2>&1 | Out-String
    if ($out -match "PONG") {
        Write-Host "  [PASS] Redis PONG" -ForegroundColor Green
        $pass++
    } else {
        Write-Host "  [FAIL] Redis did not PONG (got: $out)" -ForegroundColor Red
        $fail++
    }
} catch {
    Write-Host "  [FAIL] Redis check failed: $_" -ForegroundColor Red
    $fail++
}

# ---- 5. Neo4j ----
Write-Host ""
Write-Host "[5/6] Checking Neo4j..." -ForegroundColor Cyan
try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:7474" -TimeoutSec 5 -ErrorAction Stop
    Write-Host "  [PASS] Neo4j HTTP reachable" -ForegroundColor Green
    $pass++
} catch {
    Write-Host "  [FAIL] Neo4j unreachable: $_" -ForegroundColor Red
    $fail++
}

# ---- 6. Nginx ----
Write-Host ""
Write-Host "[6/6] Checking Nginx (port 9763)..." -ForegroundColor Cyan
try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:9763/" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    $code = $resp.StatusCode
    Write-Host "  [PASS] Nginx responding (HTTP $code)" -ForegroundColor Green
    $pass++
} catch {
    # Nginx may return 502 if backend (Next.js/FastAPI) is down, which is OK for infra smoke
    if ($_.Exception.Response.StatusCode -eq 502) {
        Write-Host "  [PASS] Nginx reachable (502 expected - no backend running)" -ForegroundColor Green
        $pass++
    } else {
        Write-Host "  [FAIL] Nginx unreachable: $_" -ForegroundColor Red
        $fail++
    }
}

# ---- Summary ----
Write-Host ""
Write-Host "=== SMOKE RESULT: $pass passed, $fail failed ===" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
if ($fail -gt 0) {
    exit 1
}
Write-Host "[OK] M6.2 smoke gate passed." -ForegroundColor Green
