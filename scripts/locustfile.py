"""Locust 压测脚本（P5-W5/D14 · reports/p5-perf.md 数据源）

场景口径（读路径为主 + diagnose 低频）：
- 登录：on_start 时 POST /api/auth/login（eng_dev），JWT 8h 内免重登
- 读路径（占 ~93% 权重）：alarms / reports 列表+详情 / knowledge 列表 / graph 邻居 / health
- 写入口（占 ~7%）：POST /api/diagnose（alarm_id=不存在的占位 ID）
  · 预期行为：先扣令牌（限流先于鉴权）→ 前 10 次及每分钟回填的少量请求放行（404 快速失败），
    其余 429 E_RATE_LIMITED（单 IP 共享桶，令牌桶容量 10 / 回填 10/分）
  · 429 属预期结果，计为 success；429 次数以服务端 PG audit_logs（event=rate_limit_exceeded）
    时间窗计数为准（权威口径），不依赖客户端计数

运行方式（headless，Windows 本机）：
  .venv\\Scripts\\python.exe -m locust -f scripts/locustfile.py \\
      --host http://127.0.0.1:8000 --headless -u 10 -r 5 --run-time 3m \\
      --csv experiments/p5/w5/locust_u10 --only-summary
三档：u10 / u20 / u50 各 3m；稳定性：u50 30m。

凭据可用环境变量覆盖：LOCUST_USER / LOCUST_PASS（默认开发种子账号）。
"""

from __future__ import annotations

import os
import random

from locust import HttpUser, between, task

_USERNAME = os.environ.get("LOCUST_USER", "eng_dev")
_PASSWORD = os.environ.get("LOCUST_PASS", "Auscult#Dev2026")

# 图查询热点实体（Neo4j 实测存在的枢纽概念；hops=2 走满受控关系白名单）
_GRAPH_ENTITY = os.environ.get("LOCUST_GRAPH_ENTITY", "振动烈度")


class AuscultUser(HttpUser):
    wait_time = between(0.5, 1.5)   # 每用户任务间隔 0.5~1.5s（u50 时整体 ≈40-60 req/s）

    def on_start(self) -> None:
        """登录取 token；预取一页 report_id 供详情任务随机抽取。"""
        with self.client.post(
            "/api/auth/login",
            json={"username": _USERNAME, "password": _PASSWORD},
            name="POST /api/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"登录失败 {resp.status_code}")
                self.token = None
                self.report_ids: list[str] = []
                return
            self.token = resp.json()["data"]["access_token"]
            resp.success()
        self.client.headers.update({"Authorization": f"Bearer {self.token}"})

        with self.client.get(
            "/api/reports?page=1&size=20",
            name="GET /api/reports(on_start 预取)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                self.report_ids = [
                    it["report_id"] for it in resp.json()["data"]["items"]] or [""]
                resp.success()
            else:
                self.report_ids = [""]
                resp.failure(f"预取报告列表失败 {resp.status_code}")

    # ------------------------------------------------------------------ 读路径

    @task(3)
    def list_alarms(self) -> None:
        self.client.get("/api/alarms?page=1&size=20", name="GET /api/alarms")

    @task(3)
    def list_reports(self) -> None:
        self.client.get("/api/reports?page=1&size=20", name="GET /api/reports")

    @task(2)
    def report_detail(self) -> None:
        rid = random.choice(self.report_ids)
        if not rid:
            return
        self.client.get(f"/api/reports/{rid}", name="GET /api/reports/{id}")

    @task(2)
    def knowledge_docs(self) -> None:
        self.client.get("/api/knowledge/docs?page=1&size=20",
                        name="GET /api/knowledge/docs")

    @task(1)
    def graph_neighbors(self) -> None:
        self.client.get(
            f"/api/graph/neighbors?entity={_GRAPH_ENTITY}&hops=2",
            name="GET /api/graph/neighbors")

    @task(2)
    def health(self) -> None:
        self.client.get("/api/health", name="GET /api/health")

    # ------------------------------------------------------------ diagnose（限流演示位）

    @task(1)
    def diagnose_rate_limit(self) -> None:
        """POST /api/diagnose（占位 alarm_id）。

        预期：404（放行，快速失败）或 429（限流），均计 success；
        500/400 等意外状态才计 failure。429 权威计数在服务端 audit_logs。
        """
        with self.client.post(
            "/api/diagnose",
            json={"alarm_id": "LOCUST-NONEXISTENT-0000"},
            name="POST /api/diagnose",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404, 429):
                resp.success()
            else:
                resp.failure(f"意外状态 {resp.status_code}: {resp.text[:120]}")
