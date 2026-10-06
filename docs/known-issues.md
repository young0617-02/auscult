# 已知缺陷清单（Known Issues）v1

> **对应验证项**：V5（主）/ V1 / V3 ｜ **里程碑**：M0.4（随 V5 完成）；新发现项随 D8–D10 追加
> **上游依据**：`云侧工业 IoT 诊断 Agent 系统 - 最终执行方案（V5.0 定稿）.md` §6.4
> **版本**：v1 ｜ **制定日期**：D1（预登记）｜ **最近更新**：2026-10-06（新增 **ISS-030** 无回归测试防护、**ISS-031** 判分器对非字符串 `aggregation` 崩溃，均当日闭环；2026-10-05 新增 ISS-027 / ISS-028 / ISS-029）
> **收录范围**：**ISS-001 – ISS-031**，覆盖 V1 / V2 / V3 / V5 / V4a / V4b 及工程侧（按"对应验证项"列区分，不限于 V5）
> **状态**：✅ **ISS-001 – ISS-014 已全部回填结论**（§二 主表；ISS-011/012/013 的复现记录见 §六）；
> **ISS-015 – ISS-023 为 2026-09-29 代码—文档一致性审计新增项**（见 §二 主表）。**ISS-012 量化档已于 2026-09-29 实测拉齐（均 Q4_K_M）**，ISS-014 已于 2026-09-29 闭环（EXP-R4-001 Pass）；
> **ISS-024（few-shot 恒取 v1）为 2026-09-30 P6 拆步落地时发现并修复**（复现记录见 §六），EXP-V1-009/010 为修复后新口径；
> **ISS-025（云端路径亦 No-Go、参数值语义为跨模型共同瓶颈）为 2026-09-30 P7 混合形态实测（EXP-M02-001）新增**（复现记录见 §六），**2026-09-30 复审已执行（F1–F6），结论更新见本行末与 §六**；
> **ISS-026（拒止行为对 system prompt 文本高度敏感、不可迁移）为 2026-09-30 V1 判据/用例口径复审（F2 四臂 EXP-M02-002）新增**（复现记录见 §六）。

---

## 一、使用规则

| # | 规则 |
|---|---|
| 1 | **`状态` 字段必须从「已修复 / 可规避 / 需换方案」中三选一**，禁止留空、禁止写"待观察" |
| 2 | 「需换方案」= 触发 `docs/checkpoint-decision.md` §5.1 的阻塞缺陷（B1–B7）→ 必须启动降级路径 |
| 3 | 每条缺陷必须指定**对应验证项**与**是否已登记到风险册**（`docs/risk-register.md`） |
| 4 | 缺陷编号一经分配**不得复用**；缺陷关闭后保留行（不删除），仅在状态列标注"已修复" |
| 5 | 凡标注「可规避」的，**规避手段必须具体到可执行步骤**，不得写"注意一下" |
| 6 | 本清单在 P0 结束时随 `docs/handover-p1.md` 移交，未闭环项自动成为 P1 遗留问题 |

---

## 二、缺陷清单（主表）

