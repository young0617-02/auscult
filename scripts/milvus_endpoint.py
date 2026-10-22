"""Milvus 端点单一事实源（ISS-042）。

## 为什么需要它

端点历史上并存**三种口径**，且分散在 compose 与脚本字面量里：

| 来源 | 端口 | 说明 |
|---|---|---|
| `docker/compose.base.yml` | `19530:19530` | Phase 0 基线（早期单栈） |
| `docker/compose.v2.yml` / `deploy/docker-compose.yml` | `19531:19530` | v2/deploy 业务栈（基线被 `kbrag_milvus` 占用而偏移） |
| 早期脚本硬编码 | `39530` | P5 复现宿主 `kee-milvus` 时用的端口 |

脚本各自写字面量 → **一键启动后写错实例**（写进别人的 collection）或自检误报端口冲突。
本模块把"宿主端口 + env 覆盖"收成一处：`deploy` 栈是当前唯一交付形态，默认 `19531`；
P5 复现 kee-milvus 时设 `MILVUS_PORT=39530` 即可，无需改代码。

## 契约

- `DEFAULT_MILVUS_PORT = 19531`：与 `deploy/docker-compose.yml` 的 `19531:19530` 一致，
  也与 `app/api/config.py::MILVUS_PORT` 默认值一致；
- `MILVUS_PORT` env 覆盖（`39530` = 宿主 kee-milvus 复现口径）；
- 非法值（`abc` / 空串）**回退默认**，不因手误把连接打到空——与设备编号口径同一条纪律。

> 容器内 Milvus gRPC 恒为 `19530`；`19531` 是**宿主机**映射端口。容器内互访不受本模块影响。
"""

from __future__ import annotations

import os

#: 交付栈宿主映射端口（容器内 19530；见 deploy/docker-compose.yml）
DEFAULT_MILVUS_PORT = 19531

#: 端点主机（本地栈；远端部署请设 `MILVUS_HOST`）
DEFAULT_MILVUS_HOST = "127.0.0.1"

#: 端口覆盖开关
PORT_ENV = "MILVUS_PORT"
HOST_ENV = "MILVUS_HOST"


def milvus_port() -> int:
    """宿主端口：env 优先，非法/缺省回退 `DEFAULT_MILVUS_PORT`。"""
    raw = (os.environ.get(PORT_ENV) or "").strip()
    if not raw:
        return DEFAULT_MILVUS_PORT
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_MILVUS_PORT
    return port if 0 < port < 65536 else DEFAULT_MILVUS_PORT


def milvus_host() -> str:
    """宿主名：env 优先，缺省 `127.0.0.1`。"""
    return (os.environ.get(HOST_ENV) or "").strip() or DEFAULT_MILVUS_HOST


def milvus_uri(host: str | None = None) -> str:
    """`http://{host}:{port}`（pymilvus 的 `uri=` 参数口径）。"""
    return f"http://{host or milvus_host()}:{milvus_port()}"
