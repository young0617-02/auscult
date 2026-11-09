# 首次推送与脱敏处理报告（2026-11-09）

> 目标：把本地仓库推送到 GitHub **私有**仓库，且**任何敏感数据不进入版本历史**，任何匿名用户无法访问。
> 本文件只记录"查了什么、怎么处置、怎么验证"，**不含任何真实凭据值**。

---

## 一、结论摘要

| 项 | 结果 |
|---|---|
| 远程仓库 | `https://github.com/young0617-02/auscult` |
| 可见性 | **private**（API 返回 `private=true`、`visibility=private`） |
| 默认分支 | `main`（本地与远程同为 `d5b1e02`） |
| 提交数 | **78**（历史重写后结构保留，哈希全部变化） |
| 匿名访问 | API `GET /repos/...` → **404**；匿名 `git ls-remote` → **认证失败** |
| 历史残留 | 个人邮箱 / 主机名 / 本地路径 / 个人材料 / 内置 JWT 密钥 **均为 0** |
| 敏感文件是否曾入库 | `env/cloud.json`、`Material/`、`backups/`、`logs/`、`.env` **从未被跟踪** |

---

## 二、扫描范围与方法

| 维度 | 方法 |
|---|---|
| 工作区（会进仓库的内容） | `git ls-files` 全量 + 正则扫描（密钥/令牌/口令/邮箱/手机号/内网地址/本地绝对路径/主机名） |
| 版本历史 | `git log --all -- <path>`（是否曾跟踪敏感文件）+ `git log -S<串>`（pickaxe，内容级检索） |
| 凭据形态 | `sk-*`、`Bearer <token>`、`ghp_*`、`AKIA*`、`password=`、`JWT_SECRET=`、`POSTGRES_PASSWORD=` |
| 个人信息 | 邮箱、手机号（11 位）、Windows 用户名、主机名、`C:\Users\...` / `D:\...` 绝对路径、个人求职材料 |

---

## 三、脱敏检查清单（逐项处置）

| # | 类别 | 查出的内容 | 处置 | 结果 |
|---|---|---|---|---|
| 1 | API Key / Token | 无（`env/cloud.json` 从未被跟踪，`.gitignore` 已忽略） | 无需处置；`.gitignore` 加固 | ✅ 干净 |
| 2 | 内置 JWT 密钥 | `app/api/config.py` 内置固定 dev 密钥；`app/api/main.py` 以该串做判断 | **彻底移除**：未注入 `JWT_SECRET` 时用 `secrets.token_urlsafe(32)` 每次启动随机生成，并置 `IS_DEV_SECRET` 供启动告警 | ✅ 已修复（仓库中不再有可用密钥） |
| 3 | 个人邮箱 | 报告文件中的 `wesley <1639630866@qq.com>`；**78 个提交的 author/committer 邮箱** | 文件内 → `<REDACTED_EMAIL>`；提交元数据 → mailmap 统一映射为 `dev <dev@localhost>` | ✅ 已清除（内容级 pickaxe = 0） |
| 4 | 个人材料 | `archive/personal/` 3 份求职问卷（git 跟踪） | 移出仓库到 `_private_excluded/`（已 gitignore）；`git rm --cached`；**历史中整条路径删除** | ✅ 工作区与历史均无 |
| 5 | 本地绝对路径 | 43 个文件 95 处 `C:\Users\wesley`、`D:\DSHproject\auscult`、`E:/Obsidian Vault` | 替换为 `<USER_HOME>` / `<REPO>` / `<PRIVATE_VAULT>`；历史同规则重写 | ✅ 已清除 |
| 6 | 主机名 / 机器指纹 | `DESKTOP-B61BCOJ`（17 文件 44 处）、`wesley-desktop`、单个 `wesley` | 替换为 `<WORKSTATION>` / `<HOST_ALIAS>` / `dev`；含主机名的文件名 `EXP-V4B-CLEANRM-DESKTOP-B61BCOJ-*.md` 重命名为 `...-WORKSTATION-*.md` | ✅ 已清除 |
| 7 | 手机号 / 身份证 | 无真实命中（`16656285696` 为内存字节数误匹配） | 无 | ✅ 干净 |
| 8 | 内网 IP | 无 `192.168/10/172.16-31` 网段；仅有 `127.0.0.1` 回环（本地服务端口，非内网拓扑） | 保留（回环地址不泄露内网结构） | ⚪ 已评估 |
| 9 | 示例文件中的口令 | `deploy/.env.example` 内含 PG 口令、`JWT_SECRET`、`NEO4J_PASSWORD` 明文 | 全部改占位符（`<PG_PASSWORD>` / `<generate-with-openssl-rand-hex-32>` / `<NEO4J_PASSWORD>`）+ 注释说明真实值写 `deploy/.env` | ✅ 已修复 |
| 10 | 本地开发默认口令 | `123456`（PG）、`auscult_p0_dev`（Neo4j）、`Auscult#Dev2026`（seed 账号）散布 20+ 处代码与 compose | **保留（见 §五）**，理由与收紧路径见下 | ⚠️ 已评估-保留 |
| 11 | 忽略规则 | `blobs/`、`chunks/`、`_private_excluded/` 未在 `.gitignore` | 追加忽略；`archive/personal/` 一并忽略防回流 | ✅ 已加固 |

