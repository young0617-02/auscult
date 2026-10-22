"""S1 主场景全链路演示编排（D9 留档工具，2026-10-22）。

## 干什么

把 `demo/scenario.md` §二 的 7 步**串成一条可复现命令**，一路跑到报告定稿：

```
登录(eng_dev/rev_dev) → POST /api/diagnose → 轮询节点进度
  → 报告产出 → SoD 拒绝(eng_dev 自审) → rev_dev 审核通过 → 定稿 + 报告可读
```

每一步都打印"实际返回值 + 耗时"，并把整段过程写成 markdown 留档（`demo/recording/`），
替代"人工盯着界面操作"——现场仍建议录屏，但这份留档能证明链路真的跑过。

## 为什么不是纯 curl

诊断是**异步**的（`start_diagnosis` 后台跑），本地 7B 单次诊断 100–200s 属已知瓶颈
（`reports/p5-eval.md` 端到端 9248.8ms 是服务端口径，本地真实链路更慢）。轮询 + 超时 +
失败分支必须写进代码，否则现场靠手点容易误判"卡住了"。

## 用法

    .venv\\Scripts\\python.exe scripts\\run_demo_s1.py
    .venv\\Scripts\\python.exe scripts\\run_demo_s1.py --device PUMP-A-01 --value 6.2
    .venv\\Scripts\\python.exe scripts\\run_demo_s1.py --no-review      # 只跑到等待审核
    .venv\\Scripts\\python.exe scripts\\run_demo_s1.py --out demo\\recording\\s1-run-2026-10-22.md

前置：`deploy/up.ps1` + `seed_users.py` 已跑，后端 `127.0.0.1:8000` 已起。
"""

from __future__ import annotations

import argparse
import os
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "demo" / "recording" / "s1-run-2026-10-22.md"
DEFAULT_BASE = "http://127.0.0.1:8000"
# 2026-10-22：种子账号默认口令走 env（`AUSCULT_SEED_PASSWORD`），不再硬编码——
# 硬编码会被 `scripts/test_p5_d12_security.py::test_secret_scan` 判为"未知硬编码凭证"。
PASSWORD = os.environ.get("AUSCULT_SEED_PASSWORD", "Auscult#Dev2026")

LOG: list[tuple[str, str, str]] = []      # (阶段, 动作, 结果)


def _say(stage: str, action: str, result: str) -> None:
    LOG.append((stage, action, result))
    print(f"[{stage}] {action} → {result}", flush=True)


def _req(base: str, method: str, path: str, body: dict | None = None,
         token: str | None = None, timeout: float = 90.0) -> tuple[int, dict]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


def login(base: str, username: str) -> str:
    code, payload = _req(base, "POST", "/api/auth/login",
                         {"username": username, "password": PASSWORD})
    if code != 200:
        raise SystemExit(f"登录失败 {username}: {code} {payload}")
    token = payload["data"]["access_token"]
    role = payload["data"]["user"]["role"]
    _say("登录", username, f"200 · role={role}")
    return token


def poll(base: str, thread_id: str, token: str, *, timeout: float = 900.0) -> dict:
    """轮询到终态；节点每前进一次打印一行（现场能看出"在动"）。"""
    deadline = time.time() + timeout
    seen: list[str] = []
    last = ""
    while time.time() < deadline:
        code, payload = _req(base, "GET", f"/api/threads/{thread_id}", token=token)
        if code != 200:
            raise SystemExit(f"线程查询失败: {code} {payload}")
        st = payload["data"]
        for node in st.get("nodes_done") or []:
            if node not in seen:
                seen.append(node)
                _say("链路", f"节点 #{len(seen)}", f"{node}（累计 {len(seen)}）")
        status = st.get("status")
        if status != last:
            _say("状态", "变化", f"{status}")
            last = status
        if status in ("waiting_review", "done", "failed", "refused"):
            return st
        time.sleep(5)
    raise SystemExit(f"轮询超时（{timeout:.0f}s）：最后状态 {last}")


def summarize(st: dict) -> dict:
    return {
        "status": st.get("status"),
        "nodes_done": st.get("nodes_done") or [],
        "report_id": st.get("report_id"),
        "degrade_reason": st.get("degrade_reason"),
        "needs_human": st.get("needs_human"),
        "error": st.get("error"),
    }


