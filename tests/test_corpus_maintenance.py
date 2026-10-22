"""离线回归锁：历史报告脱敏代号清理（ISS-062 遗留）+ 语料规模体检（02 §15 遗留）。

纪律（同 tests/ 全量）：零网络、零真实 PG 连接——
- 清理脚本经假连接（cursor 按 SQL 分发行、UPDATE 记录在案）；
- 体检脚本经 monkeypatch 的路径常量指向 tmp_path 假语料；
- PG 不可达路径经 monkeypatch `psycopg.connect` 抛异常复现（对齐当前离线环境）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts import corpus_stats as cs
from scripts import restore_masked_device_ids as rs

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------- 假件

class _FakeCursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self._conn = conn
        self._rows: list[tuple] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def execute(self, sql: str, params: tuple | None = None) -> None:
        if sql.startswith("SELECT DISTINCT device_id FROM alerts"):
            self._rows = [(d,) for d in self._conn.candidates.get("alerts", [])]
        elif sql.startswith("SELECT DISTINCT device_id FROM work_orders"):
            self._rows = [(d,) for d in self._conn.candidates.get("work_orders", [])]
        elif sql.startswith("SELECT report_id, payload::text"):
            self._rows = [(rid, text) for rid, text in self._conn.reports]
        elif sql.startswith("UPDATE reports SET payload"):
            self._conn.updates.append(params)
        else:                                                # pragma: no cover
            raise AssertionError(f"未预期的 SQL: {sql}")

    def fetchall(self) -> list[tuple]:
        return self._rows

    def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else None


class _FakeConn:
    def __init__(self, candidates: dict | None = None,
                 reports: list[tuple[str, str]] | None = None) -> None:
        self.candidates = candidates or {}
        self.reports = reports or []
        self.updates: list[tuple] = []
        self.commits = 0
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closed = True


def _token(device_id: str) -> str:
    from app.router.cloud import hash_device_id
    return hash_device_id(device_id)


# ---------------------------------------------------------------- A. 历史报告代号清理

def test_reverse_map_matches_export_algorithm():
    """反查表必须与出口同算法（sha256[:6]），不引入第二套口径。"""
    from app.router.cloud import hash_device_id

    reverse = rs.build_reverse_map({"PUMP-A", "MOTOR-1"})
    assert reverse[hash_device_id("PUMP-A")] == "PUMP-A"
    assert reverse[hash_device_id("MOTOR-1")] == "MOTOR-1"
    assert all(t.startswith("设备#") and len(t) == len("设备#") + 6 for t in reverse)


def test_restore_replaces_known_and_keeps_unknown():
    """已知代号还原、未知代号原样保留（宁可漏还原，不可错还原）。"""
    known = _token("PUMP-A")
    payload = json.dumps({"diagnosis": f"{known} 振动超标；另见 设备#deadbe 无映射"},
                         ensure_ascii=False)
    new_text, tokens, unresolved = rs.restore_payload_text(payload, {known: "PUMP-A"})
    assert "PUMP-A 振动超标" in new_text
    assert "设备#deadbe 无映射" in new_text               # 未知代号原样保留
    assert unresolved == ["设备#deadbe"]
    assert known in tokens


def test_restore_payload_without_tokens_is_noop():
    """无代号 → 原样返回、零 unresolved（已清理报告二次跑是 no-op）。"""
    text = json.dumps({"diagnosis": "PUMP-A 振动超标"}, ensure_ascii=False)
    new_text, tokens, unresolved = rs.restore_payload_text(text, {})
    assert (new_text, tokens, unresolved) == (text, [], [])


def test_candidates_cover_both_schemes_after_migration():
    """迁移后库里只剩规范编号，历史代号（按短编号 hash）仍必须可还原。

    实测：8 份历史报告的 `设备#f6de90` = `PUMP-A`（迁移前口径）；若候选集只取库里现值
    （`PUMP-A-01`）→ 反查表无此代号 → 8/8 全部无法还原（脚本空转）。
    """
    conn = _FakeConn(candidates={"alerts": ["PUMP-A-01"]})
    cands = rs.collect_candidates(conn)
    assert {"PUMP-A-01", "PUMP-A"} <= cands                # 双口径变体

    reverse = rs.build_reverse_map(cands)
    assert reverse[_token("PUMP-A")] == "PUMP-A"           # 还原为 hash 原文，不改写历史事实
    assert reverse[_token("PUMP-A-01")] == "PUMP-A-01"


def test_collect_candidates_keeps_unknown_ids():
    """未登记编号（FAN-9）不得被映射表伪造出别名。"""
    conn = _FakeConn(candidates={"alerts": ["FAN-9"]})
    assert rs.collect_candidates(conn) == {"FAN-9"}


def test_scan_reports_plans_and_apply_updates_payload():
    """扫描产出计划；--apply 只 UPDATE payload、不动其他列、逐份 commit。"""
    token = _token("PUMP-A")
    conn = _FakeConn(
        candidates={"alerts": ["PUMP-A", "PUMP-B"], "work_orders": []},
        reports=[
            ("RPT-clean", json.dumps({"diagnosis": "PUMP-A 正常"}, ensure_ascii=False)),
            ("RPT-masked", json.dumps({"diagnosis": f"{token} 振动超标"},
                                      ensure_ascii=False)),
            ("RPT-unknown", json.dumps({"diagnosis": "设备#deadbe 神秘代号"},
                                       ensure_ascii=False)),
        ],
    )
    reverse = rs.build_reverse_map(rs.collect_candidates(conn))
    plans = rs.scan_reports(conn, reverse)

    assert [p["report_id"] for p in plans] == ["RPT-masked", "RPT-unknown"]
    masked = plans[0]
    assert masked["mapping"] == {token: "PUMP-A"} and masked["changed"] is True
    assert plans[1]["changed"] is False and plans[1]["unresolved"] == ["设备#deadbe"]

    rs.apply_plan(conn, masked)
    assert len(conn.updates) == 1 and conn.commits == 1
    new_payload, report_id = conn.updates[0]
    assert report_id == "RPT-masked"
    assert json.loads(new_payload)["diagnosis"] == "PUMP-A 振动超标"


def test_main_dry_run_writes_nothing(monkeypatch):
    """默认 dry-run：只打印计划，零 UPDATE、零 commit。"""
    conn = _FakeConn(candidates={"alerts": ["PUMP-A"]},
                     reports=[("RPT-x", json.dumps({"d": _token("PUMP-A")},
                                                   ensure_ascii=False))])
    monkeypatch.setattr(rs, "_connect", lambda: conn)
    assert rs.main([]) == 0
    assert conn.updates == [] and conn.commits == 0 and conn.closed is True


def test_main_apply_and_unresolved_exit_code(monkeypatch):
    """--apply 落库；存在无法映射代号 → 退出码 1（需人工）。"""
    conn = _FakeConn(candidates={"alerts": ["PUMP-A"]},
                     reports=[("RPT-x", json.dumps({"d": f"{_token('PUMP-A')} 设备#deadbe"},
                                                   ensure_ascii=False))])
    monkeypatch.setattr(rs, "_connect", lambda: conn)
    assert rs.main(["--apply"]) == 1
    assert len(conn.updates) == 1
    assert "PUMP-A" in conn.updates[0][0] and "设备#deadbe" in conn.updates[0][0]


def test_main_pg_unreachable_returns_2(monkeypatch):
    """PG 不可达（当前离线环境即此态）→ 退出码 2，不谎称"无待清理"。"""
    import psycopg

    def _boom(*args, **kwargs):
        raise psycopg.OperationalError("connection timeout expired")

    monkeypatch.setattr(psycopg, "connect", _boom)
    assert rs.main([]) == 2


# ---------------------------------------------------------------- B. 语料规模体检

@pytest.fixture
def fake_corpus(tmp_path: Path, monkeypatch) -> Path:
    """假语料：3 子块 / 2 文档，含"轴承/振动/温度"，刻意不含"齿轮/密封"。"""
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    rows = [
        {"id": "c1", "doc_id": "d1", "doc_type": "manual", "token_count": 10,
         "text": "离心泵轴承振动异常处理，PUMP-A-01 温度升高"},
        {"id": "c2", "doc_id": "d1", "doc_type": "manual", "token_count": 8,
         "text": "轴承磨损更换标准 MOTOR-1 电流超限"},
        {"id": "c3", "doc_id": "d2", "doc_type": "work_order", "token_count": 5,
         "text": "PUMP-B-01 泄漏故障工单记录"},
    ]
    (chunks / "chunks_v1.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    (chunks / "parents_v1.jsonl").write_text(
        json.dumps({"id": "p1", "doc_id": "d1"}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "blobs").mkdir()
    (tmp_path / "parsed").mkdir()
    monkeypatch.setattr(cs, "CHUNKS_PATH", chunks / "chunks_v1.jsonl")
    monkeypatch.setattr(cs, "PARENTS_PATH", chunks / "parents_v1.jsonl")
    monkeypatch.setattr(cs, "BLOBS_DIR", tmp_path / "blobs")
    monkeypatch.setattr(cs, "PARSED_DIR", tmp_path / "parsed")
    monkeypatch.setattr(cs, "SCHEMA_PATH", tmp_path / "absent.json")   # 只用内置词表
    return tmp_path


def test_corpus_stats_counts_and_blind_spots(fake_corpus, monkeypatch):
    import psycopg

    # 本用例断言"离线不假装在线"，必须显式断掉 PG（否则本机有库时结果随环境漂移）
    def _boom(*args, **kwargs):
        raise psycopg.OperationalError("refused")
    monkeypatch.setattr(psycopg, "connect", _boom)

    st = cs.corpus_stats()
    assert st["chunks"] == 3 and st["parents"] == 1 and st["docs"] == 2
    assert st["tokens"] == 23
    assert st["doc_types"] == {"manual": 2, "work_order": 1}
    assert st["keyword_hits"]["轴承"] == 2
    assert st["keyword_hits"]["振动"] == 1
    assert "PUMP-A-01" in st["models"] and "MOTOR-1" in st["models"]
    assert st["model_families"]["PUMP"] == 2
    # 刻意未覆盖的词进盲区（检索必挂的问句）
    assert "齿轮" in st["blind_keywords"] and "密封" in st["blind_keywords"]
    assert st["online"]["pg_doc_chunks"] == "skipped"     # 离线环境不假装在线


def test_corpus_stats_skips_online_when_pg_unreachable(monkeypatch):
    import psycopg

    def _boom(*args, **kwargs):
        raise psycopg.OperationalError("refused")

    monkeypatch.setattr(psycopg, "connect", _boom)
    out = cs._online_counts()
    assert out["milvus"] == "skipped" and out["pg_doc_chunks"] == "skipped"


def test_render_markdown_lists_blind_section(fake_corpus):
    md = cs._render_markdown(cs.corpus_stats())
    assert "## 盲区（零命中 = 检索必挂的问句）" in md
    assert "| 轴承 | 2 |" in md
    assert "- 齿轮" in md


def test_main_strict_exit_code_and_write(fake_corpus, tmp_path):
    out = tmp_path / "sub" / "corpus.md"
    assert cs.main(["--strict", "--out", str(out)]) == 1     # 有盲区 → strict 失败
    assert out.exists() and "语料规模体检" in out.read_text(encoding="utf-8")
