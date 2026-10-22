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
from app.observability import prom_metrics as pm
from app.router.cloud import CloudRouter, call_cloud
from app.router import cloud as cloud_mod
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


def test_parse_keeps_usage_for_cost_tracking():
    """2026-10-21：usage 必须保留 —— 此前 token 成本完全不可观测，只能按字符估。"""
    opener = _fake_opener({
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 9300, "completion_tokens": 210, "total_tokens": 9510},
    })
    client = OpenAICompatClient(endpoint="http://x", model="m", opener=opener)
    result = client.chat([{"role": "user", "content": "q"}])
    assert result.usage["prompt_tokens"] == 9300
    assert result.usage["completion_tokens"] == 210


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


def test_execute_tool_rejects_missing_required_args():
    """2026-10-21：`validate_tool_args` 接线 —— 缺必填字段在入口即拦（可回灌纠错）。"""
    out = tr.execute_tool("query_sensor", {"device_id": "  "}, thread_id="t-argcheck")
    assert out["ok"] is False
    assert "参数校验失败" in out["error"] and "device_id" in out["error"]


def test_execute_tool_query_graph_requires_start_node():
    """回归锁：`query_graph` 必填项是 `start_node`（原表误写 `query`，会拒掉全部合法调用）。"""
    out = tr.execute_tool("query_graph", {}, thread_id="t-argcheck")
    assert out["ok"] is False and "start_node" in out["error"]


def test_execute_tool_search_knowledge_requires_query():
    """回归锁：`search_knowledge`（Agent 面主名）必须在必填表内（原表只有产品名）。"""
    out = tr.execute_tool("search_knowledge", {}, thread_id="t-argcheck")
    assert out["ok"] is False and "query" in out["error"]


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
    # 第二轮请求里应含 role=tool 回灌消息 + 代码生成的状态摘要（E3），且仍带工具面
    second_msgs = fake.calls[1]["messages"]
    roles = [m["role"] for m in second_msgs]
    assert roles == ["system", "user", "assistant", "tool", "user"]
    assert "【当前诊断状态】" in second_msgs[-1]["content"]
    assert "c_001" in second_msgs[-1]["content"]      # 已取证 chunk_id 显式摆给模型
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
    """LLM 不可达：轮内重试 1 次（ISS-059）后仍失败 → retry_count++ + E_LLM_UNREACHABLE。"""
    fake = _FakeClient([ConnectionError("LLM 不可达: refused"),
                        ConnectionError("LLM 不可达: refused")])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    out = ad.agent_diagnose(_agent_state(retry_count=1))
    assert len(fake.calls) == 2                        # 首次 + 轮内重试 1 次
    assert out["retry_count"] == 2
    assert out["diagnosis"] is None if "diagnosis" in out else True
    assert out["errors"][0]["code"] == "E_LLM_UNREACHABLE"


def test_agent_loop_timeout_retried_once_then_succeeds(monkeypatch):
    """ISS-059：超时轮内重试 1 次，第 2 次成功则整次诊断不判失败。"""
    fake = _FakeClient([TimeoutError("LLM 调用超时（>90.0s）"),
                        _final_result(_FINAL_JSON)])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    out = ad.agent_diagnose(_agent_state())
    assert len(fake.calls) == 2                        # 首次超时 + 轮内重试 1 次
    assert out["diagnosis"] == "轴承外圈剥落导致振动超标"
    assert "errors" not in out
    assert out.get("retry_count", 0) == 0              # 重试成功不消耗路由重试预算


def test_agent_loop_runtime_error_not_retried(monkeypatch):
    """RuntimeError（配置 / HTTP 4xx-5xx）不重试：只调 1 次即失败（保持既有语义）。"""
    fake = _FakeClient([RuntimeError("LLM HTTP 500")])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    out = ad.agent_diagnose(_agent_state())
    assert len(fake.calls) == 1
    assert out["errors"][0]["code"] == "E_LLM_ERROR"


# ---------------------------------------------------------------- C2. 出网脱敏（U1-D1/D2）

def test_agent_context_masks_device_id():
    """U1-D1：出网上下文不含真实设备编号，只含 设备#<hash> 代号。"""
    alarm = _alarm()
    token = ad.hash_device_id(alarm.device_id)
    ctx = ad._build_agent_context(alarm, token)
    assert alarm.device_id not in ctx
    assert token in ctx and "已脱敏" in ctx


def test_outbound_payload_masks_device_and_drops_work_order_result():
    """U1-D1/D2：回灌前设备号 hash（含任意字符串位置）、工单 result 剥离，原结果不被改。"""
    alarm = _alarm()
    token = ad.hash_device_id(alarm.device_id)
    out = {"ok": True, "result": {
        "device_id": alarm.device_id,
        "work_orders": [{"order_id": "WO-1", "fault": "轴承异响",
                         "action": "更换轴承", "result": "张工现场更换，产线A 3号工位"}],
        "series": [{"sensor_id": f"{alarm.device_id}.vib_rms", "count": 2}],
    }}
    safe = ad._outbound_payload("get_maintenance_history", out, alarm.device_id, token)
    dumped = json.dumps(safe, ensure_ascii=False)
    assert alarm.device_id not in dumped              # 含 sensor_id 等任意位置的编号
    assert token in dumped
    assert "result" not in safe["result"]["work_orders"][0]     # D2：处置描述不出网
    assert safe["result"]["work_orders"][0]["action"] == "更换轴承"
    # 原始 out 未被就地修改（内部状态归集仍用真实值）
    assert out["result"]["work_orders"][0]["result"].startswith("张工")
    assert out["result"]["device_id"] == alarm.device_id


def test_agent_loop_never_leaks_real_device_id_in_messages(monkeypatch):
    """U1-D1 端到端回归锁：发给云端的 messages 全程不含真实设备编号，工具仍拿真号。

    用 `PUMP-Z-99`（刻意避开 schema 示例里的 `PUMP-A-01`）：工具面 description
    是静态文案、非数据面，用它比对会误报。

    2026-10-21：脱敏改为随后端翻转（`AUSCULT_SANITIZE_OUTBOUND=auto` → 仅 cloud 开），
    故本锁**显式置 on** —— 锁的是"开启脱敏时不得泄漏真号"这一契约本身。
    """
    monkeypatch.setenv("AUSCULT_SANITIZE_OUTBOUND", "on")
    alarm = _alarm(device_id="PUMP-Z-99")
    token = ad.hash_device_id(alarm.device_id)
    fake = _FakeClient([
        _tool_calls_result(("query_sensor", {"device_id": token,
                                            "sensor_ids": [f"{token}.vib_rms"],
                                            "time_range": {"start": "1h"}})),
        _final_result(_FINAL_JSON),
    ])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    seen: dict[str, Any] = {}

    def _fake_execute(name, arguments, *, alarm=None, thread_id=None):
        seen["args"] = arguments
        return {"ok": True, "result": {
            "device_id": alarm.device_id,
            "series": [{"sensor_id": f"{alarm.device_id}.vib_rms",
                        "column": "vib_rms", "count": 1, "max": 7.0}],
        }}
    monkeypatch.setattr(ad, "execute_tool", _fake_execute)

    out = ad.agent_diagnose(_agent_state(alarm=alarm))
    assert out["diagnosis"] == "轴承外圈剥落导致振动超标"
    assert seen["args"]["device_id"] == alarm.device_id      # 执行时已还原真实编号
    for call in fake.calls:
        assert alarm.device_id not in json.dumps(call["messages"], ensure_ascii=False)


