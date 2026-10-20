"""P7 Agent 化回归测试：LLM 客户端 / 工具注册 / Agent 循环 / 图模式切换。

纪律（同 tests/ 全量）：**离线、零网络、零云端调用**——
- 客户端传输经注入的假 opener；
- Agent 循环经假客户端（patch 节点命名空间的 get_client）；
- 工具执行体经 monkeypatch 的 app.tools.* 与检索服务单例；
- 云端工厂逻辑经 patch `_load_cloud_settings`（不依赖 env/cloud.json 存在性）。

对应缺陷防护：统一出口回归构型、白名单/写操作护栏、max_steps 封顶、
LLM 失败重试契约、预算熔断、模式切换图形状（docs/p7-design-agent-diagnosis-2026-10-19.md）。
"""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from app.agent import tool_registry as tr
from app.agent.prompt import build_agent_system_prompt
from app.graph import build as build_mod
from app.graph.build import build_graph
from app.graph.nodes import agent_diagnose as ad
from app.graph.nodes.diagnose import diagnose
from app.graph.state import AlarmEvent, DiagnosisState
from app.llm import config as llm_config
from app.llm.client import ChatResult, OpenAICompatClient, ToolCall, get_client
from app.router.cloud import CloudRouter, call_cloud
from langgraph.checkpoint.memory import InMemorySaver


# ---------------------------------------------------------------- 假件

