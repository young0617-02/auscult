# EXP-V1-NORM —— 参数归一化纠错（收窄版）量化留存

> **目的**：为「V1 破局」第 1 优先路径「参数归一化纠错」做**量化验证与证据留存**——
> 确认白名单式归一化能否抬升首次成功率，抑或证明瓶颈在别处。
> **载体**：`scripts/param_normalizer.py`（归一化层）+ `scripts/judge_tools.py --normalize`（判分侧应用）。
> **评测基准**：`experiments/v1/raw/EXP-V1-004.jsonl`（few-shot + 拒止强化，2026-09-28）。
> **结论一句话**：**uplift = 0** —— 白名单归一化对该数据集 217 条记录零影响；首次成功率之低与
> 归一化无关，瓶颈在**内容级参数语义选择 + 多工具编排**。

---

## 一、背景与动机

- V1 三路实测均 No-Go（qwen 首次 0.50 / deepseek 0.35，EXP-V1-004），失败集中 `参数值错`。
- project-overview §8.2.1 建议优先「参数归一化纠错（对 time_range / 设备号做规则后处理）」。
- 但初步失败归因显示：多数 `参数值错` 是**语义选择错误**（window/aggregation/relation_type 等），
  仅极少数属「意图对、表达不对」的格式类误差。本实验用白名单归一化 + 离线重判来**量化**其真实收益，
  避免在此路径上空耗，或避免用超额归一化掩盖真实缺陷（违反「不编造数字」铁律）。

## 二、方法与范围

- **归一化白名单**（仅 3 条，确定性、可证伪）：
  - R1：`time_range` 相对时长单位别名 → canonical（`24小时`→`24h`、`7天`→`7d`、`90分钟`→`90m`；ISO 绝对时间不动）。
  - R2：`device_id`/`sensor_id`/`start_node`/`device_model` trim + 去内部空白（**不做大小写转换**，见 §四 关键修正）。
  - R3：数字字符串 → number（仅 schema 类型为 integer/number 的字段，严格解析）。
- **明确不做**：相对↔绝对时间转换（需 `now` 锚定，离线无参考系）；任何语义/枚举字段映射
  （window/aggregation/relation_types/depth/direction/severity/query/fault_keywords…）；
  多工具缺失补全。
- **判分侧接入**：`judge_tools --raw EXP-V1-004.jsonl --normalize` —— 归一化只在**参数比对前**对
  actual 应用；`schema_valid`、`first_tool_match` 仍基于**原始**调用计算（格式门槛不放宽）。
  不改动 `experiments/**/raw` 原始数据。
- **复现命令**：
  ```bash
  python scripts/param_normalizer.py --selftest
  python scripts/judge_tools.py --selftest
  python scripts/judge_tools.py --raw experiments/v1/raw/EXP-V1-004.jsonl \
      --schema schemas/tools_v1.json --normalize \
      --out experiments/v1/summary-normalize.csv --detail-out experiments/v1/detail-normalize.csv
  ```

## 三、结果对比（基线 vs 归一化）

数据源：基线 `experiments/v1/summary-EXP-V1-004.csv`；归一化 `experiments/v1/summary-normalize.csv`。

| 指标 | qwen 基线 | qwen 归一化 | Δ | deepseek 基线 | deepseek 归一化 | Δ |
|---|---|---|---|---|---|---|
| 工具选择准确率 | 0.85 | 0.85 | 0 | 0.65 | 0.65 | 0 |
| 参数 JSON 可解析率 | 1.00 | 1.00 | 0 | 1.00 | 1.00 | 0 |
| 参数值正确率 | 0.4118 | 0.4118 | 0 | 0.3333 | 0.3333 | 0 |
| 4a 应拒绝却调用 | 0 | 0 | 0 | 6 | 6 | 0 |
| **5 首次成功率** | **0.50** | **0.50** | **0** | **0.35** | **0.35** | **0** |
| 6 重试后成功率 | 1.00 | 1.00 | 0 | 0.85 | 0.85 | 0 |
| 失败归类（参数值错） | 40 | 40 | 0 | 35 | 35 | 0 |

**逐条 diff**：217 条记录，归一化后 `success` 或 `call_issues` **变化 0 条**。
**判据判定**：两者均为 **No-Go（<70%）**，不变。

## 四、关键修正记录（教训）

- **首次实现曾做「大小写规整」（`sensor_ids` 转大写）**，重判出现**回退**（qwen 首成 0.50→0.40、
  重试后 1.00→0.65）。根因：黄金集 `sensor_ids` 为**小写**（`PUMP-A-01.vib_x`），`_is_superset`
  比对**大小写敏感**，归一化把合法小写 actual 与小写期望拆开 → 本可通过的用例被误判失败。
- **修正**：`_canonical_id` 改为**仅 trim / 去内部空白，不做大小写转换**，保证归一化**保中性**
  （既不掩盖缺陷、也不引入误判）。修正后 0 回退、0 提升。
- **结论**：归一化必须满足「对比较器是中性变换」——任何改变会与权威期望比对的形态转换，
  都可能反向破坏判决；本轮即实证。

## 五、结论与处置建议

1. **参数归一化纠错（收窄白名单）对该评测集 uplift = 0**，无法成为 V1 破局手段。
2. 首次成功率的真实瓶颈是 **7B 模型对参数值的语义选择**（window/aggregation/relation_type/depth 等
   需结合场景判断的字段）+ **多工具串联缺失**，二者均不是确定性规则可修复的。
3. **建议转向** `docs/role-decision.md` §四 的后续路径：③ Schema 简化（需升 v2）或 ④「本地推理 +
   云端工具调用」；以及多工具编排评估。归一化层保留为生产入参 canonical 化工具（P1 可复用），
   但不作为评测抬分子段。

## 六、代价声明

- 对首次成功率的目标（≥90%）：**无贡献（uplift 0）**，如实记录，未编造。
- 对 P95：归一化层为 O(参数规模) 纯函数，纳秒级，无实质延迟影响。
- 对数字口径：本实验 0 条记录判读被归一转置，数据稳定可复现。

---

> 数据来源：`experiments/v1/summary-EXP-V1-004.csv`、`experiments/v1/summary-normalize.csv`、
> `experiments/v1/detail-normalize.csv`、`scripts/param_normalizer.py`（自检通过，2026-09-28）。