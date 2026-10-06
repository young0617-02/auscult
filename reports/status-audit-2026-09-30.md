# 项目状态审计与文件整理报告 — 2026-09-30

> **项目根**：`<REPO>`
> **执行范围**：全仓文件清点 + 哈希去重 + 路径完整性校验 + 依赖/构建/测试状态审计 + 文档同步
> **方法**：`Get-FileHash`（MD5/SHA256）分组去重、全量 JSON/JSONL 解析、`--selftest` 批量执行、`docker compose config` 校验、原始字节级编码校验
> **纪律遵循**：`experiments/**/raw/` **原始实验数据未做任何改动**；实验产物的取舍以"是否属于结论举证"为判据

---

# 第一部分：状态审计结论

## 1.1 总体判定

| 检查维度 | 判定 | 关键结论 |
|---|---|---|
| 项目是否正常运行 | 🟡 **脚本层正常，端到端不可用** | 12/12 自检通过；V5 链路因依赖缺失无法真实运行 |
| 是否存在未解决的错误 | 🔴 **3 项高风险未闭环** | 无版本控制、依赖漂移、零单元测试 |
| 依赖项是否最新/一致 | 🔴 **不一致** | 9 个锁定包未安装；1 个包版本高于锁定值 |
| 构建是否成功 | ✅ **成功** | 12/12 自检 + 4/4 Compose 校验（含 base+v4b-iso 合并） |
| 测试是否全部通过 | 🟡 **自检全通过，无单元测试** | `pytest` 收集到 **0 个用例**；6 个脚本无自检 |
| 阶段门禁 | ⛔ **M0.6 未放行** | M0.1/M0.3/M0.4/M0.5 达成；M0.2（V1）No-Go 挂起 |

## 1.2 技术栈与规模

| 项 | 值 |
|---|---|
| Python | **3.12.8**（与 `env/env-baseline-v2.md` 一致 ✅） |
| Docker | **29.6.2**（引擎可用 ✅） |
| 真实项目文件 | **198 个**（整理后） |
| 代码 | 18 个 Python 脚本（约 6,461 行）+ 2 个 PowerShell |
| 文档 | 15 份 `docs/` + 14 份 `reports/`（含 daily） + 5 份 `plan/` |
| 评测集 | golden_set 50 / v1_cases 20 / v2_cases 25 / v3_cases 25 / r4_cases 20 / corpus_100 |

> ⚠️ **工作区内存在 `.venv` 虚拟环境（31,481 个文件 / 968 MB）**，占全部文件的 99.3%。
> 它已被 `.gitignore` 正确排除（`.venv/`），但**位于工作区内**，会干扰文件检索与统计。建议移出工作区或改用工作区外的 venv。

## 1.3 代码质量

| 项 | 结果 |
|---|---|
| IDE / 静态诊断（`scripts/` 全目录） | ✅ **0 错误 0 警告** |
| 最大文件 | `judge_tools.py` 1074 行、`llm_adapter.py` 666、`run_v2.py` 652、`run_v5.py` 624 |
| 防御性设计 | 普遍含标识符白名单校验（防注入）、惰性导入带安装指引、JSON 序列化分区容错 |

## 1.4 依赖项（🔴 严重漂移）

| 包 | 锁定（`requirements.txt`） | 实装 | 状态 |
|---|---|---|---|
| protobuf / paho-mqtt / taospy / grpcio / grpcio-tools / pymilvus / jieba | 7.36.2 / 2.1.0 / 2.8.10 / 1.84.0 / 1.84.0 / 3.0.2 / 0.42.1 | 同左 | ✅ 一致 |
| **redis** | **6.3.0** | **8.1.0** | 🔴 漂移 |
| psycopg / psycopg-pool | 3.3.6 / 3.3.3 | — | 🔴 未安装 |
| langgraph / langgraph-checkpoint / langgraph-checkpoint-postgres / langgraph-sdk / langchain-core | 1.2.12 / 4.2.0 / 3.1.2 / 0.4.5 / 1.6.4 | — | 🔴 未安装 |
| langgraph-checkpoint-redis / redisvl | 0.5.2 / 0.27.2 | — | 🔴 未安装 |