| 缺陷编号 | 所属组件 | 现象 | 复现条件 | 影响 | 严重级别 | **状态（三选一）** | 规避手段 | 对应验证项 | 已登记风险册 |
|---|---|---|---|---|---|---|---|---|---|
| **ISS-001** | LangGraph checkpoint（`has_writes` 行为） | `putWrites()` 写入后，读 `getState()` 得到的 `has_writes` 标志与预期不符；已写入的 writes 可能被后续写入**覆盖** | T5.2：最小工作流中在 `interrupt()` 前后各 `putWrites()` 一次，随后读 `getState()` 比对 | 状态机判断依据不可信；可能导致审核状态被错误覆盖 | 🟡 **PG 路线未复现** | ✅ **可规避（未复现）** | ① 不依赖 `has_writes` 做业务判断，改用**业务层显式状态字段**；② writes 追加而非覆盖；③ **PG 路线实测使用正确探针签名（`before.config` + 正确 writes 格式）后未复现，走 Pass** | **V5** | ✅ R11 / R-M5 |
| **ISS-002** | LangGraph checkpoint / 工具执行 | **恢复后重复副作用**：进程重启后从 checkpoint 恢复，之前的工具节点被重放，导致重复执行 | T5.4：记录工具执行次数，杀进程重启后比对次数 | 重复生成报告、重复落库、重复通知 | 🟡 **PG 路线已规避** | ✅ **可规避** | ① **`generate_report` 移出图内**，在审核通过后由图外调用；② 携带 `idempotency_key` + PG 唯一索引；③ 只读工具天然幂等，重放无害。**实测**：重复落库 **0 次**，只读工具重放 **2 次**（天然幂等，放行） | **V5** | ✅ R12 |
| **ISS-003** | Redis checkpointer | **TTL/驱逐导致丢状态**：checkpoint 在内存压力下被 LRU/LFU/随机策略静默删除，或 TTL 到期删除 | T5.7：① 配置非 `noeviction` 策略并压测；② 给 `ckpt:*` 设短 TTL 观察 | 审核中的流程状态**永久丢失**，审核人操作时找不到流程 | 🟡 **PG 路线 N/A（未触发）** | ✅ **可规避** | ① 实例级 `maxmemory-policy noeviction`；② checkpoint 类 key **一律不设 TTL**；③ `maxmemory 1gb` + 80%/95% 内存告警；④ **PG 路线无驱逐/TTL → 无丢状态**；⑤ 达上限时写操作显式报错 | **V5** | ✅ R11 |
| **ISS-004** | 审核并发控制 | **双审核人并发 resume**：两人同时点"通过"，触发两次 resume，**产生两份报告** | T5.5：脚本并发触发 2 次审核请求；另测"持锁超过 30s 后二次提交" | 重复报告落库、状态冲突、责任不清 | 🟡 **PG 路线唯一性成立** | ✅ **可规避** | ① `lock:review:{thread_id}` SETNX + `PX 30000`，锁值=reviewer_id（Lua 脚本保证只删自己的锁）；② **PG 唯一索引 + 幂等键兜底**（实测：EXP-V5-003-T 多次 resume 后 `report_store.json` 仅 **1** 条，只产一份报告） | **V5** | ✅ R12 |
| **ISS-005** | Redis checkpointer | **Redis checkpointer 为第三方实现**（非 LangGraph 官方核心），版本兼容性与行为一致性无官方保证。**B7 根因修正**：不是"缺 RediSearch"，而是 **redis-py（客户端）↔redis-stack（服务端）连接握手被服务端关闭**（"Connection closed by server"，redis-py 8.1.0/6.3.0 均复现，走 `CLIENT SETINFO` / `on_connect_check_health`；`redis-cli` 正常 PONG） | 持续观察；在 T5.5 起走 redis-py 均失败 | 不可预期的状态异常；**候选 A 无法使用** | 🟠 **高（B7 阻塞，触发换方案）** | ✅ **需换方案（已切 PG）** | ① 锁定精确版本（`langgraph-checkpoint-redis==0.5.2`，写入 `docs/version-lock.md`）；② **已切换官方 `langgraph-checkpoint-postgres==3.1.2`（候选 B）**，T5.1–T5.7 全部 Pass；③ 本缺陷走"需换方案"并在 `docs/checkpoint-decision.md` §2.1 与 `docs/risk-register.md` 闭环 | **V5** | ✅ R-M5 |
| **ISS-006** | Redis checkpoint 体积 | **体积增长无上限**：checkpoint 随对话/审核轮次持续增长，key 数与内存单调上升，无归档与保留上限 | T5.6：连续跑 N 次诊断，采样 `DBSIZE`、`used_memory`、单 thread 体积 | 达到 `maxmemory` 后**写操作失败**，审核流程中断；内存与其它容器争抢 | 🟡 **PG 侧有界（296KB/thread）** | ✅ **可规避** | ① **审核达终态即归档** checkpoint；② 按 thread 保留最近 N 个版本（**实测建议 N=20**）；③ 监控 key 数与内存曲线。**实测**：4 表合计 **296KB**（单 thread），增长有界，可归档 | **V5** | ✅ R11 / R13 |
| **ISS-007** | WSL2 / Docker 资源配额 | **WSL2 内存配额未落地**：`.wslconfig` 尚未安装，Docker 当前内存上限仅 **15.51GB**（= 32GB 的 50%），而设计值为 `memory=20GB / processors=10 / swap=8GB` | T1.1：检查 `%UserProfile%\.wslconfig` 是否存在；`docker info` 查看内存上限 | **V4b 全组件压测结论无效**（在错误配额下测得）；V4 判据"峰值 ≤ 24GB"无法验证；所有依赖内存的结论不可比 | 🔴 **阻塞** | ✅ **已修复（2026-09-24 闭环）** | ① 写入 `.wslconfig`（memory=20GB / processors=10 / swap=8GB）；② `wsl --shutdown` 重启；③ `docker info` 核对内存上限；④ 备份原配置到 `env/wslconfig.bak`；⑤ **未生效前不得开展 V4b**。**实测**：`MemTotal ≈20GB` / `NCPU=10` / `Swap=8192 MiB`（见 `env/env-baseline-v2.md` §五） | **V4a / V4b** | ✅ R-新1 |
| **ISS-008** | WSL2 GPU 直通 | **本机只有 `docker-desktop` 工具发行版，无通用 Linux 发行版** → GPU 直通（CUDA in container）**未验证**；`nvidia-smi` 在 WSL2 内不可用 | 在 WSL2 内执行 `nvidia-smi`；检查 `wsl -l -v` 确认发行版列表 | V4 判据"GPU 可直通"无法确认；若不可直通，容器内推理方案需改为宿主机进程 → 影响 V1/V4b 部署形态 | 🟡 **已裁决（非阻塞）** | ✅ **已裁决（改走宿主 Ollama，2026-09-24）** | ① 安装一个通用发行版（如 Ubuntu）；② 或改为**宿主机原生 Ollama**（已验证可用：Ollama 0.34.2 @ `http://127.0.0.1:11434`），容器只做 DB；③ 结论写入 `docs/version-lock.md` 与 V4b 报告 | **V4a / V4b / V1** | ✅ R-新2 |
| **ISS-009** | Ollama | **版本漂移**：当前 0.34.2，存在 **0.34.3** 可升级；升级会改变模型行为与 `tool_calls` 输出细节 | 检查 `ollama --version`；对比升级前后 V1 用例结果 | V1 结论短期失效；实验不可复现（同一用例不同结果） | 中 | ✅ **已锁定 0.34.2（不升级）** | ① **V1 全流程固定在同一版本（0.34.2）**；② 若中途升级 → **V1 全部重跑**并升版环境基线；③ 版本写入 `docs/version-lock.md`；④ 报告中必须写 Ollama 版本 | **V1** | ✅ R-新3 |
| **ISS-010** | TDengine / taosX | **授权已查证（2026-09-24，文档层 + 实物层）**：官方 Sparkplug B 连接器仅随 All-in-One/Enterprise（IDMP + taosX 体系）；OSS 镜像 `tdengine/tsdb:3.3.8.0` **无 taosX / 连接器**（已实测） | T1.9：已产出 `reports/v3-auth.md`，判定**需降级（OSS + 自研 Sparkplug B 解码器 ≤2 天）** | 官方连接器不可用；采用 OSS + 自研解码器（订阅 MQTT → 自解析 DBIRTH/DDATA/NDEATH → 写 TDengine）；若自研耗时 >2 天改判 No-Go 切 MQTT JSON 直写 | 🟡 **已定稿（有条件通过）** | ✅ **已定稿 2026-09-24** | ① 已定稿：授权不阻塞；② 启动自研解码器方案 + 工期估算（≤2 天，`reports/v3-auth.md` §三口径）；③ **Broker 定后按最重方案重算内存** | **V3 / V4b** | ✅ R8 / R-新4 |
| **ISS-011** | LLM 输出解析 | **`think` 污染**：`deepseek-r1:7b` 输出夹带 `think` 推理块，直接判 JSON 会**把格式失败误判为能力不足** | V1：对 `deepseek-r1:7b` 直接解析响应为 JSON | 低估模型能力 → 错误分工决策 | 中 | ✅ **已修复（2026-09-29，可解析率 1.00）** | ① `scripts/llm_adapter.py` **统一剥离 `think` 后再判 JSON**；② 两模型走同一入口；③ 剥离逻辑须有单测；④ 单列统计"think 污染率"与"输出冗长度" | **V1** | ✅ R-新5 |
| **ISS-012** | 模型对比公平性 | **量化档不一致**导致对比不公平（如 Q4_K_M vs Q8_0），模型输在数值精度而非能力 | V1：`ollama show <model> --modelfile` 查看两模型量化档并比对 | 分工决策建立在不可比数字上 | 中 | ✅ **已修复（拉齐，2026-09-29 实测）** | ① **已实测拉齐：两模型均 `Q4_K_M`**（qwen2.5:7b 7.6B / deepseek-r1:7b 7.6B，`ollama show` 实测，2026-09-29）→ 对比公平性成立；② **胜出者补 Q8/FP16 复核**（V1 结论是否在更高精度档不倒转）→ **P1 遗留**，当前不阻塞；③ 无法拉齐则显式声明不公平 | **V1** | ✅ R-新6 |
| **ISS-013** | Ollama 服务行为 | **静默退化**：Ollama 在某些请求下返回 200 但**无 `tool_calls`**（退化为纯文本），不报错 | V1：批量调用中捕获"响应成功但无 tool_calls"的条目 | 缺失数据被计入失败统计 → 指标失真 | 中 | ✅ **已修复（本地 0 次退化；云端 2 次且已单独归类）** | ① **`scripts/llm_adapter.py` 在解析后置位 `AdapterResult.tool_calls_missing=True`**（**不抛异常**，避免单条失败中断整批；`ToolCallsMissingError` 仅供调用方按需 raise）；② 判分器据此记 **`格式退化`**、重试计数 +1、**单独统计次数**，不得记为「工具名错」；③ 原始响应完整落盘以便事后复核；④ 次数写入实验登记 `anomalies` 字段 | **V1** | ✅ R-新3 |
| **ISS-014** | R-4 证据归纳/诊断推理 | **本地可用性未验证** | P1 专项：读证据→写根因/结论→带 `evidence_refs` 引用的端到端用例 | 分工"R-4 证据归纳本地"正确性未证明 → 若本地不可用且云端不传证据原文，则证据归纳无落点 | 中 | ✅ **已闭环（EXP-R4-001 实测 Pass，2026-09-29）** | ① 专项资产：`evals/r4_cases.jsonl`（20 条）/ `prompts/r4_prompt_v1.md` / `scripts/judge_r4.py` / `scripts/run_r4.py`；② **实测（EXP-R4-001，81 响应）整体 Pass**：结构 0.96（78/81）/ 引用忠实 1.0（81/81）/ **幻觉红线 0** / 覆盖 0.96（78/81）/ 根因 0.93（75/81）/ severity 0.89（72/81）/ 动作非空 0.96（78/81）；③ 判据见 `docs/gate-criteria.md` §3.7，均已过 Pass 线；④ 原 `qwen 0.67` 为多轮工具调用分数、非证据归纳分数，已由本专项纠正；⑤ 结论回填 role-decision §6.1 R-4 与 scope-mvp §六 | 非 V1-判据（P1） | ✅ R-新7（2026-09-29） |
| **ISS-015** | Redis 配置 / 容器网络（`configs/redis.conf`） | `bind 127.0.0.1` + `protected-mode yes` 在 **Docker 容器**形态下不可用：容器内仅监听回环，docker-proxy 与同网段其它容器均连不上（且无 `requirepass` 时 protected-mode 仍拒绝非回环客户端） | `docker compose -f docker/compose.base.yml up -d redis` 后，从宿主或其它容器 `redis-cli -h <container-ip> ping` | 审核锁 `lock:review:*` 跨容器不可用；V5 的 t5.5–t5.7（Redis 侧检查）在容器形态下无法复现 | 🟠 中 | ✅ **可规避** | ① 宿主原生 `redis-server` 形态下保持现配置（本项目 V5 实测口径）；② 容器形态改用 `bind 0.0.0.0` + `protected-mode no`（`configs/redis.conf` 已给出注释化的替代块）；③ **P1 应改为 `requirepass` + 客户端带密**，避免无鉴权暴露 | **V5** | 待补登记 |
| **ISS-016** | V1 判分器（`scripts/judge_tools.py`） | 指标列名 `1b_多工具集合覆盖` 与实现语义不符：实际判据是 `Counter(expected) == Counter(actual)`（**多重集精确相等，多给工具即判否**），而"覆盖"一词易被读成"超集可接受"（数组类参数确为超集口径） | 读 `judge_tools.judge_record` 中 `tool_set_match` 的 Counter 相等判断 | 指标口径被误读，可能高估/低估模型的多工具编排能力 | 低 | ✅ **可规避** | ① 已在该函数 docstring 显式写明"多重集精确相等"；② **列名保持不变**以兼容既有 `summary-*.csv`（改名会使历史汇总不可比）；③ 下一版判分器统一改名为 `1b_多工具集合精确匹配` 并同步历史表 | **V1** | 待补登记 |
| **ISS-017** | 自研解码器（`scripts/self_decoder.py`） | **心跳超时兜底未实现**：`docs/schema-mapping.md` §5.4 与 `configs/decoder_schema_mapping.json` 的 `boundary_handling.offline.heartbeat_timeout` 要求"超过 3×上报周期无 DDATA → 置离线并告警"，代码只处理显式 `DDEATH`/`NDEATH`，**无超时计时器** | 让模拟器停止发 DDATA 且不发 DDEATH，观察 `st_device_status.online` 是否翻转 | 设备/网络静默失联（未触发 MQTT Will）时离线状态不翻转 → 告警漏报 | 中 | ✅ **可规避**（当前依赖显式离线报文） | ① Mosquitto 启用持久化并配置 Will 指向 `NDEATH`/`DDEATH`；② 解码侧补心跳计时器（**P1 任务**）；③ 在此之前，报告不得声称"离线由心跳超时兜底" | **V3** | 待补登记 |
| **ISS-018** | 环境采集（`env/hardware.json` / `scripts/collect_env.ps1`） | `env/hardware.json` 停留在 **v1 口径**且与 `env/env-baseline-v2.md` 大面积冲突：`gpu=null`、`wslconfig_present=false`、Docker `mem_total_gb=15.51` / `ncpu=20`、采集时间 `2026-09-23T20:59:50` | 逐字段比对 `env/hardware.json` 与 `env/env-baseline-v2.md` | 报告若引用本文件会得出错误环境结论（GPU 不可用、配额未落地） | 🟠 中 | ✅ **已修复（2026-09-29 闭环）** | ① 采集脚本缺陷已修并实测跑通（ISS-019/020/021）；② **`env/hardware.json` 已重采覆盖**（`collected_at = 2026-09-29T11:49:36+08:00`，**零警告**），GPU 由 `null` → `RTX 4060 Laptop / 8188 MiB / 616.56 / CC 8.9`，Docker `15.51 GB / ncpu 20` → `19.53 GB / ncpu 10`，`wslconfig_present` 由 `false` → `true`，三模型 layer digest 齐全；③ 重采值与 `env-baseline-v2.md` **逐项一致**（互为佐证）；④ 旧 v1 快照留档 `env/hardware-v1-2026-09-23.json`；⑤ 重采时 Ollama 服务未运行，`toolchain.ollama` 记为 `UNKNOWN`，**版本仍以锁定的 0.34.2 为准** | **V4a** | 待补登记 |
| **ISS-019** | 采集脚本 / WSL 交互（`scripts/collect_env.ps1`） | **发行版停止时整个采集永久挂起**：脚本无条件执行 `wsl -d docker-desktop -- sh -c ...`，当 `docker-desktop` 处于 `Stopped` 时 WSL 会尝试启动该发行版并长时间阻塞，导致快照**一个字节都写不出**（实测挂起 >120s） | `wsl -l -v` 显示 `docker-desktop Stopped` 时运行采集脚本 | 环境快照完全无法产出；且现象是"卡住"而非报错，极难定位 | 🟠 中 | ✅ **已修复** | ① 先解析 `wsl -l -v` 的发行版**状态**，仅当 `Running` 时才进入发行版执行；② 否则写 `distro_state` 并把 `live_raw` / `gpu_passthrough_in_wsl` 标为 `SKIPPED` + 记一条 warning；③ 已实测：`Stopped` 状态下脚本正常结束（exit 0）并落盘 | **V4a** | 待补登记 |
| **ISS-020** | 采集脚本 / JSON 序列化（`scripts/collect_env.ps1`） | **含 NUL 的字符串让 `ConvertTo-Json` 挂起或抛 OOM**：`wsl.exe` 输出为 UTF-16LE，经单字节码页解码后字符串里夹带 `\0` 等控制字符；PS 5.1 的 `ConvertTo-Json` 对这类字符串会抛 `OutOfMemoryException`（首次观测）甚至长时间不返回 → 整份快照写失败 | 运行采集脚本（`$wsl.version_raw` 含 NUL） | 环境快照无法产出 | 🟠 中 | ✅ **已修复** | ① 新增 `Repair-String`（去掉控制字符与非配对代理项）与 `ConvertTo-JsonSafe`（递归净化对象图）；② **序列化按分区进行**，单个分区失败只置 `null` 并记 warning，不再拖垮整份快照；③ 已实测：脚本 exit 0、产出 14 KB JSON | **V4a** | 待补登记 |
| **ISS-021** | PowerShell 脚本编码约束（`scripts/*.ps1`） | **非 ASCII 注释会损坏脚本解析**：两个 `.ps1` 均声明"ASCII-only on purpose"（PS 5.1 按 ANSI 码页读取无 BOM 的 `.ps1`），一旦写入 UTF-8 中文注释，中文字节被按 CP936 解码后会**吞掉后续换行与花括号**，造成 `Unexpected token '}'` 之类的语法错误 | 向 `.ps1` 写入任何非 ASCII 字符后用 PowerShell 解析 | 脚本完全无法执行；报错位置与实际原因相距甚远 | 🟠 中 | ✅ **已修复** | ① 两个脚本已恢复为**纯 ASCII**（实测 nonASCII 字节数 = 0，`Parser::ParseFile` 零错误）；② 在两份脚本的头部注释处**重申该约束**；③ **新增编辑纪律：任何 `.ps1` 改动后必须检查非 ASCII 字节数为 0**（见 `CHANGELOG.md` 2026-09-29 条目） | **V4a** | 待补登记 |
| **ISS-022** | WSL2 侧端口探活（`scripts/check_ports.ps1`） | **原探活方式在 `docker-desktop` 发行版中根本不可用**：busybox `sh` 不支持 `/dev/tcp` 重定向 → 恒报 `free`（**假阴性**，测不出真实占用）；改用 `bash -c` 后又实测 `bash` **未安装**（`/bin/sh: bash: not found`）→ 恒报 `unknown`。**T1.3 的"WSL2 侧端口可用性"结论此前无有效依据** | `wsl -d docker-desktop -- sh -c 'echo >/dev/tcp/127.0.0.1/19530'`（恒 free）；`wsl -d docker-desktop -- bash -c ...`（bash not found） | 端口冲突可能在 WSL2 侧被漏检，或结论无法复现 | 🟠 中 | ✅ **已修复** | ① 发行版内实测可用工具为 `netstat`（`/bin/netstat`）/ `nc`（`/usr/bin/nc`），`bash`/`ss` 缺失；② 改为**在发行版内执行一次 `netstat -ltn`、在 PowerShell 侧解析**监听端口集合，再逐个比对，把 12 次 `wsl` 调用降为 1 次；③ 与发行版内实际可见的监听端口（53/55677/9848/8848/8080）交叉自洽；④ 已实测输出 `distro state: Running` + 12 端口逐个判定 | **V4a** | 待补登记 |
| **ISS-023** | V2 汇总表落盘（`scripts/run_v2.py` → `write_summary`） | **每次 run 整表覆盖**：以 `"w"` 模式重写 `experiments/v2/summary.csv`，只跑单条路线时会把其它路线的已实测结果一并清掉——该文件一度只剩 2 行（`EXP-V2-milvus-hybrid` / `EXP-V2-pgvector-hybrid-paradedb`），须回 `raw/*.jsonl` 才能还原；且残留的 `milvus-hybrid` 行延迟字段来自另一次 run（mean 158.7872 / p95 110.0240），与 `reports/v2-report.md` §4.4 引用的 p95 **9.4800** 不符 | 连续两次以不同 `--routes` / `--mode` 运行 `run_v2.py` | 汇总对比表与报告口径脱节，破坏"结论可追溯"；易被误当作权威数字引用 | 🟠 中 | ✅ **已修复** | ① `write_summary` 改为**按 `experiment_id` 合并**：读回既有表 → 用本次结果覆盖同 id 行 → 其余保留 → 列集合取并集后重写（已用两次不同路线验证合并与幂等）；② **历史数据已用 `raw/*.jsonl` 还原**：`summary.csv` 由 2 行补全为 **7 行**，recall/mrr/p95 与 `reports/v2-report.md` §4.4 **逐项一致**（含修正 `milvus-hybrid` 行的延迟口径）；③ 原表留档 `experiments/v2/summary-pre-2026-09-29.csv`；④ 无原始文件可还原的 `EXP-V2-pgvector-hybrid-paradedb` 行原样保留（其出处为 `experiments/v2/raw/EXP-V2-BM25.md`） | **V2** | 待补登记 |
| **ISS-024** | V1 提示词装配（`scripts/llm_adapter.py` → `build_messages`） | **few-shot 恒取 v1**：`build_messages` 调 `load_fewshot()` 时未传路径，落回默认 `PROMPT_PATH = tool_call_prompt_v1.md`；当 `--prompt` 指向 v2 / step 提示词时，**system 用了新提示词、few-shot 却仍是 v1 的 3 条** → EXP-V1-004/006/007/008 宣称的"few-shot 3→8 扩容"**实际从未生效** | `python scripts/run_v1.py --prompt prompts/tool_call_prompt_v2.md ... --dry-run`，预览 messages 的 few-shot 只出现 3 条，且含仅存在于 `tool_call_prompt_v1.md` 的文本"查一下 PUMP-A-01 最近 24 小时的振动情况，看看有没有超标" | 历史实验的"提示词增强"实为**只改 system、未改 few-shot**，变量不干净；但 EXP-V1-004/006/007/008 结论方向（均为 No-Go）**不变**；EXP-V1-009/010 已用修复后 harness 干净重跑作为新口径 | 🟠 高 | ✅ **已修复（2026-09-30）** | ① `build_messages` 新增 `prompt_path` 参数，令 system 与 few-shot **同源**；② 三处调用（`run_group` / `run_step_chain_group` / dry-run）显式传 `adapter.prompt_path`（步骤链传 `--prompt-step`）；③ `--selftest` 新增防回归自检：同一输入下 v2 装配出的 messages 条数必须多于 v1；④ 修复后 dry-run 已确认 few-shot 来自 v2；⑤ **历史 raw 不追改**，仅在新实验记录中标注口径 | **V1** | 待补登记 |
| **ISS-025** | V1 云端工具调用路径（R-2/R-3 上云，P7 方案 A） | **云端路径亦 No-Go，瓶颈收敛到"参数值语义"**：`EXP-M02-001`（云端 `Qwen/Qwen3.8-27B` × `v1_cases` 20 用例 × 1，Schema v2 结构化输出，多工具不拆步）首次成功率仅 **0.60（12/20）**；即便 27B，**单工具 67% / 多轮 33% / 无效拒绝 67% 均 <70%**，参数校验 75%、多工具 50% 落中间。多工具**集合覆盖 1.00**（编排本身无问题）但**用例级仅 50%** → 失败集中在**参数值**（参数值正确率 **0.5882**，与本地/云端历史口径同源）；另 `v1-001` 出现 **1 例格式退化**。即"云端大模型能解决工具调用"的隐含前提**不成立** | `python scripts/run_v1.py --models "Qwen/Qwen3.8-27B@https://api-inference.modelscope.cn/v1/chat/completions" --constrain --repeat 1 --tag m02-hybrid-cloud --out experiments/v1/raw/EXP-M02-001.jsonl`，再 `python scripts/judge_tools.py --raw experiments/v1/raw/EXP-M02-001.jsonl --out experiments/v1/summary-EXP-M02-001.csv` | 继续"换/加模型"的收益可疑；V1 处置链 ①②③④ 已全部执行仍 No-Go，**问题定位在判据/用例侧的参数值口径**而非模型能力 | 🟠 中（**口径问题，非实现缺陷**） | ✅ **已闭环处置（复审已执行，2026-09-30）** | ① **已执行复审**：F1（`llm_adapter` 兼容裸单对象）/ F4（`_query_semantic_match` 增关键概念覆盖）/ F5（v1-018 `aggregation` 多解）/ F6（`_refs_type_ok` 对齐规格「至少一条」）落地并重判 11 实验 19 组（首次成功率 +0.05~+0.12，**整体档位无一翻 Pass、单工具档全 No-Go**）；F2（补 `schemas/tools_v4.json` 测点目录）四臂重测（`EXP-M02-002`）**采纳形态 = 只补 schema + 保留 prompt v1**（prompt v3 未采纳），四臂整体仍全 No-Go；② **M0.2 维持 No-Go**，归因修订为「判据口径缺陷 + 任务信息不足 + 模型部分错」混合归因；③ 口径复审前**不再投入换/加模型**（复审后亦然，除非有新的可证实口径缺陷）；④ 历史实验按新口径重判并留痕（历史 raw 不追改）；⑤ 遗留 `OBS-F2-1~3` + F3 转 P1；⑥ **【2026-10-06 H9 同通道实测后的限定性修正】** 本条"**参数值语义为跨模型共同瓶颈**"的表述**须限定范围**：同通道（`tools`）下两个本地 7B 的**失败主因并不相同** —— `qwen2.5:7b` 以**参数值错**为主（18 条），`deepseek-r1:7b` 以**格式退化 / 未调用工具**为主（14 条）。故只能表述为"**参数值语义是两个模型都需面对的瓶颈之一**"，**不得**说成"共同的首要瓶颈"。证据：`experiments/v1/EXP-M02-017.md` §〇 结论 3 | **V1** | ✅ **R-V1-7（2026-09-30 复审后更新）** |
| **ISS-026** | V1 提示词/判据（system prompt 文本条件化效应） | **拒止行为对 system prompt 文本高度敏感、且效应不可迁移**：F2 四臂重测（`EXP-M02-002`）中，臂 C（prompt v1 + `tools_v4`）相对臂 A（prompt v1 + `tools_v2`）**只改了 `query_sensor.sensor_ids` 一段描述**（5 个规范测点目录），却把**与测点命名完全无关**的用例一并翻转——`v1-016`（缺设备号应拒绝却调用）与 `v1-017`（寿命预测）从 **0/9 → 9/9**，无效拒绝类从 0/9 → 9/9（臂 B/D 对照：D 逐字重跑 A 复现 19/20 一致、A/D 拒止同为 0/9）。即：**system prompt 的一段文本变动即可整体改变拒止行为**，属"提示词条件化副作用"，在该配置内可复现但**不可迁移**，不构成能力证据 | 对同一 `evals/v1_cases.jsonl` 用例集，改动 `schemas/tools_*.json` 的描述文本后重跑（`EXP-M02-002` 臂 A vs C），观察与测点命名无关用例的判定翻转 | 若把该效应误读为"F2 提升了模型能力/拒止能力"，会把**不可迁移的提示词副作用**写成能力结论 → 分工决策被污染；且拒止判据对 prompt 文本敏感 → 拒止类指标跨 prompt 版本**不可直接比较** | 🟠 中（**结论可信度风险，非实现缺陷**） | ✅ **已登记（2026-09-30）** | ① 凡涉及不同 prompt 版本/文本的拒止类指标对比，**必须声明版本并交叉验证**，不得跨版本直接比较；② 本效应**不得**作为"F2 有效"或"模型能力提升"的证据（`gate-criteria.md` §3.1.1 已按诚实边界声明）；③ 后续 prompt 变更须重跑拒止类基线并留痕；④ 转 P1：复核拒止判据对 prompt 文本的敏感性，评估是否需要文本无关的拒止评测 | **V1** | ✅ **R-V1-8（2026-09-30 新增）** |
| **ISS-027** | 云端结构化输出 / `scripts/llm_adapter.py::_chat_openai_structured` | **云端 `response_format: json_schema` 未被强制（`strict: true` 未被执行）**：请求发送 `response_format={type: json_schema, json_schema:{name: tool_call_array, strict: true, schema: <工具调用数组 grammar>}}`（要求 `[{"name":..., "arguments":{...}}]`），但 `Qwen/Qwen3.8-27B` @ ModelScope **实际返回形态在三种之间漂移**：① `[{name,arguments}]`；② `{name,arguments}`（裸单对象，F1 已兼容）；③ **`{...arguments...}`（裸 arguments，丢失 `name`）**。形态 ③ **无法被 `_normalize_structured_calls` 还原** → `tool_calls=[]`、`tool_calls_missing=True` → 判「格式退化」 | `EXP-M02-013` / `EXP-M02-014`（2026-10-05）：`v1-001` 两臂均返回裸 arguments（`{"device_id":"PUMP-A-01","sensor_ids":[...],"time_range":{...},"aggregation":"trend","window":"5m","limit":500}`）；同类共 **8 条**（对照臂）/ **15 条**（`tools_v5` 臂） | **云端"约束解码"名存实亡**；云端首次成功率被"格式退化"系统性污染（09-30 = **0** 条 → 10-05 骤增至 **8–15** 条）；**云端与本地（Ollama 原生 `format` 约束确实生效）不可同口径比较** | 🟠 **高** | ✅ **可规避（2026-10-05 登记）** | ① 如实登记"**云端不存在有效输出约束**"，不得把云端结果当作"约束解码"结果引用；② **改用 OpenAI 原生 `tools` + `tool_choice="required"`**（`env/cloud.json` 已声明 `supports_tools_function_calling: true`）作为云端工具调用路径（待验，H5）；③ **不**放宽适配器去"猜"裸 arguments 属于哪个工具（会掩盖真实失败，属移动球门）；④ `tool_calls_missing` 计数在云端报告中**单列**；⑤ **【2026-10-06 修正：严重性下调为「间歇性」】** 本轮以路径 B 后的用例集重跑（`EXP-M02-018`）：`response_format` 臂**可解析率 1.0000、格式退化 0 条**（与 09-30 相同）→ 三次观测（09-30 正常 / 10-05 复现 / 10-06 正常）中**仅 1 次复现** → 该现象**不是通道固有属性，而是 provider 侧的间歇性行为**。故表述由"云端 `response_format` 名存实亡"**降级**为"**云端 `response_format` 的强制力在 provider 侧时有时无、不可依赖**"。**已生效的改进仍保留**：`--transport tools` 使输出落在标准 `message.tool_calls`，结构上不依赖正文 JSON 解析，仍是更稳健的默认选择 | **V1** | ✅ **R-V1-9（2026-10-05 新增 / 2026-10-06 下调）** |
| **ISS-028** | 云端 baseline 模型（`Qwen/Qwen3.8-27B` @ ModelScope，`env/cloud.json`） | **云端 provider 漂移 → 云端路径不可复现**：**完全相同的配置**（模型名 / endpoint / 用例集 / schema `tools_v4` / `prompt v1` / seed 42 / temp 0 / `repeat 3`）在 **2026-09-30** 与 **2026-10-05** 两次运行结果显著不同：参数 JSON 可解析率 **1.0000 → 0.8431**、格式退化 **0 → 8 条**、`v1-001` **3/3 → 0/3**、`v1-010` **0/3 → 3/3** | 逐字配置对照：`EXP-M02-011`（09-30）vs `EXP-M02-014`（10-05），两者除日期外全部相同 | **云端"可复现"不成立** → 本轮之前所有**跨日期**云端对照（`EXP-M02-001` vs `EXP-M02-006` 等）的 delta **混入 provider 漂移，不能干净归因**；`docs/version-lock.md` **仅锁模型名、无 digest**，无法检测或固定 provider 侧版本 | 🟠 **高（方法论级）** | ✅ **可规避（2026-10-05 登记）** | ① **任何云端对照必须在同日同批完成**（处理臂与对照臂同日）；② 云端结论一律标注"**依赖 provider 版本、跨日不可比**"；③ 在 `docs/version-lock.md` 增设"**云端模型不可 digest 化**"的显式声明（补上 §三第 10 行的漂移风险）；④ 关键结论须以**本地可锁版本**路径复核；⑤ **跨日云端数据不得用于单变量归因**；⑥ **【2026-10-06 加证：严重性上调】** 同一份逐字配置（`Qwen/Qwen3.8-27B` + `tools_v4` + `prompt v1` + seed 42 + temp 0 + `repeat 3` + `response_format`）在**三个日期**的成绩：**09-30 = 0.90**（`EXP-M02-011`）、**10-05 = 0.80**（`EXP-M02-014`）、**10-06 = 0.95**（`EXP-M02-018`）→ **极差 0.15**，且与 `ISS-027` 的间歇性同步出现。**更严重的含义**：漂移幅度（约 ±0.075）**足以跨越档位阈值**（如多工具 pass 线 0.70）→ **云端档位判定本身不稳定**。故：**云端结论不仅须同日成对采集，其档位判定亦须标注不确定性**；`docs/version-lock.md` 的"云端不可 digest 化"声明应据此加强 | **V1** | ✅ **R-V1-10（2026-10-05 新增 / 2026-10-06 上调）** |
| **ISS-029** | V1 判据口径（`scripts/judge_tools.py` ↔ `evals/v1_cases.jsonl` 的 `notes` / `lenient_param_defaults`） | **判据严格要求超出用例 `notes` 声明的考点**：多条用例的参数值比对**严格比对可选参数**，而这些参数**在 `notes`（考点声明）中未被列为考点**；个别用例的 `notes` 甚至**明示该参数是软性项**。**全量核对结论（`reports/v1-review-v4.md`，H8 复审，2026-10-05）**：20 用例中 **13 条**存在该现象，涉及 **19 个字段**。**证据最强的两条**：① **`v1-008`** —— `notes` 明写考点是「能否同时抽取两个工具的**必填参数**而不互相污染」，判据却在 `sensor_ids` / `aggregation` / `window` / `fault_keywords` **4 个可选参数**上严格比对；② **`v1-011`** —— `notes` 明写「**`window` 枚举精确匹配是唯一考点**」，判据却同时严格比对 `aggregation`。**其余**：`v1-002` `top_k`、`v1-004` `direction`、`v1-005` `window`、`v1-006` `category_filter`、`v1-007` `sensor_ids`/`aggregation`/`category_filter`、`v1-009` `fault_keywords`、`v1-010` `aggregation`/`category_filter`、`v1-012` `sensor_ids`、`v1-013` `aggregation`、`v1-020` `fault_keywords`（`v1-018` `sensor_ids` 可争议）。**反例（判错成立）**：`v1-009` 的 `depth` / `direction`、`v1-011` 的 `window`、`v1-001` 的 `window`（`notes` 明确讨论并配 `lenient=['5m']` 白名单）均有明确考点声明，属合理判错。**影响量化（补充分析，不替代官方口径）**：按"仅比考点字段"重判，**H5 首次成功率 0.7000 → 0.8500（+0.15）**，且 **`v1-007` 在全部 4 个臂上均由失败翻为通过** → 该用例的唯一失败原因是 `aggregation`（非考点字段） | 对同一用例集反复重跑并比较"参数值正确率"（本地 7B / 云端 27B / 各通道均受影响） | **参数值正确率在全部臂上的可比性与可信度下降**；会把"判据未声明的可选参数差异"误读为"模型参数值能力不足" → **归因污染**（`R-V1-7` 曾预警该瓶颈，但 F1–F6 复审漏掉此类） | 🟠 **中高（结论可信度风险，非实现缺陷）** | ✅ **已修复（2026-10-05，路径 B 落实）** | ① **不得**把"参数值正确率"单独作为模型能力结论；② 该类失败须在报告中**单列**为"超出考点声明的可选参数差异"；③ 引用跨臂参数值对比时**必须同步声明本缺陷**；④ ~~转 P1（H8）逐条核对~~ → ✅ **已于 2026-10-05 完成（`reports/v1-review-v4.md`）**：产出 20 用例逐条对照表（13 用例 / 19 字段）+ 影响量化（考点口径下 H5 +0.15）；⑤ **处置路径**：**路径 C 已立即采用**（不改判据，仅单列该类失败、禁止以"参数值正确率"单独作能力结论）；**路径 B（推荐，不改代码，仅补齐用例 `notes`/`lenient_param_defaults` 元数据）** 与 **路径 A（改 `compare_arguments` 为"仅比考点字段"）** 均**需授权**，且修订后**必须重跑全部 V1 实验并升版判据**（修订须按纪律三处同步留痕）；⑥ **未经授权不得擅自放宽判据**（避免移动球门） | **V1** | ✅ **R-V1-11（2026-10-05 新增）** |
| **ISS-030** | 工程侧 / 测试防护（全仓） | **无回归测试防护**：`pytest` 已安装且可运行，但仓库内**无任何测试用例**（`pytest --collect-only -q` 长期输出 `no tests collected`），全部防护仅靠 12 个脚本的 `--selftest` **冒烟自检**。历次一致性审计（2026-09-29 / 09-30 / 10-05）均记录该缺口，但**从未登记为缺陷** | `python -m pytest --collect-only -q` → `no tests collected in 0.04s` | **已修复缺陷可被后续改动静默打回**：`--selftest` 只证明"脚本不崩"，**覆盖不到判据分支**，故 B2 判据恒真、判分器 `--detail-out` 空结果 IndexError、F1 裸单对象、ISS-011 `think` 污染、D1/D2 等价口径、ISS-024 few-shot 同源、ISS-029 判据超范围等**均无回归防护**（如再次把 `_refs_type_ok` 改成恒真、禁掉 `think` 剥离、移除 `lenient` 分支，冒烟自检不会报警） | 🟠 **中** | ✅ **已修复（2026-10-06）** | ① 新增 `tests/`：**106 个用例**，覆盖 `llm_adapter`（22）/ `judge_tools`（35）/ `param_normalizer`+`run_v5`+`run_v1`（20）/ **用例集完整性**（29）；② **变异测试验证**：刻意注入 5 个缺陷，**捕获率 5/5**，且源文件还原后 MD5 一致（见 `reports/regression-suite-2026-10-06.md` §三）；③ `tests/test_cases_integrity.py` **锁定路径 B 修订**（非考点参数不得回流 + 多解机制须生效），防 `ISS-029` 复发；④ 运行方式：项目根 `python -m pytest tests/ -q`（离线、秒级、零云调用）；⑤ 建议 P1 纳入 CI 前置 | **全仓（V1–V5）** | **工程侧（未单独登记风险册）** |
| **ISS-031** | V1 判分器（`scripts/judge_tools.py::_aggregation_over_limit_equivalent` / `_aggregation_canonical`） | **判分器对非字符串 `aggregation` 崩溃**：两函数使用 `value in OVER_LIMIT_ALIAS`（`set` 成员判断，要求操作数可哈希）。当模型把枚举值**包成对象或数组**时抛 `TypeError: unhashable type: 'dict'` / `'list'` → **判分器整体崩溃、整轮实验中断**（而非判为「参数值错」）。实测：`qwen2.5:7b` 对 `v1-012` 返回 `"aggregation": {"limit": 500, "type": "count_over_limit"}` | H9（`EXP-M02-016`）实跑：执行 33 组后进程崩溃于 `judge_tools.py:291`；单次复现与取证见 `experiments/v1/EXP-M02-016.md` §3.2 | 判分器**崩溃** → 实验中断、指标无法产出；该中断若与其它现象混读，易被误判为「模型/环境问题」而非判分器缺陷。**鲁棒性审计**确认仅此两函数有隐患（`duration_equivalent` / `_window_canonical` / `_is_superset` 对 dict/list/int/None 均安全） | 🟠 **中高** | ✅ **已修复（2026-10-06）** | ① 两处均加**类型守卫**：非字符串一律「不算等价 / 原样返回」，交由后续精确比对判「参数值错」；② **零回归验证**：重判 `EXP-M02-010` ~ `EXP-M02-015` 与记录值**逐项一致**（0.80 / 0.90 / 0.85 / 0.55 / 0.80 / 0.65）→ 修复**不影响任何既有结论**，**不构成判据口径变更**，无需重跑既有实验；③ 补齐 **13 条回归测试**（非字符串取值 + 字符串行为不变的全枚举交叉验证），`tests/` 共 **119** 用例全绿；④ **覆盖缺口已登记**：该缺陷未被 `judge_tools --selftest` 与 2026-10-06 新增的 106 用例发现（当时仅覆盖**字符串**取值），**由 H9 实跑暴露** | **V1** | **工程侧（未单独登记风险册）** |

