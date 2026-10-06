"""llm_adapter 回归测试：覆盖历史上真实修复过的缺陷。

对应缺陷：ISS-011（think 污染）、ISS-013（静默退化）、ISS-024（few-shot 恒取 v1）、
        复审 F1（裸单对象）、ISS-027（裸 arguments 不可还原）、run_v1 通道选择缺陷。
"""
import json
from pathlib import Path

import pytest

import llm_adapter as la

ROOT = Path(__file__).resolve().parents[1]
PROMPT_V1 = ROOT / "prompts" / "tool_call_prompt_v1.md"
SCHEMA = ROOT / "schemas" / "tools_v4.json"


# ---------------------------------------------------------------- ISS-011 / 013：think 剥离
def test_strip_think_paired_block():
    """成对标签：正文须剥离干净，think 内容单独返回。"""
    raw = f"{la._T_OPEN}推理过程 SECRET{la._T_CLOSE}{{\"ok\": 1}}"
    clean, think = la.strip_think(raw)
    assert "SECRET" not in clean
    assert "SECRET" in think
    assert "ok" in clean


def test_strip_think_unclosed_block():
    """未闭合（max_tokens 打满）：从开标记剥到结尾，不得残留半截 JSON。"""
    raw = "前置 " + la._T_OPEN + '被打断的推理 {"partial": '
    clean, _ = la.strip_think(raw)
    assert "被打断的推理" not in clean
    assert "partial" not in clean


def test_strip_think_r1_special_token():
    """DeepSeek-R1 的 end-of-thinking 特殊 token 同样须被识别。"""
    raw = f"{la._T_OPEN}R1 推理{la.R1_END_TOKEN}{{\"done\": true}}"
    clean, think = la.strip_think(raw)
    assert "R1 推理" not in clean
    assert "R1 推理" in think


# ---------------------------------------------------------------- tool_calls 解析（标准路径优先）
def test_parse_tool_calls_prefers_native_field():
    """标准 message.tool_calls 存在时优先使用，且 arguments 须解析为 dict。"""
    message = {"tool_calls": [{"function": {"name": "query_sensor",
                                            "arguments": '{"device_id": "PUMP-A-01"}'}}]}
    calls = la.parse_tool_calls(message, clean_text="正文里有干扰 JSON 也不该被采用")
    assert len(calls) == 1
    assert calls[0].name == "query_sensor"
    assert calls[0].arguments == {"device_id": "PUMP-A-01"}
    assert calls[0].arguments_parse_error is None


def test_parse_tool_calls_fallback_to_content():
    """标准字段缺失时退化为从正文 JSON 还原（该路径须单列统计，ISS-013）。"""
    message = {}
    text = '[{"name": "search_knowledge", "arguments": {"query": "振动标准"}}]'
    calls = la.parse_tool_calls(message, clean_text=text)
    assert len(calls) == 1
    assert calls[0].name == "search_knowledge"


def test_parse_tool_calls_bare_arguments_is_unrecoverable():
    """ISS-027：只给 arguments、丢了 name 的形态**不可还原** —— 须返回空，
    以防止把"模型丢失工具名"误当作"工具名错误"或静默通过。"""
    message = {}
    text = '{"device_id": "PUMP-A-01", "sensor_ids": ["PUMP-A-01.vib_x"]}'
    assert la.parse_tool_calls(message, clean_text=text) == []


def test_parse_tool_calls_invalid_arguments_flagged():
    """arguments 非法 JSON 时须置 arguments_parse_error，不得静默当作可解析。"""
    message = {"tool_calls": [{"function": {"name": "query_sensor", "arguments": "{not json"}}]}
    calls = la.parse_tool_calls(message, clean_text="")
    assert len(calls) == 1
    assert calls[0].arguments is None
    assert calls[0].arguments_parse_error is not None


# ---------------------------------------------------------------- 复审 F1：structured_output 正文形态
@pytest.mark.parametrize("payload,expected", [
    ('[{"name": "a", "arguments": {"x": 1}}]', 1),                 # 标准数组
    ('{"tool_calls": [{"name": "a", "arguments": {}}]}', 1),       # 对象包装
    ('{"name": "a", "arguments": {"x": 1}}', 1),                   # F1：裸单对象
    ('{"x": 1}', 0),                                               # ISS-027：裸 arguments
    ('', 0),                                                       # 空
    ('not json', 0),                                               # 非 JSON
])
def test_normalize_structured_calls_forms(payload, expected):
    adapter = la.LLMAdapter(schema_path=SCHEMA, prompt_path=PROMPT_V1)
    assert len(adapter._normalize_structured_calls(payload)) == expected


