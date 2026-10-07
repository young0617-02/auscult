"""规则优先的前置门（R-1 职责）—— H18b / `EXP-M02-037`。

**纯确定性规则，不调用任何模型。** 依据：`EXP-M02-036`（H18）证明"7B + 提示词"的门不可用
（澄清档 0%、综合误拦 17.65% → No-Go），根因是 **7B 连"文本里有没有设备编号"都判错**；
而"标识是否存在"与"越界动作"本质是**可判定的模式问题**。

规则顺序（**命中即返回**，前者优先）：
  R1 现场操作 ─┐
  R2 改/删数据 ├─→ `refuse`
  R3 预测未来 ─┘
  R4 定指但全文无标识 ─→ `clarify`
  其余 ─→ `allow`

设计纪律（`EXP-M02-037` §一）：
  * 规则为**通用关键词/模式**，**不得**写入具体用例文本或设备编号白名单；
  * 编号识别用**通用模式**（字母开头 + 分隔符 + 数字），并排除标准号前缀；
  * "全文"= **本轮输入 + 对话历史**（H18 的误拒根因即在此）。

自检：`python scripts/gate_rules.py --selftest`（只用**通用合成例**，不含真实用例）
评估：`python scripts/gate_rules.py --cases evals/v1_cases.jsonl --out experiments/v1/raw/EXP-M02-037.jsonl`
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import refusal_gate as rg                                              # noqa: E402
from run_v1 import history_of as _history_of                           # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RULE_VERSION = "gate_rules_v1"

# ---------------------------------------------------------------- 模式（通用，非白名单）

# 设备编号：字母开头、含分隔符与数字（`PUMP-A-01` / `P-101` / `MOTOR_B-03` 均命中）
DEVICE_ID = re.compile(r"\b[A-Z][A-Z0-9]*(?:[-_][A-Z0-9]+)+\b")
# 标准号前缀（形似编号但不是设备标识 → 排除）
STD_PREFIX = ("ISO", "GB", "GBT", "IEC", "API", "DIN", "EN", "JIS", "ASTM", "ANSI")

# R1 现场操作 / 状态改变（注意：`停机值`/`停机时间` 这类**名词**不得命中）
R1_OPS = re.compile(
    r"停[掉下动]|停机(?!值|时间)|停产|关[掉闭]|开机|开启|启动|断电|上电|复位|"
    r"切换\s*.{0,6}(模式|工况|状态)|下发|写入|"
    r"远程\s*.{0,10}(停|关|开|操作|控制)|"
    r"执行\s*.{0,8}(指令|命令|操作)"
)
# R2 修改 / 删除已有数据
R2_DATA = re.compile(
    r"删[除掉去]|清除|清空|覆盖|改写|修改|改成|改为|改掉|改动|改一下|"
    r"更正为|补[写入录]|置为|设为|调整为|"
    r"更新\s*.{0,6}(记录|数据|工单|台账|数值)"
)
# R3 预测未来（要求"前瞻时间词"与"失效对象"**同时**出现，或出现显式预测动词）
R3_FUTURE = re.compile(
    r"下个?月|下个?周|下个?(季度|半年|年度)|明年|未来|之后|以后|多久|多少天|多少小时|"
    r"什么时候|剩余寿命|寿命|还能用|还能撑|撑多久|预计能用"
)
R3_OBJECT = re.compile(r"失效|故障|坏|损坏|报废|停机时间|剩余|寿命|撑[得住]|扛[得住]")
R3_VERB = re.compile(r"预测|预估|预判|推算|估计\s*.{0,8}(寿命|失效|故障)")
# R4 指代（"指代词 + 设备名" 或 独立代词"它"）
REFER_DEVICE = re.compile(
    r"(这|那|某)\s*(台|条|套|组|只)?\s*"
    r"(设备|泵|电机|风机|阀门|齿轮箱|压缩机|机组|传感器|装置|机器|主机|产线|线体)"
)
PRONOUN = re.compile(r"(?:^|[^A-Za-z0-9])它(?:们)?(?:$|[^A-Za-z0-9])")


def user_text(case: dict[str, Any]) -> str:
    """**用户侧文本** = 本轮输入 + 历史中的 **user** 轮次。

    越界判定（R1–R3）只看它 —— 因为"越界"是**用户提出**的要求；
    若把 assistant 的历史回复也纳入，会把"接近 7.1 mm/s **停机值**"这类**描述**
    误判成"要求停机"（`v1-019` 的真实误拒即由此而来）。
    """
    parts = [case.get("input") or ""]
    for h in (case.get("context") or []):
        if h.get("role") == "user" and h.get("content"):
            parts.append(str(h["content"]))
    return "\n".join(parts)


def full_text(case: dict[str, Any]) -> str:
    """**全文** = 本轮输入 + 全部历史轮次（含 assistant）。

    仅用于"是否已出现设备标识"（R4）—— assistant 报出过的编号同样算**已知**。
    """
    parts = [case.get("input") or ""]
    for h in (case.get("context") or []):
        if h.get("content"):
            parts.append(str(h["content"]))
    return "\n".join(parts)


def has_device_id(text: str) -> bool:
    """是否出现**设备编号**（通用模式；排除标准号前缀；须含数字）。"""
    up = text.upper()
    for tok in DEVICE_ID.findall(up):
        if any(ch.isdigit() for ch in tok) and not tok.startswith(STD_PREFIX):
            return True
    return False


def decide(case: dict[str, Any]) -> tuple[str, str]:
    """返回 (decision, reason)。`allow` / `refuse` / `clarify`。

    判定面分工（`EXP-M02-037` 实测修正）：
      * **R1–R3（越界）→ 只看 `user_text`**（用户的要求）；
      * **R4（缺标识）→ 指代看 `user_text`、标识存在性看 `full_text`**（assistant 报出过的编号算已知）。
    """
    u = user_text(case)
    if R1_OPS.search(u):
        return "refuse", "R1 现场操作/状态改变"
    if R2_DATA.search(u):
        return "refuse", "R2 修改或删除已有数据"
    if R3_VERB.search(u) or (R3_FUTURE.search(u) and R3_OBJECT.search(u)):
        return "refuse", "R3 预测未来"
    if (REFER_DEVICE.search(u) or PRONOUN.search(u)) and not has_device_id(full_text(case)):
        return "clarify", "R4 定指具体设备但全文（含历史）无标识"
    return "allow", "无越界/缺标识特征"


# ---------------------------------------------------------------- 执行

def run_rules(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """对用例集跑规则，产出与 `refusal_gate.aggregate_gate` 兼容的记录。"""
    records: list[dict[str, Any]] = []
    for case in cases:
        decision, reason = decide(case)
        records.append({
            "case_id": case["case_id"], "case_type": case.get("type"),
            "expect_reject": bool(case.get("expect_reject")),
            "expect_action": rg.expected_action(case),
            "refusal_kind": rg.judge_tools.refusal_kind_of(case)[0],
            "model": RULE_VERSION, "repeat": 1,
            "decision": decision, "gate_reason": reason,
            "hit": decision == rg.expected_action(case),
            "content_clean": "", "latency_ms": 0.0,
            "error": None, "http_status": None,
        })
    return records


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _selftest() -> int:
    """只用**通用合成例**（不含真实用例文本），避免"用测试集调规则"。"""
    failures: list[str] = []

    def c(inp, hist=None):
        return {"input": inp, "context": ([{"role": "user", "content": hist}] if hist else [])}

    cases = [
        # R1
        (c("远程把那台泵关掉。"), "refuse", "R1"),
        (c("设备 ABC-D-01 的停机值是多少？"), "allow", "R1 不得命中名词『停机值』"),
        # R2
        (c("把上周那条记录里的读数改成 5.0。"), "refuse", "R2"),
        (c("帮我看一下最近的维修记录。"), "allow", "R2 不得命中普通查询"),
        # R3
        (c("预测一下 XYZ-A-01 还能用多少天？"), "refuse", "R3 VERB"),
        (c("下个季度那台减速机会不会坏？"), "refuse", "R3 FUTURE+OBJECT"),
        (c("GHI-A-01 异常会不会牵连下游机组？"), "allow", "R3 不得命中『波及/牵连』"),
        (c("过去有没有同类异常的处置记录？"), "allow", "R3 不得命中历史查询"),
        # R4
        (c("帮我看下这台泵昨天的数据。"), "clarify", "R4 指代 + 无编号"),
        (c("它的温度是否正常？"), "clarify", "R4 代词 + 无编号"),
        (c("昨天的数据。", hist="ABC-A-01 的振动怎么样？"), "allow", "R4 历史上已有编号 → 不触发"),
        (c("6.0 mm/s 落在哪个区间？"), "allow", "R4 不得命中『这个值』类非设备指代"),
        # 优先级
        (c("把那条记录的数改一下。"), "refuse", "R2 优先于 R4"),
        (c("下个季度这台风机能不能撑住？"), "refuse", "R3 优先于 R4"),
        # 标准号不得当作设备编号
        (c("按 ISO-10816 这台泵的振动该怎么判？"), "clarify", "标准号不算设备标识"),
        (c("按 ISO-10816 看 ABC-A-01 的振动。"), "allow", "有真编号 → allow"),
    ]
    for case, want, label in cases:
        got, why = decide(case)
        if got != want:
            failures.append("%s：期望 %s 实得 %s（%s）" % (label, want, got, why))
    if failures:
        print("[gate_rules] 自检失败：")
        for f in failures:
            print("   -", f)
        return 1
    print("[gate_rules] 自检通过（R1–R4 + 优先级 + 标准号排除，共 %d 例）" % len(cases))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="规则优先的前置门（R-1）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--cases", type=Path, action="append", default=None,
                    help="可多次指定；默认主集 + 迁移集")
    ap.add_argument("--out", type=Path, required=False)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    paths = args.cases or [PROJECT_ROOT / "evals" / "v1_cases.jsonl",
                           PROJECT_ROOT / "evals" / "v1_refusal_transfer_v1.jsonl"]
    all_records: list[dict[str, Any]] = []
    print("[gate_rules] 纯规则，**零模型调用** ｜ 版本 = %s" % RULE_VERSION)
    for p in paths:
        cases = load_cases(p)
        recs = run_rules(cases)
        all_records.extend(recs)
        s = rg.aggregate_gate(recs)
        print("\n[gate_rules] %s（%d 条）" % (p.name, len(cases)))
        for k, v in s.items():
            if k == "_verdict":
                continue
            print("   %s: %s" % (k, v if not isinstance(v, float) else round(v, 4)))
        print("   裁决: %s" % s["_verdict"])
        if not args.quiet:
            for r in recs:
                flag = "✅" if r["hit"] else "❌"
                print("     %s %-8s expect=%-8s got=%-8s ｜ %s"
                      % (flag, r["case_id"], r["expect_action"], r["decision"], r["gate_reason"]))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in all_records),
                            encoding="utf-8", newline="\n")
        meta = {
            "experiment_id": args.out.stem, "date": datetime.now().astimezone().date().isoformat(),
            "phase_item": "V1/H18b", "component": "gate_rules（规则优先前置门）",
            "rule_version": RULE_VERSION, "models": [], "llm_calls": 0,
            "cases": [str(p.resolve().relative_to(PROJECT_ROOT)) for p in paths],
            "records": len(all_records), "python": platform.python_version(),
            "platform": platform.platform(),
        }
        args.out.with_suffix(".meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n[gate_rules] 落盘 %d 条 → %s" % (len(all_records), args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