def test_local_backend_does_not_mask_device_id(monkeypatch):
    """2026-10-21 口径：合规以本地部署为准 → 本地后端不出网，不掩码、不剥工单 result。"""
    monkeypatch.delenv("AUSCULT_SANITIZE_OUTBOUND", raising=False)
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "local")
    alarm = _alarm(device_id="PUMP-Z-99")
    token = ad.hash_device_id(alarm.device_id)
    fake = _FakeClient([
        _tool_calls_result(("get_maintenance_history", {"device_id": alarm.device_id})),
        _final_result(_FINAL_JSON),
    ])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    seen: dict[str, Any] = {}

    def _fake_execute(name, arguments, *, alarm=None, thread_id=None):
        seen["args"] = arguments
        return {"ok": True, "result": {
            "device_id": alarm.device_id,
            "work_orders": [{"order_id": "WO-1", "fault": "轴承异响",
                             "action": "更换轴承", "result": "张工现场更换"}],
        }}
    monkeypatch.setattr(ad, "execute_tool", _fake_execute)

    ad.agent_diagnose(_agent_state(alarm=alarm))
    assert seen["args"]["device_id"] == alarm.device_id     # 模型直接给真号
    dumped = json.dumps(fake.calls[1]["messages"], ensure_ascii=False)
    assert alarm.device_id in dumped                        # 本地不出网 → 明文
    assert token not in dumped
    assert "张工现场更换" in dumped                          # D2 也随开关关闭


def test_masked_token_restored_in_report(monkeypatch):
    """回归锁（2026-10-21 实证缺陷）：模型复述脱敏代号时，报告结论须还原真实设备号。

    实证：`reports.payload.diagnosis` 曾出现 `设备#f6de90 …`（= hash('PUMP-A')），
    因出网掩码后输出侧未回转 —— 报告是本地产物，不应把机器代号写给用户。
    """
    monkeypatch.setenv("AUSCULT_SANITIZE_OUTBOUND", "on")
    alarm = _alarm(device_id="PUMP-Z-99")
    token = ad.hash_device_id(alarm.device_id)
    payload = json.loads(_FINAL_JSON)
    payload["diagnosis"] = f"{token} 振动值超标"
    payload["root_causes"][0]["cause"] = f"{token} 轴承外圈剥落"
    payload["suggestions"][0]["action"] = f"停机检修 {token}"
    fake = _FakeClient([_final_result(json.dumps(payload, ensure_ascii=False))])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)

    out = ad.agent_diagnose(_agent_state(alarm=alarm))
    assert out["diagnosis"].startswith("PUMP-Z-99")
    assert token not in out["diagnosis"]
    assert out["root_causes"][0].cause.startswith("PUMP-Z-99")
    assert out["suggestions"][0].action.endswith("PUMP-Z-99")


def test_agent_loop_json_parse_failure(monkeypatch):
    """收口内容非 JSON → 正文前 500 字作诊断 + retry_count++（diagnose 同口径）。"""
    fake = _FakeClient([_final_result("这不是 JSON，只是说明文字。")])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    out = ad.agent_diagnose(_agent_state())
    assert out["diagnosis"] == "这不是 JSON，只是说明文字。"
    assert out["retry_count"] == 1
    assert out["errors"][0]["code"] == "E_JSON_PARSE"


# ---------------------------------------------------------------- C2c. ISS-056 设备号口径（2026-10-22）

def test_device_alias_map_normalizes_product_id(monkeypatch):
    """ISS-056 候选①：工具层按 `AUSCULT_DEVICE_ID_SCHEME` 落到库内形态（默认 canonical）。

    迁移后默认 canonical：短编号输入也落规范编号；显式 legacy 才反向落回短编号。
    """
    from app import device_ids as did

    seen: dict[str, Any] = {}

    def _fake_query_sensor(*, device_id, metric, start_ts, end_ts, timeout=0.5):
        seen["device_id"] = device_id
        return {"device_id": device_id, "metric": metric, "count": 3,
                "rows": [{"ts": 1, "value": 4.8}, {"ts": 2, "value": 5.1},
                         {"ts": 3, "value": 4.9}]}
    monkeypatch.setattr("app.tools.query_sensor.query_sensor", _fake_query_sensor)

    monkeypatch.delenv(did.SCHEME_ENV, raising=False)     # 默认 = 迁移后口径
    out = tr._exec_query_sensor({"device_id": "PUMP-A",
                                 "sensor_ids": ["PUMP-A.vib_rms"]},
                                alarm=_alarm(device_id="PUMP-A"))
    assert out["ok"] is True
    assert seen["device_id"] == "PUMP-A-01"              # 已归一到库内规范编号
    r = out["result"]
    assert r["device_id"] == "PUMP-A-01"                 # 回灌模型的是库里的真名
    assert r["device_id_resolved"] == {"requested": "PUMP-A", "used": "PUMP-A-01"}
    assert r["series"][0]["count"] == 3                  # 不再是静默空结果

    # 显式 legacy（连未迁移的旧库）：规范编号输入落回短编号
    monkeypatch.setenv(did.SCHEME_ENV, "legacy")
    out2 = tr._exec_query_sensor({"device_id": "PUMP-A-01",
                                  "sensor_ids": ["PUMP-A-01.vib_rms"]},
                                 alarm=_alarm(device_id="PUMP-A-01"))
    assert seen["device_id"] == "PUMP-A"
    assert out2["result"]["device_id_resolved"] == {"requested": "PUMP-A-01",
                                                    "used": "PUMP-A"}


def test_empty_result_distinguishes_device_not_found(monkeypatch):
    """ISS-056：库里没这台设备 → empty_reason=device_not_found（不再静默 count=0）。"""
    monkeypatch.setattr("app.tools.query_sensor.query_sensor",
                        lambda **kw: {"rows": []})
    monkeypatch.setattr(tr, "_device_has_any_data", lambda d, **kw: False)

    out = tr._exec_query_sensor({"device_id": "PUMP-Z-99",
                                 "sensor_ids": ["PUMP-Z-99.vib_rms"]},
                                alarm=_alarm(device_id="PUMP-Z-99"))
    assert out["ok"] is False
    assert out["empty_reason"] == "device_not_found"
    assert "在时序库中不存在" in out["error"]


