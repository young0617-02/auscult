# S1 主场景全链路走查留档（自动生成）

> 生成时间：2026-10-22 19:31:23 · 工具：`scripts/run_demo_s1.py`
> 输入：device_id=`PUMP-C-01` metric=`vib_rms` value=`6.2` severity=`high`
> 后端：`http://127.0.0.1:8000` · thread_id=`thr-27a0066442e74656a905`

## 一、过程

| 阶段 | 动作 | 结果 |
|---|---|---|
| 登录 | eng_dev | 200 · role=engineer |
| 登录 | rev_dev | 200 · role=reviewer |
| 发起 | POST /api/diagnose | 200 · thread_id=thr-27a0066442e74656a905 |
| 状态 | 变化 | running |
| 链路 | 节点 #1 | parse_alarm（累计 1） |
| 链路 | 节点 #2 | diagnose（累计 2） |
| 状态 | 变化 | waiting_review |
| 诊断 | 终态 | {"status": "waiting_review", "nodes_done": ["parse_alarm", "diagnose"], "report_id": null, "degrade_reason": null, "needs_human": true, "error": null} |
| SoD | eng_dev 自审 | 403 · 你的角色无此权限，请联系管理员 |
| 审核 | rev_dev approved | 200 · {"status": "done", "report_id": "RPT-c3be50e23212fe80", "degrade_reason": null, "human_review": {"status": "approved", "reviewer_id": "rev_dev", "comment": "S1  |
| 链路 | 节点 #1 | parse_alarm（累计 1） |
| 链路 | 节点 #2 | diagnose（累计 2） |
| 链路 | 节点 #3 | human_review（累计 3） |
| 链路 | 节点 #4 | finalize（累计 4） |
| 状态 | 变化 | done |
| 诊断 | 审核后终态 | {"status": "done", "nodes_done": ["parse_alarm", "diagnose", "human_review", "finalize"], "report_id": "RPT-c3be50e23212fe80", "degrade_reason": null, "needs_human": true, "error": null} |
| 报告 | GET /api/reports/{id} | 200 · review_status=approved |

## 二、终态

```json
{
  "status": "done",
  "nodes_done": [
    "parse_alarm",
    "diagnose",
    "human_review",
    "finalize"
  ],
  "report_id": "RPT-c3be50e23212fe80",
  "degrade_reason": null,
  "needs_human": true,
  "error": null
}
```

## 三、报告

- `report_id` = `RPT-c3be50e23212fe80`；`review_status` = `approved`
- 设备号（API 展示口径）= `None`
- 结论：PUMP-C-01 振动烈度 6.2 mm/s 超过 4.5 mm/s 阈值，落入 4.5~11.2 mm/s「注意」区间，应安排检修；因时序/温度/工单数据全部缺失，具体根因（不平衡/轴承磨损/对中不良等）暂无法确定，需人工现场核查。
- 引用条数：0

## 四、结论

**通过**：终态 `done`、`report_id=RPT-c3be50e23212fe80`，耗时 116.2s。报告已定稿并可经 API 读取，S1 链路『告警→证据→报告→审核→定稿』全段跑通。
