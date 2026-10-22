"""ISS-042 回归锁：Milvus 端点单一事实源（脚本侧不得再散落字面量）。

背景：端点曾三口径并存（compose.base `19530` / deploy 栈宿主 `19531` / P5 复现 `39530`），
脚本各自硬编码 → 一键启动后写错实例或自检误报。现统一走 `scripts/milvus_endpoint.py`：

- 默认 `19531`（= `deploy/docker-compose.yml` 的宿主映射，容器内仍是 19530）；
- `MILVUS_PORT` env 覆盖（`39530` = 宿主 kee-milvus 复现口径）；
- 非法值回退默认（同一纪律：配置手误不得把连接打到空）。

锁定方式：行为断言（默认/env/回退）+ 静态断言（脚本无 `127.0.0.1:19530`/`:39530` 字面量、
且 compose 的宿主端口与代码默认值同源）。**不导入** pymilvus 相关脚本，保持离线零依赖。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import milvus_endpoint as me  # noqa: E402


# ------------------------------------------------ A. 默认值 / env / 回退

def test_default_endpoint_matches_deploy_stack(monkeypatch):
    monkeypatch.delenv(me.PORT_ENV, raising=False)
    assert me.DEFAULT_MILVUS_PORT == 19531
    assert me.milvus_port() == 19531
    assert me.milvus_uri() == "http://127.0.0.1:19531"


def test_env_override_for_kee_milvus(monkeypatch):
    """P5 复现宿主 kee-milvus（39530）只需设 env，不改代码。"""
    monkeypatch.setenv(me.PORT_ENV, "39530")
    assert me.milvus_port() == 39530
    assert me.milvus_uri() == "http://127.0.0.1:39530"


def test_host_override(monkeypatch):
    monkeypatch.delenv(me.PORT_ENV, raising=False)
    monkeypatch.setenv(me.HOST_ENV, "milvus.internal")
    assert me.milvus_uri() == "http://milvus.internal:19531"
    assert me.milvus_uri("10.0.0.7") == "http://10.0.0.7:19531"   # 显式参数优先


@pytest.mark.parametrize("bad", ["abc", "", "  ", "70000", "-1"])
def test_illegal_port_falls_back_to_default(monkeypatch, bad):
    """配置手误（拼错/越界）回退默认，绝不把连接打到空。"""
    monkeypatch.setenv(me.PORT_ENV, bad)
    assert me.milvus_port() == me.DEFAULT_MILVUS_PORT


# ------------------------------------------------ B. 与 deploy 栈同源

def test_deploy_compose_host_port_equals_default():
    """`deploy/docker-compose.yml` 的 Milvus 宿主映射必须与代码默认值一致。"""
    text = (PROJECT_ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    host_ports = re.findall(r'"(\d+):19530"', text)
    assert host_ports, "compose 未声明 Milvus 端口映射（19530 容器端口不见了？）"
    assert str(me.DEFAULT_MILVUS_PORT) in host_ports


def test_app_config_defaults_to_same_port():
    """应用侧 `app/api/config.py::MILVUS_PORT` 默认值与脚本侧一致。"""
    text = (PROJECT_ROOT / "app" / "api" / "config.py").read_text(encoding="utf-8")
    m = re.search(r'MILVUS_PORT\s*=\s*int\(os\.environ\.get\("MILVUS_PORT",\s*"(\d+)"\)\)', text)
    assert m, "未找到 MILVUS_PORT 默认值定义"
    assert int(m.group(1)) == me.DEFAULT_MILVUS_PORT


# ------------------------------------------------ C. 脚本侧无残留字面量

_SCRIPTS = (
    "scripts/retrieval_base.py",
    "scripts/reconcile.py",
    "scripts/outbox_worker.py",
    "scripts/build_milvus_v1.py",
    "scripts/v2_load_test.py",
)


@pytest.mark.parametrize("rel", _SCRIPTS)
def test_scripts_have_no_hardcoded_endpoint(rel):
    text = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
    assert "127.0.0.1:19530" not in text, f"{rel} 仍硬编码 Phase-0 基线端口"
    assert "127.0.0.1:39530" not in text, f"{rel} 仍硬编码 kee-milvus 端口"
    assert "milvus_uri()" in text, f"{rel} 未走单一事实源"
