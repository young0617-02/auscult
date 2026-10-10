# Phase 4 → Phase 5 移交清单

| 项 | 值 |
|---|---|
| 移交方 | Phase 4（前端与集成） |
| 接收方 | Phase 5（评测/压测/演示） |
| 移交日期 | 2026-10-09 |
| 前置条件 | M4.1–M4.4 全部达成 |

---

## 一、M4.4 出口（D16–D20）

### D16 知识库页
- `app/(main)/knowledge` + `components/features/KnowledgeBoard.tsx` + `hooks/useKnowledge.ts` + `lib/types/knowledge.ts`
- 列表/类型/状态筛选 + 分页 + KPI；上传登记（kb_admin）；准入审核一次性决策（kb_admin）
- **版本历史降级（Q1=B）**：展示 admission_status/admitted_by 留痕，不新增 GET versions 契约

### D17 图谱可视化
- `app/(main)/graph` + `components/features/GraphExplorer.tsx` + `hooks/useGraph.ts`
- 依赖：**react-force-graph-2d**（轻量，无 three/aframe；完整版因网络与体积改用 2d 变体）
- 实体精确查询 + 跳数 ≤2 + 关系过滤 + 节点检查器 + 降级横幅（Neo4j 不可达不打断）

### D18 报告↔图谱联动 + Trace 时间线
- `components/common/TraceTimeline.tsx`：节点序列 + 总耗时 + thread_id + trace 标识
- 报告详情右栏新增「从当前报告载入图谱」链接（`/graph?entity=<device_id>`）

### D19 Nginx 单入口（Q3=HTTP 先跑通）
- `docker/compose.nginx.yml` + `configs/nginx/nginx.conf`
- 入口：`http://127.0.0.1:9763`；反代 `/`→Next.js:3000、`/api`→FastAPI:8000、`/socket.io` WS 透传
- 镜像：`nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10`
- **已验证**：`/login` 200、`/api/health` 200（经 Nginx 链路）
- **环境处置**：后端由 127.0.0.1 改绑 0.0.0.0（容器经 host.docker.internal 回源所需）；venv python 经防火墙 A/B 实测可通（9899 对照证明非程序级拦截，初始 8000 不可达系宿主仅绑 127.0.0.1）

### D20 全量回归
- vitest **53/53 PASS**（含新增 knowledge.test.ts 6 条）
- `next build` 通过（13/13 静态生成，无错误）
- Playwright E2E **9/9 PASS**（m41+m42+m43）

---

## 二、Phase 5 移交物

| 移交项 | 用途 |
|---|---|
| 五页面（alarms/diagnosis/reports/knowledge/graph） | 人工评分入口、演示 |
| 审核界面（D13-D15） | 审核覆盖率与人机一致性评测 |
| 证据卡片 + 置信度分解 | 引用正确率/幻觉率人工标注载体 |
| Socket.IO 推送链路 | 端到端延迟实测 |
| Nginx 单入口 :9763 | 端到端压测入口 |
| Playwright e2e（9 用例） | 回归基线 |

---

## 三、已知边界 / 遗留 P5

| 项 | 说明 |
|---|---|
| reports.payload 未持久化 evidence 原文 + confidence_breakdown | ConfidenceBreakdown 组件已就绪，待后端接入后启用四分量展示 |
| 知识库版本历史 | 降级为准入留痕展示（Q1=B）；如需完整版本列表，P5 补 GET versions 契约 |
| HTTPS | 本期仅 HTTP（Q3）；部署期以自签名/正式证书启用 443 |
| localhost vs 127.0.0.1 | Nginx 入口建议用 `127.0.0.1:9763`（部分环境 localhost 首跳解析异常致超时） |
| Nginx 容器 healthcheck | 报 unhealthy 系前端根路径 `/` 重定向 /login 所致，不影响反代功能；如需绿标可改探 `/login` |
