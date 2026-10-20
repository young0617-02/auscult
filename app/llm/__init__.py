"""统一 LLM 客户端包（P7 · Agent 化第一步）。

导出：
- get_client(role) / get_cloud_client()：客户端工厂
- OpenAICompatClient / ChatResult / ToolCall：传输与结果类型
- config：后端/模式/参数访问器（app.llm.config）
"""

from .client import (
    ChatResult,
    OpenAICompatClient,
    ToolCall,
    get_client,
    get_cloud_client,
    reset_client_cache,
)

__all__ = [
    "ChatResult",
    "OpenAICompatClient",
    "ToolCall",
    "get_client",
    "get_cloud_client",
    "reset_client_cache",
]