def test_empty_result_distinguishes_no_data_in_window(monkeypatch):
    """ISS-056：设备存在但窗口内无数据 → empty_reason=no_data_in_window。"""
    monkeypatch.setattr("app.tools.query_sensor.query_sensor",
                        lambda **kw: {"rows": []})
    monkeypatch.setattr(tr, "_device_has_any_data", lambda d, **kw: True)

    out = tr._exec_query_sensor({"device_id": "PUMP-A",
                                 "sensor_ids": ["PUMP-A.vib_rms"]},
                                alarm=_alarm(device_id="PUMP-A"))
    assert out["ok"] is False
    assert out["empty_reason"] == "no_data_in_window"
    assert "查询窗口内无数据" in out["error"]


def test_partial_empty_keeps_series_with_classified_reason(monkeypatch):
    """部分测点有数据、部分空 → 仍 ok=True，但空的原因要写进 partial_errors。"""
    def _fake_query_sensor(*, device_id, metric, start_ts, end_ts, timeout=0.5):
        rows = ([{"ts": 1, "value": 4.8}] if metric == "vib_rms" else [])
        return {"device_id": device_id, "metric": metric, "count": len(rows),
                "rows": rows}
    monkeypatch.setattr("app.tools.query_sensor.query_sensor", _fake_query_sensor)
    monkeypatch.setattr(tr, "_device_has_any_data", lambda d, **kw: True)

    out = tr._exec_query_sensor(
        {"device_id": "PUMP-A", "sensor_ids": ["PUMP-A.vib_rms", "PUMP-A.bearing_temp"]},
        alarm=_alarm(device_id="PUMP-A"))
    assert out["ok"] is True
    assert out["result"]["empty_reason"] == "no_data_in_window"
    assert any("查询窗口内无数据" in e for e in out["result"]["partial_errors"])
    assert out["result"]["series"][0]["sensor_id"] == "PUMP-A.vib_rms"


def test_device_has_any_data_is_conservative_on_probe_failure(monkeypatch):
    """探测失败（TDengine 抖动）→ 保守假设设备存在，不谎称"设备不存在"。"""
    import app.tools.query_sensor as qs

    def _boom(*a, **kw):
        raise ConnectionError("tdengine down")
    monkeypatch.setattr(qs, "_td_query", _boom)
    assert tr._device_has_any_data("PUMP-A") is True


# ---------------------------------------------------------------- C2b. 评审增量 E1/E2（2026-10-22）

def test_tool_arg_rejections_are_counted(monkeypatch):
    """E2：白名单/参数被拒要计数，写操作护栏**不**计（那是正确的安全行为）。"""
    monkeypatch.setenv("AUSCULT_SANITIZE_OUTBOUND", "off")
    alarm = _alarm()
    fake = _FakeClient([
        # 第 1 轮：写操作护栏（**正确拒绝**，不计数）
        _tool_calls_result(("generate_report", {})),
        # 第 2 轮：工具不在白名单（计数）
        _tool_calls_result(("delete_database", {"target": "all"})),
        # 第 3 轮：合法工具但参数缺失（计数）
        _tool_calls_result(("query_sensor", {})),
        # 第 4 轮：正常调用
        _tool_calls_result(("query_graph", {"start_node": "PUMP-A-01"})),
        _final_result(_FINAL_JSON),
    ])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    # **不打桩 execute_tool** —— 要的就是真实白名单/参数校验的拒绝路径；
    # 只把最终执行体换成假的，避免真连 Milvus/Neo4j。
    monkeypatch.setattr(tr, "_EXECUTORS", {"query_graph": lambda a, al: {
        "ok": True, "result": {"nodes": [], "edges": []}}})

    out = ad.agent_diagnose(_agent_state(alarm=alarm))
    # 白名单 1 + 参数 1 = 2；写操作护栏 0
    assert out["tool_arg_rejections"] == 2
    kinds = [s.get("reject_kind") for s in out["agent_steps"]]
    assert "write_guard" in kinds            # 轨迹里仍记录（供云端判断）
    assert "whitelist" in kinds and "arg" in kinds
    assert out["agent_steps"][0]["ok"] is False


def test_route_early_escalate_on_arg_rejections(monkeypatch):
    """E2 路由：参数被拒 ≥2 且后端为 local、未升级过 → 提前 escalate_cloud。"""
    monkeypatch.delenv("AUSCULT_CLOUD_FALLBACK", raising=False)
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "local")
    state = _agent_state(tool_arg_rejections=2, confidence=0.80)
    assert build_mod._route_condition(state) == "escalate_cloud"

    # 边界：仅 1 次不触发（仍在正常路由区间内）
    assert build_mod._route_condition(_agent_state(tool_arg_rejections=1,
                                                  confidence=0.80)) == "finalize"
    # 边界：后端即云端 → 不自我触发（escalate 会空转）
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "cloud")
    assert build_mod._route_condition(_agent_state(tool_arg_rejections=5,
                                                  confidence=0.80)) == "finalize"
    # 边界：已升级过 → 不重复触发
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "local")
    assert build_mod._route_condition(_agent_state(tool_arg_rejections=5,
                                                  confidence=0.80,
                                                  escalate_cloud=True)) == "finalize"
    # 边界：开关关闭 → 维持既有语义
    monkeypatch.setenv("AUSCULT_CLOUD_FALLBACK", "0")
    assert build_mod._route_condition(_agent_state(tool_arg_rejections=5,
                                                  confidence=0.80)) == "finalize"


def test_e2e_arg_rejections_trigger_early_cloud_fallback(monkeypatch):
    """E2 全图：Agent 两轮参数被拒 → 路由提前升级云端（而非等置信度/重试）。"""
    monkeypatch.setenv("AUSCULT_DIAGNOSIS_MODE", "agent")
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "local")
    monkeypatch.delenv("AUSCULT_CLOUD_FALLBACK", raising=False)
    monkeypatch.delenv("AUSCULT_SANITIZE_OUTBOUND", raising=False)

    # 前两轮：合法工具 + 空参数 → validate_tool_args 拒绝；第三轮给结论。
    # 注意：这里**不打桩** execute_tool，走真实白名单/参数校验路径。
    fake = _FakeClient([
        _tool_calls_result(("query_sensor", {})),
        _tool_calls_result(("search_knowledge", {})),
        _final_result(_FINAL_JSON),
    ])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)

    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "thr-e2e-reject"}}
    result = graph.invoke({"thread_id": "thr-e2e-reject",
                           "alarm": _alarm().model_dump()}, config)

    assert result.get("tool_arg_rejections") == 2
    # 云端兜底被触发：escalate_cloud 置位（本地后端下会真的去调云端 → 失败降级，
    # 但关键是**路由选择了 escalate 而非 finalize**，且没有白跑完剩余步数）
    assert result.get("escalate_cloud") is True
    assert len(fake.calls) == 3               # 没有继续烧第 4 轮


