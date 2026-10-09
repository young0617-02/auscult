# MinerU 解析首日 Spike 报告（P1-D1 · B1-Spike）

> **对应任务**：P1-D1 **B1-Spike**（`plan/p1-plan-detailed.md` §四 D1）
> **上游依据**：`plan/p1-plan-detailed.md` §四 D1「B1-Spike」、§7.1 量化门槛、§八 P1-R1
> **环境基线引用**：`env/env-baseline-v2.md`（唯一事实源）
> **版本锁定**：`docs/prj-ledger-version-lock.md` §二.2.11（MinerU / PyMuPDF）
> **数据来源规格**：`docs/p1-spec-data-sources.md` §3.1–§3.3
> **版本**：v1 ｜ **执行日期**：2026-10-08 ｜ **状态**：**✅ 通过（判据全部达成）**

---

## 一、目的与判据

**目的**：MinerU 解析质量是 Phase 1 的**最大不确定性**，须首日验证，不通过立即影响后续工期（`plan/p1-plan-detailed.md` §四 D1）。

| # | 判据 | 门槛 | 本报告实测 | 判定 |
|---|---|---|---|---|
| 1 | 文本型 PDF 文本完整率 | **≥ 95%** | **100.00%**（recall=1.0000） | ✅ |
| 2 | 扫描件 PDF OCR 可读 | 可读出正文、与源文一致 | **99.75%**（recall=0.9975） | ✅ |
| 3 | 三样本均产出结构化 Markdown | 三份全部成功 | **3/3 成功** | ✅ |
| 4 | 表格还原（补充观测，§7.1 未单列） | 单元格不丢 | **18/18 单元格语义完整** | ✅ |

> **§7.1 全量门槛（前瞻，非本 Spike 判定项）**：MinerU 文本完整率 ≥95%、解析**批量失败率 ≤5%**。本 Spike 为 3 份样本、失败率 **0/3 = 0%**，全量门槛待 D3–D4 全量解析时复测。

---

## 二、环境与版本（隔离环境）

| 项 | 值 | 依据 |
|---|---|---|
| MinerU 版本 | **4.0.10** | `mineru --version`（隔离环境 `.venv-mineru`，Python 3.12.8） |
| PyMuPDF 版本 | **1.28.2** | 项目 `.venv`（样本生成 + 替代解析备选） |
| 小模型后端 | **ONNX**（`resolve_small_model_backend` → onnx） | `.venv-mineru` 无 torch 依赖，自动落 ONNX 后端 |
| 模型来源 | **ModelScope**（国内源） | 用户裁定（2026-10-08） |
| 模型落点 | `D:\modelscope\hub\models\MinerU-4_models_onnx` | 与项目已选用 BGE-M3 / bge-reranker-v2-m3 同库 |
| 解析档位 | `basic`（`parse_server.local.managed_tier=basic`） | 仅小模型（版面/OCR/表格/公式），未启用 VLM |
| 关键环境变量 | `MINERU_MODEL_BASE_DIR=D:\modelscope\hub\models`、`MINERU_MODEL_SOURCE=local` | `mineru/config.py`（`MINERU_` 前缀环境覆盖） |

> **纪律说明**：MinerU 按要求**隔离在独立环境 `.venv-mineru`**（不进项目 `.venv`、不入 `requirements.txt`），版本已锁至 `docs/prj-ledger-version-lock.md` §二.2.11。

---

## 三、样本（自编合成，可复现）

**生成器**：`scripts/gen_sample_pdfs.py`（PyMuPDF 1.28.2）｜**seed = 42**｜**synthetic = true**

| 类别 | 文件 | 字节 | sha256（前 16 位） | 特征 |
|---|---|---|---|---|
| ① 文本型 | `sample_text.pdf` | 4,920 | `3501c6d772188c5a…` | 有文本层，可直接抽取 |
| ② 扫描件 | `sample_scanned.pdf` | 11,602,698 | `b10654a3f06c73e0…` | **无文本层**（200 dpi 图像 PDF），模拟扫描件 |
| ③ 含表格 | `sample_table.pdf` | 5,163 | `18944577b7cf68ba…` | 画线 + 单元格文本（振动烈度判据表） |

- 元数据：`experiments/p1/mineru-spike/samples/samples.meta.json`
- 内容：离心泵手册骨架（安全须知/结构原理/安装要求/运行维护/故障排查）+ 振动烈度判据表；**取自公开工业常识骨架，不含任何真实手册原文**（见 §八 局限声明）。

---

## 四、方法

```
# 1) 生成样本
.venv\Scripts\python.exe scripts\gen_sample_pdfs.py --out-dir experiments/p1/mineru-spike/samples --seed 42

# 2) 启动本地解析服务（隔离环境）
set MINERU_MODEL_BASE_DIR=D:\modelscope\hub\models
set MINERU_MODEL_SOURCE=local
.venv-mineru\Scripts\mineru.exe server start

# 3) 逐份解析（basic 档）
.venv-mineru\Scripts\mineru.exe parse experiments/p1/mineru-spike/samples/sample_text.pdf    --tier basic --pages all --wait 600 --output experiments/p1/mineru-spike/out/text
.venv-mineru\Scripts\mineru.exe parse experiments/p1/mineru-spike/samples/sample_scanned.pdf --tier basic --pages all --wait 600 --output experiments/p1/mineru-spike/out/scanned
.venv-mineru\Scripts\mineru.exe parse experiments/p1/mineru-spike/samples/sample_table.pdf   --tier basic --pages all --wait 600 --output experiments/p1/mineru-spike/out/table
```

