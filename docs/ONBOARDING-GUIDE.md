# Interview Agent 新工程师完整上手指南

> 面向刚接手本项目的初级工程师。这是一份**循序渐进的完整教程**：从"项目是什么"
> 讲到"能独立值守"，并附上详尽的速查参考和常见任务 cookbook。
>
> 本文与仓库另外两份文档分工互补，不重复：
>
> | 文档 | 形态 | 适合何时读 |
> |---|---|---|
> | **本文（ONBOARDING-GUIDE）** | 循序渐进教程 + 详尽参考附录 + cookbook | 第一次接手、想被"带一遍" |
> | [开发、运维与使用接手手册](ENGINEERING-HANDOVER-MANUAL.md) | 精炼速查、14 节概览 | 已经熟了、日常快速翻阅 |
> | [从零到企业级 Agent 工程课程](enterprise-agent-engineering-course.md) | 12 周通用 Agent 工程教学 | 想系统性补 Agent 工程基础 |
>
> 三者不矛盾：本文带你"走一遍"并给参考表，接手手册给你"查得快"，工程课程帮你
> "懂原理"。冲突时按下文事实来源优先级判断。

## 事实来源优先级（先记住这一条）

仓库不是只有一份文档。当多处说法冲突时，按以下优先级判断，**用可执行检查确认实际
行为，并在同一个变更里更新过时的来源**：

1. 可执行测试和数据库约束；
2. [机器可读功能契约](product-specs/feature-contract.json)；
3. [架构总纲](../ARCHITECTURE.md)和已采纳设计文档；
4. 产品、开发、发布和运行指南；
5. 历史路线图、完成报告和执行记录。

把以下文档加入书签：[架构总纲](../ARCHITECTURE.md)、
[功能契约](product-specs/feature-contract.json)、[开发指南](development.md)、
[API 路由参考](generated/api-routes.md)、[配置参考](generated/configuration.md)、
[运维手册](operations/OPERATIONS-MANUAL.md)、[故障排查](operations/TROUBLESHOOTING.md)、
[部署手册](release/DEPLOYMENT-RUNBOOK.md)。

---

# 上篇 · 循序渐进上手

## 第 1 章 认识这个系统

### 1.1 它是什么

Interview Agent（也叫 Interview Lab）是一个**面向技术岗位求职者的持续训练工作台**，
不是面试官机器人，也不是招聘决策系统。它把"岗位目标 → 知识问答 → 模拟面试 →
能力诊断 → 间隔复习"串成一个**有记录、可恢复、可度量**的学习闭环。

> ⚠️ 产品定位红线（来自 README 和 PRD）：模型回答和评分**仅用于学习辅助**，不能
> 包装成对候选人真实能力的权威认证；它不是简历投递平台、招聘系统或通用聊天机器人。

### 1.2 核心功能一览

| 功能域 | 说明 | 默认 |
|---|---|---|
| 身份 | 注册/登录/刷新/退出/改密/恢复码；产品与**管理员独立登录面** | 开 |
| 目标与账号 | 岗位、方向、JD、头像、提醒偏好 | 开 |
| 今日训练 | 基于目标和到期事项推荐下一步 | 开 |
| 聊天 | 流式问答、知识来源、持久历史、**幂等重试** | 开 |
| 历史 | 搜索/打开/重命名/归档/恢复/删除会话 | 开 |
| 模拟面试 | 开始/答题/**四维评分**/重答/恢复/归档/报告 | 开 |
| 能力画像 | 跨场次维度、趋势、主题、薄弱点 | 开 |
| 学习 | 生成任务、修改状态、**间隔复习** | 开 |
| 简历评估 | 上传 PDF/DOCX、岗位评估、证据化改写、DOCX 导出 | **关** |
| 简历定向面试 | 基于简历项目和 JD 差距的模拟面试 | 随简历开 |
| 真实面试复盘 | 音频/文本逐字稿、逐题复盘、学习闭环 | **关** |
| 管理员 | 独立登录、用户管理、系统监控、审计、发布、知识发布/回滚 | 开 |

### 1.3 技术栈一览

| 层 | 技术 | 版本下限 | 用途 |
|---|---|---|---|
| 后端框架 | FastAPI | ≥0.115 | HTTP API |
| ASGI | uvicorn[standard] | ≥0.30 | 单 worker 运行 |
| ORM/SQL | SQLAlchemy Core（**非 ORM**，同步） | ≥2.0 | 表元数据 + 事务脚本 |
| 迁移 | Alembic | ≥1.14 | 生产 schema 演进 |
| 缓存/队列/限流 | Redis | ≥5.2 | Lua 脚本实现的可靠任务队列 |
| 向量库 | Qdrant | 客户端 ≥1.12 | 版本化私人知识 HYBRID 检索 |
| Agent | langchain + langgraph | ≥1.0 | supervisor + 4 专家拓扑 |
| 模型适配 | langchain-openai | ≥0.3 | 调用智谱 GLM |
| 重排 | fastembed | ≥0.7 | 本地 Cross-Encoder + BM25 sparse |
| 前端 | Vue 3.5 + Vue Router 4 + Pinia 2 | — | SPA |
| 前端构建 | Vite 8 + TypeScript 5.9 | — | 产物托管在 FastAPI `/static` |
| 前端测试 | Vitest 4 + Playwright 1.62 | — | 单测 + 桌面/移动 E2E |
| 可观测 | Prometheus / Grafana / OpenTelemetry | — | 指标/看板/Trace |

**关键事实**：依赖用 `requirements.in` + `pip-tools` 生成**带哈希**的
`requirements.txt`；镜像用 digest 固定。`make lock-python` 在固定 `python:3.12-slim`
里重新生成。CI 用 `scripts.reproducibility check` 强制校验。

### 1.4 系统全景图

```text
浏览器
  │  HTTP / 流式 NDJSON
  ▼
Nginx Gateway（生产统一入口，端口 8080；/metrics 返回 404 不外暴露）
  │
  ▼
FastAPI App ──────────────────── Vue 静态产物（/static）
  │  │  │  │  \
  │  │  │  │   └─ 模型 / Embedding / 可选搜索（统一走 model_gateway）
  │  │  │  └──── 用户文件卷（与 Worker 共享 USER_FILES_DIR）
  │  │  └────── Qdrant（版本化知识集合 + 稳定别名）
  │  └──────── Redis（限流、RAG 缓存、可恢复任务队列 + Lua 脚本）
  └────────── PostgreSQL（生产）/ SQLite（快速本地测试）
                    ▲
                    │ 领取、续租、重试、确认
Worker ─────────────┘  处理 knowledge_import / resume_analysis /
                       interview_transcription / interview_review_analysis

Prometheus ◀─ /metrics ─ App ─▶ OTEL Collector ─▶ Trace 后端
Grafana    ◀─ Prometheus
```

### 1.5 组件职责表

| 组件 | 负责 | 不负责 / 注意 |
|---|---|---|
| Vue 前端 | 页面、路由、Pinia 状态、API 调用、流式渲染 | 不承担授权；隐藏按钮不是安全控制 |
| FastAPI App | HTTP 校验、认证、用例编排、静态前端、健康和指标 | 不在事件循环直接跑阻塞数据库操作 |
| Worker | 知识导入、简历分析、音频转写、复盘分析 | 需要 Redis，且与 App 共享知识/用户文件卷 |
| PostgreSQL | 用户、会话、面试、学习、审计、任务资源状态 | 生产迁移归 Alembic，**不用 `create_all`** |
| Redis | 限流、RAG 缓存、持久任务、租约和心跳 | 不能用清队列掩盖任务失败 |
| Qdrant | 混合检索的私人知识分块与向量 | 当前别名目标**不可作为临时测试删除** |
| Gateway | 公网入口、反向代理和安全响应头 | App、数据服务和指标端口不应直接暴露公网 |
| Prometheus/Grafana/OTEL | 指标、看板和 Trace | 不是请求正确性边界，标签不能带用户正文 |

