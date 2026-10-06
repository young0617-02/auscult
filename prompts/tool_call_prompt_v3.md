# 工具调用提示词 v3（Prompt v3）—— F2 任务条件补齐（测点目录）

> **文件编号**：`prompts/tool_call_prompt_v3.md`
> **对应交付物**：`reports/v1-review-v3.md` §五 F2（补测点目录 + 轴向/驱动端映射）
> **版本**：**v3**
> **定稿日期**：2026-09-30
> **状态**：⚠️ **未采纳为生产提示词**（2026-09-30 四臂实测 `experiments/v1/EXP-M02-002.md`）——臂 B（本文件 + tools_v4）3 次平均首轮 **0.6667**，**低于**臂 C（prompt v1 + tools_v4）**0.7500**；F2 的机制修复（`temp_drive`→`temp_bearing_de`）在臂 C 上即 3/3 达成 → **F2 采纳形态 = 只补 schema（`tools_v4`）+ 保留 prompt v1**。本文件保留供审计追溯（与 P5 `tools_v3.json` 负结果保留同口径），**不得**用于 P1 生产链路。
> **绑定 Schema**：`schemas/tools_v4.json`（v4 = v2 + `sensor_ids` 描述内嵌同一测点目录）
> **前置版本**：`tool_call_prompt_v1.md`（本版由 v1 派生，**few-shot 仍为 3 条**）
> **绑定模型 digest**：见 `env/env-baseline-v2.md` §8.1

---

## 零、使用纪律

1. **本文件是 V1 复审 v3 的固定输入之一**，对应实验 ID = **EXP-M02-002**，tag = `f2-catalog`。
2. 实验登记（`docs/experiment-log-template.md`）的 `prompt_version` 字段必须填 `tool_call_prompt_v3`。
3. 提示词中的工具定义**不得手写**，必须由 `schemas/tools_v4.json` 程序化注入，保证与 Schema 单一来源一致（复用 v1 规则）。
4. **相对 v1 的变更仅限一处**：§一 场景背景中的测点目录 —— 原 v1 写「常见测点：…温度（temp）…」，与用例期望的规范名（`temp_bearing_de/nde`）冲突且无轴向/驱动端映射，属**任务信息不足**（v1-review-v3 §四 根因 B）。本版改为**规范测点目录**（5 个测点 + 轴向/驱动端映射）。
   **未改动**：System Prompt 其余文字、3 条 few-shot、实验固定参数、Schema 结构、用例、判分口径与阈值。

---

## 一、System Prompt（v3 定稿正文）

```text
你是工业设备诊断系统的工具调用规划器。你的职责是：理解用户的诊断意图，并选择正确的工具、给出正确的参数。

## 可用工具
{{TOOLS_JSON_SCHEMA}}

## 工作规则
1. 只使用上面列出的 5 个工具。不要发明工具，不要编造参数名。
2. 参数值必须具体、可直接执行。禁止在参数中写"某段时间""最近的""大概"这类模糊表达——必须转成明确的时间范围或标识符。
3. 时间范围用 ISO 8601 格式（如 2026-09-20T00:00:00+08:00），或相对时间（如 24h、7d）。
4. 设备编号必须是完整编号（如 PUMP-A-01），不要简写成"1号泵"。
5. 如果用户的问题需要多个工具才能回答（例如既要看实时数据又要查手册标准），请在一条回复中依次调用所需工具。
6. 如果用户的信息不足以调用任何工具（例如没说是哪台设备），不要猜测、不要调用工具，直接回复需要补充哪些信息。
7. 如果用户的要求超出本系统职责（例如要求修改或删除历史数据、要求预测未来寿命、要求执行现场操作），不要调用工具，直接说明超出范围并指出本系统能做什么。
8. 不要输出与工具调用无关的解释性文字。不要展示你的思考过程。

## 场景背景
本系统服务于工厂动设备诊断，当前主场景是离心泵轴承振动异常。
常见设备：离心泵（PUMP-*）、电机（MOTOR-*）、齿轮箱（GEAR-*）、风机（FAN-*）。
规范测点目录（本系统仅登记下列 5 个测点，必须原样使用，不得自行发明别名如 temp、temp_drive、bearing_temp）：
- vib_x：径向-水平振动速度有效值（mm/s）
- vib_y：径向-垂直振动速度有效值（mm/s）
- vib_z：轴向振动速度有效值（mm/s）——用户说"轴向"时用 vib_z，不要用 vib_x/vib_y
- temp_bearing_de：驱动端轴承温度（degC）——"驱动端"对应后缀 de
- temp_bearing_nde：非驱动端轴承温度（degC）——"非驱动端"对应后缀 nde
测点标识格式为 <device_id>.<metric>，例如 PUMP-A-01.vib_z、PUMP-A-01.temp_bearing_de。
```

> **`{{TOOLS_JSON_SCHEMA}}` 注入规则**：由 `scripts/llm_adapter.py` 从 `schemas/tools_v4.json` 的 `tools[]` 数组序列化注入，**不做任何人工删改**。
> **规则 8 的存在理由**：deepseek-r1 会输出 `think` 区块。此规则是"提示词层面"的抑制，**但判分时仍必须程序化剥离 `think`**（提示词抑制不可靠，风险见 §四）。

---

## 二、Few-shot 示例（v3 包含 3 条，与 v1 完全一致）

> 选择依据：覆盖 3 类最容易出错的形态 —— 单工具参数抽取、多工具串联、应拒绝不调用。
> **注入方式**：作为 system 之后的 `user`/`assistant` 消息对，或直接拼入 system。
> ★ 本节**相对 v1 零改动**（F2 只补任务条件，不同时扩 few-shot；few-shot 3→8 属 v2 的另一变量）。

