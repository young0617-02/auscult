# -*- coding: utf-8 -*-
"""P5-W2/D7 监控配置自测（M5.2）

验证项：
  1. prometheus.yml 可解析 + 抓取目标正确
  2. alerts.yml 六条告警规则与 plan §5.2.2 对齐
  3. Grafana provisioning（datasource uid / dashboard 路径）
  4. dashboard JSON 可解析 + 12 panel 全部指向 prometheus 数据源
  5. compose.monitoring.yml 语法（digest 必填变量防裸 tag）
  6. 面板 PromQL 引用的 auscult_* 指标均已在 prom_metrics.py 注册

运行：.venv\\Scripts\\python.exe scripts\\test_p5_d07_monitoring.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MON = PROJECT_ROOT / "monitoring"

EXPECTED_ALERTS = {"RedisMemoryHigh", "GpuMemoryHigh", "ReconcileDiff",
                   "ReviewTimeout4h", "CloudBudgetHigh", "CheckpointGrowthAbnormal"}


def test_prometheus_yml() -> None:
    p = yaml.safe_load((MON / "prometheus.yml").read_text(encoding="utf-8"))
    sc = {c["job_name"]: c for c in p["scrape_configs"]}
    api = sc["auscult-api"]
    assert api["metrics_path"] == "/metrics"
    assert api["static_configs"][0]["targets"] == ["host.docker.internal:8000"]
    assert "alerts.yml" in p["rule_files"][0]
    print("[PASS] prometheus.yml（target=host.docker.internal:8000，rule_files 含 alerts.yml）")


def test_alerts_yml() -> None:
    a = yaml.safe_load((MON / "alerts.yml").read_text(encoding="utf-8"))
    rules = a["groups"][0]["rules"]
    names = {r["alert"] for r in rules}
    assert names == EXPECTED_ALERTS, f"规则集不符: {names ^ EXPECTED_ALERTS}"
    for r in rules:
        assert r.get("expr") and r.get("labels", {}).get("severity"), f"规则缺 expr/severity: {r['alert']}"
    sev = {r["alert"]: r["labels"]["severity"] for r in rules}
    assert sev["RedisMemoryHigh"] == "critical" and sev["ReconcileDiff"] == "critical"
    assert sev["GpuMemoryHigh"] == "warning" and sev["CloudBudgetHigh"] == "warning"
    print(f"[PASS] alerts.yml 六条规则（Critical×2 / Warning×4）: {sorted(names)}")


def test_grafana_provisioning() -> None:
    d = yaml.safe_load((MON / "grafana/provisioning/datasources/prometheus.yml")
                       .read_text(encoding="utf-8"))
    assert d["datasources"][0]["uid"] == "prometheus"
    assert d["datasources"][0]["url"] == "http://prometheus:9090"
    db = yaml.safe_load((MON / "grafana/provisioning/dashboards/dashboards.yml")
                        .read_text(encoding="utf-8"))
    assert db["providers"][0]["options"]["path"] == "/var/lib/grafana/dashboards"
    print("[PASS] Grafana provisioning（uid=prometheus / dashboards 路径）")


def test_dashboard_json() -> None:
    j = json.loads((MON / "grafana/dashboards/auscult-overview.json").read_text(encoding="utf-8"))
    assert j["uid"] == "auscult-overview"
    assert len(j["panels"]) == 12
    for pn in j["panels"]:
        assert pn["datasource"]["uid"] == "prometheus", f"panel {pn['id']} 数据源错误"
        assert pn.get("expr") is None or pn["targets"], f"panel {pn['id']} 无 targets"
    print(f"[PASS] dashboard JSON（uid=auscult-overview，{len(j['panels'])} panels）")


def test_dashboard_metrics_registered() -> None:
    """面板/告警 PromQL 引用的 auscult_* 指标必须在 prom_metrics.py 注册。"""
    src = (PROJECT_ROOT / "app/observability/prom_metrics.py").read_text(encoding="utf-8")
    registered = set(re.findall(r'"(auscult_[a-z_]+)"', src))
    j = json.loads((MON / "grafana/dashboards/auscult-overview.json").read_text(encoding="utf-8"))
    used: set[str] = set()
    for pn in j["panels"]:
        for t in pn["targets"]:
            used |= set(re.findall(r"auscult_[a-z_]+", t["expr"]))
    alerts = (MON / "alerts.yml").read_text(encoding="utf-8")
    used |= {m for m in re.findall(r"auscult_[a-z_]+", alerts) if m.startswith("auscult_")}
    missing = {m[:-7] if m.endswith("_bucket") else m for m in used if
               (m[:-7] if m.endswith("_bucket") else m) not in registered}
    assert not missing, f"PromQL 引用了未注册指标: {missing}"
    print(f"[PASS] PromQL 指标引用闭环（{len(used)} 个 auscult_* 均已注册）")


def test_compose_monitoring() -> None:
    import os   # noqa: PLC0415
    env = os.environ.copy()
    env["PROMETHEUS_IMAGE"] = "prom/prometheus@sha256:" + "0" * 64
    env["GRAFANA_IMAGE"] = "grafana/grafana@sha256:" + "0" * 64
    r = subprocess.run(
        ["docker", "compose", "-f", "docker/compose.monitoring.yml", "config", "--quiet"],
        capture_output=True, text=True, cwd=PROJECT_ROOT, env=env,
    )
    assert r.returncode == 0, f"compose config 失败: {r.stderr[:300]}"
    raw = (PROJECT_ROOT / "docker/compose.monitoring.yml").read_text(encoding="utf-8")
    assert ':?须以' in raw, "digest 必填占位（:?）缺失——裸 tag 防线"
    assert "sha256:<digest>" in raw
    print("[PASS] compose.monitoring.yml 语法有效 + digest 必填变量防裸 tag")


def main() -> int:
    checks = [
        ("prometheus.yml", test_prometheus_yml),
        ("alerts.yml", test_alerts_yml),
        ("provisioning", test_grafana_provisioning),
        ("dashboard JSON", test_dashboard_json),
        ("指标引用闭环", test_dashboard_metrics_registered),
        ("compose 语法", test_compose_monitoring),
    ]
    failed: list[str] = []
    for name, fn in checks:
        try:
            fn()
        except Exception as exc:   # noqa: BLE001
            failed.append(name)
            print(f"[FAIL] {name}: {exc}")
    print(f"\n===== D7 自测 {len(checks) - len(failed)}/{len(checks)} PASS =====")
    if failed:
        print("  失败项:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