class _FakeResponse(io.BytesIO):
    """最小 HTTP 响应桩（支持 with 语义与 read()）。"""

    def __init__(self, payload: dict):
        super().__init__(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


def _fake_opener(payload: dict):
    def _open(request, timeout=None):
        _open.last_request = request
        _open.last_timeout = timeout
        return _FakeResponse(payload)
    return _open


class _FakeClient:
    """脚本化假客户端：按序返回 ChatResult / 抛出异常。"""

    def __init__(self, script: list[Any]):
        self.script = list(script)
        self.calls: list[dict] = []

    def chat(self, messages, *, tools=None, tool_choice="auto", timeout=None):
        self.calls.append({"messages": [json.loads(json.dumps(m, ensure_ascii=False,
                                                               default=str))
                                        for m in messages],
                           "tools": tools, "tool_choice": tool_choice})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _final_result(content: str) -> ChatResult:
    return ChatResult(model="fake", content=content)


def _tool_calls_result(*calls: tuple[str, dict], content: str = "") -> ChatResult:
    return ChatResult(model="fake", content=content,
                      tool_calls=[ToolCall(id=f"call-{i}", name=n, arguments=a)
                                  for i, (n, a) in enumerate(calls)])


def _alarm(**kw) -> AlarmEvent:
    base = dict(alarm_id="a-1", device_id="PUMP-A-01", metric="vib_rms",
                value=7.1, baseline=4.5, severity="medium", ts=0)
    base.update(kw)
    return AlarmEvent(**base)


def _agent_state(**kw) -> DiagnosisState:
    base = dict(thread_id="thr-test", alarm=_alarm())
    base.update(kw)
    return DiagnosisState(**base)


_FINAL_JSON = json.dumps({
    "diagnosis": "轴承外圈剥落导致振动超标",
    "root_causes": [{"cause": "轴承外圈剥落", "citations": ["c_001"],
                     "confidence_hint": 0.8}],
    "suggestions": [{"action": "停机更换轴承", "citations": ["c_001"], "risk": "high"}],
    "self_confidence": 0.75,
}, ensure_ascii=False)


# ---------------------------------------------------------------- A. LLM 客户端

def test_chat_payload_tools_and_tool_choice(monkeypatch):
    """tools 通道：载荷含 tools + tool_choice=auto；无 tools 时不带该键。"""
    opener = _fake_opener({"choices": [{"message": {"content": "hi"}}]})
    client = OpenAICompatClient(endpoint="http://x/v1/chat/completions",
                                model="m", opener=opener)
    result = client.chat([{"role": "user", "content": "q"}])
    assert result.content == "hi"
    body = json.loads(opener.last_request.data.decode("utf-8"))
    assert "tools" not in body and "tool_choice" not in body
    assert body["model"] == "m" and body["stream"] is False
    assert body["options"]["num_ctx"] == 8192

    opener2 = _fake_opener({"choices": [{"message": {}}]})
    client2 = OpenAICompatClient(endpoint="http://x/v1/chat/completions",
                                 model="m", api_key="k", opener=opener2)
    client2.chat([{"role": "user", "content": "q"}],
                 tools=[{"type": "function", "function": {"name": "t"}}])
    body2 = json.loads(opener2.last_request.data.decode("utf-8"))
    assert body2["tool_choice"] == "auto"
    assert body2["tools"][0]["function"]["name"] == "t"
    assert opener2.last_request.headers["Authorization"] == "Bearer k"


def test_tool_choice_required_rejected():
    """H5/ISS-027/R-V1-9：tool_choice 仅允许 auto（云端 required 静默退化）。"""
    client = OpenAICompatClient(endpoint="http://x", model="m")
    with pytest.raises(RuntimeError, match="tool_choice"):
        client.chat([], tool_choice="required")


def test_parse_tool_calls_both_shapes():
    """云端（arguments JSON 串）与 Ollama（arguments dict）两种形态都要归一。"""
    opener = _fake_opener({"choices": [{"message": {
        "content": "",
        "tool_calls": [
            {"id": "1", "type": "function",
             "function": {"name": "query_sensor",
                          "arguments": '{"device_id": "PUMP-A-01"}'}},
            {"id": "2", "function": {"name": "search_knowledge",
                                     "arguments": {"query": "振动限值"}}},
            {"id": "3", "function": {"arguments": '{"x": 1}'}},      # 无 name → 丢弃
        ]}}]})
    client = OpenAICompatClient(endpoint="http://x", model="m", opener=opener)
    result = client.chat([{"role": "user", "content": "q"}], tools=[{}])
    assert [c.name for c in result.tool_calls] == ["query_sensor", "search_knowledge"]
    assert result.tool_calls[0].arguments == {"device_id": "PUMP-A-01"}
    assert result.tool_calls[1].arguments == {"query": "振动限值"}
    assert result.tool_calls_missing is False


def test_transport_errors_map_to_contract(monpatch=None):
    """传输异常 → 既有三态契约（Timeout/Connection/Runtime）。"""
    from urllib.error import URLError

    def _timeout(request, timeout=None):
        raise TimeoutError("timed out")

    def _refused(request, timeout=None):
        raise URLError("Connection refused")

    def _http500(request, timeout=None):
        raise urllib.error.HTTPError("http://x", 500, "err", {}, io.BytesIO(b"{}"))

    base = dict(endpoint="http://x", model="m")
    with pytest.raises(TimeoutError):
        OpenAICompatClient(opener=_timeout, **base).chat([])
    with pytest.raises(ConnectionError):
        OpenAICompatClient(opener=_refused, **base).chat([])
    with pytest.raises(RuntimeError, match="HTTP 500"):
        OpenAICompatClient(opener=_http500, **base).chat([])


def test_factory_local_defaults(monkeypatch):
    """默认后端 local：端点/模型/无密钥；agent 角色默认 qwen2.5:7b。"""
    monkeypatch.delenv("AUSCULT_LLM_BACKEND", raising=False)
    client = get_client(llm_config.ROLE_AGENT)
    assert client.endpoint == "http://127.0.0.1:11434/v1/chat/completions"
    assert client.model == "qwen2.5:7b"
    assert client.api_key is None


def test_factory_cloud_backend(monkeypatch):
    """cloud 后端：端点/模型/密钥来自云端配置加载器（不依赖 cloud.json 存在）。"""
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "cloud")
    monkeypatch.setattr("app.llm.client._load_cloud_settings",
                        lambda: ("https://cloud/v1/chat/completions",
                                 "Qwen/Qwen3.8-27B", "sk-test"))
    client = get_client(llm_config.ROLE_AGENT)
    assert client.model == "Qwen/Qwen3.8-27B"
    assert client.api_key == "sk-test"


def test_config_validation(monkeypatch):
    """非法配置显式报错（不静默回落）。"""
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "gpu")
    with pytest.raises(RuntimeError, match="AUSCULT_LLM_BACKEND"):
        llm_config.llm_backend()
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "local")
    monkeypatch.setenv("AUSCULT_DIAGNOSIS_MODE", "auto")
    with pytest.raises(RuntimeError, match="AUSCULT_DIAGNOSIS_MODE"):
        llm_config.diagnosis_mode()
    monkeypatch.setenv("AUSCULT_DIAGNOSIS_MODE", "agent")
    monkeypatch.setenv("AUSCULT_AGENT_MAX_STEPS", "99")
    with pytest.raises(RuntimeError, match="AUSCULT_AGENT_MAX_STEPS"):
        llm_config.agent_max_steps()


# ---------------------------------------------------------------- B. 工具注册

