-- =============================================================
-- Phase 4 迁移 0004 —— 用户与 RBAC（D0-1）
-- -------------------------------------------------------------
-- 上游依据： plan/Phase 4 §三 D3（登录 + 会话 + RBAC）/ V5.0 §7.2 RBAC 四角色
-- 目标实例： ParadeDB PG 18.6 @ 宿主 5433，库 auscult_v2（复用原库，2026-10-08 裁定）
-- 幂等：     全部 IF NOT EXISTS，可重复执行
-- 种子账号： 由 scripts/seed_users.py 幂等写入（bcrypt 哈希在应用层生成，
--            不依赖 pgcrypto 扩展）
--
-- 应用方式：
--   docker exec -i auscult-v2-pg psql -U root -d auscult_v2 -v ON_ERROR_STOP=1 -f - < db/migrations/0004_users.sql
-- 校验：
--   docker exec -it auscult-v2-pg psql -U root -d auscult_v2 -c "\d users"
-- =============================================================

BEGIN;

-- ---------------- 用户表（users） ----------------
-- RBAC 四角色：engineer(工程师) / reviewer(审核员) / kb_admin(知识库管理员) / sys_admin(系统管理员)
-- 职责分离（SoD）：工程师不可自审由 app.review.lifecycle.validate_submitter 后端强制，
--                前端仅做按钮禁用的体验优化
CREATE TABLE IF NOT EXISTS users (
    user_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username      VARCHAR(64)  NOT NULL UNIQUE,
    password_hash TEXT         NOT NULL,              -- bcrypt（<72 字节，应用层校验）
    display_name  TEXT         NOT NULL,
    role          VARCHAR(32)  NOT NULL
                  CHECK (role IN ('engineer','reviewer','kb_admin','sys_admin')),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  DEFAULT now(),
    updated_at    TIMESTAMPTZ  DEFAULT now()
);

-- 登录按用户名查询
CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);

COMMIT;
