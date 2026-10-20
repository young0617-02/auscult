"""P7 告警自动触发回归测试（全离线：PG/Redis 以 monkeypatch 挡板）。

对应缺口：自动触发引入后的三类风险——
  1. 重复触发（扫描-启动间隙 / 并发轮次 → 同告警双诊断）；
  2. 越权面扩大（severity 过滤失效 → 低等级告警也烧 LLM 预算）；
  3. 降级路径（PG 不可达 → 必须跳过而非抛出打断 watcher 循环）。

运行：.venv\\Scripts\\python.exe -m pytest tests/test_auto_trigger.py -q
"""

from __future__ import annotations

import datetime as dt

from app.api import auto_trigger as at
from app.api.errors import ApiError
from app.graph.state import AlarmEvent


def _row(alarm_id="a1", device="PUMP-A-01", metric="vib_rms",
         value=4.7, severity="high", ts=None):
    return {"alarm_id": alarm_id, "device_id": device, "metric": metric,
            "value": value, "severity": severity, "status": "open",
            "ts": ts or dt.datetime(2026, 10, 16, 12, 0, tzinfo=dt.timezone.utc)}


# ---------------------------------------------------------------- 过滤与转换

def test_severity_filter_empty_means_all():
    """默认（空过滤集）= 全部放行。"""
    assert at._severity_allowed("high") is True
    assert at._severity_allowed("info") is True


def test_severity_filter_subset(monkeypatch):
    """配置子集后仅子集放行。"""
    monkeypatch.setattr(at, "AUTO_TRIGGER_SEVERITY", ("high", "critical"))
    assert at._severity_allowed("high") is True
    assert at._severity_allowed("critical") is True
    assert at._severity_allowed("info") is False
    assert at._severity_allowed("warning") is False


def test_row_to_alarm_field_mapping():
    """alerts 行 → AlarmEvent 口径对齐 routes/diagnose._load_alarm_by_id。"""
    alarm = at._row_to_alarm(_row())
    assert isinstance(alarm, AlarmEvent)
    assert alarm.alarm_id == "a1"
    assert alarm.device_id == "PUMP-A-01"
    assert alarm.value == 4.7
    assert alarm.severity == "high"
    # ts: datetime → epoch ms
    assert alarm.ts == int(dt.datetime(2026, 10, 16, 12, 0,
                                       tzinfo=dt.timezone.utc).timestamp() * 1000)


def test_row_to_alarm_null_value():
    alarm = at._row_to_alarm(_row(value=None))
    assert alarm.value == 0.0


# ---------------------------------------------------------------- 触发主流程

def test_trigger_once_disabled(monkeypatch):
    """默认关闭 → 0 发起。"""
    monkeypatch.setattr(at, "AUTO_TRIGGER_ENABLED", False)
    assert at.trigger_once() == 0


def test_trigger_once_happy_path(monkeypatch):
    """启用 + 有待触发告警 → 全部发起，两阶段标记都走到，submitter 为系统身份。"""
    monkeypatch.setattr(at, "AUTO_TRIGGER_ENABLED", True)
    rows = [_row("a1"), _row("a2", device="PUMP-B-02")]
    monkeypatch.setattr(at, "_fetch_pending", lambda limit: rows)
    monkeypatch.setattr(at, "cache_guard_trigger", lambda aid: True)
    marked_pending, marked_done, submitters = [], [], []
    monkeypatch.setattr(at, "_mark_pending",
                        lambda aid: marked_pending.append(aid) or True)
    monkeypatch.setattr(at, "_mark_triggered",
                        lambda aid, tid: marked_done.append((aid, tid)))

    def _start(alarm, submitter):
        submitters.append(submitter)
        return f"thr-{alarm.alarm_id}"

    monkeypatch.setattr(at, "start_diagnosis", _start)

    assert at.trigger_once() == 2
    assert marked_pending == ["a1", "a2"]                       # 阶段一：占位
    assert marked_done == [("a1", "thr-a1"), ("a2", "thr-a2")]  # 阶段二：回写
    # submitter 必须是非人类身份（审核职责分离天然成立）
    assert submitters == [at.SUBMITTER, at.SUBMITTER]
    assert at.SUBMITTER == "system:auto-trigger"