**影响**：`requirements.txt` 明文规定"本文件与本机实装不一致即视为环境漂移" → 当前已构成漂移。
**V5 checkpoint 链路（M0.4 达成依据）与 V2 的 pgvector 路线事实上不可运行**；`redis` 版本不一致会污染 ISS-005 的复现结论。

## 1.5 构建与测试

| 环节 | 结果 |
|---|---|
| 12 个脚本 `--selftest` | ✅ **12/12 PASS（exit 0）** |
| `compose.base.yml` / `ingest` / `v2` / `base+v4b-iso` | ✅ **4/4 通过**（`v4b-iso` 为 override 文件，独立运行必失败，属设计） |
| JSON / JSONL 全量解析 | ✅ 通过（修复命名后无失败项） |
| pytest 用例 | ❌ **0 个**（pytest 9.1.1 已安装但完全未使用） |
| 自检覆盖 | 12 / 18 个 Python 脚本（66.7%）；覆盖率**无法量化**（无 coverage 工具） |

**未覆盖自检的脚本**：`run_v3_alert` / `verify_query_sensor` / `v2_load_test` / `v2_pg_build` / `v2_synth_corpus` / `v3_ingest_direct`

## 1.6 遗留风险

| 级别 | 风险 | 建议 |
|---|---|---|
| 🔴 高 | **无版本控制**：有 `.gitignore` 但无 `.git`，而实验登记模板强制 `code_commit` 字段 → 无法填写，违反"可复现"纪律 | `git init` + 基线提交 |
| 🔴 高 | **依赖漂移**：9 个包未装、1 个版本超锁 | 恢复至锁定版本，或按纪律 2 升版 `version-lock.md` |
| 🔴 高 | **零单元测试**：已修复缺陷（B2 判据恒真、ISS-024 few-shot 不回退等）无回归防护 | 补 pytest 回归用例 |
| 🟠 中 | V1 为 M0.2 硬阻塞（本地 7B 与云端 27B 均 No-Go） | 归因已定稿，走正式门禁评审 |

---

# 第二部分：整理前后对比

## 2.1 总体对比

| 指标 | 整理前 | 整理后 | 变化 |
|---|---|---|---|
| 工作区总文件数（含 `.venv`） | 31,692 | **31,682** | −10 |
| 真实项目文件（排除 `.venv` / `.trae`） | 208 | **198** | **−10** |
| `__pycache__` 目录 | 2 | **0** | −2 |
| 项目内 `.pyc` 文件 | 9 | **0** | −9 |
| 空目录 / 误建目录 | 4 | **0** | −4 |
| 误命名文件（扩展名与实际内容不符） | 1 | **0** | −1 |
| 字节相同的重复文件组 | 3 | **1**（保留为证据） | −2 |
| Compose 路径缺陷 | 1 | **0** | −1 |
| 文档与实际文件状态偏差 | 5 处 | **0** | −5 |

## 2.2 目录结构对比

**整理前**（真实文件，省略子文件）

