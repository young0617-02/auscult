# =============================================================
# Phase 6 deploy/init.ps1 - Idempotent initialization
#
# Steps:
#   1. PG migrations (0001-0007, ordered, idempotent)
#   2. Milvus collection build (build_milvus_v1.py)
#   3. Neo4j triples import (extract_triples.py --import-neo4j)
#
# Prerequisites:
#   - deploy/up.ps1 completed (services healthy)
#   - .venv exists (uv venv --python 3.12)
#
# Usage:
#   .\deploy\init.ps1              # full init (migrations / Milvus / Neo4j / B5 meta + Outbox + reconcile)
#   .\deploy\init.ps1 -SkipMilvus  # skip Milvus build
#   .\deploy\init.ps1 -SkipNeo4j   # skip Neo4j import
#   .\deploy\init.ps1 -SkipMeta    # skip B5 metadata / Outbox / three-write reconcile
# =============================================================

param(
    [switch]$SkipMilvus,
    [switch]$SkipNeo4j,
    [switch]$SkipMeta
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
Write-Host "[STEP 1/4] PG migrations (0001-0007)..." -ForegroundColor Cyan

# 宿主无需 psql：迁移经 auscult-pg 容器内 psql 执行（干净环境不依赖宿主安装）
$PgContainer = "auscult-pg"
$Migrations = @(
    "0001_init.sql",
    "0003_reports.sql",
    "0004_users.sql",
    "0005_knowledge_admission.sql",
    "0006_audit_logs.sql",
    "0007_alerts_auto_trigger.sql"
)

# 把迁移目录拷入容器（挂载已在 compose；此处 cp 保证脚本可独立运行）
# ⚠️ 陷阱（2026-10-16 修复）：`docker cp SRC_DIR CONTAINER:/tmp/x` 在目标**已存在**时
#   会把 SRC_DIR 拷成 `/tmp/x/migrations/` 子目录（嵌套），而非平铺 —— 幂等重跑时
#   新迁移文件（如 0007）进不了顶层，psql 报 "No such file or directory"，且该错误
#   被 `2>$null` 静默吞掉（2026-10-16 实测：0001-0006 因首次已平铺而能找到，仅 0007
#   找不到，极易误判为"文件未生成"）。故：先删目标目录再拷，保证平铺语义。
docker exec $PgContainer rm -rf /tmp/auscult-migrations 2>$null | Out-Null
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
    Write-Host "[STEP 2/4] Milvus build -- SKIPPED" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "[STEP 2/4] Milvus collection build (build_milvus_v1.py)..." -ForegroundColor Cyan
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
    Write-Host "[STEP 3/4] Neo4j import -- SKIPPED" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "[STEP 3/4] Neo4j triples import (extract_triples.py --import-neo4j)..." -ForegroundColor Cyan
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

# ---- Step 4: TDengine schema + B5 元数据 + Outbox 消费 + 三写对账（2026-10-14 新增）----
# 背景一：init 原先只做「迁表 + Milvus 建库 + Neo4j 导入」，未导入 P1-B5 元数据，
# 导致干净环境初始化后 PG documents/doc_chunks/work_orders 为空、而 Milvus/Neo4j 有数据
# —— 实测 68 条三写不一致，B6「对账零差异」判据失效（2026-10-14 审计发现）。
# 背景二：TDengine 原先默认不启动且无 schema，analyze_sensor 必现 E_TD_TIMEOUT。
# 故补本步骤：TDengine schema（幂等）→ load_meta（幂等）→ outbox_worker（消费）→
# reconcile（复检，应为零差异）。
if ($SkipMeta) {
    Write-Host ""
    Write-Host "[STEP 4/4] TDengine schema / B5 metadata / Outbox / reconcile -- SKIPPED" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "[STEP 4/4] TDengine schema + B5 metadata + Outbox + three-write reconcile..." -ForegroundColor Cyan

    # 4a) TDengine schema：iot 库 + st_pump_metrics 等 3 个超级表（CREATE ... IF NOT EXISTS，幂等）。
    #     不建库表时 query_sensor 因表不存在而失败；建后可明确区分
    #     「表存在但无数据」与「服务不可达」两种降级（后者才走 sensor_report=None）。
    #     实现要点（2026-10-14 实测踩坑）：
    #       ① 必须清除**行内** `--` 注释 —— schema 文件大量使用行尾注释，
    #          直接发送会把 `--` 之后的 SQL 全部注释掉（语句被静默截断）；
    #       ② REST 无状态，`USE iot` 不生效，故 CREATE STABLE/TABLE 需加 `iot.` 全限定前缀；
    #       ③ 逐条校验 REST 返回的 code（HTTP 200 不代表 SQL 成功）。
    $TdContainer = docker ps --filter "name=auscult-tdengine" --format "{{.Names}}"
    if ($TdContainer) {
        $Schema = Get-Content -Raw -Encoding UTF8 "$ProjectRoot\configs\tdengine\schema_master.sql"
        $TdAuth = "Basic " + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("root:taosdata"))
        foreach ($Stmt in ($Schema -split ';')) {
            $Lines = $Stmt -split "`r?`n" | ForEach-Object { $_ -replace '--.*$', '' } | Where-Object { $_.Trim() -ne '' }
            $S = ($Lines -join ' ').Trim()
            if (-not $S -or $S -match '^USE\b') { continue }
            $M = [regex]::Match($S, '^CREATE\s+(STABLE|TABLE)\s+(IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)')
            if ($M.Success) {
                $S = "CREATE $($M.Groups[1].Value) $($M.Groups[2].Value)iot.$($M.Groups[3].Value)" + $S.Substring($M.Length)
            }
            try {
                $Resp = Invoke-RestMethod -Uri "http://127.0.0.1:6041/rest/sql" -Method Post -Body $S `
                    -Headers @{ Authorization = $TdAuth } -TimeoutSec 30
                if ("$($Resp.code)" -ne "0") {
                    Write-Host "  [WARN] TDengine schema code=$($Resp.code) desc=$($Resp.desc)" -ForegroundColor Yellow
                }
            } catch {
                Write-Host "  [WARN] TDengine schema 语句失败：$($S.Substring(0,[Math]::Min(40,$S.Length)))" -ForegroundColor Yellow
            }
        }
        Write-Host "  [OK] TDengine schema initialized (iot + 3 STABLE)" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] auscult-tdengine 未运行，跳过 schema 初始化（analyze_sensor 将走降级路径）" -ForegroundColor Yellow
    }

    & $Python "$ProjectRoot\scripts\load_meta.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [FAIL] load_meta returned $LASTEXITCODE - PG 元数据未导入" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] B5 metadata imported (documents / doc_chunks / work_orders)" -ForegroundColor Green

    & $Python "$ProjectRoot\scripts\outbox_worker.py"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Outbox consumed" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] outbox_worker returned $LASTEXITCODE - 请复跑或查看 pending" -ForegroundColor Yellow
    }

    & $Python "$ProjectRoot\scripts\reconcile.py" 2>&1 | Select-String -Pattern "差异合计|零差异|✘"
    Write-Host "  [OK] 三写对账完成（上行「差异合计」应为 0 条）" -ForegroundColor Green
}

Write-Host ""
Write-Host "[DONE] Initialization complete." -ForegroundColor Green
Write-Host "Next: .\deploy\smoke.ps1  (smoke test)" -ForegroundColor Cyan
