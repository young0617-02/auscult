-- =============================================================
-- Phase 5 迁移 0006 —— 审计日志表 + 防篡改触发器（P5-W4/D12 · Q2=A）
-- -------------------------------------------------------------
-- 上游依据： plan/Phase 5 §5.4 W4（审计不可篡改：直接 UPDATE → 触发器拒绝）
-- 目标实例： ParadeDB PG 18.6 @ 宿主 5433，库 auscult_v2（与 users/reports 同库）
-- 幂等：     全部 IF NOT EXISTS / OR REPLACE / DROP TRIGGER IF EXISTS
--
-- 设计（append-only）：
--   - UPDATE / DELETE：行级 BEFORE 触发器拒绝（ERRCODE 42501）
--   - TRUNCATE：语句级 BEFORE 触发器拒绝
--   - 保留策略不在库层开 DELETE 后门，超期归档由运维侧处理
--
-- 应用方式：
--   docker exec -i auscult-v2-pg psql -U root -d auscult_v2 -v ON_ERROR_STOP=1 -f - < db/migrations/0006_audit_logs.sql
-- 校验：
--   docker exec -it auscult-v2-pg psql -U root -d auscult_v2 -c "\d audit_logs"
-- =============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS audit_logs (
    id         BIGSERIAL    PRIMARY KEY,
    ts         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    trace_id   VARCHAR(32),
    event      VARCHAR(64)  NOT NULL,
    severity   VARCHAR(16)  NOT NULL DEFAULT 'info',
    thread_id  VARCHAR(64),
    actor      VARCHAR(64),
    detail     JSONB        NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_ts        ON audit_logs (ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_event     ON audit_logs (event);
CREATE INDEX IF NOT EXISTS idx_audit_logs_thread_id ON audit_logs (thread_id);

-- 防篡改触发器（append-only：拒绝一切变更语句）
CREATE OR REPLACE FUNCTION audit_logs_block_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs 为 append-only：% 被拒绝（防篡改触发器 %）',
                    TG_OP, TG_NAME
        USING ERRCODE = '42501';
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_logs_no_update ON audit_logs;
CREATE TRIGGER trg_audit_logs_no_update
    BEFORE UPDATE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_block_mutation();

DROP TRIGGER IF EXISTS trg_audit_logs_no_delete ON audit_logs;
CREATE TRIGGER trg_audit_logs_no_delete
    BEFORE DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_block_mutation();

DROP TRIGGER IF EXISTS trg_audit_logs_no_truncate ON audit_logs;
CREATE TRIGGER trg_audit_logs_no_truncate
    BEFORE TRUNCATE ON audit_logs
    FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_block_mutation();

COMMIT;
