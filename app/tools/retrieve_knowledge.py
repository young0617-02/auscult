"""retrieve_knowledge 工具迁移（D4）

Phase 2 资产保留不动（scripts/retrieve_knowledge.py），此处为 app 层封装入口。
通过 sys.path 转发到原模块的 RetrievalService / to_openai_tool / with_tools。

Q5(a) 迁移路径：app/tools/retrieve_knowledge.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from retrieve_knowledge import (  # noqa: E402
    RetrievalService,
    to_openai_tool,
    with_tools,
)

__all__ = ["RetrievalService", "to_openai_tool", "with_tools"]