---

## 第 2 章 Day 1：把项目跑起来

### 2.1 前置条件与版本核对

需要：Python **3.12**（开发文档最低 3.11，但镜像和 CI 用 3.12）、Node.js **20.19+**、
Docker 与 Docker Compose。真实聊天用智谱 Coding Plan Key；真实 Embedding/知识导入用
智谱标准 API Key（两者**可能不通用**）。默认自动化测试不要求真实模型凭据。

```bash
python3 --version      # 期望: Python 3.12.x
node --version         # 期望: v20.19 或更高
npm --version
docker --version
docker compose version
```

### 2.2 安装依赖

在仓库根目录执行：

```bash
# 1. 创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装后端依赖（带哈希锁定，保证可复现）
pip install --require-hashes -r requirements.txt

# 3. 安装前端依赖
npm ci --prefix frontend

# 4. 从模板创建本地 .env（只改本地 .env，绝不提交）
cp .env.example .env
```

> 🔒 `.env`、Token、API Key、数据库 Dump、备份、用户数据、私人知识正文**严禁提交**，
> `.gitignore` 已禁止。第一次只需要改这几组（详见 [附录 B](#附录-b环境变量分组速查)）：
> 模型 Key、Embedding Key、数据库、Redis/Qdrant、认证开关、可选功能开关、用户文件目录、
> 观测开关。不做 Live 调用可暂时不配有效 Key。

### 2.3 启动项目（两条路径，任选其一）

#### 路径 A（推荐）：Worktree 隔离 Compose 栈

每个 Worktree 自动派生稳定且**不同**的 Compose project、主机端口、网络和卷，互不干扰。

```bash
make worktree-env          # 生成 .env.worktree（派生端口等）
make stack-config          # 校验 Compose 配置可解析
make stack-up              # 启动隔离栈（先 alembic upgrade head 再起 uvicorn）
python -m scripts.worktree_env --root . --print   # 打印本 Worktree 的实际端口
```

> ⚠️ **不要假设端口一定是 8000**。用上面 `--print` 的实际 `APP_HOST_PORT`。Compose 中
> App 容器启动时先执行 `alembic upgrade head`，Worker 在 Redis/PostgreSQL/Qdrant 健康后启动。

验证：

```bash
curl -fsS http://127.0.0.1:<APP_HOST_PORT>/health    # 进程存活
curl -fsS http://127.0.0.1:<APP_HOST_PORT>/ready     # 依赖就绪（DB+Qdrant+可选 Redis）
docker compose --env-file .env --env-file .env.worktree logs --since=10m app worker
```

停止当前 Worktree 栈（**不带 `-v`，不删卷**）：

```bash
make stack-down
```

#### 路径 B：前后端分开开发（适合改后端代码 + 热重载）

终端 1，只起依赖和后端：

```bash
docker compose up -d postgres redis qdrant
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

终端 2，起前端 dev server：

```bash
source .venv/bin/activate
npm --prefix frontend run dev
```

Vite 默认在 **5173**，把 `/api`、`/health`、`/ready`、`/metrics` 代理到 `localhost:8000`。
浏览器开发入口用 `http://localhost:5173`，OpenAPI 用 `http://localhost:8000/docs`。

### 2.4 动手任务：浏览器走通主流程

目标：用自己的眼睛验证一遍核心闭环，并建立"前端调用 → API → 后端代码"的对应感。

1. 打开 `http://localhost:<端口>`（路径 A 用 `--print` 的端口；路径 B 用 5173）。
2. **注册一个产品账号**并登录。
3. 在"今日训练"设置目标岗位、方向、可选 JD（这决定推荐和面试出题方向）。
4. 进入**聊天**，问一个领域问题；观察流式回答和**知识来源**（RAG 命中时展示）。
5. 进入**模拟面试**，选主题/难度/题数；答一题，查看四维评分（准确性/深度/沟通/实用性）。
6. 进入**能力画像**，看分数和薄弱项；进入**学习**，看生成的学习任务。
7. 打开 `http://localhost:<端口>/docs`，对照 [API 路由参考](generated/api-routes.md)，
   找到你刚才每一步操作对应的 API 端点。

> 知识问答需要真实知识内容时：把获准的 `.md`/`.txt` 放入 `knowledge/`，配好 Embedding
> 后执行 `python -m scripts.ingest`。**这会调用外部 Embedding 并修改 Qdrant 服务别名，
> 不是普通单元测试步骤**，本地第一次可以跳过。

### 2.5 今天的检查清单

- [ ] 能跑通路径 A 或路径 B，`/health` 和 `/ready` 都返回正常
- [ ] 浏览器走通 注册→设目标→聊天→面试→能力画像
- [ ] 看了一眼 `/docs`，知道端点长什么样
- [ ] `.env` 已创建且**未被** `git status` 追踪到（确认 `.gitignore` 生效）

---

## 第 3 章 Day 2-3：读懂一次请求的旅程

这一章的目标：不靠死记，而是能"追"一个请求从浏览器到数据库的完整路径。

### 3.1 分层架构与依赖方向

代码分四层，依赖只能从上往下流：

```text
API 适配器   (app/api/routers/, app/api/schemas.py, app/api/security.py)
    │  HTTP 校验、认证依赖、状态码、响应序列化
    ▼
应用服务     (app/application/*)
    │  一个用例的编排 + 事务/并发边界；依赖 repository/模型接口
    ▼
纯领域规则   (app/learning.py, app/chunks.py, app/evaluation.py, app/chat_context.py, ...)
    │  确定性计算和状态流转；禁止任何 infra 依赖
    ▲
基础设施实现 (app/storage.py, app/operations.py, app/rag.py, app/model_gateway.py, ...)
       SQLAlchemy / Redis / Qdrant / HTTP / 模型 SDK 细节
```

**这些规则不是写在文档里吓人的，而是由 `tests/test_architecture.py` 用 AST 机械强制的**
（共 8 个测试，详见 [附录](#附录-d常见任务-cookbook) 中的架构测试说明）。关键几条：

- 纯计算模块（`chat_context/chunks/evaluation/learning`）**不得** import
  fastapi/sqlalchemy/redis/qdrant/http/langchain；
- `app/database.py` 不得依赖 API/Agent/检索/网络层；
- 除 `main.py` 外，任何模块都**不得反向 import `app.main`**；
- `langchain_openai` **只允许**在 `app/model_gateway.py` 出现（模型构造收敛到网关）；
- `app/application/execution.py` 里 `asyncio.to_thread` **正好出现 1 次**，所有阻塞用例
  统一走 `SyncExecutor`，路由里不得自己 `to_thread`。

### 3.2 追踪一次聊天请求

以 `POST /api/chat/stream`（流式聊天）为例，逐层标注文件路径：

```text
浏览器 streamChat()                              frontend/src/api/chat.ts
  │  带 Idempotency-Key header，按行读 NDJSON
  ▼
POST /api/chat/stream                            app/api/routers/chat.py
  │  解析认证身份；把同步用例通过 run_sync() 派发（不自己 to_thread）
  ▼
ChatTurnService.begin()                          app/application/chat_service.py
  │  幂等键去重 + 数据库条件认领；outcome:
  │    completed(已有响应重放) / key_reused / in_progress / conflict / claimed
  ▼
plan_chat_context()                              app/chat_context.py（纯计算）
  │  在 token 预算内保留最近消息，更早的折叠成带 sha 指纹的摘要
  ▼
Agent / RAG                                      app/agent.py → app/multi_agent.py
  │  supervisor 路由到 knowledge/interviewer/evaluator/planner 专家
  │  search_interview_knowledge() 走 app/tools.py → app/rag.py（版本化别名）
  ▼
model_gateway (唯一外部出口)                     app/model_gateway.py
  │  PolicyChatOpenAI: 输入预算门控 + 并发槽 + timeout/retry + metric + token 计费
  ▼
流式 token 逐个返回                               app/api/routers/chat.py
  ▼
用户/助手消息【完成后一起】落库                    app/storage.py (ConversationStore)
       失败/取消不会留下孤立的正式消息
```

### 3.3 追踪一次模拟面试答题

以 `POST /api/interviews/{id}/answer` 为例，关注**可靠性机制**：

- **幂等**：`Idempotency-Key` + `interview_answer_attempts` 表；同键重试只计费/推进一次。
- **认领**：DB 条件认领 + `claim_token`（所有者凭证）；并发提交只允许一个 owner 执行。
- **状态机**：面试回合 `pending → generating → completed / failed / cancelled`。
- **评分**：`app/interview_engine.py` 的 `assess_answer()` 让模型输出 JSON，正则提取并
  clamp 各维度分数到 `[0,10]`；维度 = 准确性/深度/沟通/实用性。
- **落库**：评分、参考答案、下一题、execution trace 一并持久化。

> ⚠️ 架构约束：`generating` 状态下进程崩溃**不会自动接管 lease**，需运维手动恢复——
> 因为没有模型调用 fencing 就自动接管，慢的旧 owner 会破坏正确性。详见
> [架构总纲](../ARCHITECTURE.md) 和 [durable-chat-turn-lifecycle 设计文档](design-docs/durable-chat-turn-lifecycle.md)。

### 3.4 动手任务：改一个最小的东西并跑测试

挑一个**无 Schema 变化、无外部数据流**的小改动（例如给某个 API 响应加一个字段，或
修正一个纯计算函数的行为），练习完整闭环：

1. 先找到对应的**失败测试**（没有就先写一个）。
2. 在**正确的层**改（HTTP 字段改路由+schema；纯规则改领域模块并写无依赖单测；用例改
   `app/application/`）。
3. 跑聚焦测试：

```bash
pytest -q tests/<relevant_file>.py
```

4. 如果改了用户资源，测试覆盖**另一用户越权失败**的场景。
5. 同步更新 [功能契约](product-specs/feature-contract.json) 中对应 feature（若行为变了）。

---

## 第 4 章 第一周：独立完成一个小闭环

### 4.1 选题原则

第一个独立任务选**无 Schema 变化、无外部数据流变化**的：bug 修复、纯计算逻辑调整、
API 字段增补、前端小改进。避免一上来就碰迁移、知识发布、模型调用。

### 4.2 标准开发流程（六步）

```text
1. 动手前  → 读 AGENTS.md + 架构总纲 + 相关设计文档；查 feature-contract 和技术债；
              确认工作区里哪些是别人的工作，不混入无关清理；写清"期望行为 + 最小验收标准"。
              跨模块 / 改正确性边界 / 一次短会话做不完 → 建[执行计划](exec-plans/active/)。
2. 改对层  → 见第 3.1 节分层。
3. 写测试  → 同步更新或新增测试（行为证据）。
4. 跑门禁  → 从小到大（见下）。
5. 同步文档 → feature-contract / 架构设计 / 运维安全 / generated（跑 generate_docs）。
6. 收尾    → 更新执行计划与技术债；完成项移入 exec-plans/completed/。
```

### 4.3 质量门禁（从小到大）

```bash
pytest -q tests/<relevant_file>.py   # 单个后端测试
make harness-static                  # 架构 + harness 契约 + 可复现性（无需外部服务）
make backend-check                   # compileall + 全部后端 pytest
make frontend-check                  # 前端工具链/类型/单测/构建/Bundle 预算
make e2e                             # Playwright 桌面 + 移动 E2E
make harness-check                   # 仓库级完整门禁 = 上面四项之和
```

> 📋 `make harness-check` 是仓库级门禁。**不能运行时必须说明缺少什么、实际跑了什么，
> 不能静默换成更弱的验证。** 交付时建议留下证据，例如：
>
> ```text
> Focused: pytest -q tests/test_xxx.py -> passed
> Static:  make harness-static -> passed
> Full:    make harness-check -> blocked: Docker unavailable
> Risk:    E2E and Compose integration not verified locally
> ```

### 4.4 测试环境边界（别踩坑）

- 默认后端测试用**隔离 SQLite**；
- PostgreSQL 专项行为需配 `TEST_POSTGRES_URL`（标 `@pytest.mark.integration`）；
- Redis 集成测试必须指向**明确的测试实例**；
- Playwright 用临时 SQLite + Worktree 独立端口；
- **Live 模型/RAG 评估是显式成本操作**，默认门禁不运行；
- 测试**不得删除/替换正在服务的 Qdrant 集合**。

### 4.5 跟随一次非生产知识发布或 Worker 任务

第一周末，建议跟着一次知识导入或 Worker 任务走完整状态链路，建立运维直觉（操作步骤
见 [第 8 章](#第-8-章-日常运维)）。这一步会让你真正理解"版本化发布"和"可靠任务队列"
为什么是本项目的两大支柱。

---

# 中篇 · 使用手册

## 第 5 章 普通用户使用

### 5.1 基础流程（默认开启）

1. **注册/登录**：进入产品工作区注册或登录。设好密码后建议立即生成**恢复码**备用。
2. **设目标**：在"今日训练"设置目标岗位、方向、可选 JD——这决定推荐和面试出题方向。
3. **AI 问答**：创建聊天会话；流式回答会标注**知识来源**（RAG 命中时）；可在历史页
   搜索、重命名或归档。
4. **模拟面试**：选主题、难度、题数；逐题回答，查看**四维评分**（准确性/深度/沟通/
   实用性）和参考答案；可重答单题；中途离开后**可恢复**继续；结束后看报告。
5. **能力画像**：查看跨场次维度分数、趋势、主题分解和薄弱项。
6. **学习计划**：生成学习任务、修改状态、按**间隔复习**节奏（1/3/7/14/30/60 天）复习。
7. **设置**：管理头像、主题、提醒偏好、密码和恢复码。

### 5.2 简历闭环（`RESUME_FEATURE_ENABLED=true` 时，默认关）

1. 上传**可提取文本**的 PDF/DOCX（扫描件 PDF 不会自动 OCR）；
2. 等 Worker 后台分析完成，查看**六维评分**、关键词差距、问题及证据；
3. 编辑优化稿；解决**事实警告**和待补充内容后导出 DOCX（事实门禁拦截无证据改写）；
4. 选一个已通过的分析版本，可创建"**简历定向**"模拟面试（基于简历项目和 JD 差距出题）。

> ⚠️ 简历是后台长任务。卡在"处理中"时先查 Worker 心跳/任务状态/共享卷，**不要重复
> 上传制造新资源**。

### 5.3 真实面试复盘（`REVIEW_FEATURE_ENABLED=true` 时，默认关）

1. **文本逐字稿**：可直接粘贴，**不需要转写服务**；
2. **音频**：必须三重条件齐备才开放入口——①`TRANSCRIPTION_ENABLED=true`；
   ②转写提供方完整配置；③**用户逐次明确同意外部处理**。缺任意一项，音频入口不可用；
3. 校正片段和说话人（候选人 vs 面试官），确认最新逐字稿版本后再发起分析；
4. 分批生成逐题 + 整体复盘报告，反哺能力与学习闭环。修改已确认逐字稿会使旧确认失效，
   需重新确认和分析。

> 🔒 转写成功后源音频会被删除；音频/逐字稿属 Confidential 数据，**禁止传到 Issue/日志**。

## 第 6 章 管理员使用

### 6.1 创建管理员

管理员使用**独立 `/admin` 登录面**，与产品登录**完全不混用**。创建初始管理员：

```bash
python -m scripts.create_admin --username <admin-name> --password '<strong-password>'
# 密码至少 10 字符。不要把真实密码留在 shell 历史；
# 生产应通过受控 Secret / 运维流程执行，不要明文传参。
```

### 6.2 后台五大能力

| 能力 | 说明 |
|---|---|
| **系统资源监控** | 系统资源、依赖探针（DB/Qdrant/Redis/模型）、Worker 心跳 |
| **用户与角色** | 查看用户、调整角色（user/admin） |
| **审计分析** | 脱敏审计事件、**权威**聊天/面试交互、请求关联的执行 trace、工具审计 |
| **发布台账** | 部署发布历史（来自 `scripts.record_release`） |
| **知识管理** | 知识源文件 CRUD、发起后台导入、查看版本状态、**回滚服务别名** |

> ⚠️ **读取即审计**：管理员能看见跨用户内容，**不等于**可以复制到 Issue/日志。管理员
> 读取跨用户内容这个动作本身也会被审计记录。

## 第 7 章 API 调用方

### 7.1 认证机制

- 认证开启（`AUTH_REQUIRED=true`，**生产必须**）时，产品用户用 **Bearer access token**
  调用受保护接口；管理员 token 只能从 `POST /api/admin/auth/login` 取得。
- `APP_API_KEY`（部署层可选 Bearer 防护）是**附加**保护，**不能替代**用户身份和所有权
  校验——服务端始终用解析出的 `user_id` 隔离数据。
- 公开路径白名单：`/api/config`、`/api/auth/register`、`/api/auth/login`、
  `/api/admin/auth/login`、`/api/auth/refresh`、`/api/auth/reset-password`。

### 7.2 完整路由表

**不在本文内联**——路由随代码变化。权威清单见自动生成的
[API 路由参考](generated/api-routes.md)（由 `python -m scripts.generate_docs` 生成，
禁手改）。按域分类的关键端点：

- 认证：`/api/auth/{register,login,logout,refresh,change-password,reset-password,recovery-code}`、
  `GET /api/auth/me`、`GET /api/config`（公开）
- 聊天：`POST /api/chat`、`POST /api/chat/stream`（NDJSON 流式）
- 面试：`POST /api/interviews/start`、`POST /api/interviews/{id}/answer`、
  `POST .../{id}/resume`、`POST .../turns/{i}/retry`、`GET .../report`、归档/删除
- 简历：`POST /api/resumes`、`POST /api/resumes/{id}/analyses`、
  `PATCH /api/resume-analyses/{id}/draft`、`GET .../export.docx`
- 复盘：`POST /api/interview-reviews/{audio,text}`、`PATCH .../{id}/transcript`、
  `POST .../{id}/confirm-and-analyze`、`POST .../{id}/retry`
- 能力/学习：`GET /api/capability-profile`、`/api/learning-tasks/*`、`POST .../{id}/review`
- 运维：`GET /health`、`GET /ready`、`GET /metrics`（**禁公网**）
- 管理员：`/api/admin/{system-summary,resources,runtime,users,audit-events,interactions,
  releases,knowledge/*,jobs/*,tool-audits,product-events}`

### 7.3 curl 速通：登录 → 拿 token → 发一次聊天

```bash
# 1. 注册并登录（认证关闭时这一步可省略，但生产必须开启）
curl -sS -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"你的用户名","password":"你的密码"}'
# 响应里取 access_token

# 2. 发起非流式聊天（带 Bearer）
curl -sS -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'Idempotency-Key: <随机唯一键>' \
  -d '{"session_id":"<可选>","message":"用一句话解释 G1 GC"}'

# 3. 流式聊天：按行读 NDJSON（每行一个 JSON 事件，type: token 拼接 answer）
curl -sS -N -X POST http://localhost:8000/api/chat/stream \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'Idempotency-Key: <随机唯一键>' \
  -d '{"session_id":"<可选>","message":"用一句话解释 G1 GC"}'
```

### 7.4 流式协议要点

聊天流采用 **NDJSON**（每行一个 JSON 对象）。前端解析逻辑在 `frontend/src/api/chat.ts`，
协议设计见 [流式协议](architecture/STREAMING-PROTOCOL.md)。

- `Idempotency-Key`：客户端生成的唯一键，用于幂等重试（同键只推进一次）。
- 事件类型：`type: "token"`（拼接答案）、`type: "error"`（前端抛出）等。
- **不要**把普通 JSON 客户端直接套在流式接口上——要按行读取并逐行解析。

---

# 下篇 · 运维与发布

## 第 8 章 日常运维

### 8.1 每日 / 每班检查清单

```bash
docker compose ps
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready
docker compose logs --since=15m app worker
```

同时人工检查：

- HTTP 错误率、延迟、**依赖错误**是否突增（告警见 `monitoring/alerts.yml`）；
- Worker 心跳、任务积压、重试和**终态失败**；
- PostgreSQL、Qdrant、用户文件卷**容量**；
- 当前 Qdrant 稳定别名目标和最近知识发布结果；
- 最近**备份**是否成功、恢复演练是否过期；
- 模型错误、token 用量和成本；
- 最近部署、迁移、配置或知识版本变化。

> `/health` 只表示**进程存活**；`/ready` 才检查数据库、Qdrant（serving collection）
> 和启用时的 Redis。`/metrics` 只供 Prometheus，**不能直接暴露公网**。

### 8.2 日志、指标、Trace 三件套

| 来源 | 位置 |
|---|---|
| 本地日志 | `docker compose logs app worker`；生产优先用集中日志平台 |
| 指标实现 | `app/operations.py`；规则在 `monitoring/alerts.yml` |
| Grafana 看板 | `monitoring/grafana/dashboards/interview-agent.json` |
| OTEL 配置 | `monitoring/otel-collector.yml` |
| 关联手段 | 用 **request ID** 串联日志、Trace、审计和工具执行 |

> 🔒 不要在日志/Trace/Issue 中搜索、输出或截图：用户正文、Token、Key、连接串、私人知识。

### 8.3 Worker 与任务

Worker 处理四类任务，每类都有**认领、租约、心跳、确认、重试、最大尝试次数**：

| 任务类型 | 触发 |
|---|---|
| `knowledge_import` | `POST /api/admin/knowledge/import` 或 `python -m scripts.ingest` |
| `resume_analysis` | 简历上传后入队 |
| `interview_transcription` | 音频复盘（三重条件齐备） |
| `interview_review_analysis` | 确认逐字稿后分析 |

**任务不推进时**，按顺序检查：Worker 心跳 → Redis 连接 → 队列名 → 租约/尝试次数 →
共享文件卷 → 外部提供方。**不要直接清空队列或手改数据库状态**掩盖失败。

### 8.4 备份与恢复

先做无副作用校验，再决定是否备份：

```bash
python -m scripts.backup --dry-run          # 只规划，不写
python -m scripts.backup --output backups   # 受控创建备份
python -m scripts.restore backups/<timestamp>          # 只校验 Manifest/Dump/文件哈希
python -m scripts.restore backups/<timestamp> --confirm # 破坏性恢复（见下）
```

- **备份范围**：PostgreSQL Dump + Qdrant Snapshot 元数据 + 用户文件 + SHA-256 Manifest。
- **数据分级**：备份继承最高分级，**不能提交或放入开放目录**。
- **`--confirm` 是破坏性操作**：会用 `pg_restore --clean --if-exists` 覆盖目标 PostgreSQL，
  并替换用户文件目录。只在明确环境、停写、备份当前状态、获批维护窗口后执行。
- **Qdrant 恢复**：脚本按 Manifest 恢复到**独立集合**，验证后切别名，**不会自动覆盖
  当前服务集合**。完整步骤见 [备份恢复手册](operations/BACKUP-RESTORE.md)。

### 8.5 知识库发布与回滚

发布前确认：文件有权处理、Embedding 外发获批、Qdrant 容量充足、回归阈值正确。

**发布流程**（`scripts/ingest.py` + `app/knowledge_publication.py`）：

```text
读 knowledge/ → 分块 + stable_chunk_id → 校验凭据 → 抢发布锁
  → 建版本化候选集合（不动 serving）→ 结构验证 → 可选回归 gate
  → 原子切稳定别名（DeleteAlias+CreateAlias 一次调用）→ 清版本缓存
  → 保留旧版本用于回滚。失败只删候选，绝不碰 serving。
```

需要回滚时，从管理接口选择受管理历史版本，只移动稳定别名（**不删集合**）：

```bash
GET  /api/admin/knowledge/status
POST /api/admin/knowledge/rollback
{"collection_name":"<managed-version>"}
```

> 历史集合清理前，必须确认它**既不是当前目标，也不是计划回滚目标**。

## 第 9 章 发布与回滚

### 9.1 发布最短清单

1. 明确目标环境、不可变制品摘要、负责人、窗口和回滚方案；
2. 完成质量门禁（`make harness-check`）、审批和备份；
3. 记录当前应用版本、Alembic revision、Qdrant 别名、核心数据计数（恢复点基线）；
4. Canary 用**同一制品**，由**单一迁移执行者**运行 `alembic upgrade head`；
5. 启动 App/Worker，等待 `/ready`，执行认证、核心流程和管理只读冒烟；
6. 观察错误、延迟、任务和依赖，再扩大；
7. 用 `scripts.record_release` 的**稳定 release ID 幂等记录**最终结果。

**立即停止扩大的信号**：迁移失败、持续未就绪、越权/秘密泄露、错误显著升高、重复业务
结果、知识别名指向未验证集合。

### 9.2 四个回滚面（关键：它们不一样）

| 面 | 处理 |
|---|---|
| **应用问题** | 切回兼容的上一不可变 App/Worker 制品 |
| **数据库问题** | **优先保留新 Schema**，回滚兼容应用或向前修复；Alembic downgrade ≠ 无损回滚 |
| **配置问题** | 回退前确认与当前 Schema/数据兼容 |
| **知识问题** | 切换稳定别名，**不删集合** |
| **Secret 泄露** | 轮换并撤销相关 Token，**不能只改回旧值** |

详细步骤见 [部署手册](release/DEPLOYMENT-RUNBOOK.md) 和
[回滚手册](release/ROLLBACK-RUNBOOK.md)。

### 9.3 事故响应路径

```text
用户症状
 → health / readiness
 → 请求与依赖指标
 → App / Worker 日志和 Trace
 → PostgreSQL / Redis / Qdrant / 用户文件卷
 → 模型 / Embedding / 搜索 / 转写提供方
 → 最近部署、迁移、配置或知识版本
```

跨用户泄露、数据破坏、全站不可用、Secret 泄露 → **按 SEV-1**：停止变更、限制访问、
保存证据、指定指挥和沟通责任。任何事故都要记录时间线/假设/操作/结果；恢复后更新测试、
门禁和运行手册。详见 [事故响应手册](operations/INCIDENT-RESPONSE.md)。

## 第 10 章 故障速查表

| 现象 | 先检查 | 不要做 |
|---|---|---|
| `/ready` 503 | 返回的依赖类别、DB 连接/revision、Qdrant 别名、Redis、最近变更 | 只重启后宣布恢复 |
| 聊天/面试持续 409 | 幂等键与正文、回合状态、`Retry-After`、生成开始时间 | 直接改库抢占 generating |
| Worker 不推进 | Worker 心跳、Redis、队列名、租约、尝试次数、共享卷、提供方 | 清空队列掩盖失败 |
| RAG 无结果 | 别名目标、Embedding 模型/维度、阈值、K、重排开关 | 删除服务集合重新建 |
| 简历长期处理中 | 功能开关、Worker、任务状态、模型超时、共享卷权限/容量 | 重复上传制造新资源 |
| DOCX 导出拒绝 | 事实警告、待补充项、编辑版本冲突 | 绕过事实门禁 |
| 音频无法转写 | 转写开关、完整提供方配置、用户本次同意、格式/大小/限流 | 把音频传到 Issue |
| 复盘无法分析 | 最新逐字稿是否确认、说话人、是否存在候选人回答 | 手改终态 |
| 登录失败 | 产品/管理员入口、Token 撤销、系统时间、有效期 | 记录完整 Token |
| 端口冲突 | `.env.worktree` 和 `scripts.worktree_env --print` | 硬改共享固定端口 |

更完整分支见 [故障排查](operations/TROUBLESHOOTING.md)。

---

# 附录 · 速查参考

> 这是本手册相对接手手册的核心增量：完整的目录导航、环境变量表、数据表速查、任务
> cookbook、命令和学习路线。**任何 schema/字段级细节都以代码为准**——表结构看
> `app/database.py`，配置全集看 [配置参考](generated/configuration.md)（脚本生成）。

## 附录 A 目录导航树

### A.1 后端 `app/`

```text
app/
├── main.py                    组合根：依赖装配 + 中间件 + 路由注册 + 静态托管 + 健康端点
│                              ⚠️ 不再新增业务规则（架构测试限制行数且禁 /api 装饰器）
├── config.py                  Settings(BaseSettings)：从 .env 加载所有配置
├── database.py                SQLAlchemy Core 表元数据（19 张表）+ normalize_database_url
│                              ⚠️ 只定义 schema，不依赖 API/Agent/检索/网络层
├── api/
│   ├── runtime.py             ApiRuntime 依赖容器 + 模块级单例 configure_runtime/get_runtime
│   ├── schemas.py             API 请求/响应 Schema
│   ├── security.py            授权三函数：resolve_user_id / current_product_user_id / require_role
│   ├── execution.py           run_sync()：统一把同步用例丢线程池（唯一执行边界）
│   └── routers/               9 个 domain router（适配层，只做 HTTP + 鉴权 + 映射状态码）
│       ├── auth.py            认证 + /api/agent/topology + /api/config
│       ├── chat.py            /api/chat + /api/chat/stream（流式）
│       ├── conversations.py   会话列表/归档/重命名/历史
│       ├── interviews.py      面试 start/answer/resume/retry/report/归档
│       ├── interview_reviews.py  真实面试复盘（audio/text/确认/分析）
│       ├── learning.py        能力画像 + 学习任务
│       ├── profile.py         画像/头像/提醒/今日计划/product event
│       ├── resumes.py         简历上传/分析/草稿/导出
│       └── admin.py           管理员控制面（19 端点：资源/审计/发布/知识/用户）
├── application/               应用服务层（用例编排 + 事务/并发边界）
│   ├── execution.py           SyncExecutor.run —— asyncio.to_thread 唯一出现处
│   ├── chat_service.py        ChatTurnService：幂等 begin/complete/fail/cancel
│   ├── interview_service.py   InterviewStartService + InterviewAnswerService
│   ├── resume_service.py      简历后台作业编排（owner-fenced）
│   └── interview_review_service.py  复盘后台作业编排
│
├── agent.py                   Agent 入口选择器（multi_agent_enabled 决定单/多 agent）；
│                              单 agent 在本文件内用 create_agent + 工具集构造
├── multi_agent.py             Supervisor + 4 专家（knowledge/interviewer/evaluator/planner）
├── interview_engine.py        出题/评分 prompt + JSON 解析 + 四维 clamp + build_report
├── resume_engine.py           简历解析(PDF/DOCX) + analyze_resume + 事实警告 + DOCX 导出
├── interview_review_engine.py 复盘分析引擎（批量打分）
├── resume_interview.py        从简历评估构建最小化面试上下文
│
├── chat_context.py    ★纯计算  上下文窗口规划（token 预算 + 摘要折叠 + sha 指纹）
├── learning.py        ★纯计算  学习任务候选 + 间隔复习时间
├── chunks.py          ★纯计算  stable_chunk_id（uuid5 确定性 Qdrant point id）
├── evaluation.py      ★纯计算  RAG 指标：ndcg/hit@k/mrr/citation
├── capability.py      ★纯计算  跨场次能力画像聚合
├── chunking.py                分块（RecursiveCharacterTextSplitter + 标题上下文继承）
│
├── model_gateway.py   ★唯一   外部 chat/embedding 构造点：预算/并发/超时/重试/指标/token
├── rag.py                     Qdrant vector store 工厂 + serving 别名解析 + 版本化缓存
├── knowledge_publication.py   知识发布：锁/候选/验证/原子切别名/回滚
├── reranker.py / lexical_reranker.py / llm_reranker.py  三种重排实现
├── tools.py                   Agent 工具：search_interview_knowledge / search_public_web 等
├── tool_context.py            工具执行审计上下文
├── transcription.py           音频转写 provider（httpx，需逐次同意）
├── user_files.py              用户文件落盘 + content-type/大小限制
│
├── storage.py        (3466行) ConversationStore：所有事务脚本（每个 mutation 一个事务）
├── operations.py    (711行)  RedisRuntime + metrics + 限流（Lua 脚本队列/锁/心跳）
├── auth.py                    AuthService：scrypt 哈希 + token_digest + 双 token + 登录面分离
├── system_resources.py        管理员脱敏资源清单（含 httpx probe）
├── request_audit.py           audit_api_request（每请求记 audit_events，脱敏）
├── telemetry.py               OTEL FastAPI/SQLAlchemy instrumentation 开关
└── logging_config.py          结构化日志 + request_id contextvar
```

> ★ 标记是架构测试强制纯度的模块（禁 infra 依赖）/ 唯一收口点。

### A.2 前端 `frontend/src/`

```text
frontend/src/
├── main.ts             入口（createPinia + router + 样式注入）
├── App.vue             根壳（RouterView + ToastStack + ConfirmDialog + 主题初始化）
├── types.ts            共享类型
├── router/index.ts     路由（产品页都映射 AppView.vue，靠 route.meta.mode 切面板）
├── views/              AppView.vue（产品壳）、AdminView.vue（后台壳）
├── components/
│   ├── app/            业务面板：Today/Chat/Interview/Profile/Learning/History/
│   │                   Resume/ReviewPanel + Sidebar/Topbar/AuthOverlay/GoalSetup 等
│   ├── admin/          AdminOverview/Users/Resources/Audits/Releases/Knowledge/Analytics
│   └── ui/             UiButton、UiState 等基础组件
├── stores/             Pinia：auth/chat/interviews/learning/profile/resumes/reviews/
│                       admin/adminAuth/theme/toast（auth 用 localStorage 持久化）
├── api/                领域 API 客户端 + client.ts；chat.ts 实现流式 NDJSON 解析
├── composables/        confirm.ts
├── lib/                adminResources/focusTrap/format/markdown/observability
└── styles/             分区 CSS（base/app/components/admin/chat/interview/profile/...）
```

### A.3 其他关键目录

```text
migrations/versions/     16 个 Alembic 迁移（线性链，命名 YYYYMMDD_NNNN_主题.py）
scripts/                 管理脚本（见附录 E 命令速查）
tests/                   后端测试 ~56 文件（架构/契约/迁移/应用服务/运维/AI 评估）
frontend/e2e/            10 个 Playwright spec（桌面+移动，E2E 端口由 worktree_env 派生）
eval/                    RAG/Agent/业务模型评估数据集（jsonl）+ reports/
monitoring/              prometheus.yml / alerts.yml / otel-collector.yml / grafana/
deploy/nginx/            生产 gateway nginx.conf（/metrics 返回 404）
docs/                    全生命周期文档（见 docs/README.md）
```

## 附录 B 环境变量分组速查

> 全集以 [`.env.example`](../.env.example) 和
> [生成配置参考](generated/configuration.md) 为准。下表是分组速查，默认值取自
> `.env.example`。

### B.1 模型（GLM chat）

| 变量 | 默认 | 作用 / 提示 |
|---|---|---|
| `ZHIPU_API_KEY` | 占位 | 智谱 **Coding Plan** Key（与标准 Key 可能不通用） |
| `ZHIPU_MODEL` | `glm-5.2` | chat 模型 |
| `ZHIPU_API_BASE` | `.../coding/paas/v4` | Coding Plan 端点 |
| `MULTI_AGENT_ENABLED` | `true` | true=supervisor 多 agent；false=单 agent |
| `LLM_TIMEOUT_SECONDS` | `45` | 网关超时；简历/复盘另设 |
| `LLM_MAX_RETRIES` | `2` | 网关重试；简历/复盘默认 0 |
| `LLM_MAX_CONCURRENCY` | `8` | 并发槽 |
| `LLM_INPUT_CHAR_BUDGET` | `60000` | 调用前输入字符预算门控 |
| `LLM_MAX_OUTPUT_TOKENS` | `2000` | 输出上限 |
| `CHAT_CONTEXT_TOKEN_BUDGET` | `12000` | 上下文窗口 token 预算 |
| `CHAT_SUMMARY_TOKEN_BUDGET` | `2000` | 折叠摘要预算 |

### B.2 Embedding / Qdrant

| 变量 | 默认 | 作用 / 提示 |
|---|---|---|
| `ZHIPU_EMBEDDING_API_KEY` | 占位 | 智谱**标准 API**（与 Coding Plan Key 不同） |
| `ZHIPU_EMBEDDING_MODEL` | `embedding-2` | dense embedding |
| `SPARSE_EMBEDDING_MODEL` | `Qdrant/bm25` | sparse（HYBRID 检索） |
| `QDRANT_URL` | `http://localhost:6333` | Compose 会覆盖容器内地址 |
| `QDRANT_COLLECTION` | `interview_knowledge` | 物理版本前缀 |
| `QDRANT_COLLECTION_ALIAS` | `interview_knowledge_current` | 稳定读别名 |
| `KNOWLEDGE_PUBLISH_LOCK_SECONDS` | `3600` | 发布锁 TTL，应覆盖一次完整发布 |

### B.3 数据库

| 变量 | 默认 | 作用 / 提示 |
|---|---|---|
| `CONVERSATION_DB_PATH` | `data/interview-agent.db` | SQLite 路径（本地/测试） |
| `DATABASE_URL` | 空 | **生产用 PostgreSQL**；空时回退 SQLite 路径 |
| `AUTO_CREATE_SCHEMA` | `true` | ⚠️ **生产必须 false**（compose 已覆盖），schema 归 Alembic |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | interview / interview / 占位 | Compose PG |

### B.4 认证与限流

| 变量 | 默认 | 作用 / 提示 |
|---|---|---|
| `AUTH_REQUIRED` | `false` | ⚠️ **生产必须 true** |
| `APP_API_KEY` | 空 | 部署层附加 Bearer 防护（可选，不替代用户授权） |
| `ACCESS_TOKEN_MINUTES` | `60` | access token 有效期 |
| `REFRESH_TOKEN_DAYS` | `30` | refresh token 有效期 |
| `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` | `30` / `60` | 按 client host 共享限流 |

### B.5 检索与重排

| 变量 | 默认 | 作用 / 提示 |
|---|---|---|
| `RETRIEVAL_CANDIDATE_K` | `20` | 候选数 |
| `RETRIEVAL_FINAL_K` | `4` | 最终返回数 |
| `RETRIEVAL_MIN_SCORE` | `0` | 完成评估后再调 |
| `DENSE_RELEVANCE_MIN_SCORE` | `0.4` | Embedding-2 拒答阈值 |
| `LEXICAL_RERANKER_ENABLED` | `false` | 轻量词法重排（无需下载模型） |
| `LLM_RERANKER_ENABLED` | `false` | GLM 列表式重排（增加延迟/调用） |
| `RERANKER_ENABLED` | `false` | 本地 Cross-Encoder（启用替代轻量重排） |
| `RERANKER_MODEL` | `Xenova/bge-reranker-base` | — |

### B.6 搜索与评估门禁

| 变量 | 默认 | 作用 / 提示 |
|---|---|---|
| `WEB_SEARCH_ENABLED` | `false` | ⚠️ 默认关；启用后查询**外发**第三方 |
| `WEB_SEARCH_API_KEY` / `WEB_SEARCH_API_URL` | 空 / tavily | 外部搜索服务 |
| `INGEST_RUN_EVALUATION` | `false` | 导入后跑 chunk 回归 |
| `RAG_REGRESSION_MIN_NDCG` | `0` | nDCG@10 门禁阈值 |

### B.7 Redis

| 变量 | 默认 | 作用 / 提示 |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Worker 必需 |
| `REDIS_CACHE_TTL_SECONDS` | `300` | RAG 缓存 TTL |
| `REDIS_QUEUE_NAME` | `interview-agent:jobs` | 任务队列 |

### B.8 简历中心（默认关）

| 变量 | 默认 | 作用 / 提示 |
|---|---|---|
| `RESUME_FEATURE_ENABLED` | `false` | 开启前确保 App/Worker 共享 `USER_FILES_DIR` |
| `USER_FILES_DIR` | `data/user-files` | ⚠️ App 与 Worker 必须指向**同一持久卷** |
| `RESUME_MAX_UPLOAD_BYTES` | `10485760` | 10MB |
| `RESUME_PROMPT_VERSION` | `resume-analysis-v1` | prompt 版本化 |
| `RESUME_ANALYSIS_TIMEOUT_SECONDS` | `180` | 独立于聊天超时 |
| `RESUME_ANALYSIS_MAX_RETRIES` | `0` | 队列已提供有界重试 |

### B.9 面试复盘与转写（默认关）

| 变量 | 默认 | 作用 / 提示 |
|---|---|---|
| `REVIEW_FEATURE_ENABLED` | `false` | 复盘总开关 |
| `TRANSCRIPTION_ENABLED` | `false` | 音频转写；需完整提供方配置 + 用户逐次同意 |
| `TRANSCRIPTION_API_URL` / `TRANSCRIPTION_API_KEY` | 空 | 提供方 |
| `TRANSCRIPTION_TIMEOUT_SECONDS` | `120` | — |
| `REVIEW_MAX_AUDIO_BYTES` | `26214400` | 25MB |
| `REVIEW_PROMPT_VERSION` | `interview-review-v1` | — |
| `REVIEW_ANALYSIS_BATCH_SIZE` | `6` | 长面试分批 |
| `REVIEW_ANALYSIS_TIMEOUT_SECONDS` / `MAX_RETRIES` | `180` / `0` | — |

### B.10 观测

| 变量 | 默认 | 作用 / 提示 |
|---|---|---|
| `LOG_LEVEL` | `INFO` | — |
| `JSON_LOGS` | `true` | 结构化日志 |
| `OTEL_ENABLED` | `false` | 本地可关 |
| `OTEL_SERVICE_NAME` | `interview-agent` | — |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318/v1/traces` | OTLP HTTP |

### B.11 Secret 文件（免写 .env，Docker/K8s 挂载）

`ZHIPU_API_KEY_FILE`、`ZHIPU_EMBEDDING_API_KEY_FILE`、`WEB_SEARCH_API_KEY_FILE`、
`APP_API_KEY_FILE` —— 设置后无需把密钥写入 `.env`。

### B.12 前端 / 网关 / 运维探针

| 变量 | 默认 | 作用 |
|---|---|---|
| `FRONTEND_DIST` | 空 | 留空自动探测 `frontend/dist`，否则回退 `app/web/` |
| `GATEWAY_HTTP_PORT` | `80` | 生产公网仅此端口 |
| `WORKER_HEARTBEAT_INTERVAL_SECONDS` / `WORKER_HEARTBEAT_TTL_SECONDS` | `5` / `20` | Worker 活信号 |
| `RESOURCE_PROBE_TIMEOUT_SECONDS` | `2` | 管理员资源探针超时 |
| `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` | admin / 占位 | Grafana 初始凭证 |

## 附录 C 关键数据表速查

> 19 张表都在 `app/database.py`（SQLAlchemy Core `Table`，**非 ORM**）。下表是一句话职责
> 速查，**字段级以 `app/database.py` 和 [数据字典](generated/data-dictionary.md) 为准**。

| 表 | 职责一句话 |
|---|---|
| `users` | 用户账号（scrypt 密码哈希、角色、恢复码） |
| `auth_tokens` | access/refresh token 的 sha256 摘要（不存明文） |
| `user_profiles` | 目标岗位/方向/JD、头像、提醒偏好 |
| `conversations` | 聊天会话（归档、重命名） |
| `messages` | 聊天历史消息（不可变真理来源） |
| `chat_turns` | 聊天回合生命周期（pending/generating/completed/failed/cancelled + claim_token + 双幂等唯一约束） |
| `interviews` | 模拟面试实例（主题、进度、归档） |
| `interview_turns` | 面试回合（题目、用户答案、四维评分、参考答案） |
| `interview_answer_attempts` | 面试答题幂等记录（Idempotency-Key 去重） |
| `learning_tasks` | 学习任务 + 间隔复习状态 |
| `resume_documents` | 简历文件资源记录（owner-fenced） |
| `resume_analyses` | 简历评估结果（claim_token、revision、prompt_version、model_version） |
| `interview_reviews` | 真实面试复盘（external_processing_consent、transcript_revision、confirmed_revision） |
| `interview_review_turns` | 复盘逐题分析 |
| `tool_audit_logs` | Agent 工具调用审计（仅存截断摘要，**不存原始 prompt/凭据**） |
| `audit_events` | API 操作审计（脱敏） |
| `execution_traces` | 模型/工具阶段 + 安全元数据（不复制 prompt/凭据/私有知识正文） |
| `product_events` | 产品埋点事件 |
| `deployment_releases` | 部署发版台账（record_release 幂等写入） |

## 附录 D 常见任务 cookbook

### D.1 我要新增一个 API 端点

1. **改对层**：HTTP 校验/状态码/响应 DTO 放 `app/api/routers/<域>.py` + `schemas.py`；
   完整用例放 `app/application/`；路由通过 `get_runtime()` 拿依赖、`run_sync()` 派发。
2. **鉴权**：用户资源用 `resolve_user_id(request, claimed_user_id)`；新式 API（不收 client
   user_id）用 `current_product_user_id(request)`；管理路由用 `require_role`。
3. **可重试写**：在 [feature-contract](product-specs/feature-contract.json) 定义幂等键或
   乐观并发语义。
4. **测试**：API 契约测试覆盖匿名、当前用户、**另一用户越权**、管理员场景。
5. **文档**：跑 `python -m scripts.generate_docs` 重生成 `docs/generated/api-routes.md`
   （**不要手改 generated**）。

### D.2 我要改数据库表结构

⚠️ **不要只改 `app/database.py`**。正确步骤：

1. 改 `app/database.py` 元数据 + `app/storage.py` 事务脚本行为；
2. 在 `migrations/versions/` 新建**连续** Alembic revision（命名 `YYYYMMDD_NNNN_主题.py`，
   `down_revision` 指向当前 head）；
3. 对既有数据定义**回填/兼容**行为（生产发布优先向前兼容）；
4. 更新功能契约、数据字典来源（跑 `generate_docs`）和测试；
5. 验证：

```bash
alembic upgrade head
pytest -q tests/test_migrations.py
# PostgreSQL 专项行为：配 TEST_POSTGRES_URL 后跑标 integration 的测试
```

> Alembic downgrade ≠ 无损回滚。

### D.3 我要接入一个新的模型调用

⚠️ **必须走 `app/model_gateway.py`**（架构测试强制：`langchain_openai` 只允许在此出现）。

1. 用 `create_chat_model(purpose, ...)` 或 `create_embeddings(...)`，传入 `purpose`
   （用作 metric 维度，如 `knowledge`/`evaluator`/`my_new_feature`）；
2. 网关自动提供：输入预算门控 + 并发槽 + timeout/retry + metric + token 计费 + 安全错误
   映射（不泄露 provider 细节）；
3. Prompt 和结构化输出要**版本化**（DB 表里有 `prompt_version`/`model_version` 列）；
4. 复杂输出用正则提取 JSON + Pydantic 校验，**不要**直接信任自由文本 JSON；
5. 如果是新的外发数据流（搜索/转写类），加工具审计（`_run_audited`）并评估数据分级。

### D.4 我要加一个前端页面

1. 路由：在 `frontend/src/router/index.ts` 加路由，复用 `AppView.vue` + `route.meta.mode`；
2. 组件：懒加载业务组件放 `components/app/`；状态放对应 `stores/`；
3. API 客户端：在 `api/` 加领域文件，复用 `client.ts`；流式用 `chat.ts` 模式；
4. **覆盖所有状态**：加载、空、失败、权限不足、小屏、键盘；
5. 验证：`npm --prefix frontend run type-check` / `test` / `build`；关键旅程加 E2E
   （`frontend/e2e/`）。

### D.5 我要发布一个新版本

见 [第 9 章](#91-发布最短清单)。核心：完成 `make harness-check` → 记录恢复点基线 →
Canary 用同一制品、单一迁移执行者 → 等 `/ready` → 冒烟 → 观察 →
`scripts.record_release` 幂等记录。

### D.6 Worker 任务卡住了怎么排查

按顺序：① Worker 心跳（`WORKER_HEARTBEAT_TTL_SECONDS`）→ ② Redis 连接/队列名 →
③ 任务租约/尝试次数（看 `jobs/{job_id}` 状态）→ ④ App/Worker 是否共享同一
`USER_FILES_DIR` → ⑤ 外部提供方（模型/转写）是否可用。**不要清空队列或手改终态**。

### D.7 我要备份和恢复

见 [第 8.4 节](#84-备份与恢复)。核心：先 `--dry-run` → `--output backups` 建备份 →
不带 `--confirm` 只校验 → `--confirm` 才破坏性恢复（且 Qdrant 恢复到独立集合再切别名）。

### D.8 我要回滚知识库

```bash
GET  /api/admin/knowledge/status     # 找到目标 managed-version
POST /api/admin/knowledge/rollback   # {"collection_name":"<managed-version>"}
```

只移动稳定别名，**不删集合**。清理历史集合前确认它既非当前目标也非回滚目标。

## 附录 E 命令速查

```bash
# ─── 环境与启动 ─────────────────────────────────────────────
python3 -m venv .venv && source .venv/bin/activate
pip install --require-hashes -r requirements.txt
npm ci --prefix frontend
cp .env.example .env

# Worktree 隔离 Compose 栈（推荐）
make worktree-env
make stack-config
make stack-up
python -m scripts.worktree_env --root . --print   # 查实际端口
make stack-down                                     # 停止（不删卷）

# 前后端分开开发
docker compose up -d postgres redis qdrant
alembic upgrade head
uvicorn app.main:app --reload --port 8000          # 终端1
npm --prefix frontend run dev                       # 终端2 (5173)

# ─── 数据库 ─────────────────────────────────────────────────
alembic current
alembic heads
alembic upgrade head
pytest -q tests/test_migrations.py

# ─── 验证（从小到大）─────────────────────────────────────────
pytest -q tests/<file>.py       # 单个后端测试
make harness-static             # 架构 + 契约 + 可复现性（无需外部服务）
make backend-check              # compileall + 全后端 pytest
make frontend-check             # 工具链/类型/单测/构建/Bundle
make e2e                        # Playwright 桌面+移动
make harness-check              # 仓库级完整门禁

# ─── 运行与运维 ─────────────────────────────────────────────
docker compose ps
docker compose logs --since=15m app worker
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready

# ─── 受控管理操作 ───────────────────────────────────────────
python -m scripts.create_admin --username <name> --password '<pw>'   # 建管理员(≥10字符)
python -m scripts.ingest                          # 知识导入（外发+改别名，非测试步骤）
python -m scripts.backup --dry-run                # 备份预演
python -m scripts.backup --output backups         # 创建备份
python -m scripts.restore backups/<timestamp>     # 校验备份
python -m scripts.restore backups/<timestamp> --confirm  # 破坏性恢复
python -m scripts.generate_docs                   # 重生成 docs/generated（禁手改）
python -m scripts.record_release --release-id <id> ...   # 幂等记录发版
make lock-python                                  # 重生成带哈希 requirements.txt

# ─── 停止 ───────────────────────────────────────────────────
make stack-down     # 停 Worktree 栈（不删卷）
```

## 附录 F 进阶学习路线

### F.1 独立值守前能力清单

- [ ] 能解释 **health vs ready** 区别、任务租约机制、聊天/面试幂等、Qdrant 别名发布；
- [ ] 能在**不查看用户正文**的情况下，用指标、request ID、日志和 Trace 定位问题；
- [ ] 完成一次**隔离环境**备份校验和恢复演练；
- [ ] 跟随一次 Canary 发布和应用/知识**回滚演练**；
- [ ] 知道 **SEV-1 停止条件**、升级路径和证据保护规则。

### F.2 关键设计文档阅读顺序

按"越靠后越深"的顺序读 `docs/design-docs/`（持久技术决策，含 context/decision/alternatives）：

1. [synchronous-persistence-boundary](design-docs/synchronous-persistence-boundary.md) —
   为什么同步 Core + 唯一 SyncExecutor；
2. [model-policy-gateway](design-docs/model-policy-gateway.md) — 为什么模型调用收敛到网关；
3. [durable-chat-turn-lifecycle](design-docs/durable-chat-turn-lifecycle.md) —
   聊天回合生命周期与为什么 generating 不自动接管；
4. [interview-answer-idempotency](design-docs/interview-answer-idempotency.md) —
   面试答题幂等与并发认领；
5. [durable-redis-jobs](design-docs/durable-redis-jobs.md) — Redis 可靠任务队列；
6. [qdrant-versioned-publication](design-docs/qdrant-versioned-publication.md) —
   版本化知识发布与原子别名切换；
7. [chat-context-budget](design-docs/chat-context-budget.md) — 上下文 token 预算；
8. [reproducible-builds](design-docs/reproducible-builds.md) / [worktree-stack-isolation](design-docs/worktree-stack-isolation.md) /
   [frontend-toolchain-audit](design-docs/frontend-toolchain-audit.md) — 工程基础设施。

### F.3 其他建议入口

- 想补 Agent 工程原理：[从零到企业级 Agent 工程课程](enterprise-agent-engineering-course.md)（12 周）；
- 想快速查命令/概览：[开发、运维与使用接手手册](ENGINEERING-HANDOVER-MANUAL.md)；
- 想懂系统边界：[架构总纲](../ARCHITECTURE.md) + [功能契约](product-specs/feature-contract.json)。

---

## 遇到文档不一致时

先用测试、数据库约束和实际代码建立事实，再在**同一个变更**中更新过时文档。不要因为
README 写了某行为就绕过验证，也不要只修代码而留下错误运行步骤。架构性分歧记录在设计
文档/决策日志；未完成的边界问题登记 [技术债](tech-debt-tracker.md)；生产事故同步更新
运行手册和复盘。