# ---------------------------------------------------------------- ISS-024：few-shot 须与 --prompt 同源
def test_build_messages_fewshot_follows_prompt_path():
    """ISS-024 回归：few-shot 条数必须随 prompt_path 变化（不得恒回退到 v1 的 3 条）。"""
    adapter = la.LLMAdapter(schema_path=SCHEMA, prompt_path=PROMPT_V1)
    msgs_v1 = la.build_messages("测试输入", history=None, fewshot=True,
                                system_prompt=adapter.system_prompt,
                                prompt_path=PROMPT_V1)
    n_v1 = len(la.load_fewshot(PROMPT_V1))
    assert len(msgs_v1) == 1 + n_v1 + 1   # system + few-shot 消息（已是 role/content 列表）+ 本轮 user

    v2 = ROOT / "prompts" / "tool_call_prompt_v2.md"
    if v2.exists():
        n_v2 = len(la.load_fewshot(v2))
        msgs_v2 = la.build_messages("测试输入", history=None, fewshot=True,
                                    system_prompt=la.load_system_prompt(v2, SCHEMA),
                                    prompt_path=v2)
        assert len(msgs_v2) == 1 + n_v2 + 1
        assert n_v2 != n_v1, "v1/v2 的 few-shot 条数应不同，否则该测试无鉴别力"


def test_build_messages_history_injected():
    """多轮 history 须按序注入（格式为 [{role, content}]，由 run_v1.history_of 产出）。"""
    adapter = la.LLMAdapter(schema_path=SCHEMA, prompt_path=PROMPT_V1)
    history = [{"role": "user", "content": "上一轮问"},
               {"role": "assistant", "content": "上一轮答"}]
    msgs = la.build_messages("本轮输入", history=history, fewshot=False,
                             system_prompt=adapter.system_prompt, prompt_path=PROMPT_V1)
    assert msgs[0]["role"] == "system"
    assert msgs[1] == {"role": "user", "content": "上一轮问"}
    assert msgs[2] == {"role": "assistant", "content": "上一轮答"}
    assert msgs[-1]["content"] == "本轮输入"
    assert all(set(m.keys()) == {"role", "content"} for m in msgs)


# ---------------------------------------------------------------- run_v1 通道选择缺陷回归
def _dummy_result():
    return la.AdapterResult(model="m", content_raw="", content_clean="", think_text="",
                            latency_ms=0.0)


def test_chat_dispatch_cloud_structured():
    """云端 + grammar + structured_output 必须走 response_format 通道（原缺陷：误走 Ollama）。"""
    adapter = la.LLMAdapter(schema_path=SCHEMA, prompt_path=PROMPT_V1,
                            grammar={"type": "array"}, structured_output=True)
    hit = {}
    adapter._chat_openai_structured = lambda m, model: hit.setdefault("path", "structured") or _dummy_result()
    adapter._chat_native = lambda m, model: hit.setdefault("path", "native") or _dummy_result()
    adapter._chat_openai = lambda m, model, use_tools=True: hit.setdefault("path", "openai") or _dummy_result()
    adapter.chat([], model="m")
    assert hit["path"] == "structured"


def test_chat_dispatch_local_native():
    """grammar 存在但非云端 → Ollama 原生 format 通道。"""
    adapter = la.LLMAdapter(schema_path=SCHEMA, prompt_path=PROMPT_V1,
                            grammar={"type": "array"}, structured_output=False)
    hit = {}
    adapter._chat_openai_structured = lambda m, model: hit.setdefault("path", "structured") or _dummy_result()
    adapter._chat_native = lambda m, model: hit.setdefault("path", "native") or _dummy_result()
    adapter.chat([], model="m")
    assert hit["path"] == "native"


def test_chat_dispatch_tools_channel():
    """--transport tools（H5 / ISS-027）：无 grammar → OpenAI 兼容 tools 通道。"""
    adapter = la.LLMAdapter(schema_path=SCHEMA, prompt_path=PROMPT_V1, tool_choice="auto")
    hit = {}
    adapter._chat_openai = lambda m, model, use_tools=True: hit.setdefault("path", "openai") or _dummy_result()
    adapter.chat([], model="m")
    assert hit["path"] == "openai"


# ---------------------------------------------------------------- H5：tool_choice 可配置且默认 auto
def test_tool_choice_default_and_override():
    d = la.LLMAdapter(schema_path=SCHEMA, prompt_path=PROMPT_V1)
    assert d.tool_choice == "auto" == la.DEFAULT_TOOL_CHOICE
    assert la.LLMAdapter(schema_path=SCHEMA, prompt_path=PROMPT_V1,
                         tool_choice="required").tool_choice == "required"


def test_describe_reports_transport():
    """describe() 须显式打印 tool_choice，防止通道静默漂移。"""
    out = la.LLMAdapter(schema_path=SCHEMA, prompt_path=PROMPT_V1).describe()
    assert "transport" in out and "tool_choice=" in out


def test_tools_injected_into_system_prompt():
    """工具 Schema 必须程序化注入 system prompt（不得人工删改）。"""
    adapter = la.LLMAdapter(schema_path=SCHEMA, prompt_path=PROMPT_V1)
    assert "query_sensor" in adapter.system_prompt
    assert "{{TOOLS_JSON_SCHEMA}}" not in adapter.system_prompt


def test_tools_json_for_prompt_is_valid_json():
    tools = json.loads(la.tools_json_for_prompt(SCHEMA))
    assert isinstance(tools, list) and len(tools) == 5
