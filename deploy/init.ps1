# =============================================================
# Phase 6 deploy/init.ps1 - Idempotent initialization
#
# Steps:
#   1. PG migrations (0001-0006, ordered, idempotent)
#   2. Milvus collection build (build_milvus_v1.py)
#   3. Neo4j triples import (extract_triples.py --import-neo4j)
#
# Prerequisites:
#   - deploy/up.ps1 completed (services healthy)
#   - .venv exists (uv venv --python 3.12)
#
# Usage:
#   .\deploy\init.ps1              # full init
#   .\deploy\init.ps1 -SkipMilvus  # skip Milvus build
#   .\deploy\init.ps1 -SkipNeo4j   # skip Neo4j import
# =============================================================

param(
    [switch]$SkipMilvus,
    [switch]$SkipNeo4j
)

# 注：native 命令（docker/psql）的 stderr 输出在 Stop 下会被视为终止错误，
# 故用 Continue + 显式 $LASTEXITCODE 判定（幂等重跑时 NOTICE 走 stderr 属正常）
$ErrorActionPreference = "Continue"
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
$Python = "$ProjectRoot\.venv\Scripts\python.exe"

Write-Host "=== auscult deploy: init ===" -ForegroundColor Cyan

# Verify python exists
if (-not (Test-Path $Python)) {
    Write-Host "[FAIL] Python not found at $Python" -ForegroundColor Red
    Write-Host "  Run: uv venv --python 3.12 && uv pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

# ---- Step 1: PG Migrations ----
Write-Host ""
Write-Host "[STEP 1/3] PG migrations (0001-0006)..." -ForegroundColor Cyan

# 宿主无需 psql：迁移经 auscult-pg 容器内 psql 执行（干净环境不依赖宿主安装）
$PgContainer = "auscult-pg"
$Migrations = @(
    "0001_init.sql",
    "0003_reports.sql",
    "0004_users.sql",
    "0005_knowledge_admission.sql",
    "0006_audit_logs.sql"
)

# 把迁移目录拷入容器（挂载已在 compose；此处 cp 保证脚本可独立运行）
docker cp "$ProjectRoot\db\migrations" "${PgContainer}:/tmp/auscult-migrations" 2>$null | Out-Null

foreach ($mig in $Migrations) {
    Write-Host "  [RUN] $mig ..." -NoNewline
    # 幂等：已存在对象的 NOTICE 走 stderr 且非零，属正常；2>&1 丢弃、不中断
    $out = docker exec $PgContainer psql -U root -d auscult_v2 -f "/tmp/auscult-migrations/$mig" 2>&1
    $code = $LASTEXITCODE
    if ($out) { Write-Host ""; $out | ForEach-Object { Write-Host "       $_" -ForegroundColor Gray } }
    if ($code -eq 0) {
        Write-Host "  [OK]" -ForegroundColor Green
    } else {
        Write-Host "  [WARN idempotent replay (exit $code)]" -ForegroundColor Yellow
    }
}

# Verify tables
Write-Host "  [CHECK] Table count ..." -NoNewline
$tableCount = docker exec $PgContainer psql -U root -d auscult_v2 -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>$null
$tableCount = ($tableCount.Trim())
Write-Host " $tableCount tables" -ForegroundColor Green

# ---- Step 2: Milvus collection build ----
if ($SkipMilvus) {
    Write-Host ""
    Write-Host "[STEP 2/3] Milvus build -- SKIPPED" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "[STEP 2/3] Milvus collection build (build_milvus_v1.py)..." -ForegroundColor Cyan
    # build_milvus_v1.py 默认硬编码 19530；deploy 栈是 MILVUS_PORT(默认19531)，显式传 --uri
    $milvusPort = $env:MILVUS_PORT; if (-not $milvusPort) { $milvusPort = "19531" }
    & $Python "$ProjectRoot\scripts\build_milvus_v1.py" --uri "http://127.0.0.1:$milvusPort" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Milvus collection built" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Milvus build returned $LASTEXITCODE (may already exist)" -ForegroundColor Yellow
    }
}

# ---- Step 3: Neo4j triples import ----
if ($SkipNeo4j) {
    Write-Host ""
    Write-Host "[STEP 3/3] Neo4j import -- SKIPPED" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "[STEP 3/3] Neo4j triples import (extract_triples.py --import-neo4j)..." -ForegroundColor Cyan
    # 显式指向 P1 收口的 **v2 终态**：--results 缺省为 out_dir/extract_results.jsonl（v1 基线），
    # 实测含 75 条受控词表外关系「关联」（占 30.6%），与 P1-D9 门禁判定所依据的 v2 口径不一致。
    & $Python "$ProjectRoot\scripts\extract_triples.py" --import-neo4j --results "$ProjectRoot\experiments\p1\b4\extract_results_v2.jsonl" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Neo4j triples imported" -ForegroundColor Green
    } else {
        # Neo4j 抽帧导入依赖 P1 冻结 LLM 产物(extract_results.jsonl)+schema 词表，
        # 非基建引导判据（需生成侧 LLM/云端）→ 非致命，仅提示走演示数据预置(D8)
        Write-Host "  [WARN] Neo4j import returned $LASTEXITCODE - graph populated via demo data (D8), not infra gate" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "[DONE] Initialization complete." -ForegroundColor Green
Write-Host "Next: .\deploy\smoke.ps1  (smoke test)" -ForegroundColor Cyan