def test_escalate_includes_local_trajectory(monkeypatch):
    """E1：云端兜底的 messages 必须带本地排查轨迹，且不含参数值/设备号。"""
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "local")
    state = _agent_state(agent_steps=[
        {"step": 1, "tool": "query_sensor", "ok": False, "args_keys": ["device_id"],
         "latency_ms": 12.3, "reject_kind": "arg"},
        {"step": 2, "tool": "query_graph", "ok": True, "args_keys": ["start_node"],
         "latency_ms": 45.6},
        {"step": 3, "tool": None, "ok": True, "args_keys": [], "latency_ms": None,
         "forced_final": True},
    ], tool_arg_rejections=1)

    section = cloud_mod._build_trajectory_section(state)
    assert "本地 Agent 排查轨迹" in section
    assert "query_sensor" in section and "参数校验未过" in section
    assert "query_graph" in section
    assert "强制收口" in section
    assert "PUMP-A-01" not in section            # 只有参数键名，没有值

    # 空轨迹 → 空串（不污染 prompt）
    assert cloud_mod._build_trajectory_section(_agent_state()) == ""


# ---------------------------------------------------------------- C3. 合规拒答/澄清（P7 · 2026-10-21）
# 提示词规则 6a/6b 要求「信息不足或越界时只回文字」——这是**正确行为**，
# 此前被当作 E_JSON_PARSE 解析失败并白调一次云端重试。

_CLARIFY_TEXT = "告警未提供具体设备编号，请补充设备编号后我再诊断。"
_REFUSE_TEXT = "无法预测设备剩余寿命：该请求超出系统只读诊断职责范围。"


def test_clarification_when_device_id_missing(monkeypatch):
    """规则 6a：缺 device_id → 澄清，不自增 retry_count（不触发重试/云端升级）。"""
    fake = _FakeClient([_final_result(_CLARIFY_TEXT)])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    out = ad.agent_diagnose(_agent_state(alarm=_alarm(device_id="")))
    assert out["refusal"]["kind"] == "clarification"
    assert out["confidence"] == 0.0
    assert "retry_count" not in out
    assert out["errors"][0]["code"] == "W_CLARIFY_NEEDED"
    assert out["diagnosis"] == _CLARIFY_TEXT


def test_refusal_for_out_of_scope_request(monkeypatch):
    """规则 6b：越界请求 → refusal；W_ 前缀（非阻塞级），不消耗重试预算。"""
    fake = _FakeClient([_final_result(_REFUSE_TEXT)])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    out = ad.agent_diagnose(_agent_state())
    assert out["refusal"]["kind"] == "refusal"
    assert out["confidence"] == 0.0
    assert "retry_count" not in out
    assert out["errors"][0]["code"] == "W_REFUSED_COMPLIANCE"


def test_refusal_not_claimed_when_tools_were_used(monkeypatch):
    """防误伤：已取证（steps 非空）时非 JSON 仍是 E_JSON_PARSE + retry_count++。"""
    fake = _FakeClient([
        _tool_calls_result(("search_knowledge", {"query": "振动限值"})),
        _final_result("请提供更多测点数据。"),        # 命中语气词，但已取过证
    ])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    monkeypatch.setattr(ad, "execute_tool",
                        lambda *a, **kw: {"ok": True, "result": {"items": []}})
    out = ad.agent_diagnose(_agent_state())
    assert "refusal" not in out
    assert out["errors"][0]["code"] == "E_JSON_PARSE"
    assert out["retry_count"] == 1


def test_route_refusal_short_circuits_to_finalize():
    """路由：refusal 优先于 confidence<0.50 / retry 判定（否则白走 degrade）。"""
    state = _agent_state(refusal={"kind": "refusal", "reason": "越界"},
                         confidence=0.0)
    assert build_mod._route_condition(state) == "finalize"
    # 历史线程遗留 retry_count 时也不得被「重试/降级」分支截走
    state2 = _agent_state(refusal={"kind": "clarification", "reason": "缺设备号"},
                          confidence=0.0, retry_count=2)
    assert build_mod._route_condition(state2) == "finalize"


def test_agent_mode_refusal_end_to_end_no_retry(monkeypatch):
    """全图：拒答只调 1 次 LLM，不进 escalate_cloud / degrade。"""
    monkeypatch.setenv("AUSCULT_DIAGNOSIS_MODE", "agent")
    fake = _FakeClient([_final_result(_REFUSE_TEXT)])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)

    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "thr-refusal-e2e"}}
    result = graph.invoke({"thread_id": "thr-refusal-e2e",
                           "alarm": _alarm().model_dump()}, config)

    assert len(fake.calls) == 1                    # 关键：不重试
    assert result["refusal"]["kind"] == "refusal"
    assert result["confidence"] == 0.0
    assert result.get("escalate_cloud", False) is False
    assert result.get("degrade_reason") is None


def test_agent_loop_budget_exceeded_degrades(monkeypatch):
    """cloud 后端预算熔断 → degrade_reason=budget_exceeded（不调 LLM）。"""
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "cloud")

    class _Guard:
        def reserve(self):       # ISS-054：调用前占位，超限即回滚
            return False, 340, 340, "budget_exceeded(340/340)"

        def check(self):         # pragma: no cover - 新路径不得再用只读预览判熔断
            raise AssertionError("熔断判定应走 reserve()")

        def increment(self):     # pragma: no cover - 先增后调后不得再事后计费
            raise AssertionError("熔断时不得计费")

    monkeypatch.setattr("app.router.budget.BudgetGuard", _Guard)
    fake = _FakeClient([_final_result(_FINAL_JSON)])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    out = ad.agent_diagnose(_agent_state())
    assert out["degrade_reason"] == "budget_exceeded"
    assert out["errors"][0]["code"] == "E_BUDGET_EXCEEDED"
    assert fake.calls == []


def test_budget_reserve_counts_before_call_and_rolls_back(monkeypatch):
    """ISS-054：reserve 先增后调（返回含本次的计数）；超限即时回滚、不占额度。"""
    from app.router import budget as budget_mod

    class _FakeRedis:
        def __init__(self, n: int):
            self.n = n

        def incr(self, key):
            self.n += 1
            return self.n

        def decr(self, key):
            self.n -= 1
            return self.n

        def expire(self, key, ttl):
            return True

    fake_redis = _FakeRedis(5)                    # 单实例：计数须在多次 reserve 间保留
    monkeypatch.setattr(budget_mod, "_get_client", lambda: fake_redis)
    monkeypatch.setattr(budget_mod, "_get_limit", lambda: 6)
    guard = budget_mod.BudgetGuard()

    ok, count, _, reason = guard.reserve()        # 5 → 6（含本次，调用前即计）
    assert ok is True and count == 6 and reason == "ok"

    ok2, count2, _, reason2 = guard.reserve()     # 6 → 7 超限 → 回滚到 6
    assert ok2 is False and count2 == 6
    assert "budget_exceeded" in reason2

    ok3, count3, _, _ = guard.reserve()           # 回滚后余量不变，仍熔断
    assert ok3 is False and count3 == 6