---

## 四、历史重写

工具：`git filter-repo 2.47.0`（`python -m git_filter_repo`）

```bash
git filter-repo --force \
  --mailmap  <TEMP>/auscult_mailmap.txt \
  --replace-text <TEMP>/auscult_replace.txt \
  --path archive/personal --invert-paths
```

| 动作 | 规则 |
|---|---|
| 作者/提交者 | `dev <dev@localhost> ← wesley <1639630866@qq.com>` |
| 删除路径 | `archive/personal/**`（全历史） |
| 内容替换 | 本地路径三组、个人邮箱、主机名两组、内置 JWT 密钥串、`wesley` 兜底 → 占位符 |

结果：**78 个提交全部保留**（提交信息/日期/拓扑不变），哈希全部变化。重写前已备份：
`%TEMP%\auscult_pre_rewrite_20261109.bundle`（12.3 MB，`git clone` 可完整恢复）。

> 因本地仓库此前**从无 remote**，本次重写不涉及 force push，也不影响任何他人克隆。

---

## 五、保留项与理由（未处置，需你决策）

以下三组是**本地一次性容器的初始化口令**，不具备对外可达性（容器仅绑定 `127.0.0.1`），
也是 `docker-compose` 起容器时的必需参数。强行占位会导致本地栈无法启动，故保留并显式披露：

| 项 | 位置 | 性质 | 彻底移除的代价 |
|---|---|---|---|
| PG 口令 `123456` | `docker/compose.base.yml`、若干 `scripts/*.py` 默认 DSN、`conftest.py` | 本地 dev 容器口令，非生产凭据 | 需改为"必须由 `PG_PASSWORD` 注入"，克隆后无法一键启动，集成测试需前置环境变量 |
| Neo4j 口令 `auscult_p0_dev` | `deploy/docker-compose.yml`、`docker/compose.base.yml`、`scripts/*.py` | 同上 | 同上（且必须与容器 `NEO4J_AUTH` 一致） |
| seed 账号口令 `Auscult#Dev2026` | `scripts/seed_users.py` | 本地演示账号 | 改为 env 注入，`seed_users.py` 需显式传参 |

**建议**（若你要彻底消除）：把 compose 改为 `${POSTGRES_PASSWORD:?set in deploy/.env}` /
`${NEO4J_PASSWORD:?...}`，代码默认 DSN 去掉口令部分，README 增加"先 `cp deploy/.env.example deploy/.env`
并填值"的前置步骤。该改动会影响本地启动流程与集成测试，需单独一轮验证。

---

## 六、推送后验证（可复跑）

| 验证项 | 命令 | 期望 / 实测 |
|---|---|---|
| 可见性 | `GET https://api.github.com/repos/young0617-02/auscult`（带令牌） | `private=true` / `visibility=private` → **实测通过** |
| 匿名 API | 同上去掉 `Authorization` | **404** → 实测通过 |
| 匿名 Git | `git -c credential.helper= ls-remote <url>` | 认证失败 → 实测通过 |
| 远程地址 | `git remote -v` | `origin https://github.com/young0617-02/auscult.git`（fetch/push 各一） |
| 分支同步 | `git rev-parse HEAD` vs `git ls-remote --heads origin` | 均为 `d5b1e02e76ed109a485ee5e82750ede81141cb1e` |
| 提交数 | `git rev-list --count origin/main` | **78** |
| 远程树敏感路径 | `git ls-tree -r --name-only origin/main \| Select-String "Material/\|_private_excluded\|env/cloud.json\|archive/personal"` | **0 条** |

---

## 七、备注

1. `Material/`（需求/技术/架构/简历/评审回应等对外材料）**本来就被 `.gitignore` 忽略**，本次未进仓库。
   这些文件含个人信息与对外话术，如需版本化，建议单独建**私有**仓库。
2. 凭据来源：本机 Git Credential Manager 已存 GitHub 令牌（账号 `young0617-02`，scope 含 `repo`），
   推送走 HTTPS；**令牌未写入任何文件、未出现在命令历史中**。
3. 本次新增的 `ISS-068` 功能改动（测点分页/上界）在脱敏前已单独提交，历史重写后完整保留。
