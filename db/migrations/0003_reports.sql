-- =============================================================
-- Phase 3 迁移 0003 —— 诊断报告表（D19 幂等写入）
-- -------------------------------------------------------------
-- 上游依据： plan/Phase 3 §五 D9-D10 / §六.6 报告与幂等
-- 目标实例： ParadeDB PG 18.6 @ 宿主 5433，库 auscult_v2
-- 幂等：     全部 IF NOT EXISTS，可重复执行
--
-- 应用方式：
--   docker exec -i auscult-v2-pg psql -U root -d auscult_v2 -v ON_ERROR_STOP=1 -f - < db/migrations/0003_reports.sql
-- 校验：
--   docker exec -it auscult-v2-pg psql -U root -d auscult_v2 -c "\d reports"
-- =============================================================

BEGIN;

-- ---------------- 诊断报告表（reports） ----------------
-- 图外写入（finalize 仅生成 report_id，API 层调用 generate_report 幂等写入）
CREATE TABLE IF NOT EXISTS reports (
    report_id        VARCHAR(20) PRIMARY KEY,         -- RPT-<sha256[:16]>
    idempotency_key  VARCHAR(16) NOT NULL,            -- sha256(thread_id:citations:risk_level)[:16]
    thread_id        VARCHAR(255) NOT NULL,
    payload          JSONB NOT NULL,                  -- 诊断结果快照
    risk_level       VARCHAR(10) NOT NULL,            -- low / medium / high
    confidence       FLOAT,
    review_status    VARCHAR(20),                     -- approved / rejected / timeout / auto_approved / null
    degrade_reason   TEXT,                            -- 降级原因（如有）
    created_at       TIMESTAMPTZ DEFAULT now()
);

-- 幂等唯一索引：相同 thread + 引用集 + 风险等级 → 相同 report_id
CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_idempotency
    ON reports(idempotency_key);

-- 辅助索引：按 thread_id 查报告
CREATE INDEX IF NOT EXISTS idx_reports_thread
    ON reports(thread_id);

COMMIT;