def test_budget_reserve_redis_unreachable_does_not_block(monkeypatch):
    """Redis 不可达 → 不阻塞（ok=True / count=-1），与 check 同口径。"""
    from app.router import budget as budget_mod

    def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(budget_mod, "_get_client", _boom)
    monkeypatch.setattr(budget_mod, "_get_limit", lambda: 340)
    ok, count, limit, reason = budget_mod.BudgetGuard().reserve()
    assert ok is True and count == -1 and limit == 340
    assert reason.startswith("redis_unreachable")


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


def test_build_graph_default_is_agent(monkeypatch):
    """默认形态 = **agent**（2026-10-21 所有者裁决）：不设 env 即走 Agent 循环。"""
    monkeypatch.delenv("AUSCULT_DIAGNOSIS_MODE", raising=False)
    g = build_graph(InMemorySaver())
    assert _diag_impl(g) is ad.agent_diagnose
    edges = {tuple(e) for e in g.builder.edges}
    assert ("parse_alarm", "diagnose") in edges
    assert ("parse_alarm", "analyze_sensor") not in edges


def test_build_graph_deterministic_rollback(monkeypatch):
    """回退通道：`AUSCULT_DIAGNOSIS_MODE=deterministic` 恢复固定编排（保留回归防护）。"""
    monkeypatch.setenv("AUSCULT_DIAGNOSIS_MODE", "deterministic")
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
    """call_cloud 保留签名，经统一客户端出口；超时取角色化值（ISS-058）。"""
    monkeypatch.delenv("AUSCULT_CLOUD_TIMEOUT_SEC", raising=False)
    seen: dict[str, Any] = {}

    class _CloudClient:
        def chat(self, messages, *, timeout=None):
            seen["timeout"] = timeout
            return ChatResult(model="Qwen/Qwen3.8-27B", content="云端结论")

    monkeypatch.setattr("app.router.cloud.get_cloud_client", lambda: _CloudClient())
    assert call_cloud([{"role": "user", "content": "q"}]) == "云端结论"
    assert seen["timeout"] == llm_config.cloud_timeout()


def test_cloud_timeout_is_role_scoped_and_env_overridable(monkeypatch):
    """ISS-058 回归锁：兜底超时跟随 agent 角色（默认 90s），env 可覆盖且需校验。"""
    monkeypatch.delenv("AUSCULT_CLOUD_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("AUSCULT_LLM_TIMEOUT_AGENT_SEC", raising=False)
    assert llm_config.cloud_timeout() == llm_config.llm_timeout(llm_config.ROLE_AGENT)
    assert llm_config.cloud_timeout() == 90.0 > 20.0      # 不得回退到写死的 20s

    monkeypatch.setenv("AUSCULT_LLM_TIMEOUT_AGENT_SEC", "120")
    assert llm_config.cloud_timeout() == 120.0            # 跟随 agent 角色

    monkeypatch.setenv("AUSCULT_CLOUD_TIMEOUT_SEC", "45")
    assert llm_config.cloud_timeout() == 45.0             # 显式覆盖优先

    monkeypatch.setenv("AUSCULT_CLOUD_TIMEOUT_SEC", "abc")
    with pytest.raises(RuntimeError):
        llm_config.cloud_timeout()
    monkeypatch.setenv("AUSCULT_CLOUD_TIMEOUT_SEC", "-1")
    with pytest.raises(RuntimeError):
        llm_config.cloud_timeout()


def test_escalate_passes_role_timeout_to_cloud(monkeypatch):
    """ISS-058 回归锁：escalate 实际下发云端的超时 = 角色化值（非 20s 常量）。"""
    monkeypatch.delenv("AUSCULT_LLM_BACKEND", raising=False)
    monkeypatch.delenv("AUSCULT_CLOUD_TIMEOUT_SEC", raising=False)
    seen: dict[str, Any] = {}

    class _Budget:
        def reserve(self):       # ISS-054：先增后调，返回含本次的计数
            return True, 1, 340, ""

    def _fake_call(messages, *, timeout=None):
        seen["timeout"] = timeout
        return _FINAL_JSON

    monkeypatch.setattr("app.router.cloud.BudgetGuard", lambda: _Budget())
    monkeypatch.setattr("app.router.cloud.load_cloud_config",
                        lambda: {"model": "fake-cloud"})
    monkeypatch.setattr("app.router.cloud.write_audit",
                        lambda rec: seen.setdefault("audit", rec))
    monkeypatch.setattr("app.router.cloud.call_cloud", _fake_call)

    out = CloudRouter().escalate(_agent_state())
    assert seen["timeout"] == llm_config.cloud_timeout() == 90.0
    assert seen["audit"]["timeout_sec"] == 90.0
    assert out["escalate_cloud"] is True and "degrade_reason" not in out


# ---------------------------------------------------------------- G. 可观测化（P7 收尾）

def test_health_llm_probe_shape(monkeypatch):
    """/api/health 的 llm 探针：默认快照 + 配置非法降级（health 永不 500）。"""
    from app.api.routes import health
    monkeypatch.delenv("AUSCULT_LLM_BACKEND", raising=False)
    monkeypatch.delenv("AUSCULT_DIAGNOSIS_MODE", raising=False)
    snap = health._llm_probe()
    assert snap["backend"] == "local" and snap["diagnosis_mode"] == "agent"
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


def test_absorb_refusal_and_thread_status_exposes_it():
    """P7：拒答/澄清进 thread_status —— 规则 6a/6b 的**正确行为**必须对调用方可见，
    否则前端只能从 errors 的 W_ 码反推，用户会以为"诊断失败"。
    """
    from app.api import runner as runner_mod

    rec = runner_mod.ThreadRecord("thr-refusal-x", AlarmEvent(device_id="PUMP-A"), "eng")
    runner_mod._absorb_refusal(rec, "diagnose",
                               {"refusal": {"kind": "clarification", "reason": "缺设备号"}})
    runner_mod._absorb_refusal(rec, "parse_alarm", {"refusal": {"kind": "refusal"}})
    runner_mod._absorb_refusal(rec, "diagnose", {"refusal": "not-a-dict"})   # 脏数据忽略
    runner_mod._absorb_refusal(None, "diagnose", {"refusal": {"kind": "refusal"}})
    assert rec.refusal == {"kind": "clarification", "reason": "缺设备号"}

    with runner_mod._reg_lock:
        runner_mod._registry["thr-refusal-x"] = rec
    try:
        st = runner_mod.thread_status("thr-refusal-x")
        assert st["refusal"] == {"kind": "clarification", "reason": "缺设备号"}
    finally:
        with runner_mod._reg_lock:
            runner_mod._registry.pop("thr-refusal-x", None)


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
    graph.invoke({"thread_id": "thr-agent-e2e",
                  "alarm": _alarm().model_dump()}, config)

    # 2026-10-22（Must#9 修复①）：`risk=high` 一律强制人工审核 → 图在此挂起。
    # 旧断言假设 high 可直接走到 finalize（正是被判定为"绕过路径"的行为）。
    from langgraph.types import Command  # noqa: PLC0415

    snap = graph.get_state(config)
    assert snap.values.get("risk_level") == "high"
    assert "human_review" in (snap.next or ()), f"高风险未进审核：next={snap.next}"

    result = graph.invoke(Command(resume={"action": "approved", "reviewer_id": "rev_dev",
                                          "comment": "离线集成测试审核通过"}), config)

    assert result["diagnosis"] == "轴承外圈剥落导致振动超标"
    assert result["report_id"] and result["report_id"].startswith("RPT-")
    assert [e.chunk_id for e in result["evidence"]] == ["c_001"]
    assert any(s["tool"] == "search_knowledge" for s in result["agent_steps"])
    assert "blocked" not in result          # 引用有效 → 未触发硬校验
    assert (result.get("human_review") or {}).get("status") == "approved"


def test_call_ollama_relative_imports_resolve(monkeypatch):
    """确定性诊断的 LLM 出口：**函数级相对导入必须可解析**（回归锁）。

    2026-10-21 真机复跑实测（`scripts/smoke_agent_cloud.py` 之外的默认形态自检）：
    `app/graph/nodes/diagnose.py::_call_ollama` 曾写成 `from ..llm import ...`，
    在 `app.graph.nodes` 命名空间下解析成**不存在的** `app.graph.llm` →
    默认形态（deterministic）每次调用必崩 `ModuleNotFoundError`。
    该缺陷由 P7 统一客户端改造（`c80f2b4`）引入，且测试全打桩 `get_client`、
    从未真实走过函数级导入，故 260 例回归全绿也未发现。

    本测试**直接调用** `_call_ollama`（唯一 messages → 缓存必未命中），
    任何相对层级写错都会在此暴露。
    """
    import uuid

    from app.graph.nodes import diagnose as diagnose_mod

    class _FakeClient:
        model = "deepseek-r1:7b"

        def chat(self, messages, *, timeout=None):
            assert timeout == 5.0
            return ChatResult(model=self.model, content="确定性诊断结论")

    monkeypatch.setattr("app.llm.client.get_client", lambda role: _FakeClient())

    out = diagnose_mod._call_ollama(
        [{"role": "user", "content": f"reglock-import-{uuid.uuid4().hex}"}],
        timeout=5.0)
    assert out == "确定性诊断结论"


# ---------------------------------------------------------------- H. E3/E4（2026-10-22 外部评审增量）
# E4：收口契约 needs_human/human_reason → risk 强制 high → 复用既有 human_review interrupt
# E3：每轮工具调用后由**代码**回灌「当前诊断状态」摘要（不是让模型自述）

def test_finalize_needs_human_forces_high_and_carries_reason(monkeypatch):
    """E4：模型主动求助 → risk 强制 high + 原因带回 + W_HUMAN_REQUESTED 留痕。"""
    payload = json.loads(_FINAL_JSON)
    payload["needs_human"] = True
    payload["human_reason"] = "关键测点缺失，需现场确认轴承状态"
    fake = _FakeClient([_final_result(json.dumps(payload, ensure_ascii=False))])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)

    out = ad.agent_diagnose(_agent_state())
    assert out["needs_human"] is True
    assert out["human_reason"] == "关键测点缺失，需现场确认轴承状态"
    assert out["risk_level"] == "high"
    assert out["errors"][0]["code"] == "W_HUMAN_REQUESTED"


