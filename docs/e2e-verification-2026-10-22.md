# 全链路端到端验证报告（auscult）

- 时间：2026-10-22
- 后端：`http://127.0.0.1:8000`（本地）
- 账号：`eng_dev`（engineer，发起）/ `rev_dev`（reviewer，审核）
- 涉及接口：`POST /api/auth/login`、`GET /api/alarms`、`POST /api/diagnose`、`GET /api/threads/{id}`、`POST /api/threads/{id}/review`、`GET /api/reports`

---

## 一、链路 A：无有效数据 → 转人工（no-data 分支）

| 项 | 结果 |
|---|---|
| 告警 | `e2e-1792155764591-114` / PUMP-A-01 / `vib_rms=7.62` / ts `2026-10-16T13:02:44Z` |
| thread_id | `thr-1e0e428af3c140b8bb1f` |
| 收敛耗时 | ≈126s（前 121s `running`、`steps=0`，末段一次跃迁） |
| 状态跃迁 | `running` → `waiting_review` → (审核) `done` |
| nodes_done | `parse_alarm → diagnose → human_review → finalize` |
| agent_steps | 6 |
| risk / confidence | `high` / `0.52`（位于 `review_payload`，非顶层） |
| evidence_count | 5 |
| needs_human / human_reason | `True` / 「全部传感器测点在 24h/6h 窗口内均无数据…需人工现场测振、实测温度并核查数据链路」 |
| 审核人 | `rev_dev`（submitter=`eng_dev`，SoD 通过） |
| report_id | `RPT-4b37c38011435979` |
| reports.total | 82 → **83** |

**独立核实**：直接查 TDengine，`PUMP-A-01` 共 12919 行，时间跨度 `2026-10-14T11:52 ~ 2026-10-21T07:59`，但告警窗口 `10-16 12:32~13:07` **0 行**（数据只存在于 10-14、10-20、10-21 三段）。故「无数据转人工」判定**正确**，不是误判。

---

## 二、链路 B：有有效数据 → happy path

| 项 | 结果 |
|---|---|
| 告警（内联） | `e2e-happy-20261020` / PUMP-A-01 / `vib_rms=7.62` / baseline 4.5 / ts `2026-10-20T01:30:00Z` |
| thread_id | `thr-70d079acf75b466d9dae` |
| 收敛耗时 | ≈105s |
| nodes_done | `parse_alarm → diagnose → human_review → finalize` |
| agent_steps | 5 |
| risk / confidence | `high` / `0.72` |
| needs_human | `True` |
| human_reason | 「告警值 7.62 mm/s 与存储时序（最大 1.36 mm/s、超限 0 次）严重矛盾，原始数据查询返回与 3 小时窗口相同的 77 个点（时间过滤疑似失效），温度测点无数据…」 |
| report_id | `RPT-86809e0a8005b2a8` |
| reports.total | 83 → **84** |

**结论**：审核 → finalize → 报告落库 → 列表可见，全链路闭环正常（`risk=high`、`review_status=approved`）。

但该次「有数据」样本仍被判转人工，且归因指向两个**真实缺陷**（见下）。

---

## 三、已排除的"疑似缺陷"

1. **`risk_level` / `confidence` / `report_id` 为空** —— 非缺陷。
   - `thread_status()`（`app/api/runner.py:527`）顶层不返回 `risk_level`/`confidence`，它们在 `review_payload` 内。
   - `report_id` 由 `finalize` 在**审核通过后**写入（`app/api/routes/review.py:60` 注释已说明），等待审核期为空是设计。
2. **`vib_x/vib_y/vib_z` 不在 TDengine 列中** —— 非缺陷。
   - `app/agent/tool_registry.py:49` 的 `SENSOR_COLUMN_MAP` 已把它们归一为 `vib_rms`（ISS-049 已登记）。
3. **PowerShell 中文乱码** —— 客户端问题，非服务端。
   - 成因：`Invoke-RestMethod` 在响应无 `charset` 时按 Latin-1 解码 UTF-8 字节。
   - 规避：`Invoke-WebRequest -OutFile` + `[IO.File]::ReadAllText($p,[Text.Encoding]::UTF8)`（本报告全部数据用此法取得，中文正常）。

---

## 四、确认的两个缺陷

### D1 · Agent 时序窗口以 `now` 为锚，未以 `alarm.ts` 为锚（严重）

- 位置：`app/agent/tool_registry.py:139 _resolve_window(time_range, *, now_ms)`
- 调用处：`_exec_query_sensor` 里 `now_ms = int(time.time()*1000)`（第 216-217 行），告警时间**完全不参与**。
- 实测（`now=2026-10-22T13:05:06Z`，告警 `2026-10-20T01:30:00Z`）：
  - 默认窗口 = `[2026-10-21T13:05:06Z, 2026-10-22T13:05:06Z]`（应覆盖 10-20 01:30 前后）
  - 相对 `{"start":"6h"}` → 起点 `2026-10-22T07:05:06Z`
- 影响：回放/历史告警永远查不到告警时刻数据，且容易得出「告警值与存储严重矛盾」的错误结论 —— 链路 B 的 `human_reason` 正是这个表现。
- 佐证：同一告警时刻的显式窗口 `2026-10-20T01:00~02:00Z` 直查 TDengine **有数据**（100 点/小时量级），说明数据存在，是窗口错了。
- 备注：`tests/test_agent_diagnosis.py:296 test_resolve_window_defaults` 已把「now 锚点」固化为期望行为，修 D1 需同步改该用例。

### D2 · `sensor_ids` 超限被静默截断（中）