**完整率口径**：以生成器内置正文常量（`TEXT_TITLE` + `TEXT_PARAGRAPHS`）为 ground truth；两侧**去除全部空白字符**后，用最长公共子序列（LCS）占比计算 `recall = LCS/len(gt)`（避免 MinerU 在拉丁字符/数字间插入空格造成假扣分）。表格以**单元格级子串命中**计算。

---

## 五、结果

### 5.1 量化

| 样本 | ground truth 字数 | 输出字数 | recall（LCS 完整率） | ratio（相似度） |
|---|---|---|---|---|
| ① 文本型 | 407 | 407 | **1.0000** | 1.0000 |
| ② 扫描件 | 407 | 407 | **0.9975** | 0.9975 |
| ③ 表格 | 18 单元格 | — | **18/18 语义完整**（字面命中 17/18，见 §六.3） | — |

### 5.2 结构还原摘录

- **文本型**：5 个章节标题与全部段落均还原为 Markdown（`## 标题` + 段落），页边界注释 `<!-- page 1 of 1 -->` 正常生成。
- **扫描件**：OCR 成功读出全部正文（原 PDF 无文本层），章节结构完整。
- **表格**：`sample_table.pdf` 还原为规范 Markdown 表（表头 + 5 行数据），列结构 `振动烈度/设备状态/建议处置` 正确：

```
| 振动烈度 (m m/s) | 设备状态 | 建议处置 |
| --- | --- | --- |
| &lt; 1.8 | 优 | 正常运行 |
| 1.8 ~ 4.5 | 良 | 加强监测 |
| 4.5 ~ 11.2 | 注意 | 安排检修 |
| 11.2 ~ 28.0 | 严重 | 尽快停机检查 |
| > 28.0 | 危险 | 立即停机 |
```

---

## 六、问题与观察

1. **拉丁/数字间空格伪影**：输出在拉丁字符与数字间引入空格，如 `0.05 m m`、`4.5 m m/s`、`4. 5 mm/ s`。属分词/版面切分的渲染差异，**归一化去空白后不影响完整性**（§5.1 recall 已按此口径）。**建议**：D4 分块前增加一处「`m m`→`mm` 等数字-单位归一化」预处理。
2. **扫描件 OCR 个别字符级噪声**：如「高速旋转**0**」「2结构原理」（标题与编号间空格丢失）。均为**字符级、不影响语义**，recall 仍 0.9975。
3. **表格 `<` 被转义为 `&lt;`**：Markdown 序列化对 `<` 做 HTML 转义，导致「字面命中」17/18；按语义计 **18/18**，**无数据丢失**。**建议**：B2/B3 建库前对表格单元格做 `&lt;`→`<` 反解。
4. **架构事实（勿误用）**：MinerU 4.0.10 读取 PDF 走 `pypdfium2`/`pypdf`，**非** PyMuPDF；PyMuPDF 在本项目仅用于样本生成与替代解析备选。

---

## 七、结论与建议

- **判定：Spike 通过**（§一 4 项判据全部达成），MinerU 作为 P1 B1 解析路线的**不确定性已消除**。
- **不启用替代解析**：`plan/p1-plan-detailed.md` §7.2 规定「MinerU 失败率 >5% 才启用 PyMuPDF + PaddleOCR 替代解析」；本 Spike 失败率 0%，**替代解析不启用**，**不影响工期**。
- **转入 D3–D4 全量解析**（按 `docs/p1-spec-data-sources.md` §3.1 清单），全量时须复测 §7.1「批量失败率 ≤5%」。
- **D4 分块前置预处理**：落地 §六 第 1、3 条归一化（数字-单位空格、HTML 实体反解）。
- **档位策略**：本次以 `basic`（小模型）已达标；若全量语料出现复杂版式/公式丢字，**升级路径**为 `standard` 档（下载 VLM 权重，见 §二 `managed_tier`）。

---

## 八、局限声明

> **局限声明（固定文本，不得删改）**：
> 本阶段所有质量类结论（`Recall@5`、`MRR`、`NDCG@5`、引用正确率、幻觉率、置信度 ECE 等）均**基于模拟数据的初步验证**，语料由项目组自编，其分布、术语密度与真实现场资料存在差异。因此上述指标**仅证明"链路可运行、方案可比较"，不等于现场可用性结论**。Phase 1 取得真实语料后，须以同一评测集与同一流程**重测**并对齐本结论。

---

## 九、复现命令

```powershell
# 前置：MinerU 已装于 .venv-mineru（§二.2.11）；模型已下载至 D:\modelscope\hub\models\MinerU-4_models_onnx
# 1) 生成样本（项目 .venv，含 pymupdf==1.28.2）
.venv\Scripts\python.exe scripts\gen_sample_pdfs.py --out-dir experiments/p1/mineru-spike/samples --seed 42
# 2) 启动服务 + 解析（三份）——见 §四 命令块
# 3) 完整率复算：以 gen_sample_pdfs 的正文常量为 ground truth，去空白后取 LCS/len(gt)
```

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-08 | 单人（本人） | 初始建立：P1-D1 B1-Spike 三类样本（文本/扫描/表格）解析与量化，判据 4/4 通过 | 全文 |