---

## 三、严重级别判定标准

| 级别 | 判定 | 处理时限 |
|---|---|---|
| 🔴 **阻塞** | 使某项验证**无法开展或结论无效**；或违反核心保证（不丢状态、不重复） | **立即处理**，未闭环不得推进该项 |
| 🟠 **高** | 结论仍可得出但**可信度显著下降**，或需重跑全部实验 | 当日处理 |
| 中 | 有影响但有明确规避手段 | 本阶段内处理 |
| 低 | 影响可忽略，记录备查 | 记录即可 |

## 四、"状态"字段的判定标准（**三选一，必须明确**）

| 状态 | 判定标准 | 后续动作 |
|---|---|---|
| **已修复** | 缺陷的**根因已被消除**，复现步骤不再能触发问题 | 保留复现记录，标注修复方式与验证实验编号 |
| **可规避** | 根因未消除，但**有确定、可执行、经过实测的规避手段**，且规避后不影响结论有效性 | 规避手段写入本表；若触发 `docs/gate-criteria.md` 的中间区间，须记录**指标代价**（对 `Recall@5` / `P95` 的影响） |
| **需换方案** | **无可行规避**，或规避代价不可接受 → 必须切换技术方案 | **触发降级路径**：按 `docs/checkpoint-decision.md` §5.3 执行；更新 `docs/version-lock.md`；本文件状态列写"需换方案"并注明替代方案 |