def test_load_agent_tools_readonly_subset():
    """工具面 = 4 个只读工具；generate_report（写操作）不在面内。"""
    tools = tr.load_agent_tools()
    names = [t["function"]["name"] for t in tools]
    assert names == list(tr.AGENT_TOOL_NAMES)
    assert "generate_report" not in names
    for t in tools:
        assert t["type"] == "function"
        assert "parameters" in t["function"]
        assert "适用" in t["function"]["description"]      # when_to_use 已注入


def test_execute_tool_rejects_non_whitelisted():
    out = tr.execute_tool("delete_all_data", {"device_id": "PUMP-A-01"})
    assert out["ok"] is False and "白名单" in out["error"]


def test_execute_tool_blocks_write_operation():
    """ADR-007：写操作不进 Agent 工具面，幻觉调用也被护栏拦截。"""
    out = tr.execute_tool("generate_report", {"device_id": "PUMP-A-01",
                                              "diagnosis_summary": "x" * 20})
    assert out["ok"] is False and "写操作护栏" in out["error"]


def test_parse_timestamp_relative_iso_and_garbage():
    now = 1_790_000_000_000
    assert tr.parse_timestamp("24h", now_ms=now) == now - 24 * 3_600_000
    assert tr.parse_timestamp("7d", now_ms=now) == now - 7 * 86_400_000
    assert tr.parse_timestamp("15m", now_ms=now) == now - 15 * 60_000
    iso = tr.parse_timestamp("2026-09-20T00:00:00+08:00", now_ms=now)
    assert iso is not None and iso < now
    assert tr.parse_timestamp("上周", now_ms=now) is None
    assert tr.parse_timestamp(None, now_ms=now) is None


def test_resolve_window_defaults():
    now = 1_790_000_000_000
    start, end = tr._resolve_window({}, now_ms=now)
    assert end == now and start == now - 24 * 3_600_000
    start2, end2 = tr._resolve_window({"start": "2026-09-20T00:00:00+08:00"},
                                      now_ms=now)
    assert end2 == now and start2 < end2
    # 幻觉出的未来起点：钳制回 24h 窗口，不让下游拿到 start > end 的非法区间
    start3, end3 = tr._resolve_window({"start": "2099-01-01T00:00:00+08:00"},
                                      now_ms=now)
    assert start3 < end3 and end3 == now


def test_execute_query_sensor_maps_short_names(monkeypatch):
    """schema 测点短名 → TDengine 列；ISS-049 归一声明；统计摘要入结果。"""
    captured = {}

    def _fake_query_sensor(device_id, metric, start_ts, end_ts, *, timeout=0.5):
        captured.update(device_id=device_id, metric=metric,
                        start_ts=start_ts, end_ts=end_ts)
        return {"rows": [{"ts": 1, "value": 4.0}, {"ts": 2, "value": 7.0}],
                "count": 2}

    monkeypatch.setattr("app.tools.query_sensor.query_sensor", _fake_query_sensor)
    out = tr.execute_tool("query_sensor", {
        "device_id": "PUMP-A-01",
        "sensor_ids": ["PUMP-A-01.vib_z"],
        "time_range": {"start": "24h"},
    }, alarm=_alarm())
    assert out["ok"] is True
    assert captured["metric"] == "vib_rms"            # vib_z → vib_rms（ISS-049）
    series = out["result"]["series"]
    assert series[0]["column"] == "vib_rms"
    assert series[0]["count"] == 2 and series[0]["max"] == 7.0
    assert "ISS-049" in out["result"]["note"]


def test_execute_query_sensor_unmapped_and_missing_device():
    out = tr.execute_tool("query_sensor",
                          {"device_id": "PUMP-A-01", "sensor_ids": ["PUMP-A-01.rpm"]})
    assert out["ok"] is False and "未登记" in out["error"]
    out2 = tr.execute_tool("query_sensor", {"sensor_ids": ["PUMP-A-01.vib_x"]})
    assert out2["ok"] is False and "device_id" in out2["error"]


def test_execute_search_knowledge_compacts(monkeypatch):
    class _Svc:
        def retrieve(self, question, *, mode=None, cache_key=None):
            assert question == "离心泵振动限值"
            return {"degraded": False,
                    "items": [{"chunk_id": "c_001", "score": 0.9123,
                               "text": "x" * 500},
                              {"chunk_id": "c_002", "score": 0.5, "text": "短"}]}
    monkeypatch.setattr(tr, "_get_retrieval_service", lambda: _Svc())
    out = tr.execute_tool("search_knowledge", {"query": "离心泵振动限值", "top_k": 5})
    assert out["ok"] is True
    items = out["result"]["items"]
    assert [i["chunk_id"] for i in items] == ["c_001", "c_002"]
    assert items[0]["score"] == 0.9123
    assert len(items[0]["text"]) <= tr._MAX_TEXT_CHARS      # 截断生效


