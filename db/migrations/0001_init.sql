-- =============================================================
-- Phase 1 数据库迁移 0001 —— 业务表初始化
-- -------------------------------------------------------------
-- 上游依据： plan/p1-plan-detailed.md §四 D1（PG 迁移）、§5.8（B5 DDL）、§5.9（B6 Outbox）
-- 目标实例： ParadeDB PG 18.6 @ 宿主 5433，库 auscult_v2（用户 2026-10-08 裁定「复用原库」）
--           见 docs/prj-ledger-version-lock.md §二.2.8 / §二.2.11
-- 权威源：   PostgreSQL 为唯一权威源；Milvus / Neo4j 为可重建索引（§5.9）
-- 幂等：     全部 IF NOT EXISTS，可重复执行
--
-- 应用方式（容器内 psql）：
--   docker exec -i auscult-v2-pg psql -U root -d auscult_v2 -v ON_ERROR_STOP=1 -f - < db/migrations/0001_init.sql
-- 校验：
--   docker exec -it auscult-v2-pg psql -U root -d auscult_v2 -c "\dt"
-- =============================================================

BEGIN;

-- ---------------- 文档主表（documents） ----------------
-- 语料/工单等文档的元数据与索引状态；status 由 outbox worker 在写入 Milvus/Neo4j 成功后置 indexed
CREATE TABLE IF NOT EXISTS documents (
    doc_id       UUID PRIMARY KEY,
    title        TEXT NOT NULL,
    source       TEXT NOT NULL,
    doc_type     TEXT NOT NULL,                     -- manual | work_order | procedure
    device_model TEXT,
    checksum     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',   -- pending | indexed | failed
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- ---------------- 分块表（doc_chunks，Parent-Child） ----------------
-- 父块（章节级）与子块（段落级）同表，靠 parent_id 关联；parent_id 为 NULL 即父块
CREATE TABLE IF NOT EXISTS doc_chunks (
    chunk_id    VARCHAR(64) PRIMARY KEY,
    doc_id      UUID NOT NULL REFERENCES documents(doc_id),
    parent_id   VARCHAR(64),
    content     TEXT NOT NULL,
    section     TEXT,
    page        INT,
    token_count INT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ---------------- 知识版本表（knowledge_versions） ----------------
-- 文档变更审计：每次 create/update/delete 记一条，供追溯与对账
CREATE TABLE IF NOT EXISTS knowledge_versions (
    id         BIGSERIAL PRIMARY KEY,
    doc_id     UUID NOT NULL,
    version    INT NOT NULL,
    action     TEXT NOT NULL,                       -- create | update | delete
    actor      TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ---------------- 工单表（work_orders） ----------------
CREATE TABLE IF NOT EXISTS work_orders (
    order_id   TEXT PRIMARY KEY,
    device_id  TEXT NOT NULL,
    fault      TEXT NOT NULL,
    action     TEXT NOT NULL,
    result     TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

-- ---------------- 告警状态表（alerts） ----------------
-- 告警事件落盘；与 Redis 去重（dedup:alarm:{device}:{metric}）配合，Redis 仅作短期去重缓存
CREATE TABLE IF NOT EXISTS alerts (
    alarm_id  TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    metric    TEXT NOT NULL,
    value     NUMERIC,
    severity  TEXT NOT NULL,
    status    TEXT NOT NULL DEFAULT 'open',
    ts        TIMESTAMPTZ NOT NULL
);

-- ---------------- Outbox 一致性表（outbox，B6） ----------------
-- 写 PG 成功即写 outbox（milvus / neo4j 各一条），worker 消费后置 done；失败退避重试
CREATE TABLE IF NOT EXISTS outbox (
    id          BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,                      -- document | chunk
    entity_id   TEXT NOT NULL,
    op          TEXT NOT NULL,                      -- upsert | delete
    target      TEXT NOT NULL,                      -- milvus | neo4j
    payload     JSONB,
    status      TEXT NOT NULL DEFAULT 'pending',    -- pending | done | failed
    retry_count INT NOT NULL DEFAULT 0,
    last_error  TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- ---------------- 索引 ----------------
CREATE INDEX IF NOT EXISTS idx_doc_chunks_doc_id     ON doc_chunks (doc_id);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_parent_id  ON doc_chunks (parent_id);
CREATE INDEX IF NOT EXISTS idx_kv_doc_id             ON knowledge_versions (doc_id);
CREATE INDEX IF NOT EXISTS idx_work_orders_device_id ON work_orders (device_id);
CREATE INDEX IF NOT EXISTS idx_alerts_device_ts      ON alerts (device_id, ts DESC);
-- Outbox 消费走「取 pending」路径，用部分索引降低扫描面
CREATE INDEX IF NOT EXISTS idx_outbox_pending        ON outbox (target, created_at) WHERE status = 'pending';

COMMIT;