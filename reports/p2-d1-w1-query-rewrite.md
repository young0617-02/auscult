# P2-D1 W1 查询改写器实现报告

> 来源：`plan/Phase 2 详细开发计划（混合检索）.md` §W1（P2-D1）
> 日期：2026-10-09
> 状态：**实现完成，`--selftest` 0 失败**
> 产物：`scripts/query_rewrite.py`；缓存目录 `experiments/p2/w1/cache/`

---

## 一、目标与边界

把自然语言问题改写为**三路检索输入**（Dense / BM25 / 图谱）：

| 输出 | 含义 | 消费方 |
|---|---|---|
| `semantic` | 保持业务语义的规整后查询 | Dense 向量化 |
| `keywords` | 面向 BM25 的中文检索词 | BM25 |
| `entities` | 面向图谱的实体标记（equipment/parameter/fault） | 图谱召回 |

**边界**：改写器自身**不访问任何检索库**，只产出改写结果；编排在调用方完成。

## 二、两档策略

1. **规则快路径（默认，`--mode rules`）**：零模型调用。数字+单位正则 + 三类词表精确匹配
   （设备/部件/参数/故障），复用 `scripts/run_v2.py::INDUSTRIAL_TERMS` 同源词表，避免词表漂移。
   - 满足 `P95<800ms` 与可解释性。
2. **LLM 增强（可选，`--mode llm`）**：复用 `scripts/llm_adapter.py::LLMAdapter`，走云端约束解码
   （`response_format json_schema`），输出 `{semantic, keywords[], entities[]}`；
   结果按 `(model, question)` 落盘缓存，同输入二次**不重复调用**。

## 三、实测结果

### 自检（`python scripts/query_rewrite.py --selftest`）
| 项 | 结果 |
|---|---|
| 实体抽取（2 组样例，含 设备/参数/故障 分类） | ✅ 通过 |
| semantic 保真 | ✅ 通过 |
| 数值关键词抽取（11.2） | ✅ 通过 |
| 缓存写读一致、命中 100% | ✅ `[PASS] 缓存命中 100%` |
| llm_adapter 导入路径 | ✅ 通过 |
| **合计** | **0 失败** |

### 规则端到端示例
输入：`离心泵驱动端振动烈度达 11.2 超标，轴承箱温度偏高，排查什么原因？`

```
semantic : <原问>
keywords : [离心泵, 驱动端, 振动烈度, 超标, 轴承箱, 温度, 11.2]
entities : [离心泵(equipment), 驱动端(equipment), 振动烈度(parameter),
            超标(fault), 轴承箱(equipment), 温度(parameter)]
numeric  : [11.2]
mode     : rules
```

## 四、关键实现决策
- **`keywords` 直接复用实体词表文本**（而非 jieba token）：jieba 会把「驱动端/振动烈度/轴承箱」
  切成子词导致词表失配，实体文本匹配更可靠。
- **长词覆盖**：词表间有包含关系（如「振动烈度」⊃「振动」），按词长降序扫、已被更长词覆盖则跳过，
  并按原问出现顺序回排，保证输出语序正确。
- **LLM 缓存**：`sha256(model|question)[:16]` → `experiments/p2/w1/cache/<key>.json`，命中直接返回。

## 五、局限与后续
- LLM 路径**未在本报告触发真实调用**（受云端预算纪律约束）；`--mode llm` 的在线验证并入后续
  检索端到端（W2/W5）时按需触发，本报告仅验证 schema 结构 & 缓存逻辑。
- 图谱实体召回当前基于规则词表；如遇词表外新实体，须补词表或启用 LLM 路径。

## 六、复现命令
```
python scripts/query_rewrite.py --selftest
python scripts/query_rewrite.py --query "离心泵驱动端振动烈度达 11.2 超标，轴承箱温度偏高，排查什么原因？" --mode rules
```