def test_finalize_needs_human_accepts_string_and_defaults_reason(monkeypatch):
    """E4 第二例：模型把布尔写成字符串也要识别；缺原因时用兜底文案（不静默）。"""
    payload = json.loads(_FINAL_JSON)
    payload["needs_human"] = "是"
    fake = _FakeClient([_final_result(json.dumps(payload, ensure_ascii=False))])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)

    out = ad.agent_diagnose(_agent_state())
    assert out["needs_human"] is True and out["human_reason"] is None
    assert out["risk_level"] == "high"
    assert out["errors"][0]["msg"] == "模型主动请求人工介入"


def test_determine_risk_level_needs_human_override():
    """E4 决策层：needs_human 覆盖一切阈值（高置信度也必须转人工）。"""
    from app.graph.nodes.diagnose import _determine_risk_level

    assert _determine_risk_level("low", 0.99) == "low"
    assert _determine_risk_level("low", 0.99, needs_human=True) == "high"


def test_route_needs_human_goes_to_review_before_confidence(monkeypatch):
    """E4 路由：求助直达 human_review（不被 confidence<0.75 的 escalate 吞掉）。"""
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "local")
    monkeypatch.setenv("AUSCULT_CLOUD_FALLBACK", "0")
    state = _agent_state(confidence=0.60, risk_level="high", needs_human=True,
                         human_reason="需人工确认")
    assert build_mod._route_condition(state) == "human_review"
    # 重试耗尽的既有优先级不被推翻（避免死循环）
    assert build_mod._route_condition(_agent_state(confidence=0.60, needs_human=True,
                                                  retry_count=3)) == "degrade"


def test_review_rule_and_payload_honor_needs_human():
    """E4 审核侧：needs_human 命中审核、原因进 reason 与 payload（审核人能看到"要做什么"）。"""
    from app.graph.nodes import review as review_mod

    state = _agent_state(diagnosis="证据互相矛盾，需人工确认", confidence=0.62,
                         risk_level="high", needs_human=True,
                         human_reason="现场复测轴承温度后再定责")
    risk_eval = review_mod.evaluate_high_risk(state)
    assert risk_eval["needs_review"] is True
    assert any("模型主动求助" in r and "现场复测" in r for r in risk_eval["reasons"])

    payload = review_mod._build_review_payload(state, risk_eval)
    assert payload["needs_human"] is True
    assert payload["human_reason"] == "现场复测轴承温度后再定责"
    assert payload["question"] == "模型主动请求人工介入"


def test_state_brief_injected_after_each_tool_round(monkeypatch):
    """E3：同一轮多个工具后追加**一条**摘要（非每个工具一条），内容含已取证事实。"""
    fake = _FakeClient([
        _tool_calls_result(("search_knowledge", {"query": "轴承剥落"}),
                            ("query_sensor", {"device_id": "PUMP-A-01"})),
        _final_result(_FINAL_JSON),
    ])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)

    def _fake_execute(name, arguments, *, alarm=None, thread_id=None):
        if name == "search_knowledge":
            return {"ok": True, "result": {"degraded": False, "items": [
                {"chunk_id": "c_001", "score": 0.9, "text": "剥落特征"}]}}
        return {"ok": True, "result": {
            "device_id": "PUMP-A-01",
            "series": [{"sensor_id": "PUMP-A-01.vib_rms", "column": "vib_rms",
                        "count": 12, "avg": 6.2, "max": 7.1, "exceed_count": 4,
                        "threshold": 4.5}]}}
    monkeypatch.setattr(ad, "execute_tool", _fake_execute)

    ad.agent_diagnose(_agent_state())
    msgs = fake.calls[1]["messages"]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant",
                                        "tool", "tool", "user"]
    brief = msgs[-1]["content"]
    assert "【当前诊断状态】" in brief
    assert "search_knowledge×1" in brief and "query_sensor×1" in brief
    assert "c_001" in brief                       # 可引用 chunk_id 显式摆出
    assert "vib_rms" in brief and "max=7.1" in brief and "exceed_count=4" in brief


