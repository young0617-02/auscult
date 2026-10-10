# D9 演示排练记录（demo/recording/rehearsal-log.md）

> **级别**：Phase 6 交付包 · 演示留档（`M6.3` / `D9`）
> **最近更新**：2026-10-10
> **对应**：`demo/scenario.md`、`docs/pitch.md`

## 一、排练实测结论（2026-10-10）

| 项 | 实测 | 证据 |
|---|---|---|
| 基建栈 up | 8 容器 up，7 基建 healthy（nginx 依赖后端未计） | `docker ps` |
| 种子用户 | 幂等写入 4 角色（eng_dev/rev_dev/kb_dev/sys_dev） | `scripts/seed_users.py` |
| 后端启动 | uvicorn `socket_app` :8000 startup complete | 后端日志 |
| 登录 | POST `/api/auth/login` eng_dev → 返回 Bearer token | 实测 200 |
| 触发 S1 | POST `/api/diagnose` 内联 alarm vib_rms=6.2 → thread_id | 实测返回 |
| 链路推进 | thread 进度到 `parse_alarm`→`analyze_sensor`，status=running | `GET /api/threads/...` |
| **Trace 全链路（实测留档）** | Trace 完整记录 **parse_alarm→analyze_sensor→retrieve_evidence(110924ms)→get_history→diagnose(23913ms)→risk=high** 五节点全真实执行 | `reports/traces/thr-839f45544e274271a1c0.jsonl` |

**结论**：演示触发链路**真实可用**，且 S1 主场景的**关键节点（告警解析→传感器→混合检索→历史工单→诊断推理）在真实排练中全部跑通**，产出 `risk=high`（命中强制审核线）。完整出报告/审核定稿因排练后停止后端而未到节点，留现场复跑；本地 LLM 生成慢（retrieve_evidence 111s + diagnose 24s）属 P95 9.2s 已知瓶颈的放大体现。配套权威复现已由既有 E2E 测试覆盖（`tests/e2e/test_e2e_scenarios.py` E1 离心泵轴承振动→报告、E2 高风险→人工审核，Phase 3 M3.5 通过）。

## 二、排练中发现并修正（词表口径）

D9 排练前核对内联 alarm 对象词表：`AlarmEvent.severity` 为 **high/medium/low**（`app/graph/state.py`），非 `alerts` 表落库词表（critical/warning，经 `_SEV_PG_MAP` 映射）。`demo/data/alarms.json` 内联对象原用 critical/warning → 已修正为 high/medium：
- S1 vib_rms=6.2 → high（阈值 >4.5 high 规则）
- S2 bearing_temp=92 → high
- S3 motor_current=16.8 → medium
- S4 vib_rms=5.1 → high（S4 与 S1 同属振动 high 规则；纯演示 escalate_cloud 需弱证据，现场预跑确认）

> 两套词表并存已在 `docs/prj-spec-data-dictionary.md` §四.1 与 `docs/prj-spec-api.md` §2.7 如实登记。

## 三、现场演示建议

1. 演示前先 `deploy/up.ps1` + `init.ps1` + seed_users + 起后端 + 起前端（`scenario.md` §一）。
2. 诊断慢（9.2s P95）属已知瓶颈，开场前可预热一次诊断。
3. 图谱为空按 `docs/pitch.md` A1 口径如实说明，主流程是文档混合检索闭环。
4. 录屏/截图留 `demo/recording/`（D9 正式留档在此补录）。

## 四、本轮未提交变更

- 修正 `demo/data/alarms.json`（severity 词表 high/medium）
- 新增 `demo/recording/rehearsal-log.md`
- 新增 `docs/pitch.md`