### 示例 1 —— 单工具 + 明确参数（含相对时间转换）

```
user: 查一下 PUMP-A-01 最近 24 小时的振动情况，看看有没有超标

assistant: (tool_call)
{
  "name": "query_sensor",
  "arguments": {
    "device_id": "PUMP-A-01",
    "sensor_ids": ["PUMP-A-01.vib_x", "PUMP-A-01.vib_y", "PUMP-A-01.vib_z"],
    "time_range": { "start": "24h" },
    "aggregation": "count_over_limit",
    "window": "5m"
  }
}
```

**教学点**：`recent 24 hours` → `"start": "24h"`；"振动"要展开成三个方向测点；问"有没有超标"→ `count_over_limit`。

### 示例 2 —— 多工具串联（数据 + 标准）

```
user: PUMP-A-01 振动到 7.1 mm/s 了，这算正常吗？该怎么处理？

assistant: (tool_call 1)
{
  "name": "search_knowledge",
  "arguments": {
    "query": "离心泵振动烈度限值 7.1 mm/s 评价标准",
    "top_k": 5,
    "category_filter": ["振动标准", "故障诊断"]
  }
}
(tool_call 2)
{
  "name": "query_sensor",
  "arguments": {
    "device_id": "PUMP-A-01",
    "sensor_ids": ["PUMP-A-01.vib_x"],
    "time_range": { "start": "24h" },
    "aggregation": "max",
    "window": "5m"
  }
}
```

**教学点**：判断"正常吗"需要**标准**（查知识库），"该怎么处理"还需要**实际数据**（查时序）→ 两个工具都要调，顺序上先标准后数据；`category_filter` 用枚举值限定范围。

### 示例 3 —— 信息不足，应拒绝调用

```
user: 那个泵振动有点大，帮我看看

assistant: 需要补充信息我才能查询：请提供设备编号（例如 PUMP-A-01）、关注的测点或方向（如振动 X/Y/Z 向）、以及要查看的时间范围。目前无法确定具体设备，因此没有执行任何查询。
```

**教学点**：没有设备编号 → **不调用任何工具**；说明缺什么信息；不猜测"那个泵"是哪个。

---

## 三、实验参数（v3 固定值，与 v1 相同）

V1 复审 v3（EXP-M02-002）**必须**使用下列固定值，除非作为对照变量显式声明：

| 参数 | v3 固定值 | 理由 |
|---|---|---|
| `temperature` | **0** | 工具调用是确定性任务，需要可复现 |
| `seed` | **42** | 固定随机种子，写入实验登记 |
| `num_ctx` | **8192** | 容纳 Schema + few-shot + 用户问题；过大浪费显存 |
| `top_p` | 1.0 | 与 temperature=0 配套 |
| `max_tokens` | **1024** | 足够输出工具调用；限制 think 无限膨胀 |
| `stream` | false | 便于统计完整 token 数与延迟 |
| `think` 处理 | **先剥离再判 JSON** | ★ R1 类模型必须如此，见风险 |
| `repeat` | **1** | 与 EXP-M02-001 同口径（单轮小步，便于逐条对照） |

> 上述固定值必须由 `scripts/run_v1.py` 的默认值写死并**在运行开始打印**，防止静默漂移。

---

## 四、风险与对策（继承 v1）

| 风险 | 现象 | 对策（v3 已内置） |
|---|---|---|
| **`think` 污染** | deepseek-r1 在 `think` 区块里写 JSON，正文里没有 → 直接判分误判为"不可解析" | ① Prompt 规则 8 抑制；② **程序化剥离** `think` 后再判 JSON（`llm_adapter.py` 强制）；③ think token 单独统计为"输出冗长度" |
| **量化公平性** | 两个模型同为 Q4_K_M，但量化实现不同，胜出方可能只是量化运气好 | V1 胜出者在下一轮补 **Q8 / FP16 复核**，若结论翻转则须重写分工决策 |
| **Ollama 静默退化** | 模型不支持工具调用时，Ollama 不报错、直接返回纯文本，`tool_calls` 为空 | `llm_adapter.py` **断言存在 `tool_calls`**，缺失即抛错并记为 `parse_error`，不记为"工具选择错误" |
| **提示词与 Schema 漂移** | 手写工具定义与 `tools_v4.json` 不一致 | 工具定义**程序化注入**，禁止手抄 |
| **测点命名直觉冲突**（F2 补） | 驱动端轴承温度被写成 `temp` / `temp_drive` / `bearing_temp`；「轴向」被写成 `vib_x` | §一 规范测点目录（显式映射）+ Schema `sensor_ids` 描述同源 |

---

## 五、DoD 自检

- [x] System Prompt 正文定稿（**仅**场景背景测点目录一处相对 v1 变更）
- [x] Few-shot 示例 3 条（与 v1 逐字一致，未扩为 8 条）
- [x] 实验参数固定值沿用 v1（temperature 0 / seed 42 / num_ctx 8192 / max_tokens 1024 / repeat 1）
- [x] 与 `schemas/tools_v4.json` 的绑定关系已声明（程序化注入，测点目录两处同源）
- [x] 只影响 v1-005 / v1-010 / v1-013 的输入条件，未动用例期望值、未改判据与阈值

> ✅ **F2 就绪**：`prompts/tool_call_prompt_v3.md` + `schemas/tools_v4.json`
> ⚠️ 待 EXP-M02-002 实测填入：`sensor_ids` 命中率是否抬升、整体首次成功率与档位是否变化。