def test_execute_get_maintenance_history(monkeypatch):
    captured = {}

    def _fake_history(device_id, *, limit=10, timeout=2.0):
        captured.update(device_id=device_id, limit=limit)
        return [{"order_id": "WO-1", "device_id": device_id, "fault": "轴承异响",
                 "action": "更换轴承", "result": "完成", "created_at": "2026-09-01 10:00:00"}]
    monkeypatch.setattr("app.tools.get_maintenance_history.get_maintenance_history",
                        _fake_history)
    out = tr.execute_tool("get_maintenance_history",
                          {"device_id": "PUMP-A-01", "limit": 5})
    assert out["ok"] is True and captured["limit"] == 5
    wo = out["result"]["work_orders"][0]
    assert wo["order_id"] == "WO-1" and wo["fault"] == "轴承异响"


def test_execute_query_graph_degraded(monkeypatch):
    monkeypatch.setattr("app.tools.query_graph.query_graph",
                        lambda q: {"degraded": True, "reason": "Neo4j 不可达"})
    out = tr.execute_tool("query_graph", {"start_node": "PUMP-A-01"})
    assert out["ok"] is True and out["result"]["degraded"] is True


# ---------------------------------------------------------------- C. Agent 循环

def test_agent_loop_tool_call_then_final(monkeypatch):
    """主路径：一轮工具调用 → 回灌 → 收口 JSON → 诊断契约 + 状态增量。

    工具执行打桩（离线纪律：不依赖 Milvus/TDengine 等基础设施是否在线）。
    """
    fake = _FakeClient([
        _tool_calls_result(("search_knowledge", {"query": "振动限值"})),
        _final_result(_FINAL_JSON),
    ])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)

    def _fake_execute(name, arguments, *, alarm=None, thread_id=None):
        return {"ok": True, "result": {
            "degraded": False,
            "items": [{"chunk_id": "c_001", "score": 0.9, "text": "限值说明"}],
        }}
    monkeypatch.setattr(ad, "execute_tool", _fake_execute)

    state = _agent_state()
    out = ad.agent_diagnose(state)

    assert out["diagnosis"] == "轴承外圈剥落导致振动超标"
    assert out["root_causes"][0].cause == "轴承外圈剥落"
    assert out["root_causes"][0].citations == ["c_001"]
    assert out["risk_level"] == "high"          # 自评 0.75 → 复合后 <0.85 且 severity medium
    assert out["confidence"] > 0
    assert len(out["agent_steps"]) == 1 and out["agent_steps"][0]["tool"] == "search_knowledge"
    # 第二轮请求里应含 role=tool 回灌消息，且仍带工具面
    second_msgs = fake.calls[1]["messages"]
    roles = [m["role"] for m in second_msgs]
    assert roles == ["system", "user", "assistant", "tool"]
    assert fake.calls[1]["tools"] is not None


def test_agent_loop_collects_state_from_real_tool_results(monkeypatch):
    """真实 execute_tool 路径：工具结果归集为状态增量（evidence/sensor_report）。"""
    fake = _FakeClient([
        _tool_calls_result(
            ("query_sensor", {"device_id": "PUMP-A-01",
                              "sensor_ids": ["PUMP-A-01.vib_x"],
                              "time_range": {"start": "24h"}}),
            ("search_knowledge", {"query": "轴承剥落特征"})),
        _final_result(_FINAL_JSON),
    ])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    monkeypatch.setattr("app.tools.query_sensor.query_sensor",
                        lambda device_id, metric, start_ts, end_ts, *, timeout=0.5:
                        {"rows": [{"ts": 1, "value": 5.0}], "count": 1})

    class _Svc:
        def retrieve(self, question, *, mode=None, cache_key=None):
            return {"degraded": False,
                    "items": [{"chunk_id": "c_001", "score": 0.9, "text": "剥落特征"}]}
    monkeypatch.setattr(tr, "_get_retrieval_service", lambda: _Svc())

    out = ad.agent_diagnose(_agent_state())
    assert out["sensor_report"]["count"] == 1
    assert [e.chunk_id for e in out["evidence"]] == ["c_001"]
    assert out["evidence"][0].source_type == "knowledge"