```
auscult/
├─ .venv/                     ← 31,481 文件 / 968 MB（已在 .gitignore，但位于工作区内）
├─ .trae/documents/           ← 3 份游离文档（见 §4.3 未处理项）
├─ configs/
│  ├─ decoder_schema_mapping.json
│  ├─ mosquitto.conf
│  ├─ redis.conf
│  └─ milvus/                 ← 空目录（无任何文档引用）
├─ docker/
│  ├─ compose.base.yml  ← Redis 挂载 ./configs/redis.conf 指向不存在的路径
│  ├─ compose.ingest.yml / compose.v2.yml / compose.v4b-iso.yml
│  ├─ Dockerfile.decoder
│  └─ configs/                ← ✗ 误建目录
│     ├─ mosquitto.conf/      ← ✗ 以文件名命名的空目录
│     └─ redis.conf/          ← ✗ 以文件名命名的空目录
├─ scripts/
│  ├─ *.py (18) / *.ps1 (2)
│  └─ __pycache__/            ← 8 个 .pyc 缓存
├─ protos/
│  ├─ *.proto / *.py
│  └─ __pycache__/            ← 1 个 .pyc 缓存
├─ experiments/v1/
│  ├─ detail-EXP-V1-006.jsonl ← ✗ 内容实为 CSV
│  ├─ summary-EXP-V1-004-tiered.csv ← ✗ 零引用且与 summary-EXP-V1-004.csv 字节相同
│  └─ ...
└─ README.md / CHANGELOG.md / requirements.txt / .gitignore
```

**整理后**

```
auscult/
├─ .venv/                     ← 未改动（已在 .gitignore 排除）
├─ .trae/documents/           ← 未改动（见 §4.3）
├─ configs/
│  ├─ decoder_schema_mapping.json
│  ├─ mosquitto.conf
│  └─ redis.conf              ← 空目录 milvus/ 已删除
├─ docker/
│  ├─ compose.base.yml        ← ✅ Redis 挂载修正为 ../configs/redis.conf
│  ├─ compose.ingest.yml / compose.v2.yml / compose.v4b-iso.yml
│  └─ Dockerfile.decoder      ← 误建目录 configs/ 已整体删除
├─ scripts/                   ← 纯脚本，无 __pycache__
├─ protos/                    ← 无 __pycache__
├─ experiments/v1/
│  ├─ detail-EXP-V1-006.csv   ← ✅ 扩展名已修正
│  ├─ summary-normalize.csv / detail-normalize.csv ← 保留（uplift=0 的举证）
│  └─ ...
└─ README.md / CHANGELOG.md / requirements.txt / .gitignore
```

---

# 第三部分：变更清单

## 3.1 清理类（删除）

| # | 对象 | 类型 | 理由 | 可逆性 |
|---|---|---|---|---|
| 1 | `scripts/__pycache__/`（8 个 `.pyc`） | 目录 | 可再生的字节码缓存；`.gitignore` 已覆盖 | 运行 Python 即自动再生 |
| 2 | `protos/__pycache__/`（1 个 `.pyc`） | 目录 | 同上 | 同上 |
| 3 | `configs/milvus/` | 空目录 | **零文档引用**的空目录 | 可重建 |
| 4 | `docker/configs/`（含 `mosquitto.conf/`、`redis.conf/` 两个空目录） | 目录 | **以文件名错误创建的目录**，非真实配置；真实配置在项目根 `configs/` | 可重建 |
| 5 | `experiments/v1/summary-EXP-V1-004-tiered.csv` | 文件 | **零文档引用**且与 `summary-EXP-V1-004.csv` **字节完全相同**（825 B）；SHA256 = `AD487E57…0D0B2BA`；可用 `judge_tools.py` 从 `raw/EXP-V1-004.jsonl` 再生 | 命令再生 |

## 3.2 重命名类

| # | 原路径 | 新路径 | 理由 | 同步的引用 |
|---|---|---|---|---|
| 6 | `experiments/v1/detail-EXP-V1-006.jsonl` | `experiments/v1/detail-EXP-V1-006.csv` | 内容首行为 `case_id,case_type,…`，实为 **CSV**；同目录其余 10 个同类文件均为 `.csv` | `reports/v1-report.md` L277 |

## 3.3 缺陷修复类

