# 版本控制基线（首次纳入 Git）· 2026-10-06

> **授权**：用户于 2026-10-06 明确授权提交
> **对应缺陷**：`docs/prj-template-experiment-log.md` 强制要求 `code_commit` 字段，而仓库**长期无 `.git`** → 该字段**无法填写**
> （在 2026-09-30、2026-10-05 两次状态核查中均被列为未闭环项）
> **成本**：零云端调用

---

## 一、结果

| 项 | 值 |
|---|---|
| 分支 | `main`（`git init -b main`） |
| **基线提交** | **`672143eacf08acf9255cccb7f9fa5bf0cf1f27ff`**（短 `672143e`） |
| **基线标签** | **`baseline-2026-10-06`** |
| 提交作者 | `dev <<REDACTED_EMAIL>>`（复用已有全局配置，**未改动任何 git 配置**） |
| 入库文件 | **265** |
| 提交 1 | `672143e` `chore: 建立基线（首次纳入版本控制）` |
| 提交 2 | `76678e9` `docs: 登记基线提交，使 code_commit 可填写` |

**`code_commit` 自此可填**：模板已完成说明 —— 引用基线写 `672143e`；工作区有未提交改动时写 `dirty-<短hash>`。

---

## 二、安全验证（提交前 / 提交后各一轮）

### 2.1 密钥泄漏防护

| # | 检查 | 方法 | 结果 |
|---|---|---|---|
| 1 | `env/cloud.json` 是否被忽略 | `git check-ignore -v env/cloud.json` | ✅ 命中 **`.gitignore:3`** |
| 2 | 密钥是否出现在**其他**文件中 | 全仓扫描（排除 `.venv/.git/__pycache__`），用真实 key 字面量匹配 | ✅ **仅** `env/cloud.json` 一处 |
| 3 | `sk-` / `Bearer` 形态密钥字符串 | 正则全仓扫描 | ✅ 无 |
| 4 | 待提交清单是否含密钥文件 | `git ls-files --cached` 过滤 | ✅ 无 |
| 5 | **全历史**是否出现被禁文件 | `git log --all --name-only` 过滤 | ✅ `cloud.json` / `.venv` / `__pycache__` / `_tmp` **均无** |
| 6 | **HEAD 树内**是否含被禁文件 | `git ls-tree -r --name-only HEAD` 过滤 | ✅ 均无 |
| 7 | **密钥字面量是否进入任何提交对象** | 遍历 `git rev-list --objects HEAD`，逐 blob `cat-file -p` 匹配真实 key | ✅ **未命中任何提交对象** |

### 2.2 行尾与字节一致性

本机全局 `core.autocrlf = true`（**未改动**），而仓库行尾**本就混杂**：
`README.md` / `CHANGELOG.md` 为 **CRLF**；`.gitignore` / `scripts/*.py` / `docs/*.md` / `env/*.json` 为 **LF**。

若不声明属性，`git add` 会把 LF 文件**归一化后再在 checkout 时改写成 CRLF** → **工作区字节与提交对象不一致**，
直接破坏基线「取回后逐字节一致」的要求。

**处置**：新增 **`.gitattributes`（`* -text`）** —— 入库即所见、取回即所存，**绝不改写任何字节**。
（`-text` 只关闭 EOL 转换，**不影响 diff/合并**：已用 `git diff --cached --numstat` 验证各文件**正常给出行列数**，未被当作二进制。）

**验证**（工作区 `git hash-object` vs 库内 `git rev-parse HEAD:<path>`）：

| 文件 | 结果 |
|---|---|
| `.gitignore` / `.gitattributes` / `README.md` / `CHANGELOG.md` | ✅ 一致 |
| `scripts/llm_adapter.py` / `scripts/collect_env.ps1` | ✅ 一致 |
| `env/hardware.json` / `docs/prj-ledger-known-issues.md` / `evals/v1_cases.jsonl` | ✅ 一致 |

→ **9/9 逐字节一致**。提交后对 5 个文件复核，仍全部一致。

**未纳入版本控制**（`.gitignore` 覆盖）：`.venv/`（约 968 MB）、`env/cloud.json`、`**/__pycache__/`。

---

## 三、遗留项（**本次未解决，如实记录**）

| # | 项 | 说明 | 处置 |
|---|---|---|---|
| 1 | **仓库含可再生成的合成语料** | `experiments/v2/raw/corpora_v2/`（3 文件 / **76.36 MB**，占 `experiments/v2/raw` 的 96.2%），由 `scripts/v2_synth_corpus.py` 以**固定种子 42** 生成、可完全复现 | ✅ **已处置（2026-10-06，用户选定）**：加入 `.gitignore`（第 18 行，附三条生成命令）+ `git rm -r --cached`，**仅移出索引、磁盘文件保留**（已实测 3 文件仍在）。受版本控制文件数 **266 → 263**。提交 `b99df0a` |
| 2 | **历史仍含这 3 个 blob** | `.git` 当前 **26.88 MB**（git 压缩后，远小于 76 MB 原始体积）—— 基线提交 `672143e` 仍引用它们，故 `git rm --cached` **不会**回收这部分空间 | ⏳ **待决策**：如需回收须重写历史（当前仅 4 个提交、**无远程**，成本最低）。**未擅自执行**（属破坏性操作） |
| 3 | **依赖漂移未解决** | 9 个锁定包未安装（`psycopg` / `langgraph` 全家桶 / `redisvl`）；`redis` 实装 8.1.0 vs 锁定 6.3.0 → **V5 checkpoint（M0.4 依据）与 V2 pgvector 路线事实不可运行** | ⏳ 按 `docs/prj-ledger-version-lock.md` 恢复或按纪律 2 升版 |
| 4 | `M0.6` 门禁未放行 | 与本次无关，一并声明 | 见 `reports/p0-gate-review.md` |

---

## 四、提交后回归（确认未破坏）

| 检查 | 结果 |
|---|---|
| `python -m pytest tests/ -q` | ✅ **106 passed** |
| 脚本自检（抽查 `llm_adapter` / `judge_tools` / `run_v1`） | ✅ 全部 `[OK]`；`describe()` 已显示 `transport : tools + tool_choice=auto` |
| `git status --short` | ✅ **空**（工作区干净） |
| 临时脚本 | ✅ 已全部清理，未入库 |

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-06 | 单人（本人） | 初始建立：首次纳入 Git 并建立基线 `672143e` / 标签 `baseline-2026-10-06`；记录密钥防护与字节一致性验证；列出遗留项与提交后回归 | `reports/`（本文件）、`.gitattributes`（新）、`CHANGELOG.md`、`docs/prj-template-experiment-log.md` |
| 2026-10-06 | 单人（本人） | **遗留项 #1 已处置**：经用户选定，将 `experiments/v2/raw/corpora_v2/`（76.36 MB 可再生成语料）移出版本控制（`.gitignore` + `git rm -r --cached`，**磁盘文件保留**），提交 `b99df0a`；并补记历史 blob 未回收（`.git` 26.88 MB）与重写历史的待决项 | 本文件 §三、`.gitignore` |
