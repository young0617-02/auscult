-- =============================================================
-- Phase 4 迁移 0005 —— 知识文档准入审核（D0-6 契约补丁）
-- -------------------------------------------------------------
-- 上游依据： plan/Phase 4 §四.4 / V5.0 §7.1 R-M3（知识库投毒 → 文档准入审核
--           + 来源可信度分级 + 版本留痕可回滚）
-- 契约：     POST /api/knowledge/docs/{doc_id}/admission {action: approve|reject}
-- 目标实例： ParadeDB PG 18.6 @ 宿主 5433，库 auscult_v2（复用原库，2026-10-08 裁定）
-- 幂等：     IF NOT EXISTS，可重复执行
--
-- 语义：
--   admission_status = pending  待准入（上传默认态，流水线不得索引）
--   admission_status = approved 准入通过（status 由索引流水线推进 indexed/failed）
--   admission_status = rejected 准入驳回（永不进入索引，保留行供审计追溯）
--
-- 应用方式：
--   docker exec -i auscult-v2-pg psql -U root -d auscult_v2 -v ON_ERROR_STOP=1 -f - < db/migrations/0005_knowledge_admission.sql
-- 校验：
--   docker exec -it auscult-v2-pg psql -U root -d auscult_v2 -c "\d documents"
-- =============================================================

BEGIN;

ALTER TABLE documents ADD COLUMN IF NOT EXISTS admission_status TEXT
    NOT NULL DEFAULT 'pending';          -- pending | approved | rejected
ALTER TABLE documents ADD COLUMN IF NOT EXISTS admitted_by TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS admitted_at TIMESTAMPTZ;

-- 准入队列查询（kb_admin 待审列表）
CREATE INDEX IF NOT EXISTS idx_documents_admission
    ON documents (admission_status) WHERE admission_status = 'pending';

COMMIT;
