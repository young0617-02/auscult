# ADR-009：Nginx 仅在生产化阶段引入（开发期直连 8000/3000）

> **层级**：项目级长期有效（ADR）｜ **对应里程碑**：`M6.1`（Phase 6 文档收口 · D5 产出）｜ **状态**：🟢 **活动**｜ **最近更新**：2026-10-10

---

## 一、状态

**Accepted**（2026-10-10 收敛确认）。
上游决策时点如实标注：入口网关选型与分期于 `plan/工业设备诊断 Agent.md` §3.11 定稿（2026-09-21，V5.0 定稿）；Nginx 实际引入于 Phase 4 D19（`docs/p4-handover-p5.md` §一 D19）。

## 二、背景（Context）

- 开发验证期（Phase 0–3）以内网直连为最快路径，统一入口/HTTPS/WS 透传等网关职责在单机演示下非刚需（`plan/工业设备诊断 Agent.md` §3.11 分期建议）。
- Socket.IO 实时推送依赖 WebSocket 升级：反向代理若不透传 `Upgrade`/`Connection` 头会**直接失效**，故网关引入时机与 WS 兼容性必须一并设计（同上 §3.11 职责表）。

## 三、决策（Decision）

**Nginx 仅在生产化阶段引入；开发期直连 FastAPI(:8000) / Next.js(:3000)。**

| 阶段 | 是否用 Nginx | 入口形态 | 出处 |
|---|---|---|---|
| Phase 0–3（开发验证） | ❌ 不用 | 直接 `localhost:8000` / `:3000` | `plan/工业设备诊断 Agent.md` §3.11 分期表 |
| Phase 4（前端集成） | ⚠️ 可选 | Next.js rewrite 代理 API（**实际 D19 提前落地 Nginx 单入口**，见 §3.1） | 同上；`docs/p4-handover-p5.md` §一 D19 |
| Phase 5+（演示/生产化） | ✅ 引入 | Nginx 统一入口 + HTTPS + WS | 同上 |

### 3.1 现状（已就位）

| 项 | 口径 | 出处 |
|---|---|---|
| 资产 | `docker/compose.nginx.yml` + `configs/nginx/nginx.conf` 已交付并验证（`/login` 200、`/api/health` 200 经 Nginx 链路） | `docs/p4-handover-p5.md` §一 D19 |
| 入口口径 | `http://127.0.0.1:9763`；反代 `/`→Next.js:3000、`/api`→FastAPI:8000、`/socket.io` WS 透传 | 同上；`README.md` §4.7 |
| 镜像 | `nginx:1.27-alpine`（digest 已锁） | `docs/p4-handover-p5.md` §一 D19；`docs/prj-ledger-version-lock.md` §二.2.1 |
| 常驻状态 | P5 移交时刻常驻栈含 nginx(9763) | `docs/p5-handover-p6.md` §六 |
| 职责边界 | 反向代理 ⭐5 / WS 透传 ⭐5 / SSL 终止 ⭐3 / 静态资源 ⭐3 / 限流防刷 ⭐3 / 负载均衡 ⭐（当前单实例）/ 安全响应头 ⭐2；架构位置图见上游 | `plan/工业设备诊断 Agent.md` §3.11 |

## 四、备选方案与放弃理由（Options & Rejected）

| 备选 | 处置 | 出处 |
|---|---|---|
| 开发期（Phase 0–3）即引入 Nginx | **否决**：分期表明确 Phase 0–3 不用，直连即可；提前引入徒增调试一跳与配置负担 | `plan/工业设备诊断 Agent.md` §3.11 分期表 |
| Caddy 作为统一入口 | 列为"纯内网演示可替代"项，**未采纳为标准入口**（非否决性裁决，属备选未启用） | 同上 §3.11 结论段 |
| 跳过网关直曝端口上生产 | **否决**：WS 透传/SSL/限流等职责需要 ⭐5 级组件承担；D19 已按单入口落地 | 同上 §3.11 职责表；`docs/p4-handover-p5.md` §一 D19 |

## 五、后果（Consequences）

| 类型 | 内容 |
|---|---|
| ✅ 正面 | 开发期少一跳、直连调试；生产化阶段获得统一入口 + WS 透传 + SSL 预留；Phase 5 压测以 Nginx :9763 为端到端入口，口径与交付一致（`docs/p4-handover-p5.md` §二） |
| ⚠️ 负面 | D19 环境处置使后端由 `127.0.0.1` 改绑 `0.0.0.0`（容器经 `host.docker.internal` 回源所需），暴露面较纯本机回环扩大 |
| 📎 已知边界 | 本期仅 HTTP（Q3=HTTP 先跑通），HTTPS/443 待部署期以自签名/正式证书启用；Nginx 容器 healthcheck 报 unhealthy 系前端 `/` 重定向 `/login` 所致，不影响反代功能；入口建议用 `127.0.0.1:9763`（部分环境 `localhost` 首跳解析异常致超时）——均见 `docs/p4-handover-p5.md` §三 |

## 六、事实源

- `plan/工业设备诊断 Agent.md` §3.11
- `docs/p4-handover-p5.md` §一 D19、§二、§三
- `docs/p5-handover-p6.md` §六
- `docs/prj-ledger-version-lock.md` §二.2.1
- `README.md` §4.7；`docker/compose.nginx.yml`；`configs/nginx/nginx.conf`

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-10 | 单人（本人） | Phase 6 D5 初版 | 本文件 |
