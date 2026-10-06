# Phase 0 详细开发计划（技术验证与范围锁定 · D1–D10 可执行版）

> **上游依据**：`云侧工业 IoT 诊断 Agent 系统 - 最终执行方案（V5.0 定稿）.md` §九
> **方案定位**：本计划**替代**大纲中的 Phase 0，并把"环境搭建 / 评测集 / 模拟数据"下沉为本阶段门禁产出。
> **执行主体**：单人（"机器并行、人串行"）
> **总工期**：10 个工作日（D1–D10）+ D0 决策冻结（0.5d）
> **制定日期**：2026-09-21
> **使用方式**：逐日执行，**每个 V 项开跑前必须确认其 Pass/中间/No-Go 判据已定稿**。

---

## 目录

- [一、总览](#一总览)
- [二、D0 决策冻结（前置，0.5 天）](#二d0-决策冻结前置05-天)
- [三、逐日详细计划（D1–D10）](#三逐日详细计划d1d10)
- [四、验证项详细规格（V1–V7）](#四验证项详细规格v1v7)
- [五、门禁判据表](#五门禁判据表)
- [六、工程目录与交付物清单](#六工程目录与交付物清单)
- [七、风险与应对](#七风险与应对)
- [八、每日执行检查清单](#八每日执行检查清单)

---

## 一、总览

### 1.1 六阶段 / 十天

| 阶段 | 时间 | 核心任务 | 出口里程碑 |
|---|---|---|---|
| 一 决策冻结 | D0（0.5d） | 5 项开放问题闭环 | 定位声明 |
| 二 方案修订 | D0–D1 | 固化为规范文本（V5.0 已完成） | 执行版方案 |
| 三 基线建立 | D1 | 环境基线 + Schema v1 + 数据盘点 + 实验登记 | **M0.1** |
| 四 判据补全 | D1–D2 | 每项 V 补齐 Pass/中间/No-Go | 判据表定稿 |
| 五 主验证执行 | D2–D8 | V1/V2/V3/V5/V7/V4b 实测 | M0.2–M0.4 |
| 六 仲裁与门禁 | D8–D10 | 联合仲裁 + 版本锁定 + 门禁评审 | **M0.6** |

### 1.2 甘特（机器并行、人串行）

```
D1   ██████ V4a 约束采集 + Schema v1 + 数据盘点 + 授权确认        ★M0.1
D2   ██████ V1 工具调用（独占 GPU）  ┊ V7 评测集
D3   ██████ V1 续 + 云端 baseline    ┊ V7 评测集                ★M0.2
D4   ██████ V2 混合检索（纯 CPU）    ┊ V3 连接器/Broker
D5   ██████ V2 决策 + V3 映射/契约   ┊ 告警链路                 ★M0.3
D6   ██████ V5 checkpoint 恢复/缺陷复现 ┊ V6 MVP 范围
D7   ██████ V5 幂等/并发/体积治理        ┊ V6 MVP 范围          ★M0.4
D8   ██████ V4b 全组件压测 + 联合仲裁                            ★M0.5(部分)
D9   ██████ 版本锁定 + 风险册 + 电梯演讲                          ★M0.5
D10  ██████ M0.6 门禁评审 + P1 移交清单                           ★M0.6
```

### 1.3 验证项一览

| 编号 | 名称 | 资源占用 | 时长 |
|---|---|---|---|
| **V4a** | 约束采集（硬件/WSL2/端口/磁盘） | 低 | 0.5d |
| **V1** | LLM 工具调用能力对比 | **独占 GPU** | 1.5d |
| **V2** | 混合检索方案验证 | 纯 CPU | 1.5d |
| **V3** | TDengine + Sparkplug B 接入 | CPU | 1d |
| **V4b** | 全组件运行态资源实测 | 全组件 | 0.5d |
| **V5** | LangGraph checkpoint 可靠性 | 低 | 1.5d |
| **V6** | 数据来源与范围锁定 | 人为主导 | 0.5d |
| **V7** | 评测集与标注规范 | CPU | 0.75d |

### 1.4 三条铁律

1. **顺序不可跳**：阶段一/三必须先于阶段五，否则验证结论整批作废；
2. **判据前置**：任一 V 项开跑前，其 Pass/中间/No-Go 必须已定义；
3. **降级必带代价**：任何轻量替代都须标注对 `Recall@5`、`P95` 的影响。

---

## 二、D0 决策冻结（前置，0.5 天）

### 2.1 五项开放问题核对

| 编号 | 问题 | 状态 | 结论 |
|---|---|---|---|
| Q1 | 本方案替代还是前置于大纲 P0 | ✅ 已裁决 | **替代**；环境/评测集/模拟数据下沉为门禁产出 |
| Q2 | 开发机实际配置 | ✅ 已实测 | 32GB / RTX4060 8GB / i7-13650HX / 954GB；`.wslconfig` 待配置（D1） |
| Q3 | Milvus 目标版本 | ✅ 已锁定 | **v3.0.0**（本机镜像）；BM25 = 服务端 `FunctionType.BM25` |
| Q4 | 是否接受拆分 | ✅ 已裁决 | 接受：V4→V4a/V4b；V6→V6/V7 |
| Q5 | MinerU 解析验证归属 | ✅ 已裁决 | P1 首日 Spike + P0 遗留风险 |

### 2.2 D0 出口（DoD）

- [ ] 定位声明写入 V5.0（已完成）
- [ ] 硬件参数表填入环境基线（D1 实测补全）
- [ ] P0 遗留风险条目登记（MinerU）
- [ ] 本计划文档确认并冻结

> **结论**：D0 已在 V5.0 定稿中闭环，**可直接进入 D1**。

---

## 三、逐日详细计划（D1–D10）

### D1 · 基线建立（最高优先级，硬门禁）

> **目标**：产出一份被所有验证项引用的**唯一环境基线**，并冻结工具 Schema v1。
> **前置**：无。**出口：M0.1**

| 任务 | 步骤 | 产出物 |
|---|---|---|
| **T1.1 WSL2/Docker 配置** | 写入 `%UserProfile%\.wslconfig`（memory=20GB / processors=10 / swap=8GB）→ `wsl --shutdown` 重启 → `docker info` 核对内存上限 | `env/wslconfig.bak` |
| **T1.2 硬件采集** | 运行采集脚本，记录 CPU/内存/GPU/磁盘/CUDA/驱动 | `env/hardware.json` |
| **T1.3 端口检查** | 扫描 19530/9091/7474/7687/6030/6041/5432/6379/11434/1883/8000/3000，冲突项记重映射方案 | `env/ports.md` |
| **T1.4 组件版本登记** | `docker images` + `ollama list` + `nvidia-smi`，记录**镜像/模型 digest** | `env/env-baseline-v1.md` |
| **T1.5 目录初始化** | 按 §六 建立工程目录 | 目录树 |
| **T1.6 Schema v1 冻结** | 编写 5 工具 Pydantic ↔ JSON Schema，落盘并打版本号 | `schemas/tools_v1.json` |
| **T1.7 数据来源盘点** | 逐类盘点手册/工单/传感器：名称/格式/体量/获取方式/许可/替代 | `docs/data-sources-v1.md` |
| **T1.8 实验登记规范** | 定稿模板字段（digest/seed/prompt 版本/num_ctx/temperature/commit） | `docs/experiment-log-template.md` |
| **T1.9 TDengine 授权确认** | 查证社区版（OSS）是否含 SparkplugB 接入；不通过则立即启降级评估 | `reports/v3-auth.md` |

**关键命令**：
```powershell
# 硬件采集（PowerShell）
Get-CimInstance Win32_Processor | Select Name,NumberOfCores,NumberOfLogicalProcessors
Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum
Get-CimInstance Win32_VideoController | Select Name,AdapterRAM,DriverVersion
Get-PSDrive C | Select Used,Free
nvidia-smi
```

```bash
# 端口检查（WSL2）
for p in 19530 9091 7474 7687 6030 6041 5432 6379 11434 1883 8000 3000; do
  (echo >/dev/tcp/127.0.0.1/$p) >/dev/null 2>&1 && echo "$p OCCUPIED" || echo "$p free"
done
```

```bash
# 组件版本登记（以 digest 为准）
docker images --digests
ollama list
ollama show qwen2.5:7b --modelfile | head
```

**DoD（M0.1）**：
- [ ] `env-baseline-v1.md` 字段完整（OS/Docker/WSL2/GPU/CUDA/Python/Node/各镜像与模型 digest）
- [ ] `schemas/tools_v1.json` 落盘并标注 v1
- [ ] `data-sources-v1.md` 含兜底路线（默认自编模拟数据）
- [ ] `experiment-log-template.md` 可用
- [ ] TDengine 授权结论已出（可用 / 需降级）

---

### D2–D3 · V1 LLM 工具调用（独占 GPU） + V7 评测集

> **目标**：产出"模型 → 角色"映射表；产出 50 条种子评测集。
> **前置**：Tool Schema v1（D1）。**出口：M0.2**

**D2 上午 — 准备（不占 GPU）**
| 任务 | 说明 | 产出 |
|---|---|---|
| T2.1 用例库 | 20 条用例，含**难度分层**与**类型**（单工具/多工具/参数校验/无效拒绝/多轮），对齐主场景"离心泵轴承振动" | `evals/v1_cases.jsonl` |
| T2.2 自动判分器 | 工具名精确匹配 + JSON Schema 校验 + 参数值比对（`time_range` ±10% 语义等价）+ 重试计数 + 失败归类 | `scripts/judge_tools.py` |
| T2.3 统一适配层 | 一个入口适配两模型（OpenAI 兼容 `/v1/chat/completions`），统一**剥离 `think`** | `scripts/llm_adapter.py` |
| T2.4 落盘与统计 | 原始请求/响应 JSONL + 汇总表 + 断点续跑 | `scripts/run_v1.py` |

**D2 下午–D3 — 执行**
```bash
# 2 模型 × 20 用例 × 3 次；R1 先剥离 think 再判 JSON
python scripts/run_v1.py --models qwen2.5:7b,deepseek-r1:7b --repeat 3 --out experiments/v1/raw_results.jsonl
python scripts/run_v1.py --models <cloud-model> --repeat 1 --tag baseline_cloud   # 上界校准
```

**8 项指标（必须逐项定义并分开报）**：

| 指标 | 定义 |
|---|---|
| 工具选择准确率 | 首次响应 `tool_calls[0].name` 与期望一致比例 |
| 参数 JSON 可解析率 | 剥离 `think` 后可通过 JSON Schema 校验 |
| 参数值正确率 | 必填参数全对；枚举/ID 精确匹配，`time_range` ±10% 语义等价 |
| 无效请求拒绝率 | 应拒绝却调用 / 应调用却拒绝，**单独统计** |
| **首次成功率** | 第 1 次即全对（与重试后分开报） |
| **重试后成功率** | ≤3 次重试内全对（校验错误回灌，固定策略） |
| 平均 / P95 延迟 | 区分冷/热启动，记录输出 token 与 `think` token |
| 输出冗长度 | `think` token / 总输出 token |

**并行（V7 评测集构建）**
- 50 条问答对：问题 / 期望答案要点 / 相关文档块 ID / 类别（7 类）/ 难度
- 标注规范 v1 + 一致性检验计划（P5 双人标注算 Cohen's Kappa）
- 产出：`evals/golden_set_v1.jsonl`、`docs/labeling-spec-v1.md`

**DoD（M0.2）**：
- [ ] `reports/v1-report.md`（含 8 项指标 + 云端 baseline）
- [ ] `docs/role-decision.md`（含 70–90% 中间区间处置）
- [ ] `prompts/tool_call_prompt_v1.md`
- [ ] `evals/golden_set_v1.jsonl`（50 条）

---

### D4–D5 · V2 混合检索（纯 CPU） + V3 时序接入

> **目标**：检索路线 + 参数基线表；时序接入方案 + 告警路线。
> **前置**：V7 评测集（V2 Step2 强依赖）、V4a。**出口：M0.3**

**V2 Step 1 — 环境与版本确认**
```bash
docker run -d --name milvus -p 19530:19530 -p 9091:9091 milvusdb/milvus:v3.0.0
# 确认镜像 digest 并写入版本锁定清单
docker inspect --format='{{index .RepoDigests 0}}' milvusdb/milvus:v3.0.0
```
- [ ] 锁定唯一 Milvus 版本 + digest
- [ ] 确认 sparse/BM25 走**服务端 `FunctionType.BM25`**（`enable_analyzer=True`）
- [ ] **中文 analyzer 验证**：配置 `jieba` tokenizer + 分词结果人工抽检（≥20 条，检查工业术语切分）

**V2 Step 2 — 质量对比**
```bash
python scripts/run_v2.py --eval evals/golden_set_v1.jsonl --routes milvus,pgvector
```
- 同一评测集算 `Recall@5` / `MRR` / Top-5 相关性
- pgvector 侧用**真 BM25（ParadeDB `pg_search`）**或显式声明"仅代表 tsvector 路线"
- 参数基线表：索引类型 / 度量 / BGE-M3 维度 / analyzer / RRF k
- 压力档：**1 万–10 万块**只测延迟与内存（不做质量）

**V2 Step 3 — 决策**：结合 V4a 内存约束给出路线结论。

**V3 Step 1–3**
| 步骤 | 内容 | 产出 |
|---|---|---|
| Step1 | Broker 选型（Mosquitto 默认 / EMQX 备选）+ **连接器授权**结论 | 结论 |
| Step2 | Schema 映射：Sparkplug topic/metric → 超级表/列；覆盖 4 类边界（建表/新增 metric/re-birth/离线） | `docs/schema-mapping.md` |
| Step3 | `query_sensor` 聚合契约验证 + **告警生成路线**（阈值+滑动窗口 vs 流式） | 契约结论 |

**DoD（M0.3）**：
- [ ] Milvus 版本 + analyzer 结论、参数基线表、检索对比结论
- [ ] 时序接入决策 + Schema 映射表 + `query_sensor` 契约 + 告警路线

---

### D6–D7 · V5 checkpoint 可靠性 + V6 范围锁定

> **目标**：checkpoint 方案定论 + 审核生命周期策略。
> **前置**：无强依赖（**用确定性规则触发 interrupt，解耦 V1**）。**出口：M0.4**

**V5 Step 1–2**
| 任务 | 内容 |
|---|---|
| T5.1 最小工作流 | 3–4 节点 + 1 个 `interrupt()` 审核节点（关键词命中触发） |
| T5.2 缺陷复现 | 定向复现 `has_writes` 覆盖问题（`putWrites` 后读 `getState()`） |
| T5.3 恢复测试 | 强制杀进程/重启后从 checkpoint 恢复，校验 payload |
| T5.4 幂等验证 | 记录工具执行次数，检测恢复后重复执行 |
| T5.5 并发/多实例 | 双审核人竞争 resume、多 worker 行为 |
| T5.6 体积治理 | checkpoint 增长速率、key 数、归档与保留上限 |
| T5.7 TTL/驱逐 | 强制 `noeviction`；不设 TTL；内存上限告警 |

**Redis 模板**：
```
redis-server --appendonly yes --maxmemory 1gb --maxmemory-policy noeviction
```

**架构建议落盘**：只读工具在图内；**写操作 `generate_report` 移出图内** + 幂等键。

**V6 Step 2（并行，文档）**：Must 链 13 项逐条可验收；Won't 扩充；停止条件。

**DoD（M0.4）**：
- [ ] `reports/v5-report.md`（状态完整性 / payload / 重复执行 / 恢复耗时）
- [ ] `docs/known-issues.md`（`has_writes` / 重复执行 / TTL / 并发 → 标注"已修复/可规避/需换方案"）
- [ ] `configs/redis.conf`、`docs/checkpoint-decision.md`、`docs/review-lifecycle.md`

---

### D8 · V4b 全组件实测 + 联合仲裁

> **目标**：全组件运行态压测；一次性仲裁组合方案。**出口：M0.5(部分)**

| 任务 | 内容 |
|---|---|
| T8.1 启动矩阵 | 单启 → 组合启 → 全启，记录每步增量 |
| T8.2 资源探针 | 容器级内存/CPU 峰值、GPU 显存峰值、启动耗时 |
| T8.3 模型探针 | 7B 首 token/总延迟；BGE-M3 吞吐；reranker 单次延迟与显存 |
| T8.4 判据核算 | 峰值 ≤ 32GB × **75% = 24GB**；GPU 可直通 |
| T8.5 联合仲裁 | **先定内存档 → 再定向量库与图谱 → 最后定 Broker 与 LLM 驻留** |

> **纪律**：任何"降级后仍宣称原指标"处必须显式标注代价（见 V5.0 §3.5）。

**DoD**：`reports/v4b-report.md`（资源实测表 + 分组策略 + 替代清单 + 指标代价）

---

### D9 · 版本锁定 + 风险册 + 电梯演讲

| 任务 | 产出 |
|---|---|
| T9.1 版本锁定清单 | `docs/version-lock.md`（所有组件精确版本 + digest） |
| T9.2 风险登记册 v1 | `docs/risk-register.md`（统一字段：风险/概率/影响/触发/应对/剩余） |
| T9.3 停止条件 | 写入 `docs/scope-mvp.md` |
| T9.4 电梯演讲 | 一句话卖点 + 30 秒稿 |

**DoD（M0.5）**：版本锁定清单与各验证报告 digest 一致；MVP 范围、评测集、风险册齐备。

---

### D10 · M0.6 门禁评审 + P1 移交

| 任务 | 内容 |
|---|---|
| T10.1 逐项判定 | V1/V2/V3/V4/V5/V6-V7 判 Pass/中间/No-Go |
| T10.2 中间项处置 | 记录**具体处置动作与指标代价** |
| T10.3 报告合集 | `reports/P0-summary.md` |
| T10.4 P1 移交清单 | `docs/handover-p1.md` |

**DoD（M0.6）**：判据全部过闸；中间区间≠通过；P1 移交清单可直接作为输入基线。

---

## 四、验证项详细规格（V1–V7）

### V1 — LLM 工具调用能力对比

| 项 | 内容 |
|---|---|
| 核心目标 | 在**固定部署形态 + 固定 Schema v1**下，产出 `模型 → 角色` 映射表 |
| 输入 | Tool Schema v1；20 用例；两模型（含 digest）；Prompt v0；GPU 可用性结论 |
| 输出 | `raw_results.jsonl`、对比报告（8 指标）、分工决策（含中间区间）、Prompt v1 |
| 判据 | Pass：首次成功率 ≥90% 且可解析率 ≥95%；中间 70–90%；No-Go <70% |
| 关键风险 | `think` 污染（先剥离）、量化公平性（胜出者补 Q8/FP16 复核）、Ollama 静默退化（断言存在 `tool_calls`） |

### V2 — 混合检索方案验证

| 项 | 内容 |
|---|---|
| 核心目标 | 产出 Milvus 与 pgvector 路线的质量/复杂度/资源三维对比 + **P1 建库参数基线** |
| 输入 | 100 条模拟语料；**V7 评测集（硬依赖）**；V4a 约束 |
| 输出 | 版本结论（含 digest）、参数基线表、质量对比、工程对比、路线决策 |
| 判据 | Pass：支持 jieba analyzer + 原生 BM25，`Recall@5` 不低于对照 |
| 关键风险 | **中文分词器**（最高优先级）、BM25 路径混淆、对比不公平、规模不足 |

### V3 — TDengine + Sparkplug B 接入

| 项 | 内容 |
|---|---|
| 核心目标 | 确认组件形态/授权边界/主题→超级表映射，产出 `query_sensor` 契约可行性证明 |
| 输入 | TDengine/taosX/Broker 版本；Sparkplug 模拟器；模拟测点（振动/温度/电流） |
| 输出 | 接入报告（含授权结论）、Compose 片段、Schema 映射表、`query_sensor` 契约、告警路线 |
| 判据 | Pass：社区版可用且映射正确；中间：需自研解码 ≤2 天；No-Go：商业授权/不可控 |
| 关键风险 | 授权边界（最高）、Broker 选型反向推翻内存预算 |

### V4a / V4b — 硬件资源

| 项 | 内容 |
|---|---|
| V4a（D1） | 采集物理约束，**预先裁定**轻量替代；判据 = 峰值 ≤ 物理内存 × 75% |
| V4b（D8） | 全组件运行态压测，校准分组策略与替代清单 |
| 维度 | 内存/CPU/GPU 显存/磁盘/端口/OS-WSL2 + Neo4j + BGE 系列 |
| 关键风险 | 判据基准错误、缺 GPU 显存维度、替代代价未评估 |

### V5 — LangGraph checkpoint 可靠性

| 项 | 内容 |
|---|---|
| 核心目标 | 重启 + 跨天审核场景下验证状态完整性、幂等性、持久性 |
| 输出 | 可靠性报告、已知缺陷清单、Redis 模板、方案决策、审核生命周期策略 |
| 判据 | Pass：重启完整 + payload 正确 + 无重复副作用 + 无 TTL 丢状态 |
| 关键风险 | Redis checkpointer 为**第三方实现**；TTL/驱逐；并发 resume |

### V6 — 数据来源与范围锁定

| 项 | 内容 |
|---|---|
| 输出 | 数据来源清单（含合法性）、MVP 范围文档、**停止条件**、电梯演讲、风险册 v1、版本锁定清单 |
| 关键风险 | Must 链不完整、Won't 过窄、缺停止条件、版权判定延迟 |

### V7 — 评测集与标注规范

| 项 | 内容 |
|---|---|
| 核心目标 | 50 条种子问答对 + 标注规范 v1，作为 V2 与 P2/P5 的唯一基准 |
| 输出 | `golden_set_v1.jsonl`（问题/答案要点/文档块 ID/类别/难度）、标注规范 v1、一致性检验计划 |
| 依赖 | 上游 V6 数据盘点；下游 V2 Step2、P2、P5 |
| 关键风险 | 单人标注可信度 → 显式声明"基于模拟数据的初步验证" |

---

## 五、门禁判据表

| 验证项 | Pass | 中间区间处置 | No-Go → 备选 |
|---|---|---|---|
| **V1** | 首次成功率 ≥90% 且可解析率 ≥95% | 70–90%：约束解码 + few-shot；仍不达标→"本地推理 + 云端工具调用" | 两模型均 <70% → 云端工具调用转正 |
| **V2** | jieba analyzer + 原生 BM25；`Recall@5` ≥ 对照 | 质量接近 → 按内存约束决策 | BM25 需大量自研 → 切轻量路线 |
| **V3** | 社区版可用 + Schema 映射正确 | 自研解码器 ≤2 天 → 有条件通过 | 商业授权/不可控 → MQTT JSON 或自研消费者 |
| **V4** | 峰值 ≤ 24GB 且 GPU 可直通 | 超限 ≤10% → 分组启动 | 严重超限 → 启用降级映射并调整 MVP |
| **V5** | 重启完整 + 无重复副作用 + 无 TTL 丢状态 | 非阻塞缺陷 → 记录规避清单 | 阻塞缺陷 → 切 PostgreSQL checkpointer |
| **V6/V7** | 数据合法可用 + 评测集可执行 + Must 链完整 | 需自编 → 模拟数据交付并标注局限 | 评测集不可执行 → 需重做 |

> **纪律**：中间区间 **≠ 通过**，必须写处置动作。

### 里程碑

| 里程碑 | 内容 | 时间 | 通过条件 |
|---|---|---|---|
| M0.1 | 约束与基线锁定 | D1 | 环境基线 + Schema v1 + 数据来源清单（**口径说明 2026-09-29**：本行为精简表述；通过条件的权威清单为 `reports/daily/D1-status.md` §六 的 **6 项逐项核对表**，裁定见 `reports/P0-summary.md` §5.2 / §6.3） |
| M0.2 | V1 完成 | D3 | 分工决策表 + 指标（含云端基线） |
| M0.3 | V2 + V3 完成 | D5 | 检索路线 + 时序接入 + 告警路线 |
| M0.4 | V5 完成 | D7 | checkpoint 方案定论 |
| M0.5 | V4b + V6 + V7 完成 | D9 | 资源实测 + MVP + 评测集 + 版本锁定 |
| M0.6 | P0 门禁评审 | D10 | 判据全部过闸 |

---

## 六、工程目录与交付物清单

### 6.1 建议目录结构

```
project/
├─ docker/
│  ├─ compose.base.yml            # Milvus/etcd/MinIO/PG/Redis/Neo4j/TDengine
│  └─ compose.nginx.yml           # Phase 4+ 入口网关
├─ configs/
│  ├─ redis.conf                  # noeviction + appendonly
│  ├─ mosquitto.conf
│  └─ milvus/
├─ env/
│  ├─ env-baseline-v1.md          # ★ 唯一环境基线
│  ├─ hardware.json
│  ├─ ports.md
│  └─ wslconfig.bak
├─ schemas/
│  └─ tools_v1.json               # ★ 5 工具 Schema v1（冻结）
├─ prompts/
│  └─ tool_call_prompt_v1.md
├─ evals/
│  ├─ v1_cases.jsonl              # V1 20 用例
│  ├─ golden_set_v1.jsonl         # V7 50 条评测集
│  └─ corpora_v1/                 # V2 100 条模拟语料
├─ scripts/
│  ├─ collect_env.ps1
│  ├─ check_ports.ps1
│  ├─ llm_adapter.py
│  ├─ judge_tools.py
│  ├─ run_v1.py
│  ├─ run_v2.py
│  └─ run_v5.py
├─ experiments/
│  └─ v1/v2/v5/raw/               # 原始 JSONL（可追溯）
├─ reports/
│  ├─ v1-report.md
│  ├─ v2-report.md
│  ├─ v3-auth.md
│  ├─ v4b-report.md
│  ├─ v5-report.md
│  └─ P0-summary.md               # ★ 门禁评审合集
└─ docs/
   ├─ data-sources-v1.md
   ├─ labeling-spec-v1.md
   ├─ schema-mapping.md
   ├─ role-decision.md
   ├─ checkpoint-decision.md
   ├─ review-lifecycle.md
   ├─ known-issues.md
   ├─ risk-register.md
   ├─ version-lock.md             # ★ 版本锁定清单
   ├─ scope-mvp.md                # ★ MVP + 停止条件
   └─ handover-p1.md              # ★ P1 移交清单
```

### 6.2 交付物清单（按阶段）

| 阶段 | 交付物 |
|---|---|
| 阶段一/二 | 定位声明、拆分声明、硬件参数表、P0 遗留风险（均已在 V5.0） |
| 阶段三 | `env-baseline-v1.md`、`tools_v1.json`、`data-sources-v1.md`、`experiment-log-template.md` |
| 阶段四 | 门禁判据表定稿 |
| 阶段五 | V1 报告 + 分工决策 + Prompt v1；V2 参数基线表；V3 接入报告 + Schema 映射 + 契约；V5 报告 + 缺陷清单 + Redis 模板；V7 评测集 + 标注规范 |
| 阶段六 | 联合决策结论、版本锁定清单、P0 报告合集、P1 移交清单 |

---

## 七、风险与应对

| 编号 | 风险 | 影响 | 应对 | 阶段 |
|---|---|---|---|---|
| R1 | 阶段定位不裁决 | 返工 | 已闭环（D0） | 已完成 |
| R2 | 开发机配置未知 | 路线误判 | 已实测；D1 配 `.wslconfig` | 一/三 |
| R3 | 无统一环境基线 | 不可复现 | T1.4 强制落盘，报告引用其版本 | 三 |
| R4 | 工具 Schema 未冻结 | V1 结论短期失效 | T1.6 冻结 v1，改动即升版 | 三 |
| R5 | 评测集缺失 | V2 无判据 | V7 独立并前置到 V2 Step2 前 | 四/五 |
| R6 | 中文分词器无效 | BM25 收益为 0 | T2 强制 jieba analyzer + 人工抽检 | 四 |
| R7 | 版本描述冲突 | 验证≠开发对象 | 全文唯一版本 + digest | 一/三 |
| R8 | 连接器商业授权 | 时序路线作废 | T1.9 首步确认，不通过即启降级 | 五 |
| R9 | Broker 选型改内存预算 | V4 判据失准 | Broker 定后按最重方案重算 | 五 |
| R10 | GPU/内存争抢 | V1/V2 互拖 | V1 独占 GPU、V2 纯 CPU | 五 |
| R11 | checkpoint TTL/驱逐 | 审核不可恢复 | 不设 TTL + `noeviction` + 超时降级 | 四/五 |
| R12 | 恢复后重复副作用 | 重复报告 | 写操作移出图内 + 幂等键 | 四/五 |
| R13 | 降级后仍宣称原指标 | 结论失真 | 仲裁强制标注代价 | 六 |
| R14 | MinerU 解析质量 | P1 最大不确定项 | P1 首日 Spike + P0 遗留风险 | 一 |
| R15 | 版权/隐私判定延迟 | 唯一不可控外部依赖 | 默认自编模拟数据兜底 | 三 |
| R16 | 工期超载 | 第 1 周不可执行 | 10 工作日 + "机器并行、人串行" | 二/五 |

---

## 八、每日执行检查清单

### 通用规则（每天开工前）

- [ ] 今日 V 项的 **Pass/中间/No-Go 已定义**
- [ ] 实验按 `experiment-log-template.md` 登记（digest/seed/prompt 版本/commit）
- [ ] 原始数据落盘 `experiments/**/raw/`（可追溯，含断点续跑）
- [ ] 结论引用 `env-baseline-v1.md` 版本号

### D1 出口
- [ ] `.wslconfig` 生效（`docker info` 确认内存上限）
- [ ] `env-baseline-v1.md` 字段完整
- [ ] `tools_v1.json` 冻结
- [ ] `data-sources-v1.md` 含兜底
- [ ] TDengine 授权结论已出 → **M0.1**

### D2–D3 出口
- [ ] V1 报告 8 指标齐全（首次/重试分开 + 云端 baseline）
- [ ] 分工决策含 70–90% 中间区间
- [ ] 50 条评测集 + 标注规范 → **M0.2**

### D4–D5 出口
- [ ] Milvus digest + jieba analyzer 抽检通过
- [ ] 参数基线表 + 检索对比
- [ ] Schema 映射（4 类边界）+ `query_sensor` 契约 + 告警路线 → **M0.3**

### D6–D7 出口
- [ ] checkpoint 恢复/幂等/并发/体积 全部有结论
- [ ] Redis 模板 + 审核生命周期策略 → **M0.4**

### D8–D9 出口
- [ ] 资源实测表 + 分组策略 + 替代代价
- [ ] 版本锁定清单 + 风险册 + MVP 停止条件 → **M0.5**

### D10 出口
- [ ] 6 项验证逐项 Pass/中间/No-Go
- [ ] 中间项处置动作 + 指标代价
- [ ] 版本锁定与报告 digest 一致
- [ ] P1 移交清单可直接使用 → **M0.6**

---

## 九、时间预算

| 阶段 | 时间 | 工时性质 |
|---|---|---|
| 一 决策冻结 | D0 | 裁决类，0.5d |
| 二 方案修订 | D0–D1 | 文档流，可与执行并行 |
| 三 基线建立 | D1 | 关键路径起点 |
| 四 判据补全 | D1–D2 | 文档流，可与执行并行 |
| 五 主验证执行 | D2–D8 | 实验流，关键路径 |
| 六 仲裁与门禁 | D8–D10 | 结论收敛 |

> **并行释义**："并行任务"指**机器并行、人串行**，非同时做两件事。
> **工期纪律**：不新增验证项；新增维度一律"并入现有项"；MinerU 记为 P1 首日 Spike。
