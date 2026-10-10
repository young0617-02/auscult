"""结构化 JSON 日志装配（P5-W2/D8 · M5.2）

职责：
  1. 读 `configs/logging.yml` 装配 logging（RotatingFileHandler → logs/auscult.jsonl 风格
     JSONL + stderr 镜像）；
  2. JsonFormatter：每行一个 JSON 对象（ts/level/logger/msg/trace_id/module/funcName），
     trace_id 从 `app.api.errors.get_trace_id()`（contextvar）注入，与 X-Trace-Id 响应头
     和响应包络同源——实现「trace_id 贯穿」（plan/Phase 5 D8）；
  3. AUSCULT_LOG_LEVEL 环境变量覆盖根级别。

集中查询口径：单机部署以 logs/ 轮转 JSONL 为查询面（jq 可查），trace_id 为关联键；
后续若上 Loki/ELK 只需把轮转文件接入采集端，应用侧零改动。

对应交付物：plan/Phase 5 §四 D8 / `configs/logging.yml`
"""

from __future__ import annotations

import json
import logging
import logging.config
import os
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGGING_CONFIG = PROJECT_ROOT / "configs" / "logging.yml"
LOGS_DIR = PROJECT_ROOT / "logs"

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """结构化 JSON formatter（一行一条，含 trace_id 贯穿字段）。"""

    def format(self, record: logging.LogRecord) -> str:
        from app.api.errors import get_trace_id   # noqa: PLC0415（惰性避免循环导入）

        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": get_trace_id(),
            "module": record.module,
            "funcName": record.funcName,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(force: bool = False) -> None:
    """装配结构化日志（幂等；main.py lifespan 与脚本均可调用）。"""
    global _CONFIGURED
    if _CONFIGURED and not force:
        return
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    import yaml   # noqa: PLC0415

    cfg = yaml.safe_load(LOGGING_CONFIG.read_text(encoding="utf-8"))
    # filename 统一锚定到项目 logs/（dictConfig 相对路径跟随 CWD，不可靠）
    for h in cfg.get("handlers", {}).values():
        if isinstance(h.get("filename"), str):
            h["filename"] = str(LOGS_DIR / Path(h["filename"]).name)
    level = os.environ.get("AUSCULT_LOG_LEVEL", "").upper()
    if level in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        cfg["root"]["level"] = level
    logging.config.dictConfig(cfg)
    _CONFIGURED = True


def query_by_trace(trace_id: str, logs_dir: Path | None = None) -> list[dict]:
    """按 trace_id 检索日志行（集中查询的最小实现，供自测/审计用）。"""
    out: list[dict] = []
    directory = logs_dir or LOGS_DIR
    if not directory.exists():
        return out
    for f in sorted(directory.glob("auscult.log*")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("trace_id") == trace_id:
                out.append(obj)
    return out