def test_trigger_once_severity_skip(monkeypatch):
    """severity 过滤命中的告警不得发起，也不得占位。"""
    monkeypatch.setattr(at, "AUTO_TRIGGER_ENABLED", True)
    monkeypatch.setattr(at, "AUTO_TRIGGER_SEVERITY", ("high",))
    rows = [_row("a1", severity="high"), _row("a2", severity="info")]
    monkeypatch.setattr(at, "_fetch_pending", lambda limit: rows)
    monkeypatch.setattr(at, "cache_guard_trigger", lambda aid: True)
    marked = []
    monkeypatch.setattr(at, "_mark_pending",
                        lambda aid: marked.append(aid) or True)
    monkeypatch.setattr(at, "_mark_triggered", lambda aid, tid: None)
    monkeypatch.setattr(at, "start_diagnosis",
                        lambda alarm, submitter: "thr-x")

    assert at.trigger_once() == 1
    assert marked == ["a1"]                                # a2 被过滤，未占位


def test_trigger_once_guard_block_skips(monkeypatch):
    """Redis 护栏拦截（已触发过）→ 跳过，不进 PG 占位。"""
    monkeypatch.setattr(at, "AUTO_TRIGGER_ENABLED", True)
    monkeypatch.setattr(at, "_fetch_pending", lambda limit: [_row("a1")])
    monkeypatch.setattr(at, "cache_guard_trigger", lambda aid: False)
    marked = []
    monkeypatch.setattr(at, "_mark_pending",
                        lambda aid: marked.append(aid) or True)

    assert at.trigger_once() == 0
    assert marked == []


def test_trigger_once_pending_marker_blocks(monkeypatch):
    """PG 条件 UPDATE 抢锁失败（他轮已占位）→ 跳过。"""
    monkeypatch.setattr(at, "AUTO_TRIGGER_ENABLED", True)
    monkeypatch.setattr(at, "_fetch_pending", lambda limit: [_row("a1")])
    monkeypatch.setattr(at, "cache_guard_trigger", lambda aid: True)
    monkeypatch.setattr(at, "_mark_pending", lambda aid: False)   # rowcount=0
    started = []
    monkeypatch.setattr(at, "start_diagnosis",
                        lambda alarm, submitter: started.append(alarm) or "t")

    assert at.trigger_once() == 0
    assert started == []


def test_trigger_once_single_failure_does_not_block_others(monkeypatch):
    """单条发起异常 → 记 error 继续其余；失败条不回写 thread_id。"""
    monkeypatch.setattr(at, "AUTO_TRIGGER_ENABLED", True)
    rows = [_row("a1"), _row("a2")]
    monkeypatch.setattr(at, "_fetch_pending", lambda limit: rows)
    monkeypatch.setattr(at, "cache_guard_trigger", lambda aid: True)
    monkeypatch.setattr(at, "_mark_pending", lambda aid: True)

    def _boom(alarm, submitter):
        if alarm.alarm_id == "a1":
            raise RuntimeError("graph build failed")
        return "thr-a2"

    monkeypatch.setattr(at, "start_diagnosis", _boom)
    done = []
    monkeypatch.setattr(at, "_mark_triggered",
                        lambda aid, tid: done.append((aid, tid)))

    assert at.trigger_once() == 1
    assert done == [("a2", "thr-a2")]                      # 仅成功条回写


def test_trigger_once_pg_down_skips_round(monkeypatch):
    """PG 不可达（ApiError）→ 本轮跳过返回 0，不抛出（watcher 循环不中断）。"""
    monkeypatch.setattr(at, "AUTO_TRIGGER_ENABLED", True)

    def _down(limit):
        raise ApiError("E_UPSTREAM", "数据库暂不可用")

    monkeypatch.setattr(at, "_fetch_pending", _down)
    assert at.trigger_once() == 0