> **纪律**：`状态` 为「需换方案」的条目，**必须**同时出现在 `docs/checkpoint-decision.md` §2.1 结论表与 `docs/risk-register.md` 中，形成闭环。

---

## 五、与风险册的对应关系

| 缺陷编号 | 风险册编号 | 说明 |
|---|---|---|
| ISS-001 | R11 / R-M5 | `has_writes` 行为属第三方实现细节，归入"checkpoint 可靠性"风险族 |
| ISS-002 | R12 | 重复副作用 |
| ISS-003 | R11 | TTL/驱逐丢状态 |
| ISS-004 | R12 | 并发 resume 导致重复写 |
| ISS-005 | R-M5 | 第三方实现（结构性问题） |
| ISS-006 | R11 / R13 | 体积增长 + 降级代价 |
| ISS-007 | R-新1 | `.wslconfig` 已安装并核验 live≈20GB（2026-09-24） |
| ISS-008 | R-新2 | 无通用 WSL2 发行版 → GPU 直通未验证 → **已裁决改走宿主 Ollama（U-03，2026-09-24，不再阻塞）** |
| ISS-009 | R-新3 | Ollama 版本漂移 |
| ISS-010 | R8 / R-新4 | TDengine 授权已查证（2026-09-24）：需降级（OSS + 自研解码器 ≤2 天） |
| ISS-011 | R-新5 | `think` 污染 |
| ISS-012 | R-新6 | 量化公平性 |
| ISS-013 | R-新3 | Ollama 行为不确定性 |
| ISS-014 | R-新7 | R-4 证据归纳/诊断本地可用性（2026-09-29 补挂；经验证**已闭环 Pass**，见 §六 ISS-014 复现记录） |
| ISS-025 | R-V1-7 | 云端工具调用路径（P7 方案 A）亦 No-Go、参数值语义为跨模型共同瓶颈（2026-09-30 登记；**复审已执行**，见 §二 主表与 §六 ISS-025 复审结论更新） |
| ISS-026 | R-V1-8 | 拒止行为对 system prompt 文本高度敏感、效应不可迁移（2026-09-30 新增，见 §六 ISS-026 复现记录） |