| # | 对象 | 问题 | 修复 |
|---|---|---|---|
| 7 | `docker/compose.base.yml` L133 | Redis 配置挂载写作 `./configs/redis.conf`（相对 `docker/` 解析 = `docker/configs/redis.conf`），而该处为**空目录**，而 Mosquitto 用的是 `../configs/` → 路径不一致，**运行时会挂载空目录导致 redis-server 读不到配置** | 改为 `../configs/redis.conf`，并补注释说明相对基准；`docker compose config` 实测解析为 `<REPO>\configs\redis.conf` ✅ |

## 3.4 文档同步类

| # | 文件 | 改动 |
|---|---|---|
| 8 | `README.md` | 目录结构块按实际补全（schemas v1–v4 / prompts v1–v3+step+r4 / evals 6 项 / experiments 含 r4+plans / env 8 文件 / reports 明细）；脚本数 **16 → 18**；自检数 **10 → 12**（补 `run_r4` / `judge_r4`）；常用入口补 R-4 两条命令；移除已删除的 `configs/milvus/` |
| 9 | `reports/README.md` | §一 报告索引补登 5 份（`project-overview` / `project-summary-2026-09-29` / `v1-review-v2` / `v1-review-v3` / `status-audit-2026-09-30`）；§五 目录树补全并约定 `project-summary-*.md` / `status-audit-*.md` 命名范式；§六 评测集 **3 → 6** 项、执行器由"五个脚本"更正为"18 个 Python 脚本（12 个含自检）"；追加修订记录 |
| 10 | `reports/v1-report.md` | L277 引用 `detail-EXP-V1-006.jsonl` → `.csv` |
| 11 | `docs/risk-register.md` | **§5.3「当前闭环状态」表严重过期已更正**：原称 ISS-001~006「未闭环」、ISS-009~013「未闭环」、「是否存在需换方案条目：当前**无**」，与 §二 主表（ISS-001~006 已闭环、**ISS-005 需换方案**）直接矛盾；已按实测结论逐行更正并补 ISS-014~ISS-026 状态。§六 两条已完成的「【待 D7】/【待 D8】」占位行回填为实际记录。追加修订记录 |
| 12 | `docs/known-issues.md` | **消除文件内自相矛盾**：页头声明"ISS-001–ISS-014 已全部回填结论"，但 ISS-011 / ISS-013 状态列仍为「🔲 待 D2–D3 填入」；按同文件补遗记录更正为 ✅ 已修复 |
| 13 | `CHANGELOG.md` | 新增 **2026-09-30** 条目（代码/配置/数据/结论/文件整理/验证）；修正 `[未发布]` 中与 `reports/README.md` 矛盾的里程碑口径（"仅 M0.3/M0.4 达成" → "M0.1/M0.3/M0.4/M0.5 达成，M0.2 挂起"） |
| 14 | `reports/status-audit-2026-09-30.md` | 本文件（新增） |

## 3.5 保留说明（**判定为"非冗余"，故不删**）

| 对象 | 看似冗余 | 实际性质 |
|---|---|---|
| `experiments/v1/summary-normalize.csv` <br> `experiments/v1/detail-normalize.csv` | 与 `summary-EXP-V1-004.csv` / `detail-EXP-V1-004.csv` **字节相同** | **这两处字节相同正是 EXP-V1-NORM「uplift = 0」结论的举证本身**，被 `experiments/v1/EXP-V1-NORM.md` 显式引用（L38 / L43 / L85–86）及其复现命令引用。删除会破坏证据链，违反"可追溯"纪律 → **保留** |
| `experiments/v2/summary-pre-2026-09-29.csv` | 与 `summary.csv` 并存 | 项目**既定归档惯例**（CHANGELOG 2026-09-29 载明"原表留档"）→ **保留** |
| `env/hardware-v1-2026-09-23.json`、`env/env-baseline-v1.md`、`env/wslconfig.bak` | 旧版本文件 | 历史基线与回滚路径，文档明确标注"留档备查" → **保留** |
| `experiments/v2/raw/EXP-V2-BM25/` 下与上级**同名**的 `EXP-V2-*.jsonl` | 命名冲突 | 经哈希比对**内容不同**（为不同 run），属**命名规范问题**而非重复 → 保留数据，见 §4.2 建议 |
| `experiments/**/embed_cache.json`（2 处，2.1 MB + 0.7 MB） | 缓存 | 属运行期缓存，非结论产物；但位于 `raw/` 内且不同 run 内容不同 → 保留，见 §4.2 |

