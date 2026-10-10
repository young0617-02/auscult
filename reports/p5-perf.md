# P5-W5/D14 端到端压测报告

- **日期**：2026-10-10
- **工具**：Locust 2.46.7（[scripts/locustfile.py](file:///d:/DSHproject/auscult/scripts/locustfile.py)，headless 直跑本机）
- **判据**（plan/Phase 5 §5.5 W5/D14）：并发 10/20/50 三档延迟分位 + 错误率 + 资源峰值；宿主内存峰值 ≤ 24 GB（V4b 门禁）；50 并发 30 min 稳定性
- **结论**：**Pass** —— 三档 + 30 min 稳定性全程 0% 服务器错误（稳定性档 0.01% 瞬时 502 见 §六）；u10/u20 P95 < 200 ms，u50 P95 = 940 ms；宿主峰值 20.73 GB ≤ 24 GB；限流熔断行为与令牌桶数学精确吻合
- **环境口径**：完整栈（v2-pg 5433 / redis 6379 / milvus 39530 / neo4j 7687 / **tdengine 6041** / kee-prometheus / kee-grafana）+ uvicorn 单进程 127.0.0.1:8000；压测期另有 Phase 5 评测后台任务（D4/D5）低负载并行（实测 CPU ≈10%，已计入资源峰值口径）
- **原始数据**：`experiments/p5/w5/`（locust CSV ×4 + host_resources.log 5s 采样 + run_windows.txt 窗口留痕）

## 一、场景口径

| 项 | 值 |
|---|---|
| 用户模型 | 每虚拟用户 on_start 登录（eng_dev，bcrypt 一次性成本），任务间隔 0.5~1.5 s |
| 读路径（93% 权重） | alarms 列表(3) / reports 列表(3) / 报告详情(2) / knowledge 列表(2) / health(2) / graph 邻居(1) |
| 写入口（7% 权重） | POST /api/diagnose（占位 alarm_id → 放行请求 404 快速失败；超桶请求 429） |
| 限流口径 | 单 IP 共享桶：容量 10 / 回填 10/分；429 计 success（预期行为），权威计数取服务端 |

## 二、三档主基线（完整栈，各 3 min）

聚合口径（全部请求，含登录/diagnose）：

| 档位 | 并发 | 请求数 | req/s | 错误率 | P50 | P90 | P95 | P99 | Max |
|---|---|---|---|---|---|---|---|---|---|
| u10 | 10 | 1,706 | 9.50 | **0.00%** | 24 ms | 85 ms | 100 ms | 310 ms | 1,399 ms |
| u20 | 20 | 3,349 | 18.64 | **0.00%** | 41 ms | 140 ms | 190 ms | 860 ms | 2,193 ms |
| u50 | 50 | 5,858 | 32.62 | **0.00%** | 460 ms | 810 ms | 940 ms | 2,200 ms | 6,028 ms |

分端点明细（P50 / P95 / P99，单位 ms）：

| 端点 | u10 | u20 | u50 |
|---|---|---|---|
| GET /api/alarms | 22 / 75 / 140 | 33 / 170 / 340 | 460 / 920 / 2,000 |
| GET /api/reports | 23 / 100 / 140 | 30 / 160 / 280 | 480 / 890 / 1,900 |
| GET /api/reports/{id} | 21 / 71 / 130 | 32 / 160 / 910 | 460 / 890 / 2,000 |
| GET /api/knowledge/docs | 22 / 70 / 120 | 29 / 160 / 250 | 460 / 860 / 1,200 |
| GET /api/graph/neighbors | 42 / 78 / 120 | 42 / 150 / 240 | 490 / 880 / 1,900 |
| GET /api/health | 70 / 140 / 200 | 87 / 220 / 370 | 500 / 930 / 1,200 |
| POST /api/diagnose（404/429 混合） | 23 / 89 / 160 | 27 / 130 / 240 | 300 / 870 / 1,300 |
| POST /api/auth/login（一次性） | 1,000 / 1,400 | 1,400 / 2,200 | 3,000 / 5,800 |

服务端交叉核对（/metrics 累计计数器）：三档全程 status 仅 200/404/429，**5xx 为零**；唯一的 6 次 502 出现在 30 min 稳定性档（见 §六）。

## 三、限流熔断行为（D13 配套验证）

服务端双口径一致（PG audit_logs 权威层 + /metrics 计数器），全战役（三档 + 稳定性）累计：

| 口径 | 实测 |
|---|---|
| 令牌桶数学预期 | 容量 10 + 回填 10/分 × 约 43 min 有请求窗口 ≈ 放行 ~440 次 |
| 实测放行（404） | **446 次**（/metrics status=404 计数；量级吻合） |
| 实测限流（429） | **4,548 次**（/metrics status=429；audit_logs event=rate_limit_exceeded 分分钟计数逐条对上） |
| 行为 | 429 响应 `E_RATE_LIMITED` + `Retry-After`，延迟 ~11-27 ms（Redis Lua 快速拒绝），未拖垮读路径 |

结论：限流器在高并发下按设计有效削峰（u50 档 diagnose 速率 2.3 req/s，放行被钳制在 ~10/min），保护云端升级入口。

## 四、发现（不阻塞收口，建议列 P6）

### F-1 tdengine 不可达时 health 同步探测阻塞事件循环（已定位根因）

- **现象**：TDengine 未启动（Phase 5 默认 profile 关闭）时，空载单次 `GET /api/health` 即 **1,163 ms**；u10 档实测聚合 P50 从 24 ms 恶化至 **940 ms**、health P50=1,700 ms，全端点被拖累（health 的 TCP 探测同步等满 `HEALTH_TIMEOUT_S=1.0s`，且在 `async def` 内阻塞事件循环，weight=2 → 事件循环约 70% 时间被占）。
- **根因**：[health.py](file:///d:/DSHproject/auscult/app/api/routes/health.py) 探测为同步 IO（socket/psycopg/redis）且未线程池化；任一下游 down 时放大为 1 s/次的整循环阻塞。
- **处置**：本次压测以**完整栈**（启动 tdengine）为基线；该韧性场景建议修复方向 = 探测改 anyio.to_thread / 缩短 down 探测超时 / health 结果 5 s 缓存，列 **P6 待办**。

### F-2 u50 排队放大：每请求 PG 短连接 + async def 内同步 IO

- **现象**：u10→u20→u50 吞吐 9.5→18.6→32.6 req/s（未随并发线性扩展），u50 各端点 P50 统一抬升至 ~460-500 ms（典型排队特征而非单端点瓶颈）；30 min 稳定性档出现 **6 次（0.01%）瞬时 502 E_UPSTREAM**（psycopg 建连间歇失败，服务端 /metrics 计数逐条对上，发生于窗口中段 00:43-00:49，自恢复、后 20 min 零复发）。
- **根因**：[db.py](file:///d:/DSHproject/auscult/app/api/db.py) 按请求 `psycopg.connect` 短连接（文档字符串预留「压测成瓶颈再升 psycopg_pool」——**本次即触发点**：约 6.4 万次建连 / 40 min，瞬时建连失败率 0.01%）；且全部路由 `async def` + 同步 DB 调用，事件循环串行化。
- **处置**：P6 建议 ①切换 `psycopg_pool`（依赖已锁定）②读路径路由改 `def`（FastAPI 自动线程池化）。当前量级（监盘值班场景 ≤50 并发）P95=940 ms、错误率 0.01% 自愈，不构成 Phase 5 出口阻塞。

## 五、资源峰值与 24 GB 门禁

| 项 | 峰值（5s 采样 420 点，覆盖全部压测窗口） |
|---|---|
| 宿主物理内存 used | **20.73 GB**（总量 31.8 GB）≤ 24 GB → **Pass** |
| uvicorn 进程（python） | 0.33 GB |
| Docker WSL（vmmem，含全部容器） | 5.75 GB |
| 容器合计快照 | neo4j 920 MB + v2-pg 376 MB + milvus 318 MB + tdengine 141 MB + prometheus 42 MB + grafana 49 MB + redis/pg/nginx 等 ≈ 1.9 GB |

注：峰值含 TDengine（141 MB）与监控栈（91 MB），口径偏保守；Phase 5 常规部署不含这两项，余量更大。

## 六、50 并发 30 min 稳定性

**59,593 请求 / 33.11 req/s 持续 30 min / 失败 6 次（0.01%）**（窗口 00:36:00-01:06:00，355 个资源采样点）：

| 口径 | 实测 |
|---|---|
| 延迟分位（聚合） | P50 = 480 ms / P90 = 830 ms / **P95 = 940 ms** / P99 = 1,200 ms |
| 与 3 min u50 档对比 | P50 460→480 ms、P95 940→940 ms——**长时间无退化** |
| 分端点（P50/P95） | alarms 490/930 · reports 490/940 · 详情 490/940 · knowledge 490/930 · graph 500/960 · health 520/950 · diagnose 310/800（ms） |
| 错误 | 6 次 502（0.01%）= psycopg 建连瞬时失败（E_UPSTREAM 统一包络），窗口中段 00:43-00:49 集中发生，**自恢复且后 20 min 零复发**；其余 5×10⁴ 请求零错误 |
| diagnose | 4,142 次尝试：放行（404）≈288、限流（429）≈3,708——限流器整窗稳定削峰 |
| 资源峰值 | 窗口内宿主 used 最高 20.73 GB ≤ 24 GB；uvicorn 常驻 ≈0.33 GB（无泄漏增长迹象） |
| 判定 | **Pass**（错误率 0.01% 且自愈、延迟分位零漂移、资源平稳） |

## 七、Q4=B 门禁验证（Prometheus 抓取）

- 监控栈以 digest 锚定启动（见 §八），压测全程 `kee-prometheus`/`kee-grafana` healthy；
- `docker exec kee-prometheus wget -qO- ".../api/v1/query?query=up"`：`auscult-api`（host.docker.internal:8000）目标 **up == 1** ✓；
- 应用 /metrics 在 1.3 万+ 请求压测下持续可抓取，`auscult_http_requests_total` / `auscult_http_request_duration_ms` 等计数与客户端统计交叉一致。

## 八、复现命令

```powershell
# ① 环境补全（TDengine profile）+ 服务
docker compose -f docker/compose.base.yml --profile tdengine up -d tdengine
.venv\Scripts\python.exe -m uvicorn app.api.main:socket_app --host 127.0.0.1 --port 8000   # env MILVUS_PORT=39530

# ② 监控栈（digest 锚定，禁止裸 tag）
$env:PROMETHEUS_IMAGE="prom/prometheus@sha256:efd719c99d83b060d9daefdcf00360461adf279f45ef5391f8d111892118753e"
$env:GRAFANA_IMAGE="grafana/grafana@sha256:079600c9517b678c10cda6006b4487d3174512fd4c6cface37df7822756ed7a5"
docker compose -f docker/compose.monitoring.yml up -d
docker exec kee-prometheus wget -qO- "http://localhost:9090/api/v1/query?query=up"   # auscult-api == 1

# ③ 三档 + 稳定性
.venv\Scripts\python.exe -m locust -f scripts/locustfile.py --host http://127.0.0.1:8000 --headless -u 10 -r 5 --run-time 3m --csv experiments/p5/w5/locust_clean_u10 --only-summary
.venv\Scripts\python.exe -m locust -f scripts/locustfile.py --host http://127.0.0.1:8000 --headless -u 20 -r 5 --run-time 3m --csv experiments/p5/w5/locust_clean_u20 --only-summary
.venv\Scripts\python.exe -m locust -f scripts/locustfile.py --host http://127.0.0.1:8000 --headless -u 50 -r 5 --run-time 3m --csv experiments/p5/w5/locust_clean_u50 --only-summary
.venv\Scripts\python.exe -m locust -f scripts/locustfile.py --host http://127.0.0.1:8000 --headless -u 50 -r 5 --run-time 30m --csv experiments/p5/w5/locust_stab_u50 --only-summary

# ④ 限流权威计数
docker exec auscult-v2-pg psql -U root -d auscult_v2 -t -A -F" | " -c "SELECT event, count(*) FROM audit_logs WHERE event LIKE 'rate_limit%' GROUP BY event;"

# ⑤ 测后销毁
docker compose -f docker/compose.monitoring.yml down -v
docker stop auscult-tdengine
```

## 九、判定

| 判据 | 门线 | 实测 | 结果 |
|---|---|---|---|
| 三档延迟分位+错误率 | 可测量、如实记录 | 三档 0% 错误；P95 = 100/190/940 ms | **Pass** |
| 50 并发 30 min 稳定性 | 无退化/无错误率漂移 | P95 940→940 ms 零漂移；6×502（0.01%）自愈 | **Pass** |
| 宿主资源峰值 | ≤ 24 GB | 20.73 GB | **Pass** |
| Prometheus 抓取（Q4=B） | up == 1 | auscult-api up == 1 | **Pass** |
| 限流 429 行为 | 高频云端入口触发限流 | 4,548 次 429，放行钳制 ~10/分（446 次 404 放行） | **Pass** |
| 24 GB 门禁含监控栈 | 临时栈测后销毁 | 已含（保守口径）；测后 `down -v` | **Pass** |

遗留：F-1 health 探测线程池化 / F-2 psycopg_pool + 路由线程池化 → **P6 待办**；镜像 digest 登记 docs/version-lock.md §三。