---

## 六、复现记录区（每条缺陷实验完成后回填）

### ISS-001 `has_writes` 覆盖问题
```
实验编号     ：EXP-V5-002（PG 路线）
复现步骤     ：跑到 interrupt() 后调用 put_writes()，再读 get_state() 比对 values / next
观察结果     ：首次 put_writes 报 KeyError（探针签名错误，二次修正：KeyError 'checkpoint_ns'）；
                修正为正确签名（before.config 含 checkpoint_ns + [("probe_channel", {...})]）后：
                put_writes_ok=True，values 与 next 均未变
是否复现     ：❌ 未复现（探针正确性修正后）
根因判断     ：前期报错为探针签名错误（非缺陷）；正确探针下 B4 未触发
状态判定     ：可规避（未复现）
规避/修复手段：不依赖 has_writes 做业务判断；writes 追加不覆盖；用正确探针签名
```
**状态**：✅ **可规避（PG 未复现）**

### ISS-002 恢复后重复副作用
```
实验编号     ：EXP-V5-004
工具执行次数（恢复前/后）：2 次（只读工具天然重放，设计允许）
重复副作用次数：0（generate_report 重复落库 0 次）
幂等键是否拦住：是（report_store.json 幂等键唯一，RPT-84b52ae611d4 复用）
状态判定     ：可规避
```
**状态**：✅ **可规避**