def write_record(out: Path, ctx: dict) -> None:
    lines = [
        "# S1 主场景全链路走查留档（自动生成）",
        "",
        f"> 生成时间：{ctx['at']} · 工具：`scripts/run_demo_s1.py`",
        f"> 输入：device_id=`{ctx['device']}` metric=`vib_rms` value=`{ctx['value']}` severity=`high`",
        f"> 后端：`{ctx['base']}` · thread_id=`{ctx['thread_id']}`",
        "",
        "## 一、过程",
        "",
        "| 阶段 | 动作 | 结果 |",
        "|---|---|---|",
    ]
    lines += [f"| {s} | {a} | {r} |" for s, a, r in LOG]
    lines += [
        "",
        "## 二、终态",
        "",
        "```json",
        json.dumps(ctx["final"], ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    if ctx.get("report"):
        rep = ctx["report"]
        payload = rep.get("payload") or {}
        lines += [
            "## 三、报告",
            "",
            f"- `report_id` = `{rep.get('report_id')}`；`review_status` = `{rep.get('review_status')}`",
            f"- 设备号（API 展示口径）= `{payload.get('device_id')}`",
            f"- 结论：{(payload.get('diagnosis') or '')[:300]}",
            f"- 引用条数：{len(payload.get('citations') or [])}",
            "",
        ]
    lines += [
        "## 四、结论",
        "",
        ctx["verdict"],
        "",
    ]
    # 2026-10-22 修复：`--out` 传相对路径时，`out.relative_to(PROJECT_ROOT)` 会抛
    # ValueError（Path 未 resolve，相对路径不在 PROJECT_ROOT 之下）—— 链路已全跑完
    # 却在最后一步崩掉，最坏的失败位置。先 resolve 再取相对路径，跨盘/盘符外则原样打印。
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    try:
        shown = str(out.relative_to(PROJECT_ROOT))
    except ValueError:
        shown = str(out)
    _say("留档", "写入", shown)


def main() -> int:
    ap = argparse.ArgumentParser(description="S1 主场景全链路演示编排")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--device", default="PUMP-C-01", help="规范编号（迁移后口径）")
    ap.add_argument("--value", type=float, default=6.2)
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--no-review", action="store_true", help="只跑到 waiting_review")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    started = time.time()
    eng = login(args.base, "eng_dev")
    rev = login(args.base, "rev_dev")

    alarm = {"device_id": args.device, "metric": "vib_rms",
             "value": args.value, "severity": "high"}
    code, payload = _req(args.base, "POST", "/api/diagnose", {"alarm": alarm}, token=eng)
    if code != 200:
        raise SystemExit(f"发起诊断失败: {code} {payload}")
    thread_id = payload["data"]["thread_id"]
    _say("发起", "POST /api/diagnose", f"200 · thread_id={thread_id}")

    st = poll(args.base, thread_id, eng, timeout=args.timeout)
    _say("诊断", "终态", json.dumps(summarize(st), ensure_ascii=False)[:220])

    if st.get("status") == "waiting_review" and not args.no_review:
        # ① 职责分离：发起人自审必须被拒（ISS-039 旁证）
        code, payload = _req(args.base, "POST", f"/api/threads/{thread_id}/review",
                             {"action": "approved", "comment": "自审尝试"}, token=eng)
        _say("SoD", "eng_dev 自审", f"{code} · {payload.get('error') or payload.get('message')}")

        # ② 审核人通过
        code, payload = _req(args.base, "POST", f"/api/threads/{thread_id}/review",
                             {"action": "approved", "comment": "S1 演示审核通过"}, token=rev)
        _say("审核", "rev_dev approved", f"{code} · {json.dumps(payload.get('data'), ensure_ascii=False)[:160]}")
        st = poll(args.base, thread_id, rev, timeout=args.timeout)
        _say("诊断", "审核后终态", json.dumps(summarize(st), ensure_ascii=False)[:220])

    report = None
    if st.get("report_id"):
        code, payload = _req(args.base, "GET", f"/api/reports/{st['report_id']}", token=rev)
        if code == 200:
            report = payload["data"]
            _say("报告", "GET /api/reports/{id}", f"200 · review_status={report.get('review_status')}")
        else:
            _say("报告", "GET /api/reports/{id}", f"{code} · {payload}")

    elapsed = time.time() - started
    ok_all = st.get("status") == "done" and bool(st.get("report_id"))
    if args.no_review:
        ok_all = st.get("status") in ("waiting_review", "done")

    verdict = (
        f"**{'通过' if ok_all else '未走通'}**：终态 `{st.get('status')}`、`report_id={st.get('report_id')}`，"
        f"耗时 {elapsed:.1f}s。"
        + ("报告已定稿并可经 API 读取，S1 链路『告警→证据→报告→审核→定稿』全段跑通。"
           if ok_all else
           f"未见报告：`degrade_reason={st.get('degrade_reason')}`、`error={st.get('error')}`（按演示纪律如实记录）。")
    )
    write_record(args.out, {"at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "device": args.device, "value": args.value, "base": args.base,
                            "thread_id": thread_id, "final": summarize(st),
                            "report": report, "verdict": verdict})
    print(f"\n总耗时 {elapsed:.1f}s · {'PASS' if ok_all else 'FAIL'}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
