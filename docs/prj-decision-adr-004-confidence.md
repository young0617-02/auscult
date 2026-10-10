# ADR-004：复合置信度公式与三档阈值（0.50 / 0.60 / 0.75）

> **层级**：项目级长期有效（ADR）｜ **对应里程碑**：`M6.1`（Phase 6 文档收口 · D5 产出）｜ **状态**：🟢 **活动**｜ **最近更新**：2026-10-10

---

## 一、状态

**Accepted**（2026-10-10 收敛确认）。
上游决策时点如实标注：置信度公式与校准方法于 `plan/工业设备诊断 Agent.md` §6.1 定稿（2026-09-21，V5.0 定稿，为解决"置信度 0.75 无来源"的结构性缺失而补齐）；P5 实测校准结论见 §六。

## 二、背景（Context）

- 单一 `llm_self_score` 或裸阈值 0.75 无法解释、无法审计，评审定性为"魔法数字"（`plan/工业设备诊断 Agent.md` §零 结构性缺失行、§6.1 标题"把 0.75 从魔法数字变为可解释阈值"）。
- 路由（降级 / 云端升级 / 审核 / 定稿）需要**可判定的数值依据**（同上 §5.4）。

## 三、决策（Decision）

### 3.1 复合置信度公式（加权和，各项归一化 0~1）

```
confidence = 0.35 * retrieval_score      # Top-K 检索得分归一化均值
           + 0.20 * sensor_consistency   # 传感器异常与候选故障模式的一致性
           + 0.15 * graph_support        # 图谱是否存在支撑路径（有=1，无=0.3）
           + 0.30 * llm_self_score       # 推理模型自评（经温度缩放校准）
```

| 项 | 口径 | 出处 |
|---|---|---|
| 权重 | 0.35 / 0.20 / 0.15 / 0.30 | `plan/工业设备诊断 Agent.md` §6.1；`docs/prj-design-architecture.md` §5.2 |
| 代码落地 | `app/graph/nodes/diagnose.py`（文件头 D7：检索 0.35 / 传感器 0.20 / 图谱 0.15 / 自评 0.30；`compute_confidence` 实现）；云端升级后**复用同源函数重算**（`app/router/cloud.py` import `compute_confidence`/`calibrate_confidence`） | 代码（2026-10-10 核对） |
| 校准 | 对 `llm_self_score` 施加**温度缩放**（Temperature Scaling）；目标 **ECE ≤ 0.10**；50 条评测集标注正确/错误构造校准集 | `plan/工业设备诊断 Agent.md` §6.1；`docs/p0-spec-scope-mvp.md` §七 |
| 0.75 阈值依据 | "达到可自动生成正式报告所需精确率（≥85%）对应的**校准后阈值**"，非拍脑袋 | 同上 |
| 分解留痕 | 置信度四分量随状态输出（`confidence_breakdown`），供前端证据卡片分解展示 | `app/graph/nodes/diagnose.py`、`app/router/cloud.py` 返回结构 |

### 3.2 三档阈值语义（权威口径：三者是不同用途的独立阈值，非同一参数三种口径）

| 阈值 | 语义 | 触发动作 | 出处 |
|---|---|---|---|
| **0.50 降级线** | `confidence < 0.50` | 走 Must #12 降级路径：只出"初步判断，建议人工确认"，**不出正式报告**，显式标注 `degrade_reason` | `docs/p0-spec-scope-mvp.md` §七「三档置信度阈值」；`app/graph/build.py`（`< 0.50 → degrade`） |
| **0.60 强制审核线** | `confidence < 0.60` | 命中审核触发规则 **T-3**，强制人工审核 | `docs/p0-spec-scope-mvp.md` §七；`docs/prj-spec-review-lifecycle.md` §2.2 |
| **0.75 自动生成线（兼升级线）** | `confidence ≥ 0.75` 达自动生成线；`0.50 ≤ confidence < 0.75` 触发**云端升级**（云端失败 → 按降级处理） | `escalate_cloud` | `docs/p0-spec-scope-mvp.md` §七；`plan/工业设备诊断 Agent.md` §5.4；`app/graph/build.py`（`< 0.75 → escalate_cloud`） |

> **口径偏差如实登记**：任务口径曾表述"0.60 = 重检索线"，与权威文档不符——`docs/p0-spec-scope-mvp.md` §七 明确 0.60 为**强制审核线**（T-3）；"重检索"仅出现在 `plan/工业设备诊断 Agent.md` §4.3 数据流的"云端升级 / 重检索"并列表述中，**落地实现为云端升级、未单独实现重检索动作**（`app/graph/build.py` 路由分支仅 degrade / escalate_cloud / human_review / finalize）。【待确认：是否需要把"重检索"立为独立动作】

## 四、备选方案与放弃理由（Options & Rejected）

| 备选 | 放弃理由 | 出处 |
|---|---|---|
| 维持单一裸阈值 0.75（无公式、无校准） | 评审定性"0.75 无来源"为结构性缺失，被 V5.0 定稿补齐否决 | `plan/工业设备诊断 Agent.md` §零 表格行、§6.1 |
| 仅用 `llm_self_score` 单分量 | 模型自评不可解释、不可校准、无法审计拆解；复合公式使每一分量的贡献可见 | `plan/工业设备诊断 Agent.md` §6.1（公式设计意图） |
| 不做温度缩放直接用自评分 | 校准方法（温度缩放 + ECE ≤ 0.10）为定稿口径的一部分，跳过即回到"拍脑袋" | 同上 §6.1 校准方法 1–4 |

## 五、后果（Consequences）

| 类型 | 内容 |
|---|---|
| ✅ 正面 | 阈值可解释、路由可判定、审计可拆解（`confidence_breakdown`）；三档语义分离避免"一值多用"歧义 |
| ⚠️ 负面 | P5 实测 **ECE = 0.0 属"零方差巧合性校准"**（生成置信度自评零方差，无区分度）——达标带星号（✅*），不代表校准真实有效 |
| 📎 已知边界 | ECE 区分度为 P6 遗留：改 logit 置信度或多采样一致性后再校准（`docs/p5-handover-p6.md` §五 第 6 条）；golden 50 题待扩语料重评后校准集须同步重建（同上 §五 第 7 条、`docs/p0-spec-scope-mvp.md` §七 重测要求） |

## 六、P5 实测诚实声明

`docs/p5-handover-p6.md` §二 指标终值表：置信度 ECE 目标 ≤ 0.10，实测 **0.0（自评零方差，巧合性校准，无区分度）**，判定 **✅\***（达标但带保留）。依据该节 §五 遗留第 6 条，此结论**不得**引用为"校准已验证有效"；详见 `reports/p5-eval.md`。

## 七、事实源

- `plan/工业设备诊断 Agent.md` §4.3、§5.4、§6.1
- `docs/p0-spec-scope-mvp.md` §七（三档阈值、ECE 流程、重测要求）
- `docs/prj-design-architecture.md` §5.1、§5.2
- `app/graph/nodes/diagnose.py`、`app/graph/build.py`、`app/router/cloud.py`
- `docs/prj-spec-review-lifecycle.md` §2.2（T-3）
- `docs/p5-handover-p6.md` §二、§五；`reports/p5-eval.md`

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-10 | 单人（本人） | Phase 6 D5 初版（含 0.60 语义口径偏差登记与 ECE=0.0 诚实声明） | 本文件 |