- 位置：`app/agent/tool_registry.py:68 _MAX_SENSORS_PER_CALL = 3`，第 212 行 `[:_MAX_SENSORS_PER_CALL]`
- 实测：传入 5 个测点（`vib_x/vib_y/vib_z/temp_bearing_de/temp_bearing_nde`），实际只查 3 个振动测点；返回 `ok=True`、`partial_errors=None`、**无任何截断提示**。
- 影响：模型把「没查」误判为「温度测点无数据」——链路 A、B 的 `human_reason` 都出现该错误归因，直接污染人工介入的理由。
- 对比：同文件 `_device_has_any_data`（ISS-056 补丁）已经贯彻「不静默包装空结果」的原则，此处遗漏。

---

## 五、修复（已实施 2026-10-22，登记 ISS-064 / ISS-065）

| 缺陷 | 处置 |
|---|---|
| D1 | `_resolve_window(..., anchor_ms=None)`：告警存在时以 `alarm.ts` 为锚 —— 缺省窗口 `[锚点-24h, 锚点]`、相对时间从锚点起算；`ts=0`/未来锚点回落 `now`；绝对 ISO 不受影响；终点不越过 `now`。`_exec_query_sensor` 传 `anchor_ms=alarm.ts`，并把实际窗口回灌 `result.window`。 |
| D2 | `_MAX_SENSORS_PER_CALL` 3→**5**（告警 5 测点一次查完）；仍超限时回灌 `notices` 列出未查询测点并注明「没有结论」，全失败/部分成功两条路径都带。 |

**回归**：`tests/test_agent_diagnosis.py` 新增 `test_resolve_window_anchors_on_alarm_ts`、`test_execute_query_sensor_reports_truncation`；`pytest tests -q --ignore=tests/e2e` → **391 passed**。

**修复后实测**（直连 TDengine，告警 `2026-10-20T01:30:00Z`，不传 `time_range`）：

```
window = 2026-10-19T01:30:00Z → 2026-10-20T01:30:00Z   # 锚在告警时刻
series = vib_x/vib_y/vib_z(vib_rms) 各 77 点 max 1.3645
         temp_bearing_de/nde(bearing_temp) 各 77 点 max 59.2856
notices = None                                          # 5 测点无截断
```

> 注：告警值 `7.62` 仍与存储窗口最大值 `1.36` 不符 —— 该告警值由 e2e 脚本构造，属
> **测试数据本身的矛盾**，不是系统缺陷。真实数据下窗口与取数已对齐。

> 生效前提：改为进程内常量/函数，运行中的后端需**重启**才能应用。

### 5.1 重启后复测（2026-10-22 14:1x，已重启后端）

后端以 `AUSCULT_LLM_BACKEND=cloud` + `AUSCULT_DIAGNOSIS_MODE=agent` 重启，`/api/health` 全绿
（pg / milvus / neo4j / tdengine / redis 均 up；`cloud_budget 197/340`）。

**链路 B（有数据，修复后）** `thr-9d6d6526f0bc413da265`，≈125s、5 步：

```
risk=high  conf=0.795  evidence=5  needs_human=True
human_reason=告警值 7.62 mm/s 与系统存储时序（24h 峰值 1.36 mm/s、零超限）严重矛盾，
             且 raw 粒度查询未能提供更细分辨率数据，系统无法自主裁决是误报还是真实尖峰；
             需人工现场手持测振复测，并核查传感器/采集链路与告警管道数据源
diagnosis=…（24h 峰值 1.36 mm/s、零超限、趋势平稳、轴承温度 58.7°C 正常）…
```

对比修复前：**「时间过滤疑似失效」「温度测点无数据」两条错误归因消失**，温度被测到并写进结论
（`58.7°C 正常`），confidence 0.72 → **0.795**。仍转人工的原因只剩一条真事实 —— 告警值 `7.62`
与存储峰值 `1.36` 矛盾（e2e 构造值），系统判「误报 or 尖峰」无法自主裁决，**属合理转人工**。

**链路 A（无数据，修复后）** `thr-b5e2bcfb6ed644e6aadd`，≈110s、6 步：

```
risk=high  conf=0.52  evidence=5  needs_human=True
human_reason=设备全部测点时序数据缺失（6h/24h 窗口均无数据），无法确认振动形态（突升/渐升）、
             轴向分量与轴承温度，候选根因（轴承/不平衡/不对中/松动）无法在线区分…
```

窗口锚到 `10-15~10-16` 后仍为 0 行（数据只存在于 10-14 / 10-20 / 10-21 三段），**「无数据」这次是
对告警窗口的真实描述**，转人工分支未被改坏。

> 两条线程均停在 `waiting_review`（未代人做审核决策）；需要落报告时用 §六 的命令以 `rev_dev` 提交。

---

## 六、复现要点

```powershell
# 审核员登录
$lr = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/auth/login' -Method Post `
      -ContentType 'application/json' `
      -Body ([Text.Encoding]::UTF8.GetBytes((@{username='rev_dev';password='Auscult#Dev2026'} | ConvertTo-Json)))
$RH = @{Authorization='Bearer '+$lr.data.access_token}

# 提交审核（注意：审核人 ≠ 发起人，否则 E_PERMISSION）
$rb = @{action='approved';comment='同意归档'} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/threads/$tid/review" -Method Post -Headers $RH `
  -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($rb))

# 中文不乱码的读法
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/threads/$tid" -Headers $RH -OutFile $tmp -UseBasicParsing
$d = ([IO.File]::ReadAllText($tmp,[Text.Encoding]::UTF8) | ConvertFrom-Json).data
```