### ISS-003 TTL/驱逐丢状态
```
实验编号     ：EXP-V5-007
Redis 配置   ：--appendonly yes --maxmemory 1gb --maxmemory-policy noeviction
强制非 noeviction 后的现象：N/A（PG 路线，未走 Redis 存储）
丢状态次数   ：0
OOM 写失败次数：0（PG 无内存驱逐/TTL）
状态判定     ：可规避（PG 路线 N/A）
```
**状态**：✅ **可规避（PG 路线 N/A，无丢状态）**

### ISS-004 双审核人并发 resume
```
实验编号     ：EXP-V5-005（PG 侧评估）
并发请求数  ：2（多次 resume 于 EXP-V5-003-T）
实际生成报告数：1（report_store.json 仅 1 条，RPT-84b52ae611d4 唯一）
锁拦截次数   ：—
唯一索引拦截次数：幂等键兜底生效（1 条）
CAS 拦截次数  ：—
状态判定     ：可规避
```
**状态**：✅ **可规避（PG 路线只产 1 份报告）**

### ISS-005 第三方实现兼容性
```
LangGraph 版本：1.2.12
redis checkpointer 版本：0.5.2（候选 A，未采用）
异常行为记录  ：redis-py 走 t5.5 起连线均被服务端关闭（"Connection closed by server"，
              CLIENT SETINFO/on_connect_check_health；redis-cli 正常 PONG）
状态判定     ：需换方案（B7 阻塞 → 切 PG checkpointer；根因 ≠ 缺 RediSearch）
```
**状态**：✅ **需换方案（已切 PostgreSQL checkpointer 并实测通过）**