def test_agent_loop_max_steps_forced_final(monkeypatch):
    """步数上限：超限后走无工具强制收口轮（不再调工具）。"""
    fake = _FakeClient([
        _tool_calls_result(("search_knowledge", {"query": "q1"})),
        _tool_calls_result(("search_knowledge", {"query": "q2"})),
        _final_result(_FINAL_JSON),
    ])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    monkeypatch.setenv("AUSCULT_AGENT_MAX_STEPS", "2")
    out = ad.agent_diagnose(_agent_state())
    assert out["diagnosis"] == "轴承外圈剥落导致振动超标"
    assert len(out["agent_steps"]) == 3
    assert out["agent_steps"][-1]["forced_final"] is True
    assert fake.calls[-1]["tools"] is None            # 收口轮不带工具


def test_agent_loop_llm_failure_retry_contract(monkeypatch):
    """LLM 不可达 → retry_count++ + E_LLM_UNREACHABLE（路由接管重试/降级）。"""
    fake = _FakeClient([ConnectionError("LLM 不可达: refused")])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    out = ad.agent_diagnose(_agent_state(retry_count=1))
    assert out["retry_count"] == 2
    assert out["diagnosis"] is None if "diagnosis" in out else True
    assert out["errors"][0]["code"] == "E_LLM_UNREACHABLE"


def test_agent_loop_json_parse_failure(monkeypatch):
    """收口内容非 JSON → 正文前 500 字作诊断 + retry_count++（diagnose 同口径）。"""
    fake = _FakeClient([_final_result("这不是 JSON，只是说明文字。")])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    out = ad.agent_diagnose(_agent_state())
    assert out["diagnosis"] == "这不是 JSON，只是说明文字。"
    assert out["retry_count"] == 1
    assert out["errors"][0]["code"] == "E_JSON_PARSE"


def test_agent_loop_budget_exceeded_degrades(monkeypatch):
    """cloud 后端预算熔断 → degrade_reason=budget_exceeded（不调 LLM）。"""
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "cloud")

    class _Guard:
        def check(self):
            return False, 340, 340, "budget_exceeded(340/340)"

        def increment(self):     # pragma: no cover - 不应被调用
            raise AssertionError("熔断时不得计费")

    monkeypatch.setattr("app.router.budget.BudgetGuard", _Guard)
    fake = _FakeClient([_final_result(_FINAL_JSON)])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    out = ad.agent_diagnose(_agent_state())
    assert out["degrade_reason"] == "budget_exceeded"
    assert out["errors"][0]["code"] == "E_BUDGET_EXCEEDED"
    assert fake.calls == []


def test_agent_loop_no_alarm():
    out = ad.agent_diagnose(DiagnosisState(thread_id="t"))
    assert out["errors"][0]["code"] == "E_NO_ALARM"


def test_agent_system_prompt_injects_tools_and_refusal_rules():
    """系统提示词：工具注入 + prompt v4 拒止规则 6a 沿用 + 输出契约。"""
    prompt = build_agent_system_prompt('{"tools": []}')
    assert "{{TOOLS_JSON_SCHEMA}}" not in prompt
    assert '"tools": []' in prompt
    assert "绝不编造或默认任何设备号" in prompt
    assert "self_confidence" in prompt


# ---------------------------------------------------------------- D. 图模式切换

def _diag_impl(compiled):
    node = compiled.builder.nodes["diagnose"]
    return node.runnable.func.__wrapped__


def test_build_graph_deterministic_default(monkeypatch):
    """默认模式：图形状与节点实现不变（回归防护）。"""
    monkeypatch.delenv("AUSCULT_DIAGNOSIS_MODE", raising=False)
    g = build_graph(InMemorySaver())
    assert _diag_impl(g) is diagnose
    edges = {tuple(e) for e in g.builder.edges}
    assert ("parse_alarm", "analyze_sensor") in edges
    assert ("get_history", "diagnose") in edges
    assert ("parse_alarm", "diagnose") not in edges


def test_build_graph_agent_mode(monkeypatch):
    """agent 模式：diagnose 槽位切 Agent 实现；gather 链不接入边。"""
    monkeypatch.setenv("AUSCULT_DIAGNOSIS_MODE", "agent")
    g = build_graph(InMemorySaver())
    assert _diag_impl(g) is ad.agent_diagnose
    edges = {tuple(e) for e in g.builder.edges}
    assert ("parse_alarm", "diagnose") in edges
    assert ("parse_alarm", "analyze_sensor") not in edges
    assert ("get_history", "diagnose") not in edges


