"""运行期产物目录的**单一来源**（审计 / 轨迹 / 指标）。

背景（2026-10-22 集成测试隔离）：这些 jsonl 产物原先各自在模块里写死
`<repo>/reports/...`，而 `scripts/test_*.py` 会打真栈、跑图、打点 —— 于是每跑一次
回归都会往**已跟踪**的仓库文件里追加内容（reports/security_audit.jsonl、
reports/traces/*.jsonl、experiments/v1/raw/*.jsonl …），工作区脏一片、diff 无法评审。

现在统一由 `AUSCULT_REPORTS_DIR` 指定根目录：

- 生产/本地默认：`<repo>/reports`（行为与改造前完全一致）；
- pytest 根 conftest 在**导入任何 app 模块之前**把它指向临时目录，回归产物不再入库。

注意：模块常量（`AUDIT_LOG_PATH` / `TRACE_DIR` / `METRICS_DIR`）在 **import 时**取值，
因此覆盖必须发生在 import 之前 —— 这也是为什么 conftest 在模块级（而非 fixture 里）设置。
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: 产物根目录：`AUSCULT_REPORTS_DIR` 可覆盖（绝对路径或相对项目根）
REPORTS_DIR = Path(
    os.environ.get("AUSCULT_REPORTS_DIR") or (PROJECT_ROOT / "reports")
).expanduser()

#: 子目录常量（供各模块直接引用，避免再出现"每处自己拼路径"）
TRACE_DIR = REPORTS_DIR / "traces"
METRICS_DIR = REPORTS_DIR / "metrics"


def reports_file(name: str) -> Path:
    """产物文件路径（不自动建目录；写入方负责 mkdir）。"""
    return REPORTS_DIR / name


__all__ = ["PROJECT_ROOT", "REPORTS_DIR", "TRACE_DIR", "METRICS_DIR", "reports_file"]
