# P1-D7–D8 · B5 元数据与工单导入报告（PostgreSQL）

> 来源：`plan/p1-plan-detailed.md` §四 D7–D8 · §5.8（B5 DDL）
> 目标库：`postgresql://root:123456@127.0.0.1:5433/auscult_v2`（ParadeDB PG 18 @ 宿主 5433，`auscult-v2-pg`；端口占用审计见 `env/p1-audit-ports-2026-10-08.md`）
> 脚本：`scripts/load_meta.py`（纯 stdlib + `psycopg`，`ON CONFLICT DO UPDATE` 幂等）
> 日期：2026-10-08

## 一、范围

把 B1/B2 产物与维修工单文本 metadata 落 PostgreSQL，供 Phase 2 混合检索与 Phase 3 Agent 复用。

| 表 | 来源 | 说明 |
|---|---|---|
| `documents` | `chunks/chunks_v1.jsonl`（按 doc_id 去重） | 文档元数据 + 索引状态 |
| `doc_chunks` | `chunks/chunks_v1.jsonl`（父+子块） | Parent-Child 分块 |
| `work_orders` | `parsed/workorders_*.md`（6 表） | 工单表 |

## 二、确定性映射（脚本内注释亦记载，勿改）

- `documents.doc_id = uuid5(NS,"auscult:<doc_id字符串>")` —— 幂等、可追溯。
- `doc_type`（分块中文字段）→ 枚举：设备手册→`manual`、维修工单→`work_order`、标准判据/故障案例/拓扑→`procedure`。
- `work_orders.created_at`：工单「日期」列原为合成「工作日第N天」非时间戳 → `BASE_WORKDAY(2025-06-02) + (N-1)天`（UTC）。
- `work_orders.order_id`：工单编号列在合成样本中**重复**（非唯一），为保证主键唯一，`order_id="<工单编号列>-%03d"`（按文件内行序）——该编号为合成标签，不代替业务工单号。
- `work_orders.result`：源表无结果字段 → NULL。

## 三、结果

| 表 | 行数 | 校验 |
|---|---|---|
| `documents` | **19** | 按类型：manual=4 / procedure=9 / work_order=6 |
| `doc_chunks` | **36** | 父+子块同表，`doc_id` 关联 documents |
| `work_orders` | **48** | 6 文件×8 行；`order_id` 唯一；样例 `WO-A-2024-001 / C 0泵 / 电流超限 / 更换机械密封 / 2025-06-02` |

导入前 `--selftest` 全绿（doc_type 映射完整、分块类型全覆盖、uuid5 确定性、工单 md 可解析、工作日日期映射正确）。

## 四、局限声明

> **局限声明**：本报告所有结论仅针对本次实验环境与合成模拟语料有效。`doc_id` 与 `created_at`/`order_id` 均采用确定性合成映射（上述），不代表真实业务工单号与真实时间戳；`work_orders.result` 为空。数据源为合成语料，字段口径受 MinerU 表格解析与生成器格式约束。导入幂等基于 `ON CONFLICT DO UPDATE`，若上游分块/工单源结构变更需重放完整映射逻辑。

## 五、产物清单

- `scripts/load_meta.py`
- PG `auscult_v2`：`documents` 19 / `doc_chunks` 36 / `work_orders` 48
- 校验命令：`docker exec -it auscult-v2-pg psql -U root -d auscult_v2 -c '\dt'`

## 六、下一步

1. B6（一致性：Outbox + 补偿队列 + 对账，`scripts/outbox_worker.py`、`scripts/reconcile.py`）；
2. B4「处置为」专项并入图谱（挂 P1 待办）。