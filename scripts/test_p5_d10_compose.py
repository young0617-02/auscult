# -*- coding: utf-8 -*-
"""D10 Compose 硬化自测（M5.2 收口项）

验证 docker/compose.base.yml 四道纪律：
1. 全服务 healthcheck（8/8，含 profile tdengine）
2. milvus depends_on 使用 service_healthy 长格式（etcd/minio 就绪后再启）
3. 全服务资源限额：memory + cpus 双限（deploy.resources.limits）
4. 镜像全部锚定 digest（禁裸 tag 纪律）

运行: python scripts/test_p5_d10_compose.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker" / "compose.base.yml"

results: list[tuple[bool, str]] = []


def check(ok: bool, name: str) -> None:
    results.append((ok, name))


def main() -> int:
    raw = COMPOSE.read_text(encoding="utf-8")
    doc = yaml.safe_load(raw)
    services: dict = doc.get("services", {})

    # 1) 全服务 healthcheck
    no_hc = [name for name, svc in services.items() if "healthcheck" not in svc]
    check(not no_hc, f"1. 全服务 healthcheck：{len(services)} 个服务"
                     f"{'，缺: ' + ', '.join(no_hc) if no_hc else ' ✓'}")

    # 2) milvus depends_on 长格式 + service_healthy
    deps = services["milvus"].get("depends_on", {})
    ok2 = (isinstance(deps, dict)
           and deps.get("etcd", {}).get("condition") == "service_healthy"
           and deps.get("minio", {}).get("condition") == "service_healthy")
    check(ok2, "2. milvus depends_on: etcd/minio 均 condition=service_healthy")

    # 3) 全服务 memory + cpus 双限额
    missing: list[str] = []
    for name, svc in services.items():
        limits = (svc.get("deploy", {}).get("resources", {})
                  .get("limits", {})) or {}
        if "memory" not in limits or "cpus" not in limits:
            missing.append(f"{name}(mem={'memory' in limits},cpu={'cpus' in limits})")
    check(not missing, f"3. 全服务 memory+cpus 双限：{len(services)}/{len(services)}"
                       f"{'，缺: ' + '; '.join(missing) if missing else ' ✓'}")

    # 3b) 内存限额合计 ≤ 24GB 门禁线（容器侧）
    total_mb = 0.0
    for svc in services.values():
        mem = (svc.get("deploy", {}).get("resources", {})
               .get("limits", {}).get("memory", "")) or ""
        mult = {"g": 1024.0, "m": 1.0}
        if mem and mem[-1].lower() in mult:
            total_mb += float(mem[:-1]) * mult[mem[-1].lower()]
    check(total_mb <= 24 * 1024, f"3b. 容器内存限额合计 {total_mb / 1024:.2f}g ≤ 24g 门禁线")

    # 4) 镜像锚定 digest
    bare = [name for name, svc in services.items()
            if "@sha256:" not in svc.get("image", "")]
    check(not bare, f"4. 镜像全部锚定 digest{'，裸 tag: ' + ', '.join(bare) if bare else ' ✓'}")

    passed = sum(1 for ok, _ in results if ok)
    for ok, name in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n结果: {passed}/{len(results)} PASS")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