def test_e2e_needs_human_triggers_existing_review_interrupt(monkeypatch):
    """E4 全图：求助 → 走**既有** human_review interrupt（不新增中断类型/节点）。"""
    monkeypatch.setenv("AUSCULT_DIAGNOSIS_MODE", "agent")
    payload = json.loads(_FINAL_JSON)
    payload.update({"needs_human": True,
                    "human_reason": "证据互相矛盾，需人工判定",
                    "self_confidence": 0.95})
    fake = _FakeClient([_final_result(json.dumps(payload, ensure_ascii=False))])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)

    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "thr-needs-human"}}
    graph.invoke({"thread_id": "thr-needs-human",
                  "alarm": _alarm().model_dump()}, config)

    snap = graph.get_state(config)
    assert "human_review" in (snap.next or ())
    intr = next(getattr(i, "value", None) for t in snap.tasks
                for i in getattr(t, "interrupts", ()) or ())
    assert intr["needs_human"] is True
    assert intr["human_reason"] == "证据互相矛盾，需人工判定"
    assert intr["risk_level"] == "high"
    assert intr["question"] == "模型主动请求人工介入"
    assert any("模型主动求助" in r for r in intr["risk_eval"]["reasons"])


def test_state_brief_shows_failed_tool_calls(monkeypatch):
    """E3 失败分支：被拒/失败也要进摘要（否则模型会无限重试同一调用）。"""
    fake = _FakeClient([
        _tool_calls_result(("query_graph", {"start_node": "PUMP-A-01"})),
        _final_result(_FINAL_JSON),
    ])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    monkeypatch.setattr(ad, "execute_tool", lambda *a, **kw: {
        "ok": False, "rejected": True, "reject_kind": "arg",
        "error": "参数校验失败：缺少必填参数 start_node"})

    ad.agent_diagnose(_agent_state())
    brief = fake.calls[1]["messages"][-1]["content"]
    assert "失败/被拒" in brief
    assert "query_graph（参数校验未过）" in brief
    assert "失败/被拒" not in ad._Collector().brief(step=1, max_steps=4)   # 无失败不造假


# ---------------------------------------------------------------- I. E5 未收敛信号（2026-10-22）
# 材料二 #6 的触发条件三组合里，"未收敛"此前的缺口：forced_final 只落 agent_steps，
# 路由不消费——模型烧完步数被截停与正常收敛在路由上无差别。本组把该信号接进路由。

def test_agent_loop_forced_final_marks_not_converged(monkeypatch):
    """E5：步数用尽被强制收口 → not_converged=True；正常收敛不置位。"""
    fake = _FakeClient([
        _tool_calls_result(("search_knowledge", {"query": "q1"})),
        _tool_calls_result(("search_knowledge", {"query": "q2"})),
        _final_result(_FINAL_JSON),
    ])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)
    monkeypatch.setenv("AUSCULT_AGENT_MAX_STEPS", "2")
    out = ad.agent_diagnose(_agent_state())
    assert out["agent_steps"][-1]["forced_final"] is True
    assert out["not_converged"] is True

    fake2 = _FakeClient([_final_result(_FINAL_JSON)])
    monkeypatch.setattr(ad, "get_client", lambda role: fake2)
    out2 = ad.agent_diagnose(_agent_state())
    assert out2.get("not_converged", False) is False


def test_route_not_converged_escalates_before_confidence(monkeypatch):
    """E5 路由：未收敛（local + 未升级）→ 提前 escalate_cloud；求助优先级更高。"""
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "local")
    monkeypatch.delenv("AUSCULT_CLOUD_FALLBACK", raising=False)
    # confidence 0.80 本应 finalize —— 未收敛是比 confidence 更早的失败信号
    assert build_mod._route_condition(
        _agent_state(confidence=0.80, not_converged=True)) == "escalate_cloud"
    # 护栏：已升级过 → 不重复触发
    assert build_mod._route_condition(
        _agent_state(confidence=0.80, not_converged=True,
                     escalate_cloud=True)) == "finalize"
    # 护栏：后端即云端 → 不自我触发
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "cloud")
    assert build_mod._route_condition(
        _agent_state(confidence=0.80, not_converged=True)) == "finalize"
    # 求助优先于未收敛（"要人定夺" vs "云端再裁一次"）
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "local")
    assert build_mod._route_condition(
        _agent_state(confidence=0.80, not_converged=True, needs_human=True,
                     risk_level="high")) == "human_review"


def test_e2e_not_converged_triggers_cloud_fallback(monkeypatch):
    """E5 全图：forced_final → 路由提前升级云端（而非等 confidence 判定）。"""
    monkeypatch.setenv("AUSCULT_DIAGNOSIS_MODE", "agent")
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "local")
    monkeypatch.delenv("AUSCULT_CLOUD_FALLBACK", raising=False)
    monkeypatch.delenv("AUSCULT_SANITIZE_OUTBOUND", raising=False)
    monkeypatch.setenv("AUSCULT_AGENT_MAX_STEPS", "2")   # 2 轮工具 + 1 次强制收口
    fake = _FakeClient([
        _tool_calls_result(("search_knowledge", {"query": "q1"})),
        _tool_calls_result(("search_knowledge", {"query": "q2"})),
        _final_result(_FINAL_JSON),
    ])
    monkeypatch.setattr(ad, "get_client", lambda role: fake)

    class _Svc:
        def retrieve(self, question, *, mode=None, cache_key=None):
            return {"degraded": False, "items": []}
    monkeypatch.setattr(tr, "_get_retrieval_service", lambda: _Svc())

    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "thr-e5-notconv"}}
    result = graph.invoke({"thread_id": "thr-e5-notconv",
                           "alarm": _alarm().model_dump()}, config)

    assert result.get("not_converged") is True
    assert result.get("escalate_cloud") is True       # 路由选了 escalate 而非 finalize
    assert len(fake.calls) == 3                       # 没有继续烧第 4 轮


# ---------------------------------------------------------------- J. 求助率监控与调用方可见性（E4）

