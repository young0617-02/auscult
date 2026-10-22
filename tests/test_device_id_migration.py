"""离线回归锁：ISS-056 候选①（数据层编号统一）——映射源 / 迁移脚本 / 查询兼容。

纪律：零真实 PG/TDengine/Neo4j；连接与 REST/HTTP 全部打桩，默认 dry-run 断言"不写库"。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app import device_ids as did

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------- A. 映射源（单一事实源）

def test_canonical_and_legacy_are_inverse():
    assert did.canonical("PUMP-A") == "PUMP-A-01"
    assert did.legacy("PUMP-A-01") == "PUMP-A"
    # 已是目标形态 / 未登记编号：原样透传（不伪造已知设备）
    assert did.canonical("PUMP-A-01") == "PUMP-A-01"
    assert did.legacy("FAN-9") == "FAN-9"
    assert did.canonical("") == ""


def test_storage_id_follows_scheme(monkeypatch):
    """默认（迁移后）= canonical 查规范编号；显式 legacy = 旧库查短编号；未知编号恒原样。"""
    monkeypatch.delenv(did.SCHEME_ENV, raising=False)
    assert did.device_id_scheme() == "canonical"        # 2026-10-22 真机迁移后的默认
    assert did.storage_id("PUMP-A-01") == "PUMP-A-01"
    assert did.storage_id("PUMP-A") == "PUMP-A-01"      # 两跳：短 → 规范
    assert did.storage_id("FAN-9") == "FAN-9"           # 未登记不迁移

    # 显式 legacy：连未迁移的旧库时才用
    monkeypatch.setenv(did.SCHEME_ENV, "legacy")
    assert did.device_id_scheme() == "legacy"
    assert did.storage_id("PUMP-A-01") == "PUMP-A"
    assert did.storage_id("PUMP-A") == "PUMP-A"

    # 配置手误不得把查询打到空 → 回退默认（canonical）
    monkeypatch.setenv(did.SCHEME_ENV, "Canoncial")
    assert did.device_id_scheme() == "canonical"


# ---------------------------------------------------------------- B. 工具层按 scheme 取库内形态

def test_query_sensor_uses_storage_scheme(monkeypatch):
    from app.agent import tool_registry as tr

    seen: dict[str, str] = {}

    def _fake_query_sensor(device_id, metric, start_ts, end_ts, timeout=None):
        seen["device_id"] = device_id
        # 返回非空，避免走 `_device_has_any_data` 的真实库探测
        return {"rows": [{"value": 4.0}], "count": 1}
    monkeypatch.setattr("app.tools.query_sensor.query_sensor", _fake_query_sensor)

    monkeypatch.delenv(did.SCHEME_ENV, raising=False)
    tr.execute_tool("query_sensor", {"device_id": "PUMP-A",
                                     "sensor_ids": ["PUMP-A.vib_rms"],
                                     "time_range": {"start": "1h"}})
    assert seen["device_id"] == "PUMP-A-01"             # 默认（迁移后）：短输入也落规范编号

    monkeypatch.setenv(did.SCHEME_ENV, "legacy")
    tr.execute_tool("query_sensor", {"device_id": "PUMP-A-01",
                                     "sensor_ids": ["PUMP-A-01.vib_rms"],
                                     "time_range": {"start": "1h"}})
    assert seen["device_id"] == "PUMP-A"                # 显式 legacy：落历史短编号


def test_executor_default_devices_are_canonical():
    """灌数端默认值已改规范编号（否则迁移后新数据又写回旧口径）。"""
    for name in ("v3_ingest_direct.py", "gen_sparkplug.py", "spb_simulator.py"):
        text = (PROJECT_ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "PUMP-A-01,PUMP-B-01,PUMP-C-01" in text, name


def test_tool_layer_counts_scheme_mismatch(monkeypatch):
    """映射退场判据（ISS-056）：客户端传"非库内形态"编号时打点，正常口径不计。

    指标连续为 0 才说明所有调用方跟上迁移 → 才可删兼容层（见 `app/device_ids` 头注）。
    """
    from app.agent import tool_registry as tr
    from app.observability import prom_metrics as pm

    def _fake_query_sensor(device_id, metric, start_ts, end_ts, timeout=None):
        return {"rows": [{"value": 4.0}], "count": 1}
    monkeypatch.setattr("app.tools.query_sensor.query_sensor", _fake_query_sensor)

    def _count(direction: str) -> float:
        return pm.DEVICE_ID_SCHEME_MISMATCH.labels(direction=direction)._value.get()

    monkeypatch.delenv(did.SCHEME_ENV, raising=False)     # 默认 canonical
    before = _count("short_input")
    tr.execute_tool("query_sensor", {"device_id": "PUMP-A",     # 短编号 = 逆口径
                                     "sensor_ids": ["PUMP-A.vib_rms"],
                                     "time_range": {"start": "1h"}})
    assert _count("short_input") == before + 1

    merged = _count("short_input")
    tr.execute_tool("query_sensor", {"device_id": "PUMP-A-01",  # 与库内一致 → 不计数
                                     "sensor_ids": ["PUMP-A-01.vib_rms"],
                                     "time_range": {"start": "1h"}})
    assert _count("short_input") == merged


# ---------------------------------------------------------------- A2. 展示口径（只归一文本，不改库内）

def test_canonicalize_text_only_touches_standalone_ids():
    """短编号归一为规范编号；已规范 / 未登记 / 被连字符词字符包裹的一律不动。"""
    assert did.canonicalize_text("PUMP-A 振动超标") == "PUMP-A-01 振动超标"
    assert did.canonicalize_text("PUMP-A-01 正常") == "PUMP-A-01 正常"        # 幂等
    assert did.canonicalize_text("PUMP-A.vib_rms 正常") == "PUMP-A-01.vib_rms 正常"
    assert did.canonicalize_text("FAN-9 与 PUMP-D 未登记") == "FAN-9 与 PUMP-D 未登记"
    assert did.canonicalize_text("X-PUMP-A / PUMP-AX") == "X-PUMP-A / PUMP-AX"
    assert did.canonicalize_text("") == ""


def test_canonicalize_ids_walks_nested_payload():
    payload = {
        "diagnosis": "PUMP-B 温升",
        "root_causes": [{"cause": "PUMP-C 气蚀", "citations": ["PUMP-A.vib_rms"]}],
        "confidence": 0.8,
    }
    out = did.canonicalize_ids(payload)
    assert out["diagnosis"] == "PUMP-B-01 温升"
    assert out["root_causes"][0]["cause"] == "PUMP-C-01 气蚀"
    assert out["root_causes"][0]["citations"] == ["PUMP-A-01.vib_rms"]
    assert out["confidence"] == 0.8                        # 非字符串原样


def test_report_detail_shows_canonical_but_keeps_stored_payload(monkeypatch):
    """读取出口统一口径：历史 payload 显示规范编号，库内证据（dict）不被改写。"""
    import asyncio

    from app.api.routes import reports as reports_route

    stored = {"report_id": "RPT-x", "payload": {"diagnosis": "PUMP-A 振动速度 5.1"}}
    monkeypatch.setattr(reports_route, "_fetch_report", lambda rid: stored)

    out = asyncio.run(reports_route.get_report_detail("RPT-x", _={"username": "t"}))
    assert out["data"]["payload"]["diagnosis"] == "PUMP-A-01 振动速度 5.1"
    assert stored["payload"]["diagnosis"] == "PUMP-A 振动速度 5.1"   # 库内事实不变


# ---------------------------------------------------------------- C. 迁移脚本

class _PgCursor:
    def __init__(self, conn: "_PgConn") -> None:
        self.conn = conn
        self._rows: list[tuple] = []

    def __enter__(self) -> "_PgCursor":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.conn.sql.append(sql.split()[0])
        if sql.startswith("SELECT count(*) FROM alerts"):
            self._rows = [(self.conn.alert_counts.get(params[0], 0),)]
        elif sql.startswith("SELECT count(*) FROM work_orders"):
            self._rows = [(0,)]                          # 工单库无产品编号 → 如实 0 行
        elif sql.startswith("UPDATE alerts"):
            self.conn.updates.append(params)
        else:                                            # pragma: no cover
            raise AssertionError(f"未预期 SQL: {sql}")

    def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else None


class _PgConn:
    def __init__(self, alert_counts: dict[str, int] | None = None) -> None:
        self.alert_counts = alert_counts or {}
        self.updates: list[tuple] = []
        self.sql: list[str] = []
        self.commits = 0

    def cursor(self) -> _PgCursor:
        return _PgCursor(self)

    def commit(self) -> None:
        self.commits += 1


class _TdConn:
    """`rows` 为 `SELECT DISTINCT tbname, device_id` 的返回（真机口径）。"""

    def __init__(self, rows: list[tuple], fail_on: str = "") -> None:
        self.rows = rows
        self.fail_on = fail_on
        self.executed: list[str] = []

    def query(self, sql: str):
        assert "tbname" in sql, f"必须按实际子表名查询（真机踩坑），实际: {sql}"

        class _Res:
            data = self.rows
        return _Res()

    def execute(self, sql: str) -> None:
        self.executed.append(sql)
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("syntax error near tbl")


def test_migrate_pg_dry_run_writes_nothing():
    from scripts import migrate_device_ids as mig

    conn = _PgConn(alert_counts={"PUMP-A": 3, "PUMP-B": 1})
    rep = mig.migrate_pg(conn, mig._pairs(), apply=False)
    assert rep["planned"] == 4
    assert rep["applied"] == 0 and conn.updates == [] and conn.commits == 0
    assert any("alerts: PUMP-A → PUMP-A-01 (3 行)" in d for d in rep["detail"])
    assert any("work_orders: PUMP-A → PUMP-A-01 (0 行)" in d for d in rep["detail"])


def test_migrate_pg_apply_updates_and_commits():
    from scripts import migrate_device_ids as mig

    conn = _PgConn(alert_counts={"PUMP-A": 3})
    rep = mig.migrate_pg(conn, mig._pairs(), apply=True)
    assert rep["applied"] == 3 and conn.commits == 1
    assert ("PUMP-A-01", "PUMP-A") in conn.updates


def test_migrate_td_sets_tag_only(tmp_path=None):
    """真机结论：只 SET TAG、不发 RENAME（3.3.8.0 语法不通且无必要）。"""
    from scripts import migrate_device_ids as mig

    conn = _TdConn([("d_plant1_PUMP-A", "PUMP-A"), ("d_plant1_FAN-9", "FAN-9")])
    rep = mig.migrate_td(conn, mig._pairs(), apply=False)
    assert rep["planned"] == 1                          # 未登记的 FAN-9 不动
    joined = "\n".join(rep["detail"])
    assert "SET TAG device_id='PUMP-A-01'" in joined
    assert "RENAME" not in joined                       # 不再尝试改名
    assert conn.executed == []                          # dry-run 不执行

    conn2 = _TdConn([("d_plant1_PUMP-A", "PUMP-A")])
    rep2 = mig.migrate_td(conn2, mig._pairs(), apply=True)
    assert rep2["applied"] == 1 and len(conn2.executed) == 1


def test_migrate_td_targets_actual_tbname_not_template():
    """真机踩坑回归：子表名与 `d_{group}_{device}` 模板不一致时，必须改**实际表**。

    场景 = 迁移后（TAG 已是 PUMP-A-01、子表名仍是历史的 d_plant1_PUMP-A），
    此时若按模板推导会生成 `d_plant1_PUMP-A-01`（空表）→ 历史数据 TAG 永远回滚不了。
    """
    from scripts import migrate_device_ids as mig

    conn = _TdConn([("d_plant1_PUMP-A", "PUMP-A-01")])
    rep = mig.migrate_td(conn, mig._pairs(revert=True), apply=True)
    assert rep["applied"] == 1
    assert "`d_plant1_PUMP-A`" in conn.executed[0]
    assert "d_plant1_PUMP-A-01" not in conn.executed[0]
    assert "SET TAG device_id='PUMP-A'" in conn.executed[0]


def test_migrate_td_failure_recorded_as_error():
    """SET TAG 失败 = 真故障（名实不符），进 errors；其余子表继续。"""
    from scripts import migrate_device_ids as mig

    conn = _TdConn([("d_plant1_PUMP-A", "PUMP-A"), ("d_plant1_PUMP-B", "PUMP-B")],
                   fail_on="PUMP-A")
    rep = mig.migrate_td(conn, mig._pairs(), apply=True)
    assert rep["applied"] == 1                          # B 成功、A 失败但未中断
    assert len(rep["errors"]) == 1 and "SET TAG" in rep["errors"][0]


def test_migrate_neo4j_counts_and_updates(monkeypatch):
    from scripts import migrate_device_ids as mig
    from scripts import retrieval_base as rb

    calls: list[str] = []

    def _fake_neo4j_run(statements, **kwargs):
        calls.extend(statements)
        if statements[0].startswith("MATCH (e {name:'PUMP-A'}) RETURN"):
            return [{"data": [{"row": [2]}]}]
        if statements[0].startswith("MATCH (e {name:'PUMP-B'}) RETURN"):
            return [{"data": []}]
        return [{"data": []}]
    monkeypatch.setattr(rb, "neo4j_run", _fake_neo4j_run)

    rep = mig.migrate_neo4j(mig._pairs(), apply=True)
    assert rep["planned"] == 2                           # 只有 PUMP-A 有 2 个实体
    assert any("SET e.name='PUMP-A-01'" in s for s in calls)


def test_revert_pairs_are_reversed():
    from scripts import migrate_device_ids as mig

    fwd = dict(mig._pairs())
    rev = dict(mig._pairs(revert=True))
    assert fwd["PUMP-A"] == "PUMP-A-01"
    assert rev["PUMP-A-01"] == "PUMP-A"


def test_check_ids_rejects_unknown():
    from scripts import migrate_device_ids as mig

    mig._check_ids("PUMP-A", "PUMP-A-01")                # 受控集合内
    try:
        mig._check_ids("PUMP-A; DROP TABLE alerts")
    except ValueError:
        pass
    else:                                                # pragma: no cover
        raise AssertionError("非受控编号必须拒绝拼接")


def test_main_offline_exit_code(monkeypatch):
    """三侧全不可达（当前离线环境）→ 退出码 2，不谎称"无可迁移数据"。"""
    import psycopg

    from scripts import migrate_device_ids as mig
    from scripts import retrieval_base as rb

    def _boom(*args, **kwargs):
        raise psycopg.OperationalError("connection timeout expired")

    monkeypatch.setattr(psycopg, "connect", _boom)
    monkeypatch.setattr(mig, "_td_connect", lambda *a, **kw: (_ for _ in ()).throw(
        RuntimeError("td refused")))
    monkeypatch.setattr(rb, "neo4j_run", lambda *a, **kw: (_ for _ in ()).throw(
        RuntimeError("neo4j refused")))

    assert mig.main(["--json"]) == 2


def test_verify_reports_unreachable_sides(monkeypatch):
    import psycopg

    from scripts import migrate_device_ids as mig
    from scripts import retrieval_base as rb

    monkeypatch.setattr(psycopg, "connect", lambda *a, **kw: (_ for _ in ()).throw(
        psycopg.OperationalError("refused")))
    monkeypatch.setattr(mig, "_td_connect", lambda *a, **kw: (_ for _ in ()).throw(
        RuntimeError("refused")))
    monkeypatch.setattr(rb, "neo4j_run", lambda *a, **kw: (_ for _ in ()).throw(
        RuntimeError("refused")))

    result = mig.verify()
    assert result["ok"] is False
    assert all("unreachable" in str(v) for v in result["sides"].values())
    assert json.dumps(result)                            # 可机读
