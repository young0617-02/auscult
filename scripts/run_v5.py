"""V5 Checkpoint 可靠性验证器（T5.1–T5.7）

对应交付物：`Phase 0 详细开发计划（D1-D10 可执行版）.md` §三 D6–D7 · T5.1–T5.7
判据依据：`docs/gate-criteria.md` V5 行 ｜ 决策依据：`docs/checkpoint-decision.md` §五
实验编号：`EXP-V5-001` ~ `EXP-V5-007`（与 `docs/checkpoint-decision.md` §6.1 一一对应）

覆盖的 7 个步骤：
  T5.1 最小工作流（3–4 节点 + 1 个 `interrupt()` 审核节点，**关键词命中触发**）
  T5.2 缺陷复现：`has_writes` 覆盖问题（`putWrites` 后读 `getState()`）
  T5.3 恢复测试：进程被杀后从 checkpoint 恢复并校验 payload
  T5.4 幂等验证：记录工具执行次数，检测恢复后是否重复执行
  T5.5 并发/多实例：双审核人竞争 resume（`lock:review:{thread_id}` SETNX）
  T5.6 体积治理：checkpoint 增长速率、key 数、归档与保留上限
  T5.7 TTL/驱逐：`noeviction` + 无 TTL + 内存上限告警验证

依赖（惰性导入，缺失时给出明确安装指引）：
  uv pip install langgraph langgraph-checkpoint-redis redis

自检：`python scripts/run_v5.py --selftest`（不依赖 langgraph / redis）
用法：
  python scripts/run_v5.py --step t5.1 --out experiments/v5/raw/EXP-V5-001.jsonl
  python scripts/run_v5.py --step t5.3 --resume <thread_id>   # 杀进程后执行
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "experiments" / "v5" / "raw"

REDIS_URL = "redis://127.0.0.1:6379/0"
# 候选 B（PostgreSQL checkpointer）连接串 —— 项目库 auscult_v2（一项目一库纪律）
# 端口 5433 = docker/compose.v2.yml 的 paradedb 宿主映射（见 docs/version-lock.md §二.2.8）
POSTGRES_URL = "postgresql://root:123456@127.0.0.1:5433/auscult_v2"
REVIEW_LOCK_TTL = 30                 # 秒，见 checkpoint-decision §3.3
CKPT_KEY_PATTERN = "ckpt:*"
CKPT_BYTES_LIMIT = 1 * 1024 * 1024   # 单 thread 体积告警线（1MB，须实测后回填 §6.2）
MEMORY_WARN_RATIO = 0.80             # 内存告警阈值（80% / 95%）
MEMORY_CRIT_RATIO = 0.95
SCHEMA_VERSION = "report_v1"

# 触发强制人工审核的关键词（T5.1「关键词命中触发」）
REVIEW_KEYWORDS = ("停机", "更换", "高风险", "critical", "立即处理")

STEPS: dict[str, dict[str, str]] = {
    "t5.1": {"experiment_id": "EXP-V5-001", "title": "最小工作流（关键词命中触发 interrupt）"},
    "t5.2": {"experiment_id": "EXP-V5-002", "title": "缺陷复现：has_writes 覆盖问题"},
    "t5.3": {"experiment_id": "EXP-V5-003", "title": "恢复测试：杀进程后从 checkpoint 恢复"},
    "t5.4": {"experiment_id": "EXP-V5-004", "title": "幂等验证：恢复后工具重复执行计数"},
    "t5.5": {"experiment_id": "EXP-V5-005", "title": "并发/多实例：双审核人竞争 resume"},
    "t5.6": {"experiment_id": "EXP-V5-006", "title": "体积治理：增长速率与保留上限"},
    "t5.7": {"experiment_id": "EXP-V5-007", "title": "TTL/驱逐：noeviction + 无 TTL 验证"},
}

# 阻塞缺陷（B1–B7，见 checkpoint-decision §5.1）→ 检查项编号
# ⚠️ B7（第三方实现兼容性缺陷）**没有任何步骤会赋值**：它是"候选 A 环境不可用"的
#    人工判定结论（Redis 路线握手被服务端关闭，见 docs/checkpoint-decision.md §2.1），
#    本执行器不自动触发。因此 `blocking_defects()` 的返回值中**不会**出现 B7。
BLOCKING_CHECKS: dict[str, str] = {
    "B1": "重启后状态不完整",
    "B2": "payload 不一致",
    "B3": "重复副作用（幂等键未拦住）",
    "B4": "has_writes 覆盖且不可规避",
    "B5": "TTL/驱逐导致丢状态",
    "B6": "双审核人并发无法保证唯一性",
    "B7": "第三方实现兼容性缺陷",
}


# ---------------------------------------------------------------- 纯逻辑（可自检）

def needs_review(text: str, keywords: tuple[str, ...] = REVIEW_KEYWORDS) -> bool:
    """关键词命中即触发人工审核（T5.1 的触发条件）。"""
    return any(kw in text for kw in keywords)


def idempotency_key(thread_id: str, report_type: str, content: str,
                    schema_version: str = SCHEMA_VERSION) -> str:
    """幂等键 = sha256(thread_id + report_type + content_digest + schema_version)。

    逐字采用 `docs/checkpoint-decision.md` §4.3 的构成。
    """
    content_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    raw = f"{thread_id}{report_type}{content_digest}{schema_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RedisLike(Protocol):
    """`redis.Redis` 的最小子集，便于自检时用内存桩替换。"""

    def set(self, name: str, value: str, nx: bool = False, ex: int | None = None) -> Any: ...
    def get(self, name: str) -> Any: ...
    def delete(self, *names: str) -> Any: ...
    def ttl(self, name: str) -> int: ...
    def scan_iter(self, match: str = "*") -> Any: ...
    def config_get(self, name: str) -> Any: ...


def acquire_review_lock(client: RedisLike, thread_id: str,
                        ttl: int = REVIEW_LOCK_TTL) -> bool:
    """双审核人并发保护：`SETNX lock:review:{thread_id}`，返回是否抢到锁。"""
    return bool(client.set(f"lock:review:{thread_id}", "1", nx=True, ex=ttl))


def release_review_lock(client: RedisLike, thread_id: str) -> None:
    client.delete(f"lock:review:{thread_id}")


def collect_ckpt_stats(client: RedisLike, thread_id: str | None = None) -> dict[str, Any]:
    """统计 checkpoint 体积：key 数、总字节、单 key 最大值、TTL 异常 key。

    `ttl == -1` 表示未设过期（**期望值**）；`ttl >= 0` 表示设了 TTL（**违反无 TTL 纪律**）。
    """
    pattern = f"ckpt:{thread_id}:*" if thread_id else CKPT_KEY_PATTERN
    keys = list(client.scan_iter(match=pattern))
    total_bytes = 0
    max_bytes = 0
    with_ttl: list[str] = []
    for key in keys:
        size = _key_size(client, key)
        total_bytes += size
        max_bytes = max(max_bytes, size)
        ttl = client.ttl(key)
        if ttl is not None and ttl >= 0:
            with_ttl.append(key)
    return {
        "thread_id": thread_id,
        "key_count": len(keys),
        "total_bytes": total_bytes,
        "max_key_bytes": max_bytes,
        "keys_with_ttl": len(with_ttl),
        "keys_with_ttl_sample": with_ttl[:5],
    }


def _key_size(client: RedisLike, key: str) -> int:
    usage = getattr(client, "memory_usage", None)
    if callable(usage):
        size = usage(key)
        return int(size or 0)
    value = client.get(key)
    if value is None:
        return 0
    if isinstance(value, bytes):
        return len(value)
    return len(str(value).encode("utf-8"))


def check_redis_policy(client: RedisLike) -> dict[str, Any]:
    """验证实例级配置：`maxmemory-policy=noeviction` 且 `maxmemory` 已设上限。

    内存占用比取自 `INFO memory` 的 `used_memory / maxmemory`（取不到则记 None，
    不得用估算值冒充实测）。
    """
    policy = _config_value(client, "maxmemory-policy")
    maxmemory = _config_value(client, "maxmemory")
    maxmemory_int = int(maxmemory) if str(maxmemory).isdigit() else 0
    used, ratio = _memory_usage(client, maxmemory_int)
    return {
        "maxmemory_policy": policy,
        "noeviction_ok": policy == "noeviction",
        "maxmemory": maxmemory,
        "maxmemory_set": maxmemory_int > 0,
        "used_memory": used,
        "usage_ratio": ratio,
        "warn_threshold": MEMORY_WARN_RATIO,
        "crit_threshold": MEMORY_CRIT_RATIO,
    }


def _memory_usage(client: RedisLike, maxmemory: int) -> tuple[int | None, float | None]:
    info_fn = getattr(client, "info", None)
    if not callable(info_fn):
        return None, None
    try:
        info = info_fn("memory")
    except Exception:                                         # noqa: BLE001 - 不同实现差异
        return None, None
    used = info.get("used_memory") if isinstance(info, dict) else None
    if used is None:
        return None, None
    return int(used), (int(used) / maxmemory if maxmemory else None)


def _config_value(client: RedisLike, name: str) -> Any:
    result = client.config_get(name)
    if isinstance(result, dict):
        for key, value in result.items():
            decoded = key.decode() if isinstance(key, bytes) else key
            if decoded == name:
                return value.decode() if isinstance(value, bytes) else value
    return None


def compare_payload(before: dict[str, Any], after: dict[str, Any],
                    fields: tuple[str, ...] = ("alarm", "evidence", "risk_level",
                                               "root_cause", "confidence")) -> list[str]:
    """恢复前后 payload 逐字段比对，返回差异描述（空列表 = 无差异）。"""
    diffs: list[str] = []
    for name in fields:
        if name not in before or name not in after:
            diffs.append(f"字段缺失：{name}（恢复前 {'有' if name in before else '无'} / "
                         f"恢复后 {'有' if name in after else '无'}）")
            continue
        if before[name] != after[name]:
            diffs.append(f"字段不一致：{name}")
    return diffs


def blocking_defects(checks: dict[str, bool]) -> list[str]:
    """把检查项结果映射到 B1–B7 阻塞缺陷编号（True = 通过）。"""
    return [code for code, _ in BLOCKING_CHECKS.items() if checks.get(code) is False]


def verdict(blocking: list[str]) -> str:
    if blocking:
        return f"No-Go（阻塞缺陷 {', '.join(blocking)}）→ 切 PostgreSQL checkpointer"
    return "Pass"


# ---------------------------------------------------------------- 内存桩（自检用）


class MemoryRedis:
    """`redis.Redis` 的内存桩，仅用于自检（不写入任何实验数据）。"""

    def __init__(self, policy: str = "noeviction", maxmemory: str = "1073741824") -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.config = {"maxmemory-policy": policy, "maxmemory": maxmemory}

    def set(self, name: str, value: str, nx: bool = False, ex: int | None = None) -> Any:
        if nx and name in self.store:
            return None
        self.store[name] = value
        if ex is not None:
            self.ttls[name] = ex
        return True

    def get(self, name: str) -> Any:
        return self.store.get(name)

    def delete(self, *names: str) -> Any:
        for name in names:
            self.store.pop(name, None)
            self.ttls.pop(name, None)
        return len(names)

    def ttl(self, name: str) -> int:
        if name not in self.store:
            return -2
        return self.ttls.get(name, -1)

    def scan_iter(self, match: str = "*") -> Any:
        prefix = match.rstrip("*")
        return [k for k in list(self.store) if k.startswith(prefix)]

    def config_get(self, name: str) -> Any:
        return {name: self.config.get(name, "")}

    def memory_usage(self, name: str) -> int:
        return len(self.store.get(name, "").encode("utf-8"))


# ---------------------------------------------------------------- LangGraph 装配


def _require_langgraph() -> dict[str, Any]:
    try:
        from langgraph.graph import END, START, StateGraph           # noqa: PLC0415
        from langgraph.types import Command, interrupt                # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "缺少 langgraph，请先安装：uv pip install langgraph langgraph-checkpoint-redis redis"
        ) from exc
    return {"StateGraph": StateGraph, "START": START, "END": END,
            "Command": Command, "interrupt": interrupt}


@contextmanager
def build_checkpointer(kind: str, redis_url: str):
    """构造 checkpointer 生命周期（contextmanager）。

    langgraph 官方 checkpointer（redis / postgres）的 `from_conn_string()` 现返回
    **上下文管理器**：连接池的连接生命周期由 `with` 块界定。故本函数以 contextmanager
    暴露 saver，`graph.compile + invoke/get_state` 必须位于 `with` 块内，块退出即关连接。
    """
    if kind == "memory":
        from langgraph.checkpoint.memory import InMemorySaver        # noqa: PLC0415
        yield InMemorySaver()
        return
    if kind == "redis":
        # 候选 A（第三方，langgraph-checkpoint-redis）
        try:
            from langgraph.checkpoint.redis import RedisSaver        # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "缺少 langgraph-checkpoint-redis（第三方实现，候选 A），请安装："
                "uv pip install langgraph-checkpoint-redis") from exc
        # ⚠️ B7：当前 vanilla redis:8 缺 RediSearch 模块，RedisSaver 连接即被服务端断开。
        #     该路径在 V5 实测中被判为 No-Go（见 reports/v5-report.md §六 B7）。
        with RedisSaver.from_conn_string(redis_url) as saver:
            yield saver
        return
    if kind == "postgres":
        # 候选 B（官方，langgraph-checkpoint-postgres）—— 本次 V5 采纳路线
        try:
            from langgraph.checkpoint.postgres import PostgresSaver  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "缺少 langgraph-checkpoint-postgres（候选 B），请安装："
                "uv pip install langgraph-checkpoint-postgres") from exc
        with PostgresSaver.from_conn_string(POSTGRES_URL) as saver:
            saver.setup()
            yield saver
        return
    raise ValueError(f"未知 checkpointer：{kind}")


def build_graph(checkpointer: Any, side_effects: Path) -> Any:
    """最小工作流：告警解析 → 只读工具 → 诊断推理 → interrupt() 审核。

    ★ 只读工具留在图内（天然幂等）；`generate_report` 写操作**移出图内**
      （见 `docs/checkpoint-decision.md` §四）。工具执行次数落盘到 `side_effects`，
      供 T5.4 检测恢复后的重复执行。
    """
    api = _require_langgraph()
    StateGraph, START, END = api["StateGraph"], api["START"], api["END"]
    interrupt = api["interrupt"]

    def node_parse_alarm(state: dict[str, Any]) -> dict[str, Any]:
        return {**state,
                "alarm": {"device_id": state["device_id"], "metric": "vib_x",
                          "value": 7.1, "limit": 4.5},
                "evidence": [], "steps": ["parse_alarm"]}

    def node_readonly_tools(state: dict[str, Any]) -> dict[str, Any]:
        for tool in ("query_sensor", "search_knowledge"):
            side_effects.parent.mkdir(parents=True, exist_ok=True)
            with side_effects.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"thread_id": state["thread_id"], "tool": tool,
                                     "ts": time.time()}, ensure_ascii=False) + "\n")
        return {**state,
                "evidence": ["PUMP-A-01.vib_x=7.1mm/s", "ISO 10816 振动烈度限值"],
                "steps": state["steps"] + ["readonly_tools"]}

    def node_diagnose(state: dict[str, Any]) -> dict[str, Any]:
        return {**state,
                "root_cause": "轴承外圈剥落（疑似）", "confidence": 0.78,
                "risk_level": "high" if needs_review(state["text"]) else "low",
                "recommended_actions": ["停机更换轴承", "复核对中"],
                "steps": state["steps"] + ["diagnose"]}

    def node_review(state: dict[str, Any]) -> dict[str, Any]:
        # 关键词命中 → 强制人工审核；未命中则直接放行（无 interrupt）
        if not needs_review(state["text"]):
            return {**state,
                    "review": {"decision": "auto_pass"},
                    "steps": state["steps"] + ["review:auto"]}
        # 用 state 中已计算的 root_cause / risk_level（此时值来自 checkpoint 恢复）
        state_root_cause = state.get("root_cause", "轴承外圈剥落（疑似）")
        state_risk_level = state.get("risk_level", "high")
        decision = interrupt({"thread_id": state["thread_id"],
                              "question": "诊断结论含高风险动作，需人工审核",
                              "root_cause": state_root_cause,
                              "risk_level": state_risk_level})
        return {**state,
                "review": {"decision": decision},
                "steps": state["steps"] + ["review:manual"]}

    graph = StateGraph(dict)
    graph.add_node("parse_alarm", node_parse_alarm)
    graph.add_node("readonly_tools", node_readonly_tools)
    graph.add_node("diagnose", node_diagnose)
    graph.add_node("review", node_review)
    graph.add_edge(START, "parse_alarm")
    graph.add_edge("parse_alarm", "readonly_tools")
    graph.add_edge("readonly_tools", "diagnose")
    graph.add_edge("diagnose", "review")
    graph.add_edge("review", END)
    return graph.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------- 图外写操作


def generate_report_out_of_graph(state: dict[str, Any], store_path: Path) -> dict[str, Any]:
    """图外写操作：携带 `idempotency_key`，用文件存储模拟 PG 唯一索引去重。

    P0 阶段报告表未建，故用 `report_store.json` 的 key 唯一性模拟
    `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING RETURNING id` 的语义。
    该模拟**必须在报告中显式声明**，不得声称已验证 PG 侧行为。
    """
    content = json.dumps({"root_cause": state.get("root_cause"),
                          "evidence": state.get("evidence"),
                          "actions": state.get("recommended_actions")},
                         ensure_ascii=False, sort_keys=True)
    key = idempotency_key(state["thread_id"], "diagnosis_report", content)

    store: dict[str, Any] = {}
    if store_path.exists():
        store = json.loads(store_path.read_text(encoding="utf-8"))
    first_write = key not in store
    if first_write:
        store[key] = {"report_id": f"RPT-{key[:12]}", "thread_id": state["thread_id"],
                      "content": content}
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"idempotency_key": key, "first_write": first_write,
            "report_id": store[key]["report_id"]}


def count_tool_executions(side_effects: Path, thread_id: str) -> int:
    """统计某 thread 的只读工具执行次数（T5.4 幂等判据：恢复后不得重复）。"""
    if not side_effects.exists():
        return 0
    total = 0
    for line in side_effects.read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line).get("thread_id") == thread_id:
            total += 1
    return total


def count_report_entries(store_path: Path, thread_id: str) -> int:
    """统计某 thread 在报告存储中已有的报告条目数。

    幂等键去重后，同一 thread 应始终只有 ≤1 条报告（重复写入被唯一键拦住）：
    若条目数 > 1（触发第二份报告或去重失效）→ 判定为重复副作用（B3 阻塞）。
    """
    if not store_path.exists():
        return 0
    store = json.loads(store_path.read_text(encoding="utf-8"))
    return sum(1 for v in store.values() if v.get("thread_id") == thread_id)


# ---------------------------------------------------------------- 步骤实现


def _record(out_path: Path, payload: dict[str, Any]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _base(step: str, extra: dict[str, Any]) -> dict[str, Any]:
    return {"experiment_id": STEPS[step]["experiment_id"], "step": step,
            "phase_item": "V5", "title": STEPS[step]["title"],
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"), **extra}


def step_run(step: str, out_path: Path, checkpointer_kind: str, redis_url: str,
             thread_id: str, text: str, resume_value: str | None) -> int:
    """T5.1–T5.4 的图执行路径（checkpointer 生命周期由 CM 界定）。"""
    api = _require_langgraph()
    side_effects = RAW_DIR / "tool_executions.jsonl"
    config = {"configurable": {"thread_id": thread_id}}
    initial = {"thread_id": thread_id, "device_id": "PUMP-A-01", "text": text}

    def _run(checkpointer: Any) -> int:
        graph = build_graph(checkpointer, side_effects)
        if step in ("t5.3", "t5.4") and resume_value is not None:
            # 恢复路径：不重跑初始输入，直接从 checkpoint 续跑。
            # ★ B2（payload 一致性）必须取 **resume 前** 的 checkpoint 状态与 resume 后比对。
            #   历史缺陷：把 resume 后的状态与自身比较，差异恒为空 → B2 永远为真、判据失效。
            pre_snapshot = graph.get_state(config)
            pre_values = dict(getattr(pre_snapshot, "values", None) or {})
            track_keys = ("alarm", "evidence", "risk_level", "root_cause", "confidence")
            before = {k: pre_values.get(k) for k in track_keys}
            result = graph.invoke(api["Command"](resume=resume_value), config=config)
            state = dict(result)
            snapshot = graph.get_state(config)
            after = {k: state.get(k) for k in track_keys}
            checks = {
                "B1": all(k in state for k in ("alarm", "evidence", "risk_level")),
                "B2": not compare_payload(before, after),
            }
            report = generate_report_out_of_graph(state, RAW_DIR / "report_store.json")
            exec_count = count_tool_executions(side_effects, thread_id)
            # B3（无重复副作用）：幂等去重后，同一 thread 报告条目必须 ≤1。
            # 注意：不能用 report["first_write"]——首次合法写入时它为 True，恢复重放时同内容写
            # 被幂等键拦住返回 False，两种场景都代表"无重复"，须以条目总数判断。
            checks["B3"] = count_report_entries(RAW_DIR / "report_store.json", thread_id) <= 1
            payload = _base(step, {"thread_id": thread_id, "mode": "resume",
                                   "resume_value": resume_value, "state": _jsonable(state),
                                   "next": list(snapshot.next or []), "checks": checks,
                                   "tool_exec_count": exec_count,
                                   "report": report})
            payload["blocking"] = blocking_defects(checks)
            payload["verdict"] = verdict(payload["blocking"])
            _record(out_path, payload)
            print(f"[V5] {step} 恢复完成：tool_exec_count={exec_count}，"
                  f"next={payload['next']}，判定={payload['verdict']}")
            return 0 if not payload["blocking"] else 1

        # 首次执行：跑到 interrupt 或结束
        result = graph.invoke(initial, config=config)
        state = dict(result)
        snapshot = graph.get_state(config)
        interrupted = bool(getattr(snapshot, "next", None))
        payload = _base(step, {"thread_id": thread_id, "mode": "invoke",
                               "state": _jsonable(state), "interrupted": interrupted,
                               "next": list(snapshot.next or []),
                               "has_writes": getattr(snapshot, "metadata", {}).get("writes")
                               if isinstance(getattr(snapshot, "metadata", None), dict) else None})
        _record(out_path, payload)
        print(f"[V5] {step} 首次执行完成：interrupted={interrupted}，next={payload['next']}")
        if interrupted:
            print(f"     下一步（模拟被杀进程后恢复）：\n"
                  f"       python scripts/run_v5.py --step {step} --resume {thread_id} "
                  f"--checkpointer {checkpointer_kind}")
        return 0

    with build_checkpointer(checkpointer_kind, redis_url) as checkpointer:
        return _run(checkpointer)


def step_has_writes(out_path: Path, checkpointer_kind: str, redis_url: str,
                    thread_id: str) -> int:
    """T5.2：`putWrites` 后读 `getState()`，复现 `has_writes` 覆盖问题。"""
    api = _require_langgraph()

    def _run(checkpointer: Any) -> int:
        graph = build_graph(checkpointer, RAW_DIR / "tool_executions.jsonl")
        config = {"configurable": {"thread_id": thread_id}}
        graph.invoke({"thread_id": thread_id, "device_id": "PUMP-A-01",
                      "text": "振动超标，建议停机更换轴承"}, config=config)
        before = graph.get_state(config)

        observed: dict[str, Any] = {}
        put_ok = False
        try:
            # 探针：向与审核节点互斥的通道写入（正确签名 = (channel, value) 元组序列），
            # 检测外部写入是否污染审核中的状态（ISS-001「has_writes 覆盖」）。
            # put_writes 需要含 checkpoint_ns / checkpoint_id 的完整内部 config，
            # 取自 get_state 返回的 snapshot.config（公开 API 不含这些内部字段）。
            checkpointer.put_writes(before.config, [("probe_channel", {"probe": True})],
                                    task_id=f"{thread_id}-probe")
            put_ok = True
            after = graph.get_state(config)
            observed = {"next_before": list(before.next or []), "next_after": list(after.next or []),
                        "values_changed": before.values != after.values,
                        "values_before_keys": sorted(before.values.keys()),
                        "values_after_keys": sorted(after.values.keys())}
        except Exception as exc:                              # noqa: BLE001 - 复现缺陷本身
            observed = {"error": f"{type(exc).__name__}: {exc}"}

        reproduced = bool(observed.get("values_changed")) or bool(observed.get("error"))
        checks = {"B4": not reproduced}
        payload = _base("t5.2", {"thread_id": thread_id, "put_writes_ok": put_ok,
                                 "observed": observed, "reproduced": reproduced,
                                 "checks": checks, "blocking": blocking_defects(checks)})
        payload["verdict"] = verdict(payload["blocking"])
        _record(out_path, payload)
        print(f"[V5] t5.2 has_writes 覆盖是否复现：{reproduced} ｜ 判定={payload['verdict']}")
        print("     ⚠️ 若复现：须记录规避手段；不可规避则计入 B4（阻塞，切 PG checkpointer）")
        return 0 if not payload["blocking"] else 1

    with build_checkpointer(checkpointer_kind, redis_url) as checkpointer:
        return _run(checkpointer)


def step_concurrency(out_path: Path, redis_url: str, thread_id: str,
                     reviewers: int = 2) -> int:
    """T5.5：双审核人竞争 resume —— `lock:review:{thread_id}` SETNX 唯一性验证。"""
    try:
        import redis                                              # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("缺少 redis，请先安装：uv pip install redis") from exc
    client = redis.from_url(redis_url, decode_responses=True)

    winners: list[str] = []
    losers: list[str] = []
    for idx in range(reviewers):
        reviewer = f"reviewer-{idx + 1}"
        if acquire_review_lock(client, thread_id):
            winners.append(reviewer)
        else:
            losers.append(reviewer)
    release_review_lock(client, thread_id)

    unique_ok = len(winners) == 1
    checks = {"B6": unique_ok}
    payload = _base("t5.5", {"thread_id": thread_id, "reviewers": reviewers,
                             "winners": winners, "losers": losers,
                             "lock_ttl": REVIEW_LOCK_TTL, "checks": checks,
                             "blocking": blocking_defects(checks)})
    payload["verdict"] = verdict(payload["blocking"])
    _record(out_path, payload)
    print(f"[V5] t5.5 并发抢占：winners={winners} losers={losers} → 判定={payload['verdict']}")
    print("     ⚠️ 单进程 SETNX 只验证锁语义；多实例并发须另起 worker 复核（同编号新开 attempt）")
    return 0 if not payload["blocking"] else 1


def step_volume(out_path: Path, redis_url: str, thread_id: str | None) -> int:
    """T5.6：checkpoint 体积、key 数与增长速率（归档与保留上限的依据）。"""
    try:
        import redis                                              # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("缺少 redis，请先安装：uv pip install redis") from exc
    client = redis.from_url(redis_url, decode_responses=True)

    stats = collect_ckpt_stats(client, thread_id)
    over_limit = stats["max_key_bytes"] > CKPT_BYTES_LIMIT
    payload = _base("t5.6", {**stats, "single_key_limit_bytes": CKPT_BYTES_LIMIT,
                             "over_limit": over_limit,
                             "growth_note": "增长速率须以同 thread 多次诊断的两次采样差计算"})
    _record(out_path, payload)
    print(f"[V5] t5.6 体积：key 数={stats['key_count']}，总字节={stats['total_bytes']}，"
          f"单 key 最大={stats['max_key_bytes']}（告警线 {CKPT_BYTES_LIMIT}）")
    return 0


def step_ttl(out_path: Path, redis_url: str, thread_id: str | None) -> int:
    """T5.7：`noeviction` + 无 TTL + 内存上限告警验证。"""
    try:
        import redis                                              # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("缺少 redis，请先安装：uv pip install redis") from exc
    client = redis.from_url(redis_url, decode_responses=True)

    policy = check_redis_policy(client)
    stats = collect_ckpt_stats(client, thread_id)
    checks = {
        "B5": policy["noeviction_ok"] and policy["maxmemory_set"]
              and stats["keys_with_ttl"] == 0,
    }
    payload = _base("t5.7", {"policy": policy, **stats, "checks": checks,
                             "blocking": blocking_defects(checks)})
    payload["verdict"] = verdict(payload["blocking"])
    _record(out_path, payload)
    print(f"[V5] t5.7 策略={policy['maxmemory_policy']} maxmemory={policy['maxmemory']} "
          f"带 TTL 的 ckpt key={stats['keys_with_ttl']} → 判定={payload['verdict']}")
    return 0 if not payload["blocking"] else 1


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return {k: _jsonable(v) for k, v in dict(value).items()} if isinstance(value, dict) \
            else str(value)


# ---------------------------------------------------------------- 自检


def _selftest() -> int:
    failures: list[str] = []

    # 1) 关键词触发
    if not needs_review("振动超标，建议停机更换轴承"):
        failures.append("关键词「停机/更换」未触发审核")
    if needs_review("记录一下本次巡检数据"):
        failures.append("普通文本被误判为需审核")

    # 2) 幂等键：同输入同键、换 thread 换键、内容变则键变
    k1 = idempotency_key("t-1", "diagnosis_report", "abc")
    if k1 != idempotency_key("t-1", "diagnosis_report", "abc"):
        failures.append("幂等键不稳定")
    if k1 == idempotency_key("t-2", "diagnosis_report", "abc"):
        failures.append("不同 thread 生成了同一幂等键")
    if k1 == idempotency_key("t-1", "diagnosis_report", "abd"):
        failures.append("内容变化未改变幂等键")
    if k1 == idempotency_key("t-1", "review_summary", "abc"):
        failures.append("报告类型变化未改变幂等键")

    # 3) 审核锁语义（内存桩）
    client = MemoryRedis()
    if not acquire_review_lock(client, "t-1"):
        failures.append("首个审核人未抢到锁")
    if acquire_review_lock(client, "t-1"):
        failures.append("第二个审核人重复抢到锁（违反 B6）")
    release_review_lock(client, "t-1")
    if not acquire_review_lock(client, "t-1"):
        failures.append("释放后未能重新抢锁")

    # 4) 体积与 TTL 统计
    client.set("ckpt:t-1:1", "x" * 100)
    client.set("ckpt:t-1:2", "y" * 50, ex=60)
    client.set("ckpt:t-2:1", "z" * 10)
    stats = collect_ckpt_stats(client, "t-1")
    if stats["key_count"] != 2 or stats["total_bytes"] != 150:
        failures.append(f"体积统计错误：{stats}")
    if stats["keys_with_ttl"] != 1:
        failures.append("带 TTL 的 ckpt key 未被识别（违反无 TTL 纪律）")

    # 5) 策略校验
    policy = check_redis_policy(MemoryRedis())
    if not (policy["noeviction_ok"] and policy["maxmemory_set"]):
        failures.append("noeviction / maxmemory 校验错误")
    bad_policy = check_redis_policy(MemoryRedis(policy="allkeys-lru"))
    if bad_policy["noeviction_ok"]:
        failures.append("非 noeviction 策略未被识别")

    # 6) payload 差异比对
    same = compare_payload({"alarm": 1, "evidence": [1]}, {"alarm": 1, "evidence": [1]})
    if not any("字段缺失" in d for d in same):
        failures.append("缺失字段未被识别")
    diff = compare_payload({"alarm": 1}, {"alarm": 2})
    if not any("不一致" in d for d in diff):
        failures.append("字段不一致未被识别")

    # 7) B1–B7 映射与判定
    if blocking_defects({"B1": True, "B4": False}) != ["B4"]:
        failures.append("阻塞缺陷映射错误")
    if "No-Go" not in verdict(["B5"]) or verdict([]) != "Pass":
        failures.append("判定分档错误")

    # 8) 图外写操作幂等（文件存储模拟 PG 唯一索引）
    store = RAW_DIR / "_selftest_report_store.json"
    try:
        state = {"thread_id": "t-selftest", "root_cause": "x", "evidence": ["e"],
                 "recommended_actions": ["a"]}
        first = generate_report_out_of_graph(state, store)
        second = generate_report_out_of_graph(state, store)
        if not first["first_write"]:
            failures.append("首次写入被判为重复")
        if second["first_write"]:
            failures.append("重复写入未被幂等键拦住（违反 B3）")
        if first["report_id"] != second["report_id"]:
            failures.append("重复写入未复用同一 report_id")
    finally:
        store.unlink(missing_ok=True)

    if failures:
        print("[FAIL] run_v5 自检未通过：")
        for f in failures:
            print("  -", f)
        return 1
    print("[OK] run_v5 自检通过：关键词触发 / 幂等键 / 审核锁 / 体积与TTL / 策略 / B1-B7映射")
    return 0


# ---------------------------------------------------------------- 入口


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V5 Checkpoint 可靠性验证器（T5.1–T5.7）")
    parser.add_argument("--step", choices=sorted(STEPS), default="t5.1")
    parser.add_argument("--out", type=Path, default=None,
                        help="原始数据落盘（默认 experiments/v5/raw/<EXP 编号>.jsonl）")
    parser.add_argument("--checkpointer", choices=("redis", "memory", "postgres"),
                        default="postgres",
                        help="已采纳路线=postgres（候选 B，docs/checkpoint-decision.md §2.1）｜"
                             "redis=候选 A，仅用于复现 B7｜memory=本地联调桩")
    parser.add_argument("--redis-url", default=REDIS_URL)
    parser.add_argument("--thread-id", default=None, help="不指定则按步骤自动生成")
    parser.add_argument("--text", default="PUMP-A-01 振动 7.1 mm/s，建议停机更换轴承",
                        help="告警文本（含关键词则触发人工审核）")
    parser.add_argument("--resume", metavar="THREAD_ID", default=None,
                        help="T5.3/T5.4：被杀进程后按 thread_id 从 checkpoint 恢复")
    parser.add_argument("--resume-value", default="approved", help="审核决定：approved/rejected")
    parser.add_argument("--selftest", action="store_true", help="运行自检（不依赖 langgraph/redis）")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    thread_id = args.resume or args.thread_id or \
        f"{STEPS[args.step]['experiment_id']}-{int(time.time())}"
    out_path = args.out or RAW_DIR / f"{STEPS[args.step]['experiment_id']}.jsonl"
    print("=" * 78)
    print(f"V5 {args.step} ｜ {STEPS[args.step]['title']} ｜ {STEPS[args.step]['experiment_id']}")
    print(f"thread_id={thread_id} ｜ checkpointer={args.checkpointer} ｜ out={out_path}")
    if args.step in ("t5.5", "t5.6", "t5.7"):
        print("⚠️ t5.5–t5.7 是 Redis 侧检查（审核锁 SETNX / 体积 / TTL·驱逐策略），"
              "**不随 --checkpointer 切换**；")
        print("   PG 路线下这三项的结论取自 PG 侧核验（见 reports/v5-report.md §六）。")
    print("=" * 78)

    try:
        if args.step in ("t5.1", "t5.3", "t5.4"):
            return step_run(args.step, out_path, args.checkpointer, args.redis_url,
                            thread_id, args.text,
                            args.resume_value if args.resume else None)
        if args.step == "t5.2":
            return step_has_writes(out_path, args.checkpointer, args.redis_url, thread_id)
        if args.step == "t5.5":
            return step_concurrency(out_path, args.redis_url, thread_id)
        if args.step == "t5.6":
            return step_volume(out_path, args.redis_url, args.resume)
        return step_ttl(out_path, args.redis_url, args.resume)
    except (RuntimeError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