### ISS-006 体积增长
```
实验编号     ：EXP-V5-006（PG 侧统计）
单 thread 体积：296 KB（checkpoints 29 / checkpoint_writes 55 / checkpoint_blobs 29 / checkpoint_migrations 10）
总 DB 大小   ：≈ 8.66 MB
增长速率     ：≈ 296 KB/次诊断（有界）
保留上限     ：建议 N=20（审核达终态即归档）
状态判定     ：可规避（增长有界，可归档）
```
**状态**：✅ **可规避（296KB/thread，有界）**

### ISS-007 WSL2 内存配额（✅ 已闭环 2026-09-24）
```
检查项                    实测值                        设计值              是否一致
.wslconfig 是否存在       是（已安装：2026-09-24）       存在                ✅（配置落地）
Docker 内存上限           ≈20GB（docker info）           20GB                 ✅（已核验）
processors                10（docker info）              10                   ✅（已核验）
swap                      8GB（free -m）                 8GB                  ✅（已核验）
```
**修复步骤**：① ✅ 已写入 `%UserProfile%\.wslconfig`（复制 `env/wslconfig.proposed`）；② ✅ 已 `wsl --shutdown`；③ ✅ 已重启 Docker Desktop 并用 `docker info` 核对该文件生效值（≈20GB/10vCPU/8GB）；④ ✅ 备份到 `env/wslconfig.bak`
**状态**：✅ **已核验闭环**（2026-09-24）；基线已升 `env-baseline-v2.md`

### ISS-008 GPU 直通
```
wsl -l -v 输出         ：仅 docker-desktop（无通用发行版）
容器内 nvidia-smi      ：🔲 未测（无通用 WSL2 发行版）
宿主机 nvidia-smi      ：可用（RTX 4060 Laptop 8GB，驱动 616.56，compute cap 8.9）
状态判定               ：✅ **已裁决改走宿主原生 Ollama（2026-09-24，U-03）**——推理统一走宿主
                         127.0.0.1:11434，容器仅承载 DB/存储，不承载模型推理；
                         GPU 直通保持 UNVERIFIED 但**不再阻塞**（V1/V2/V5 均走宿主 Ollama 跑完）
```
**状态**：✅ **已闭环（2026-09-24，U-03 裁决「改走宿主 Ollama」）**

### ISS-009 Ollama 版本漂移
```
当前版本   ：0.34.2（API http://127.0.0.1:11434）
可升级版本 ：0.34.3
是否升级   ：✅ 已决 —— 锁定 0.34.2，**不升级**
状态判定   ：升级会改变模型行为与 tool_calls 输出细节 → 全流程冻结在 0.34.2
```
**状态**：✅ 已锁定 0.34.2（不升级，2026-09-24 裁决；`docs/version-lock.md` §二.2.6）

### ISS-010 TDengine 授权
```
查证方式   ：✅ 已填（官方文档 §二渠道1/2 + 发行包实物层渠道3/4；镜像 tdengine/tsdb:3.3.8.0）
结论       ：✅ 需降级（OSS 社区版 + 自研 Sparkplug B 解码器 ≤2 天，判有条件通过；官方连接器仅 All-in-One/Enterprise）
产出       ：reports/v3-auth.md
状态判定   ：🟡 已定稿（有条件通过）—— 授权不阻塞，启动自研解码器方案 + 工期估算
```
**状态**：✅ 已定稿 2026-09-24（覆盖原 "🔲 待 D1 填入"）

### ISS-011 `think` 污染
```
实验编号        ：EXP-V1-003 / EXP-V1-004
think 污染率    ：不适用（适配层在判分前**统一剥离**）；qwen2.5:7b 无 think 输出；deepseek-r1:7b think token 均值 593.71（字符近似），think 占比 1.4236
剥离后 JSON 通过率：**1.00**（两模型，EXP-V1-003；`experiments/v1/summary-EXP-V1-003.csv`）
状态判定        ：格式退化已根除，可解析率达 100%
```
**状态**：✅ **已修复**（`scripts/llm_adapter.py` 统一剥离 `think`，两模型走同一入口）

### ISS-012 量化公平性
```
qwen2.5:7b 量化档      ：✅ Q4_K_M（7.6B，`ollama show` 实测，2026-09-29）
deepseek-r1:7b 量化档  ：✅ Q4_K_M（7.6B，`ollama show` 实测，2026-09-29）
是否同档               ：✅ 同档（拉齐，对比公平性成立）
胜出者 Q8/FP16 复核结论 ：未做（V1 已挂起）；**P1 遗留**（当前不阻塞，不宣称更高精度档不倒转）
状态判定               ：✅ 拉齐完成（2026-09-29）；Q8/FP16 复核留 P1
```
**状态**：✅ **已回填（2026-09-29）**——两模型实测均 Q4_K_M，拉齐完成；引用 V1 双模型对比数字无须再加"量化档未知"声明。**P1 遗留**：胜出者补 Q8/FP16 本地量化复核，确认结论不倒转。

### ISS-013 Ollama 静默退化
```
实验编号        ：EXP-V1-003（本地）/ EXP-V1-005（云端约束解码）
静默退化次数    ：本地 **0 / 110 次调用**（可解析率 1.00）；云端约束解码 **2 / 20**（失败归类含「格式退化」2 例）
状态判定        ：退化被单独归类、未混入「工具名错」；本地路径已根除
```
**状态**：✅ **已修复（可观测）**（`scripts/llm_adapter.py` 置位 `tool_calls_missing` → 判分器记「格式退化」）

### ISS-014 R-4 本地证据归纳/诊断可用性（2026-09-28 新增，非 V1 判据）
> **登记原因**：role-decision §6.1 R-4 现值 0.67 实为**多轮工具调用**分数，非"读证据→写根因/结论→带 `evidence_refs` 引用"的证据归纳/诊断分数；R-4 因合规锁死本地（云端仅传脱敏摘要与结构化参数、不传证据原文，scope-mvp §六）。

| 字段 | 内容 |
|---|---|
| 专项资产 | **已闭环（2026-09-29）**：`evals/r4_cases.jsonl`（20 条，含干扰+伪造陷阱）/ `prompts/r4_prompt_v1.md` / `scripts/judge_r4.py`（判分+`--selftest`）/ `scripts/run_r4.py`（执行+合规本地强制+`--selftest`）；判据见 `docs/gate-criteria.md` §3.7 |
| 实验编号 | **已跑 EXP-R4-001**（`python scripts/run_r4.py --models qwen2.5:7b --repeat 3 ...`，详见 P0-summary/方案）；判分结果见 §二 主表 |
| 状态判定 | ✅ **已闭环（整体 Pass）**：六维全 Pass，幻觉红线 = 0（结构 0.96 / 引用忠实 1.0 / 幻觉 0 / 覆盖 0.96 / 根因 0.93 / severity 0.89 / 动作非空 0.96）；结论已回填 role-decision §6.1 R-4（Pass）与 scope-mvp §六 |
| 对应验证项 | 非 V1-判据（**V1 只测 R-2/R-3**）；P1 证据归纳专项 |
| 已登记风险册 | ✅ **R-新7（2026-09-29 补登记）** |

**状态**：✅ **已闭环（EXP-R4-001 实测 Pass，2026-09-29）**

---

