# P5-W4/D12~D13 安全回归报告

- **日期**：2026-10-09
- **自测脚本**：`scripts/test_p5_d12_security.py`（`.venv\Scripts\python.exe` 直跑，结果 **8/8 PASS**）
- **前置**：auscult-v2-pg(5433) + auscult-redis(6379) 在跑；对应交付物 plan/Phase 5 §5.4 W4

## 一、八项回归结果总表

| # | 项目 | 验证内容 | 关键实测 | 结果 |
|---|---|---|---|---|
| ① | Prompt 注入防御 | 10 条恶意样本（角色劫持/指令覆盖/提示提取/工具注入，中英混合） | 10/10 `injected=True`，净化后原文指令零泄漏（替换为 `[已净化]`） | **Pass** |
| ② | 工具白名单 | 白名单外工具拒绝 + 双轨审计 | `validate_tool_call("delete_all_data")=False`；JSONL 尾行 + PG audit_logs 权威层均留痕（event=tool_call, allowed=false） | **Pass** |
| ③ | 高风险确定性判定 | 规则判定无 LLM、可复现 | 「停机检修」命中关键词、「更换轴承并动火作业」命中操作；纯规则 **1.4 ms**，同输入两次结果一致，源码无模型调用引用 | **Pass** |
| ④ | 审计不可篡改 | audit_logs append-only 触发器 | INSERT 成功；UPDATE/DELETE/TRUNCATE 三类语句均被拒（异常含 append-only，ERRCODE 42501） | **Pass** |
| ⑤ | 职责分离（SoD） | 提交者不得自审 | `validate_submitter("u1","u1")=False`；`("u1","u2")=True` | **Pass** |
| ⑥ | 凭证扫描 | 全仓硬编码扫描 + env 可覆盖 | 扫 **141 文件**：无未知硬编码；JWT/PG/Redis/Neo4j/TDengine/种子密码均 `os.environ.get` 形式（dev 默认可覆盖）；main.py JWT dev 警告存在 | **Pass** |
| ⑦ | 限流熔断 | 令牌桶单元 + 端到端 | 单元：容量 3 第 4 次 `consume=False`；端到端 TestClient `POST /api/diagnose` ×4 → `[401,401,401,429]`，第 4 次 429 + `code=E_RATE_LIMITED` + `Retry-After` 头（限流先于鉴权，401 亦正确扣减令牌）；测后清理 redis key 不污染真桶 | **Pass** |
| ⑧ | 预算熔断 | 当日额度写满 → 强制降级 | 写满 340 → `check()=False`（reason=budget_exceeded）、`check_budget()=False`；恢复原值后放行 | **Pass** |

## 二、回归期间发现并修复的问题

1. **真实 bug**：`check_rate_limit` 原为同步函数，而 `main.py trace_and_envelope` 以 `await` 调用 → 端到端首次触发即 `TypeError`。**修复**：改为 `async def`（app/security/rate_limit.py）；此前自测未覆盖 POST 链路，本次 ⑦ 端到端项抓出。
2. **硬编码凭证 5 处**（⑥ 扫描发现）→ 全部改 `os.environ.get` 形式（dev 默认保留、可 env 覆盖）：
   - [query_sensor.py](file:///d:/DSHproject/auscult/app/tools/query_sensor.py)：`TDENGINE_PASSWORD`
   - [outbox_worker.py](file:///d:/DSHproject/auscult/scripts/outbox_worker.py) / [reconcile.py](file:///d:/DSHproject/auscult/scripts/reconcile.py) / [retrieval_base.py](file:///d:/DSHproject/auscult/scripts/retrieval_base.py)：`NEO4J_PASSWORD`
   - [seed_users.py](file:///d:/DSHproject/auscult/scripts/seed_users.py)：`AUSCULT_SEED_PASSWORD`
3. **扫描误报 1 处**：[llm_adapter.py](file:///d:/DSHproject/auscult/scripts/llm_adapter.py) 的 `R1_END_TOKEN`（DeepSeek-R1 特殊 token 字面量，非凭证）→ 白名单豁免并留注释。
4. ③ 断言校准：注释中「不依赖 LLM」字样会误报，改为检测真实模型调用引用（`llm_adapter/ollama/openai/requests.post`）。

## 三、新增资产（D12~D13）

| 资产 | 说明 |
|---|---|
| [db/migrations/0006_audit_logs.sql](file:///d:/DSHproject/auscult/db/migrations/0006_audit_logs.sql) | audit_logs 表 + 3 个 append-only 触发器（行级 UPDATE/DELETE + 语句级 TRUNCATE，ERRCODE 42501），已应用至 auscult_v2 |
| [app/security/pg_audit.py](file:///d:/DSHproject/auscult/app/security/pg_audit.py) | `append_audit()`：PG 审计持久化（失败 warning+False 不阻断业务） |
| [app/security/rate_limit.py](file:///d:/DSHproject/auscult/app/security/rate_limit.py) | Redis Lua 原子令牌桶；`consume()`（fail-open + 审计）+ `check_rate_limit()`（async）；参数 env `AUSCULT_RATE_LIMIT="capacity:refill"`（默认 10 : 10/60s）；429 走统一包络 + Retry-After + Prometheus 打点 |
| [scripts/test_p5_d12_security.py](file:///d:/DSHproject/auscult/scripts/test_p5_d12_security.py) | 八项回归自测脚本 |
| 修改 | [main.py](file:///d:/DSHproject/auscult/app/api/main.py)（call_next 前限流分支）；[errors.py](file:///d:/DSHproject/auscult/app/api/errors.py)（E_RATE_LIMITED→429）；[sanitizer.py](file:///d:/DSHproject/auscult/app/security/sanitizer.py)（安全事件 PG 双写） |

## 四、边界与遗留

1. 限流为**单实例进程内中间件**（Redis 桶共享但 Nginx 多上游时桶口径按 X-Forwarded-For 首跳）——单机部署形态下成立，多副本部署需网关层限流（P6 运维项）。
2. 审计超期归档不在库层开 DELETE 后门（触发器拒绝一切变更），归档由运维侧 `pg_dump` 增量处理（与 p5-backup.md §四一致）。
3. PG 双轨审计中 JSONL 为进程本地兜底、PG 为权威层；JSONL 轮转策略未定（量级极低，暂不阻塞）。

## 五、判定

M5.3（D11 备份 + D12 审计 + D13 限流/安全回归）判据全部实测通过 → **M5.3 收口**。
配套：备份演练见 [p5-backup.md](file:///d:/DSHproject/auscult/reports/p5-backup.md)（Pass，TDengine/定时备份挂 P6）。
