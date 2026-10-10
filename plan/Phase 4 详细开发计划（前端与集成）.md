# Phase 4 详细开发计划（前端与集成）

> **上游依据**：`云侧工业 IoT 诊断 Agent 系统 - 最终执行方案（V5.0 定稿）.md` §五 / §3.11 / §九
> **前一阶段**：Phase 3（Agent 工作流实现）——须 **M3.5 门禁通过**后启动
> **本阶段定位**：把 Agent 能力**交付到用户手上**——五类页面 + 实时推送 + 审核界面 + 图谱可视化，并首次引入 **Nginx 入口层**完成端到端集成。
> **执行主体**：单人（"机器并行、人串行"）
> **总工期**：20 个工作日（P4-D1 – P4-D20，占比 20%）
> **制定日期**：2026-09-24

---

## 目录

- [一、阶段目标与出口](#一阶段目标与出口)
- [二、阶段前置（Phase 3 移交物核对）](#二阶段前置phase-3-移交物核对)
- [三、技术栈与工程结构](#三技术栈与工程结构)
- [四、五类页面规格](#四五类页面规格)
- [五、分周计划（P4-D1 – P4-D20）](#五分周计划p4-d1--p4-d20)
- [六、关键模块详细设计](#六关键模块详细设计)
- [七、里程碑](#七里程碑)
- [八、测试计划](#八测试计划)
- [九、验收标准与门禁](#九验收标准与门禁)
- [十、风险与应对](#十风险与应对)
- [十一、交付物与目录](#十一交付物与目录)
- [十二、检查清单](#十二检查清单)

---

## 一、阶段目标与出口

### 1.1 阶段目标

> 交付一个**可用、实时、可审核、可追溯**的前端应用：
> ① 五类页面覆盖核心场景；② Socket.IO 实时推送诊断进度与告警；③ 审核界面完整承载 `review:required` → `review:submit`；
> ④ Nginx 统一入口（反代 + WebSocket 透传 + HTTPS）完成端到端集成。

### 1.2 阶段出口（M4.4）

| 出口物 | 判据 |
|---|---|
| 五类页面 | 告警看板 / 诊断对话 / 报告详情+审核 / 知识库 / 图谱可视化全部可用 |
| 实时性 | `alarm:new`、`diagnosis:progress`、`diagnosis:done`、`review:required` 端到端推送 ≤1s |
| 审核闭环 | 审核人可查看证据/置信度/风险 → 通过/驳回 → 状态回写并刷新 |
| RBAC | 三角色 + 知识库管理员路由守卫生效；禁止自审 |
| 集成 | Nginx 单入口 HTTPS，`/api` 与 `/socket.io` 正常 |
| 质量 | e2e 场景（Playwright）全部通过 |

### 1.3 与前后阶段的关系

```
Phase 3（Agent 工作流）
   └─► Phase 4（本阶段：交付与集成）
            ├─► Phase 5 评测与硬化：复用前端做人工评分入口
            └─► Phase 6 收敛交付：演示脚本基于本阶段页面
```

---

## 二、阶段前置（Phase 3 移交物核对）

| # | 移交物 | 用途 | 状态 |
|---|---|---|---|
| 1 | `diagnosis:progress` / `diagnosis:done` 事件定义 | 实时进度 | ☐ |
| 2 | `review:required` payload（含 preview/risk/confidence/evidence） | 审核界面 | ☐ |
| 3 | `chat:ask` 契约（对话式追问） | 诊断对话页 | ☐ |
| 4 | 报告 Schema + `reports` 表 | 报告详情页 | ☐ |
| 5 | 置信度 `confidence_breakdown` | 前端"为何这样判断" | ☐ |
| 6 | 审核状态机（pending/approved/rejected/timeout） | 审核 UI 状态 | ☐ |
| 7 | REST 契约（§5.5）+ 统一响应 `{code,message,data,trace_id}` | API 客户端 | ☐ |
| 8 | RBAC 角色定义（工程/审核/知识库管理员/系统管理员） | 路由守卫 | ☐ |
| 9 | `query_graph` 返回结构（nodes/paths） | 图谱可视化 | ☐ |
| 10 | Langfuse `trace_id` 透出 | 详情页追溯 | ☐ |

---

## 三、技术栈与工程结构

### 3.1 技术栈（与 V5.0 §3.1 一致）

| 层 | 选型 |
|---|---|
| 框架 | **Next.js（App Router）** |
| 样式 | **Tailwind CSS** + **shadcn/ui** |
| 数据请求 | TanStack Query（缓存/重试/失效） |
| 实时 | **socket.io-client** |
| 图谱 | **react-force-graph** |
| 图表 | Recharts（趋势/分布） |
| 表单校验 | react-hook-form + zod（复用后端 Schema 语义） |
| 测试 | Playwright（e2e）+ Vitest（单元） |
| 入口 | **Nginx**（Phase 4 引入，见 §6.7） |

### 3.2 工程结构

```
client/
├─ app/
│  ├─ (auth)/login/page.tsx
│  ├─ (main)/
│  │  ├─ layout.tsx                 # 侧边栏 + 顶栏 + 实时连接状态
│  │  ├─ alarms/page.tsx            # ① 告警看板
│  │  ├─ chat/[threadId]/page.tsx   # ② 诊断对话
│  │  ├─ reports/[id]/page.tsx      # ③ 报告详情 + 审核
│  │  ├─ knowledge/page.tsx         # ④ 知识库管理
│  │  └─ graph/page.tsx             # ⑤ 图谱可视化
├─ components/
│  ├─ ui/                           # shadcn 基础组件
│  ├─ alarm/ report/ review/ chat/ graph/ knowledge/
│  ├─ common/{EvidenceCard,ConfidenceBadge,RiskTag,TraceTimeline}.tsx
├─ lib/
│  ├─ api.ts                        # REST 客户端（统一响应/错误码）
│  ├─ socket.ts                     # Socket.IO 客户端（重连/房间）
│  ├─ auth.ts                       # 会话与 RBAC
│  └─ format.ts
├─ hooks/{useAlarms,useReport,useSocket,useReview}.ts
└─ tests/e2e/
```

---

## 四、五类页面规格

### ① 告警看板 `/alarms`

| 项 | 规格 |
|---|---|
| 元素 | 实时告警列表（设备/测点/值/严重度/时间/去重计数）、状态筛选、分页、一键"发起诊断" |
| 数据 | `GET /api/alarms` + `alarm:new` 实时插入 |
| 交互 | 新告警高亮；点击跳转诊断对话或报告 |
| 权限 | 三角色可见 |

### ② 诊断对话 `/chat/[threadId]`

| 项 | 规格 |
|---|---|
| 元素 | 消息流、**节点级进度条**（parse→sensor→retrieve→diagnose→route）、证据卡片、追问输入框 |
| 数据 | `POST /api/diagnose` + `chat:ask`；`diagnosis:progress` / `diagnosis:done` |
| 交互 | 进度实时刷新；点证据卡展开来源/页码；追问复用上下文 |
| 权限 | 工程师及以上 |

### ③ 报告详情 + 审核 `/reports/[id]`

| 项 | 规格 |
|---|---|
| 元素 | 诊断结论、根因列表、建议列表、**置信度 breakdown 可视化**、证据引用（可跳原文）、风险标签、Trace 时间线；审核区（通过/驳回 + 意见） |
| 数据 | `GET /api/reports/{id}`；审核 `POST /api/reports/{id}/review`；`review:required` |
| 交互 | 无来源结论**禁止展示为确定结论**；驳回必填意见；提交后状态刷新 |
| 权限 | 审核员可写；**提交者不可自审**（按钮禁用 + 后端二次校验） |

### ④ 知识库管理 `/knowledge`

| 项 | 规格 |
|---|---|
| 元素 | 文档列表（状态 pending/indexed/failed）、上传（**准入审核**）、版本历史、来源可信度分级 |
| 数据 | `GET /api/knowledge/docs`；上传 `POST /api/knowledge/docs` |
| 交互 | 上传后显示索引进度；失败项可重试（对接 Outbox） |
| 权限 | 知识库管理员可写，其他角色只读 |

### ⑤ 图谱可视化 `/graph`

| 项 | 规格 |
|---|---|
| 元素 | 力导向图（实体/关系）、邻居查询输入、路径高亮、点击实体看详情 |
| 数据 | `GET /api/graph/neighbors?entity=` |
| 交互 | 按关系类型过滤；与报告页联动（从证据跳图） |
| 权限 | 三角色可见 |

### 4.6 页面 ↔ 接口 ↔ 事件 映射

| 页面 | REST | Socket.IO（收） | Socket.IO（发） |
|---|---|---|---|
| 告警看板 | `GET /api/alarms` | `alarm:new` | — |
| 诊断对话 | `POST /api/diagnose` | `diagnosis:progress`、`diagnosis:done` | `chat:ask` |
| 报告/审核 | `GET /api/reports/{id}`、`POST .../review` | `review:required` | `review:submit` |
| 知识库 | `GET/POST /api/knowledge/docs` | — | — |
| 图谱 | `GET /api/graph/neighbors` | — | — |

---

## 五、分周计划（P4-D1 – P4-D20）

### 第 1 周（D1–D5）· 工程搭建与告警看板

| 天 | 任务 | 产出 |
|---|---|---|
| D1 | Next.js + Tailwind + shadcn/ui 初始化；主题（含深色模式）；布局骨架（侧边栏/顶栏/连接状态） | `client/app/(main)/layout.tsx` |
| D2 | `lib/api.ts` REST 客户端（统一响应解包、错误码映射、401 跳登录） | `lib/api.ts` |
| D3 | 登录页 + 会话（JWT 存储/刷新）+ RBAC 路由守卫 | `app/(auth)/login`、`lib/auth.ts` |
| D4 | 告警看板：列表 + 筛选 + 分页 + 严重度可视化 | `app/(main)/alarms` |
| D5 | `lib/socket.ts` 连接与重连；接入 `alarm:new` 实时插入 | `lib/socket.ts` |

> **出口 M4.1**：登录可用、告警看板实时更新。

### 第 2 周（D6–D10）· 诊断对话与实时进度

| 天 | 任务 | 产出 |
|---|---|---|
| D6 | 诊断对话页骨架：消息流 + 输入框 + 会话上下文 | `app/(main)/chat` |
| D7 | 节点级进度组件（`diagnosis:progress` 驱动，映射六节点） | `components/chat/ProgressSteps.tsx` |
| D8 | 证据卡片组件（来源/页码/得分/图谱线索）；点击展开原文 | `components/common/EvidenceCard.tsx` |
| D9 | `diagnosis:done` 处理（跳报告 / 置信度徽章 / 风险标签） | 同页 |
| D10 | 对话式追问 `chat:ask`（复用 thread 上下文） | `hooks/useSocket.ts` |

> **出口 M4.2**：可发起诊断并实时看到节点进度。

### 第 3 周（D11–D15）· 报告详情与审核

| 天 | 任务 | 产出 |
|---|---|---|
| D11 | 报告详情页：结论/根因/建议 + 引用列表 | `app/(main)/reports/[id]` |
| D12 | **置信度 breakdown 可视化**（0.35/0.20/0.15/0.30 分解图） | `components/common/ConfidenceBadge.tsx` |
| D13 | 审核界面：证据/风险/置信度 + 通过/驳回 + 意见必填 | `components/review/` |
| D14 | 审核状态机前端（pending/approved/rejected/timeout）+ `review:required` 提醒 | `hooks/useReview.ts` |
| D15 | **禁止自审** + RBAC 按钮级控制 + 审核历史 | 同上 |

> **出口 M4.3**：审核闭环可用，职责分离生效。

### 第 4 周（D16–D20）· 知识库、图谱与集成

| 天 | 任务 | 产出 |
|---|---|---|
| D16 | 知识库页：列表/状态/上传/准入审核/版本历史 | `app/(main)/knowledge` |
| D17 | 图谱可视化：react-force-graph + 邻居查询 + 关系过滤 | `app/(main)/graph` |
| D18 | 报告↔图谱联动、Trace 时间线展示 | `components/common/TraceTimeline.tsx` |
| D19 | **Nginx 集成**：反代 `/`、`/api`、`/socket.io`（WS 透传）+ HTTPS | `docker/compose.nginx.yml`、`configs/nginx/` |
| D20 | 端到端联调 + 验收 + `p4-handover-p5.md` | **M4.4** |

---

## 六、关键模块详细设计

### 6.1 API 客户端（统一响应与错误码）

```ts
// lib/api.ts
type ApiResp<T> = { code: number; message: string; data: T; trace_id: string };

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  const body: ApiResp<T> = await res.json();
  if (body.code !== 0) throw new ApiError(body.code, body.message, body.trace_id);
  return body.data;
}
```

**错误码映射**：`E_TIMEOUT`→"请求超时，请重试"；`E_PERMISSION`→"无权限"；`E_CONFLICT`→"状态已变更，请刷新"；`E_UPSTREAM`→"服务暂不可用"。

### 6.2 Socket.IO 客户端

```ts
// lib/socket.ts
export const socket = io("/", {
  path: "/socket.io",
  transports: ["websocket"],
  reconnection: true,
  reconnectionDelayMax: 5000,
});

socket.on("connect", () => socket.emit("join", { userId }));
socket.on("alarm:new", (a) => queryClient.setQueryData(["alarms"], insert(a)));
socket.on("diagnosis:progress", (p) => updateSteps(p));
socket.on("review:required", (r) => toast.warn("有待审核报告") + invalidate(["reports"]));
```

| 事件 | 方向 | 页面处理 |
|---|---|---|
| `alarm:new` | 收 | 告警列表插入 + 高亮 |
| `diagnosis:progress` | 收 | 进度条更新 |
| `diagnosis:done` | 收 | 跳报告 / 徽章 |
| `review:required` | 收 | 全局提醒 + 列表失效 |
| `review:submit` | 发 | 提交审核 |
| `chat:ask` | 发 | 追问 |

**可靠性**：断线重连；重连后 `invalidateQueries` 全量校正，避免丢事件导致界面陈旧。

### 6.3 审核界面（核心交互）

```
┌───────────────────────────────────────────────┐
│ 风险：HIGH  |  置信度：0.68  ⓘ 查看 breakdown  │
├───────────────────────────────────────────────┤
│ 结论：驱动端轴承磨损，伴随润滑不足…            │
│ 根因：1) 轴承磨损  [证据 c_00123 ↗]            │
│       2) 润滑不足  [证据 c_00456 ↗]            │
│ 建议：1) 检查润滑  [证据 c_00456 ↗]  risk: low │
│       2) 停机更换  [证据 c_00789 ↗]  risk: high│
├───────────────────────────────────────────────┤
│ ⚠ 该建议涉及停机，请确认现场安全条件            │
│ ○ 通过   ○ 驳回（必填意见）                    │
│ [提交审核]   （提交者=本人时禁用）              │
└───────────────────────────────────────────────┘
```

**规则**：无 citation 的结论以"依据不足"样式展示，不显示为确定结论；高风险建议强制二次确认。

### 6.4 置信度 breakdown 可视化

| 分量 | 权重 | 展示 |
|---|---|---|
| 检索得分 | 0.35 | 条 |
| 传感器一致性 | 0.20 | 条 |
| 图谱支撑 | 0.15 | 有路径/无路径 |
| 模型自评（校准） | 0.30 | 条 + 校准标记 |

> 目的：让审核人看到"为什么系统这么判断"，这是安全边界的一部分。

### 6.5 RBAC 前端

| 角色 | 告警 | 诊断 | 审核 | 知识库 | 图谱 |
|---|---|---|---|---|---|
| 工程师 | 只读+发起 | ✅ | ❌ | 草稿 | 只读 |
| 审核员 | 只读 | 只读 | ✅ | 审批 | 只读 |
| 知识库管理员 | 只读 | 只读 | ❌ | ✅ | 只读 |
| 系统管理员 | 只读 | ❌ | ❌ | 用户管理 | ❌ |

**双重校验**：前端守卫 + 后端强制（前端仅体验优化，不构成安全边界）。

### 6.6 前端安全

- **禁止 `dangerouslySetInnerHTML`** 渲染模型输出；统一文本渲染；
- 输入长度/字符白名单校验；
- JWT 存储避免 XSS（内存 + httpOnly refresh）；
- 所有写接口携带 `trace_id` 便于审计关联。

### 6.7 Nginx 集成（Phase 4 首次引入）

```nginx
map $http_upgrade $connection_upgrade { default upgrade; '' close; }

server {
    listen 443 ssl;
    server_name diagnosis.local;
    ssl_certificate /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;

    location / { proxy_pass http://frontend:3000; }

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /socket.io/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;      # ★ 关键
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 3600s;
    }
}
```

> Compose 增 `nginx` 服务，`depends_on` frontend/backend 健康检查；统一入口后端口仅暴露 443。

---

## 七、里程碑

| 里程碑 | 内容 | 时间 | 通过条件 |
|---|---|---|---|
| **M4.1** | 框架与告警看板 | D5 | 登录 + RBAC + 实时告警插入 |
| **M4.2** | 诊断对话与进度 | D10 | 发起诊断并实时看到节点进度 |
| **M4.3** | 报告与审核 | D15 | 审核闭环 + 禁止自审 |
| **M4.4** | 知识库/图谱/集成 | D20 | 五页面可用 + Nginx 单入口 e2e 通过 |

---

## 八、测试计划

### 8.1 e2e（Playwright）必测

| # | 场景 | 期望 |
|---|---|---|
| F1 | 登录 → 告警看板加载 | 列表正确、权限过滤生效 |
| F2 | 新告警实时到达 | 无需刷新即插入并高亮 |
| F3 | 发起诊断 | 进度条按六节点推进 |
| F4 | 诊断完成 | 跳转报告，置信度/风险正确展示 |
| F5 | 高风险报告审核 | `review:required` 提醒 → 审核页可提交 |
| F6 | **自审拦截** | 提交者本人按钮禁用，直连接口被后端拒绝 |
| F7 | 驳回必填意见 | 未填意见不可提交 |
| F8 | 知识库上传 | 状态从 pending → indexed，失败可重试 |
| F9 | 图谱邻居查询 | 节点/关系渲染正确，过滤生效 |
| F10 | 断线重连 | 重连后数据自动校正，无陈旧视图 |
| F11 | Nginx 单入口 | HTTPS 访问，`/api` 与 WS 均正常 |

### 8.2 兼容与可用性

- 目标浏览器：Chrome/Edge 最新两个版本；
- 分辨率：1600×900 起，兼顾 1366×768；
- 深色模式全覆盖；
- 键盘可达性（审核操作可键盘完成）。

---

## 九、验收标准与门禁

### 9.1 指标

| 指标 | 目标 |
|---|---|
| 实时推送端到端延迟 | ≤ 1s |
| 首屏加载（本机内网） | ≤ 2s |
| 五页面功能完备 | 100% |
| e2e 场景通过率 | 100%（F1–F11） |
| 前端错误率（控制台异常） | 0 阻断级 |
| 审核操作完成时长 | ≤ 3 次点击 |

### 9.2 门禁判定

| 情况 | 处置 |
|---|---|
| 全项达标 | **M4.4 通过**，进入 Phase 5 |
| 推送延迟 1–3s | 中间区间：检查 WS 链路与 Nginx 配置；记录处置 |
| 非阻断级 e2e 失败 | 记录缺陷 + 排期修复，允许有条件进入 Phase 5 |
| **自审可绕过** | **阻塞**：安全缺陷，必须修复 |
| WS 在 Nginx 下不可用 | **阻塞**：集成未完成 |

> 中间区间 **≠ 通过**，须写处置动作与代价。

---

## 十、风险与应对

| 编号 | 风险 | 影响 | 应对 | 归属 |
|---|---|---|---|---|
| P4-R1 | Nginx WS 透传配置错误 | 实时功能全失 | 按 §6.7 样板；单独验证 `/socket.io` | D19 |
| P4-R2 | 事件丢失致界面陈旧 | 状态不一致 | 重连后 `invalidateQueries` 全量校正 | D5 |
| P4-R3 | 审核权限仅前端控制 | 越权风险 | 后端二次强制校验 | D15 |
| P4-R4 | 模型输出 XSS | 安全风险 | 禁用 HTML 渲染，纯文本展示 | 全程 |
| P4-R5 | 前后端契约漂移 | 联调返工 | 契约以 `tools_v1.json` + REST 契约为唯一源 | 全程 |
| P4-R6 | 接口超时无反馈 | 体验差 | 统一错误码映射 + 超时提示 | D2 |
| P4-R7 | 图谱数据量大渲染卡顿 | 页面不可用 | 限制默认返回节点数 + 按需展开 | D17 |
| P4-R8 | 深色模式样式遗漏 | 体验不一致 | 主题 token 统一 + 视觉巡检 | D1/D20 |

---

## 十一、交付物与目录

### 11.1 目录增量

```
project/
├─ client/                                  # ★ 前端应用
│  ├─ app/(auth)/login/
│  ├─ app/(main)/{alarms,chat,reports,knowledge,graph}/
│  ├─ components/{ui,alarm,chat,report,review,knowledge,graph,common}/
│  ├─ lib/{api.ts,socket.ts,auth.ts,format.ts}
│  └─ tests/e2e/
├─ configs/nginx/nginx.conf
├─ docker/compose.nginx.yml
└─ docs/
   ├─ p4-ui-spec.md
   └─ p4-handover-p5.md
```

### 11.2 交付物清单

| 类别 | 交付物 |
|---|---|
| 页面 | 五类页面完整实现 |
| 组件 | 证据卡 / 置信度分解 / 风险标签 / 进度条 / Trace 时间线 |
| 客户端 | REST 客户端 + Socket.IO 客户端（含重连校正） |
| 权限 | RBAC 守卫 + 禁止自审 |
| 集成 | Nginx 配置 + Compose 片段 + HTTPS |
| 测试 | Playwright e2e 用例与报告 |
| 移交 | `p4-handover-p5.md` |

---

## 十二、检查清单

### 通用规则
- [ ] 接口契约以 Phase 3 移交为准，不擅自改字段
- [ ] 前端权限仅作体验优化，**后端必须二次校验**
- [ ] 模型输出一律纯文本渲染，禁用 HTML 注入点
- [ ] 所有请求携带并展示 `trace_id`

### 第 1 周（M4.1）
- [ ] 登录 + 会话 + RBAC 守卫
- [ ] REST 客户端统一错误码映射
- [ ] 告警看板 + `alarm:new` 实时插入

### 第 2 周（M4.2）
- [ ] 诊断对话页可用
- [ ] 节点级进度实时刷新
- [ ] 证据卡片可展开来源

### 第 3 周（M4.3）
- [ ] 报告详情 + 置信度 breakdown
- [ ] 审核通过/驳回 + 意见必填
- [ ] 禁止自审（前后端双重）

### 第 4 周（M4.4）
- [ ] 知识库上传 + 状态流转
- [ ] 图谱可视化 + 邻居查询
- [ ] Nginx 单入口 HTTPS + WS 正常
- [ ] F1–F11 e2e 全通过
- [ ] `p4-handover-p5.md` 齐备

---

## 附：Phase 4 → Phase 5 移交要点

| 移交项 | 用途 |
|---|---|
| 五类页面与组件 | Phase 5 人工评分入口、演示 |
| 审核界面 | Phase 5 审核覆盖率与人机一致性评测 |
| 证据卡片 + 置信度分解 | Phase 5 引用正确率/幻觉率人工标注载体 |
| Socket.IO 推送链路 | Phase 5 端到端延迟实测 |
| Nginx 单入口 | Phase 5 端到端压测入口 |
| Playwright e2e | 回归基线 |