### ISS-024 few-shot 恒取 v1（2026-09-30 发现并修复）

> **发现场景**：P6 拆步落地后做 dry-run 装配校验时，预览 messages 发现 few-shot 仍是 v1 的 3 条。

```
实验编号     ：EXP-V1-009（拆步，修复后重跑）/ EXP-V1-010（单响应对照，修复后重跑）
复现步骤     ：python scripts/run_v1.py --prompt prompts/tool_call_prompt_v2.md --dry-run
               → 检查装配出的 messages 中 role=user/assistant 的 few-shot 条数与来源文本
观察结果     ：few-shot 仅 3 条，且含"查一下 PUMP-A-01 最近 24 小时的振动情况，看看有没有超标"
               —— 该文本仅存在于 prompts/tool_call_prompt_v1.md:57
根因判断     ：build_messages 调 load_fewshot() 未传 prompt_path，落回模块级默认
               PROMPT_PATH=tool_call_prompt_v1.md（system 侧因显式传 system_prompt 而正常取新提示词）
是否复现     ：✅ 已复现（dry-run 装配预览）
影响范围     ：EXP-V1-004 / 006 / 007 / 008 的"提示词增强"变量不干净（只改 system、未改 few-shot）；
               各实验结论方向（No-Go）不受影响，但"few-shot 扩容的收益"从未被真正测过
状态判定     ：已修复
修复手段     ：① build_messages 新增 prompt_path 参数（system 与 few-shot 同源）；
               ② run_group / run_step_chain_group / dry-run 三处显式传路径；
               ③ --selftest 新增防回归自检（v2 装配条数必须多于 v1）；
               ④ 历史 raw 不追改，EXP-V1-009/010 为修复后新口径
```

**状态**：✅ **已修复（2026-09-30）**，修复验证 = `python scripts/llm_adapter.py --selftest` + `run_v1.py --selftest` + dry-run 装配预览

---

### ISS-025 云端工具调用路径亦 No-Go（参数值语义为跨模型共同瓶颈）

> **发现场景**：P7 混合形态（方案 A：R-2/R-3 上云）实施后，用 `EXP-M02-001` 实测云端 27B 的单响应编排能力。

```
实验编号     ：EXP-M02-001（云端 Qwen/Qwen3.8-27B × v1_cases 20 用例 × 1，Schema v2 结构化输出，多工具不拆步）
复现步骤     ：python scripts/run_v1.py --models "Qwen/Qwen3.8-27B@https://api-inference.modelscope.cn/v1/chat/completions" \
                 --constrain --repeat 1 --max-retry 1 --tag m02-hybrid-cloud \
                 --out experiments/v1/raw/EXP-M02-001.jsonl
               python scripts/judge_tools.py --raw experiments/v1/raw/EXP-M02-001.jsonl \
                 --out experiments/v1/summary-EXP-M02-001.csv
观察结果     ：首次成功率 0.60（12/20）→ 整体 No-Go
               单工具 67% / 多轮 33% / 无效拒绝 67%（均 <70%）；参数校验 75% / 多工具 50%（中间）
               多工具集合覆盖 1.00，但用例级首次通过率仅 50%
               参数值正确率 0.5882；热平均 9081.7ms / 热 P95 22529.1ms（冷 5406.5ms）
               失败归类：{参数值错 6, 格式退化 1（v1-001）, 该拒绝却调用 1}
根因判断     ：跨模型（本地 7B / 云端 27B）失败共同收敛到"参数值语义"，而非"编排/工具选择"；
               云端 27B 亦仅 0.60 → "换/加模型即可解决工具调用"的隐含前提不成立
是否复现     ：✅ 已复现（EXP-M02-001，20 条落盘 + 判分 CSV）
影响范围     ：V1 处置链 ①②③④（约束解码 / few-shot / Schema 简化 / 混合形态）已全部执行仍 No-Go；
               下一步指向"复审参数值判据/用例口径"，而非继续换/加模型
状态判定     ：已登记（口径问题，非实现缺陷；不追改历史 raw）
后续动作     ：① 复审 gate-criteria §3.1.1 与 judge_tools 参数值比对口径；② 口径复审前不投入换/加模型；
               ③ 复核历史实验按新口径重判并留痕
```

**状态**：✅ **已登记（2026-09-30）**，依据 `experiments/v1/EXP-M02-001.md`、`reports/P0-summary.md` §三 决策5

**复审结论更新（2026-09-30，F1–F6）**：本项指向的「复审参数值判据/用例口径」**已执行**——F1/F4/F5/F6 落地并重判 11 实验 19 组（首次成功率 +0.05~+0.12，**整体档位无一翻 Pass、单工具档全 No-Go**）；F2 四臂重测（`EXP-M02-002`）**采纳形态 = 只补 `schemas/tools_v4.json` + 保留 prompt v1**（prompt v3 未采纳），四臂整体仍全 No-Go。→ **`ISS-025` 状态更新为「已闭环处置」；M0.2 维持 No-Go**，归因修订为「判据口径缺陷 + 任务信息不足 + 模型部分错」混合归因。依据 `reports/v1-review-v3.md` §六/§七.1、`reports/P0-summary.md` §三 决策6。

**状态**：✅ **已闭环处置（复审已执行，2026-09-30）**

---

### ISS-026 拒止行为对 system prompt 文本高度敏感（2026-09-30 新增）

> **发现场景**：V1 判据/用例口径复审的 F2 四臂实验（`EXP-M02-002`）中，臂 C 相对臂 A **只改了 `query_sensor.sensor_ids` 的一段描述**，却整体改变了拒止行为。

```
实验编号     ：EXP-M02-002（F2 四臂：A 基线 / D 复现对照 / C 仅 schema / B 双载体）
复现步骤     ：同一 evals/v1_cases.jsonl 用例集，仅替换 schemas/tools_*.json 的描述文本
               （A/D 用 tools_v2；C/B 用 tools_v4），其余 prompt=图 v1（B 用 v3）、
               temperature=0 / seed=42 / num_ctx=8192 / repeat=3 / --constrain 全同
观察结果     ：与测点命名完全无关的用例一并翻转——
               v1-016（缺设备号、应拒绝却调用）0/9 → 9/9；v1-017（寿命预测）0/9 → 9/9；
               无效拒绝类 0/9 → 9/9
               对照：臂 D 逐字重跑 A 复现 19/20 一致（唯一差异 v1-008），
               且 A/D 无效拒绝同为 0/9 → 非"坏运行"，效应来自 system prompt 文本差异
根因判断     ：拒止行为对 system prompt 文本高度敏感——文本条件化副作用；
               在该配置内可复现，但影响面超出测点命名机制，属"不可迁移"效应
是否复现     ：✅ 已复现（EXP-M02-002 臂 A vs C，含臂 D 复现性对照）
影响范围     ：若误读为"F2 提升了模型能力/拒止能力"，会把不可迁移的提示词副作用写成能力结论；
               拒止类指标跨 prompt 版本不可直接比较
状态判定     ：已登记（结论可信度风险，非实现缺陷；不作能力结论）
处置手段     ：① 拒止类指标跨 prompt 版本对比须声明版本 + 交叉验证；② 不得作为"F2 有效"证据；
               ③ prompt 变更须重跑拒止类基线并留痕；④ 转 P1 复核文本敏感性
```

**状态**：✅ **已登记（2026-09-30）**，依据 `experiments/v1/EXP-M02-002.md`、`reports/v1-review-v3.md` §七.1、风险册 `R-V1-8`

---

## 七、DoD 自查（M0.4 对应项）

- [x] ISS-001 ~ ISS-006 **全部完成复现并回填状态**（**2026-09-24 已闭环**）：ISS-001~004/006=可规避，ISS-005=需换方案（B7 切 PG）
- [x] ISS-007（WSL2 配额）已修复并核对（**V4b 前置硬条件**）
- [ ] ISS-008（GPU 直通）结论已出（V4 判据前置）
- [ ] ISS-009 ~ ISS-013 已完成并回填（V1 / V3 相关）
- [x] 每条缺陷的"状态"均为「已修复 / 可规避 / 需换方案」三选一，无留空（**ISS-001~006 已确认**）
- [x] 所有「需换方案」条目已同步到 `docs/checkpoint-decision.md` §2.1 与 `docs/risk-register.md`（**ISS-005/B7 → PG，§2.1 已填**）
- [x] 所有「可规避」条目的规避手段具体可执行（**ISS-001~004/006 已填实测值**）
- [ ] 本清单已随 `docs/handover-p1.md` 移交流程准备就绪