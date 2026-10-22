"""离线回归锁：A/C 类检索扩展（`configs/query_synonyms.json` + `query_rewrite.expand_keywords`）。

对应盲区：`reports/p1-corpus-stats-2026-10-22.md` 的 15 词盲区里，8 个是**用词差异**
（语料有事实但不含该词）。本轮只做纯追加扩展，不扩语料、不动语义向量。

钉死的约束：
  1. **只追加**：原有 keywords 一项不少、顺序不变，`semantic` 恒等于原问（否则检索基线平移）；
  2. **不伪造**：语料也没有的词（齿轮/阀门/喘振）不得凭空生成"近义词"；
  3. **可回退**：`AUSCULT_QUERY_EXPAND=0` 完全恢复旧行为；
  4. 配置缺失/损坏 → 静默退化，不抛异常中断检索。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import query_rewrite as qr  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch):
    """每个用例重置词表缓存与开关，避免跨用例污染（缓存是模块级全局）。"""
    monkeypatch.setattr(qr, "_synonym_cache", None)
    monkeypatch.delenv(qr.EXPAND_ENV, raising=False)
    yield
    qr._synonym_cache = None


def test_synonyms_file_is_valid_and_evidence_backed():
    """词表必须可解析，且只包含语料里有命中实证的近义词（不配置齿轮/阀门/喘振）。"""
    cfg = json.loads((PROJECT_ROOT / "configs" / "query_synonyms.json").read_text(encoding="utf-8"))
    syn = cfg["synonyms"]
    assert syn["汽蚀"] == ["气蚀"]
    assert syn["异响"] == ["噪声"]
    for absent in ("齿轮", "阀门", "喘振", "裂纹", "疲劳"):
        assert absent not in syn, f"{absent} 在语料中无命中，不应配置成已解决的近义词"


def test_expand_appends_synonyms_without_touching_original_keywords():
    """纯追加：原词一个不少、顺序不变；扩展词进 keywords 并进审计报告。"""
    out = qr.expand_keywords("离心泵汽蚀的原因", ["离心泵"])
    assert out["keywords"][:1] == ["离心泵"]                 # 原有词原样在前
    assert "气蚀" in out["keywords"]
    assert out["report"]["enabled"] is True
    assert out["report"]["synonyms"] == {"汽蚀": ["气蚀"]}


def test_expand_covers_the_documented_blind_spots():
    """体检报告里的 A 类盲区逐个验证（语料侧命中数见报告）。"""
    cases = {
        "泵体异响怎么判断": "噪声",
        "温度趋势如何看": "漂移",
        "振动波形特征": "频谱",
        "油液多久更换": "润滑油",
        "振动烈度阈值是多少": "警戒值",
        "轴承剥落是什么表现": "磨损",
    }
    for question, expected in cases.items():
        out = qr.expand_keywords(question, [])
        assert expected in out["keywords"], f"{question} 未扩展到 {expected}"


def test_expand_does_not_fabricate_missing_domain_terms():
    """语料真缺失的域（齿轮/阀门/喘振）不得产生任何扩展——避免假装已解决。"""
    for question in ("齿轮箱如何诊断", "阀门卡涩原因", "离心泵喘振怎么处理"):
        out = qr.expand_keywords(question, [])
        assert out["report"]["synonyms"] == {}, question
        assert out["keywords"] == []


def test_device_id_canonical_expands_to_legacy():
    """C 类：PUMP-A-01 → 追加短编号 PUMP-A（语料/图谱仍是短编号）。"""
    out = qr.expand_keywords("PUMP-A-01 振动超标原因", ["振动"])
    assert "PUMP-A" in out["keywords"]
    assert out["report"]["device_variants"] == ["PUMP-A"]
    # 未登记编号不伪造
    other = qr.expand_keywords("FAN-9-07 异常", [])
    assert other["report"]["device_variants"] == []


def test_expand_switch_off_restores_old_behavior(monkeypatch):
    """`AUSCULT_QUERY_EXPAND=0` → 零扩展（只为复现 2026-10-22 之前基线）。"""
    monkeypatch.setenv(qr.EXPAND_ENV, "0")
    out = qr.expand_keywords("离心泵汽蚀 PUMP-A-01", ["离心泵"])
    assert out["keywords"] == ["离心泵"]
    assert out["report"]["enabled"] is False

    rw = qr.rewrite_rules("离心泵汽蚀 PUMP-A-01 的原因")
    assert rw["semantic"] == "离心泵汽蚀 PUMP-A-01 的原因"   # semantic 恒等于原问
    assert "气蚀" not in rw["keywords"]


def test_rewrite_rules_keeps_semantic_unchanged_by_default():
    """默认开启时 semantic 仍必须是原问——改 semantic 会让 dense/rerank 打分平移。"""
    q = "离心泵汽蚀异响的阈值"
    rw = qr.rewrite_rules(q)
    assert rw["semantic"] == q
    assert "气蚀" in rw["keywords"] and "噪声" in rw["keywords"]
    assert rw["expansion"]["enabled"] is True


def test_missing_config_degrades_silently(tmp_path, monkeypatch):
    """配置缺失 → 空词表、原样返回（检索不因配置文件丢失而中断）。"""
    out = qr.expand_keywords("汽蚀", ["泵"], path=tmp_path / "absent.json")
    assert out["keywords"] == ["泵"]
    assert out["report"]["synonyms"] == {}