def test_review_counts_needs_human_reason(monkeypatch):
    """E4 可观测：转人工原因分开计数（模型求助 vs 风险等级高）。"""
    from app.graph.nodes import review as review_mod

    before_model = pm.NEEDS_HUMAN.labels(reason="needs_human")._value.get()
    before_risk = pm.NEEDS_HUMAN.labels(reason="risk_high")._value.get()
    monkeypatch.setattr(review_mod, "interrupt",
                        lambda payload: {"action": "approved", "reviewer_id": "rev-j"})

    review_mod.human_review(_agent_state(diagnosis="证据矛盾，需人工确认",
                                         risk_level="high", needs_human=True,
                                         human_reason="现场复测轴承温度"))
    assert pm.NEEDS_HUMAN.labels(reason="needs_human")._value.get() == before_model + 1
    assert pm.NEEDS_HUMAN.labels(reason="risk_high")._value.get() == before_risk

    # 纯风险高（非求助，关键词命中）→ 计 risk_high，不污染求助占比
    review_mod.human_review(_agent_state(diagnosis="需立即停机检查轴承",
                                         risk_level="high"))
    assert pm.NEEDS_HUMAN.labels(reason="risk_high")._value.get() == before_risk + 1
    assert pm.NEEDS_HUMAN.labels(reason="needs_human")._value.get() == before_model + 1


def test_absorb_needs_human_and_thread_status_exposes_it():
    """E4 调用方可见性：求助标记进 ThreadRecord 与 thread_status（同 refusal 口径）。"""
    from app.api import runner as runner_mod

    rec = runner_mod.ThreadRecord("thr-nh", AlarmEvent(device_id="PUMP-A"), "eng")
    runner_mod._absorb_needs_human(rec, "diagnose",
                                   {"needs_human": True, "human_reason": "现场复测"})
    runner_mod._absorb_needs_human(rec, "parse_alarm", {"needs_human": True})  # 非 diagnose 忽略
    runner_mod._absorb_needs_human(rec, "diagnose", {"needs_human": False})    # 假值不清除
    runner_mod._absorb_needs_human(rec, "diagnose", {"needs_human": True})     # 无 reason 不崩
    runner_mod._absorb_needs_human(None, "diagnose", {"needs_human": True})    # rec=None 安全
    assert rec.needs_human is True and rec.human_reason == "现场复测"

    with runner_mod._reg_lock:
        runner_mod._registry["thr-nh"] = rec
    try:
        st = runner_mod.thread_status("thr-nh")
        assert st["needs_human"] is True and st["human_reason"] == "现场复测"
    finally:
        with runner_mod._reg_lock:
            runner_mod._registry.pop("thr-nh", None)


# ---------------------------------------------------------------- K. ISS-056 图谱/工单侧收尾（2026-10-22）

def test_exec_get_maintenance_history_alias_and_empty_reason(monkeypatch):
    """ISS-056 工单侧：别名归一 + 空结果回灌库里**真实编号样本**（不单向猜映射）。"""
    from app import device_ids as did

    captured: dict[str, Any] = {}

    def _fake_history(device_id, *, limit=10, timeout=2.0):
        captured["device_id"] = device_id
        return []
    monkeypatch.setattr("app.tools.get_maintenance_history.get_maintenance_history",
                        _fake_history)
    monkeypatch.setattr("app.tools.get_maintenance_history.list_known_devices",
                        lambda **kw: ["PUMP-A", "PUMP-B"])

    monkeypatch.delenv(did.SCHEME_ENV, raising=False)          # 默认 = 迁移后口径
    out = tr.execute_tool("get_maintenance_history", {"device_id": "PUMP-A"})
    assert out["ok"] is True
    res = out["result"]
    assert captured["device_id"] == "PUMP-A-01"                # 已按别名归一（短 → 规范）
    assert res["device_id_resolved"] == {"requested": "PUMP-A", "used": "PUMP-A-01"}
    assert res["empty_reason"] == "no_work_orders"
    assert res["known_device_ids"] == ["PUMP-A", "PUMP-B"]    # 模型可据此自我纠正

    monkeypatch.setenv(did.SCHEME_ENV, "legacy")               # 显式旧库口径
    out2 = tr.execute_tool("get_maintenance_history", {"device_id": "PUMP-A-01"})
    assert captured["device_id"] == "PUMP-A"
    assert out2["result"]["device_id_resolved"] == {"requested": "PUMP-A-01",
                                                    "used": "PUMP-A"}

    # 探测失败（库不可达）→ 保守不给样本，不谎称"无此设备"
    monkeypatch.delenv(did.SCHEME_ENV, raising=False)
    monkeypatch.setattr("app.tools.get_maintenance_history.list_known_devices",
                        lambda **kw: None)
    out3 = tr.execute_tool("get_maintenance_history", {"device_id": "PUMP-A-01"})
    res3 = out3["result"]
    assert res3["empty_reason"] == "no_work_orders"
    assert "known_device_ids" not in res3
    assert "device_id_resolved" not in res3                    # 未命中原样透传


def test_exec_query_graph_start_node_alias(monkeypatch):
    """ISS-056 图谱侧：start_node 归一进 question；空命中给可解释 note。"""
    from app import device_ids as did

    seen: dict[str, Any] = {}

    def _fake_graph(question):
        seen["question"] = question
        return {"degraded": False, "entities_hit": [], "hits": []}
    monkeypatch.setattr("app.tools.query_graph.query_graph", _fake_graph)

    monkeypatch.delenv(did.SCHEME_ENV, raising=False)          # 默认 = 迁移后口径
    out = tr.execute_tool("query_graph", {"start_node": "PUMP-A"})
    assert seen["question"].startswith("PUMP-A-01 ")          # 短编号 → 规范编号
    res = out["result"]
    assert res["device_id_resolved"] == {"requested": "PUMP-A", "used": "PUMP-A-01"}
    assert "图谱未命中实体" in res["note"]                    # 空结果可解释

    # 显式 legacy（未迁移的旧图谱）：完整编号不进图谱问题
    monkeypatch.setenv(did.SCHEME_ENV, "legacy")
    out2 = tr.execute_tool("query_graph", {"start_node": "PUMP-A-01"})
    assert seen["question"].startswith("PUMP-A ")
    assert "PUMP-A-01" not in seen["question"]
    assert out2["result"]["device_id_resolved"] == {"requested": "PUMP-A-01",
                                                    "used": "PUMP-A"}

    # 未命中别名表 → 原样透传、不假装归一
    monkeypatch.delenv(did.SCHEME_ENV, raising=False)
    seen.clear()

    def _fake_graph2(question):
        seen["question"] = question
        return {"degraded": False, "entities_hit": ["FAN-9"], "hits": []}
    monkeypatch.setattr("app.tools.query_graph.query_graph", _fake_graph2)
    out3 = tr.execute_tool("query_graph", {"start_node": "FAN-9"})
    assert seen["question"].startswith("FAN-9 ")
    assert "device_id_resolved" not in out3["result"]
    assert "note" not in out3["result"]                       # 有实体命中 → 不给空结果提示

