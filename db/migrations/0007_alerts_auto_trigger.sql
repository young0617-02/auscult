-- 0007：告警自动触发诊断（P7）
-- alerts.diagnosed_thread_id：权威「已触发」标记（NULL = 未触发）。
--   两阶段写入：先 'trigger-pending'（占位，防扫描-启动间隙重复触发），
--   成功后回写真实 thread_id（UI 可由此反查诊断线程）。
-- 部分索引：自动触发扫描路径（status='open' AND diagnosed_thread_id IS NULL）
--   与 outbox pending 同款低扫描面写法。
BEGIN;

ALTER TABLE alerts ADD COLUMN IF NOT EXISTS diagnosed_thread_id TEXT;

CREATE INDEX IF NOT EXISTS idx_alerts_pending_diagnosis
    ON alerts (ts ASC) WHERE diagnosed_thread_id IS NULL;

COMMIT;