## 3.6 校验结果

| 校验项 | 结果 |
|---|---|
| 12 个脚本 `--selftest` | ✅ 12/12 PASS（整理后复测） |
| `docker compose config --quiet` | ✅ base / ingest / v2 / base+v4b-iso = **4/4 通过** |
| Redis 挂载路径解析 | ✅ `<REPO>\configs\redis.conf` |
| JSON / JSONL 全量解析 | ✅ 无失败项 |
| 静态诊断（`scripts/`） | ✅ 0 错误 0 警告 |
| 残留 `__pycache__`（排除 `.venv`） | ✅ 0 |
| `.gitignore` 编码与换行 | ✅ 原始字节校验：UTF-8 无 BOM + LF，规则 `env/cloud.json` / `__pycache__/` / `*.pyc` / `.venv/` 均**独立成行且生效** |

---

# 第四部分：未处理项与建议

## 4.1 需你决策的破坏性/超范围操作

| # | 项 | 说明 |
|---|---|---|
| 1 | `.venv/` 移出工作区 | 968 MB / 31,481 文件，干扰检索与统计。已被 `.gitignore` 排除，故**不影响交付物**；是否移出需你决定（涉及路径变更与 IDE 解释器配置） |
| 2 | 依赖恢复 | 执行 `uv pip install -r requirements.txt` 会改变本机环境；若你确需 `redis 8.1.0`，应按纪律 2 同步升版 `docs/version-lock.md` 与 `env/env-baseline-v2.md` |

## 4.2 建议（未执行）

| 优先级 | 建议 |
|---|---|
| P1 | `git init` + 基线提交（解除 `code_commit` 无法填写的问题） |
| P1 | 为 6 个无自检脚本补 `--selftest`；为已修复缺陷补 pytest 回归用例 |
| P2 | 规范 V2 数据区命名：`experiments/v2/raw/EXP-V2-BM25/` 下的同名文件加 run 后缀，避免与上级目录同名 |
| P2 | 将 `experiments/**/embed_cache.json` 迁出 `raw/`（缓存非证据），或加 `.gitignore` |
| P2 | 拆分 `judge_tools.py`（1074 行） |

## 4.3 明确未改动（需专项处理）

| 对象 | 原因 |
|---|---|
| `.trae/documents/` 下 3 份文档<br>（`R4-本地证据归纳专项测试.md`、`V2 压力档（1万-10万块延迟与内存实测）.md`、`V2 真 BM25 对标（M0.3-补齐）.md`） | 内容为**开发过程文档**（Context / 新建文件 / 修改文件），信息已并入 `docs/known-issues.md`（ISS-014）、`reports/v2-report.md` 等正式文档。`.trae/` 属**其他工具的元数据目录**，非本项目目录结构的一部分，动用可能影响该工具。建议由你确认后，迁移至 `docs/` 或 `reports/` 归档 |
| `experiments/**/raw/**` 全部原始数据 | 遵循"**原始实验数据只增不改**"纪律，未做任何改动 |
| `.venv/` | 第三方依赖，非项目文件 |

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-09-30 | 单人（本人） | 初始建立：状态审计（代码/依赖/构建/测试）+ 全仓文件整理（清理 9 个 `.pyc`、3 个空/误建目录，修正 1 处误命名、1 处 Compose 挂载路径缺陷）+ 文档同步（README / reports README / CHANGELOG / risk-register / known-issues / v1-report） | 全仓 |