# ---------------------------------------------------------------- E. escalate 适配

def test_escalate_skipped_when_backend_is_cloud(monkeypatch):
    """后端即云端时 escalate 空转保留结论（不重复计费/调用）。"""
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "cloud")
    out = CloudRouter().escalate(_agent_state())
    assert out["escalate_cloud"] is True
    assert out["errors"][0]["code"] == "W_BACKEND_ALREADY_CLOUD"
    assert "degrade_reason" not in out


def test_call_cloud_delegates_to_unified_client(monkeypatch):
    """call_cloud 保留签名，经统一客户端出口。"""
    class _CloudClient:
        def chat(self, messages, *, timeout=None):
            assert timeout == 20.0
            return ChatResult(model="Qwen/Qwen3.8-27B", content="云端结论")
    monkeypatch.setattr("app.router.cloud.get_cloud_client", lambda: _CloudClient())
    assert call_cloud([{"role": "user", "content": "q"}]) == "云端结论"


# ---------------------------------------------------------------- G. 可观测化（P7 收尾）

def test_health_llm_probe_shape(monkeypatch):
    """/api/health 的 llm 探针：默认快照 + 配置非法降级（health 永不 500）。"""
    from app.api.routes import health
    monkeypatch.delenv("AUSCULT_LLM_BACKEND", raising=False)
    monkeypatch.delenv("AUSCULT_DIAGNOSIS_MODE", raising=False)
    snap = health._llm_probe()
    assert snap["backend"] == "local" and snap["diagnosis_mode"] == "deterministic"
    assert "api_key" not in snap
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "bogus")
    degraded = health._llm_probe()
    assert degraded.get("error") == "config_invalid"
    assert degraded["backend"] is None


def test_absorb_agent_steps_captures_diagnose_increment():
    """runner 轨迹归集：只取 diagnose 增量的 agent_steps；非 dict 项与空 rec 安全。"""
    from app.api.runner import ThreadRecord, _absorb_agent_steps
    from app.graph.state import AlarmEvent

    rec = ThreadRecord("thr-x", AlarmEvent(device_id="PUMP-A-01"), "eng")
    _absorb_agent_steps(rec, "parse_alarm", {"diagnosis": "x"})      # 非 diagnose 忽略
    _absorb_agent_steps(rec, "diagnose", {"agent_steps": [
        {"step": 1, "tool": "query_sensor", "ok": True},
        "not-a-dict",                                                # 脏数据过滤
    ], "diagnosis": "y"})
    assert len(rec.agent_steps) == 1 and rec.agent_steps[0]["tool"] == "query_sensor"
    _absorb_agent_steps(None, "diagnose", {"agent_steps": [{}]})     # rec=None 安全
    _absorb_agent_steps(rec, "diagnose", "not-a-dict")               # update 非 dict 安全


# ---------------------------------------------------------------- F. agent 模式全图集成

def test_agent_mode_graph_end_to_end(monkeypatch):
    """agent 模式全图跑通：parse_alarm → agent_diagnose → finalize → report_id。

    全离线：假客户端 + 桩工具执行体；验证模式接线、状态合并、引用校验、定稿。
    """
    monkeypatch.setenv("AUSCULT_DIAGNOSIS_MODE", "agent")
    fake = _FakeClient([
        _tool_calls_result(("search_knowledge", {"query": "轴承剥落"})),
        _final_result(_FINAL_JSON),
    ])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)

    class _Svc:
        def retrieve(self, question, *, mode=None, cache_key=None):
            return {"degraded": False,
                    "items": [{"chunk_id": "c_001", "score": 0.9,
                               "text": "轴承外圈剥落特征：频谱出现外圈故障频率"}]}
    monkeypatch.setattr(tr, "_get_retrieval_service", lambda: _Svc())

    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "thr-agent-e2e"}}
    result = graph.invoke({"thread_id": "thr-agent-e2e",
                           "alarm": _alarm().model_dump()}, config)

    assert result["diagnosis"] == "轴承外圈剥落导致振动超标"
    assert result["report_id"] and result["report_id"].startswith("RPT-")
    assert [e.chunk_id for e in result["evidence"]] == ["c_001"]
    assert any(s["tool"] == "search_knowledge" for s in result["agent_steps"])
    assert "blocked" not in result          # 引用有效 → 未触发硬校验
