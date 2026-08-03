# Interview Agent 开发、运维与使用接手手册

> 面向第一次接手本项目的初级工程师。本文是“如何开始工作”的统一入口，不替代
> 功能契约、生成参考和专项运行手册。发生冲突时，按“测试/数据库约束 → 功能契约
> → 架构与设计文档 → 本手册”的优先级判断。

## 1. 先记住这几件事

1. 这是一个 **FastAPI + Vue 的模块化单体**，部署单元是 App 和独立 Worker，
   不是微服务集群。
2. PostgreSQL/SQLite 保存业务事实；Redis 保存共享限流、缓存和可恢复任务；
   Qdrant 保存版本化私人知识索引；用户文件卷保存简历、头像和临时音频。
3. `app/main.py` 只应负责装配、中间件、健康检查和前端托管，不能继续堆业务规则。
4. 生产 Schema 只能通过 Alembic 演进。`AUTO_CREATE_SCHEMA` 仅适合本地和隔离测试。
5. 用户数据必须用服务端认证得到的 `user_id` 隔离；客户端传入 ID 不能作为授权。
6. 模型、Embedding、搜索和转写都可能把数据发给第三方；没有审批和明确开关时不要
   启用，也不要运行 Live 评估。
7. 知识发布必须“建候选 → 验证 → 原子切别名”，不能删除当前服务集合来重新导入。
8. App 与 Worker 必须共享同一个 `USER_FILES_DIR` 持久卷，否则简历和复盘任务会
   找不到用户文件。
9. 仓库级交付门禁是 `make harness-check`。不能运行时必须说明缺少什么、实际跑了
   什么，不能静默换成更弱验证。
10. 不提交 `.env`、Token、Key、数据库 Dump、备份、用户数据或私人知识正文。
11. Agent只使用用户确认的训练记忆；工具外发和业务变更遵循DLP及预览确认；持久运行
    的命令步骤依赖所有者围栏、幂等结果重放和显式恢复。

建议把以下文档加入书签：

- [架构总纲](../ARCHITECTURE.md)
- [机器可读功能契约](product-specs/feature-contract.json)
- [开发指南](development.md)
- [API 路由参考](generated/api-routes.md)
- [配置参考](generated/configuration.md)
- [运维手册](operations/OPERATIONS-MANUAL.md)
- [故障排查](operations/TROUBLESHOOTING.md)
- [部署手册](release/DEPLOYMENT-RUNBOOK.md)

## 2. 系统全景

```text
浏览器
  |
  | HTTP / 流式 NDJSON
  v
Nginx Gateway（生产统一入口）
  |
  v
FastAPI App ─────────────── Vue 静态产物
  |  |  |  |  \
  |  |  |  |   `─ 模型 / Embedding / 可选搜索
  |  |  |  `──── 用户文件卷（与 Worker 共享）
  |  |  `─────── Qdrant（版本化知识集合 + 稳定别名）
  |  `────────── Redis（限流、缓存、任务）
  `───────────── PostgreSQL（生产）/ SQLite（快速本地测试）
                         ^
                         |
Worker ── 领取、续租、重试、确认后台任务

Prometheus <- /metrics <- App -> OTEL Collector -> Trace 后端
Grafana    <- Prometheus
```

### 2.1 组件职责

| 组件 | 负责 | 不负责/注意事项 |
|---|---|---|
| Vue 前端 | 页面、路由、状态、API 调用、流式渲染 | 不承担授权；隐藏按钮不是安全控制 |
| FastAPI App | HTTP 校验、认证、用例编排、静态前端、健康和指标 | 不应在事件循环直接跑阻塞数据库操作 |
| Worker | 知识导入、简历分析、音频转写、复盘分析 | 需要 Redis，且与 App 共享知识/用户文件卷 |
| PostgreSQL | 用户、会话、面试、学习、审计、任务资源状态 | 生产迁移归 Alembic，不用 `create_all` |
| Agent应用层 | 预算上下文、训练记忆、确认、运行/步骤、反馈和模型路由 | LangGraph不是业务状态来源，模型不能自行授权变更 |
| Redis | 限流、RAG 缓存、持久任务、租约和心跳 | 不能用清队列掩盖任务失败 |
| Qdrant | 混合检索的私人知识分块与向量 | 当前别名目标不可作为临时测试删除 |
| Gateway | 公网入口、反向代理和安全响应头 | App、数据服务和指标端口不应直接暴露公网 |
| Prometheus/Grafana/OTEL | 指标、看板和 Trace | 不是请求正确性边界，标签不能带用户正文 |

### 2.2 主要业务链路

- **聊天**：请求鉴权 → 创建/认领持久回合 → 规划有预算的上下文 → RAG/Agent →
  模型网关 → 声明级证据/流式返回 → 用户/助手消息一起持久化 → 可选回合反馈。失败或
  取消不会留下孤立正式消息。
- **个性化训练**：服务端预算上下文 + 已确认记忆 → 生成训练预览 → 用户确认 →
  持久Agent运行/步骤原子创建去重任务；重复确认重放结果，过期领取可安全恢复。
- **模拟面试**：创建面试 → 生成题目 → 幂等提交回答 → 评分和反馈 → 下一题/报告
  → 更新能力画像和学习任务。同键重试重放结果，并发提交只允许一个所有者执行。
- **简历评估**：上传 PDF/DOCX → 保存用户文件和资源记录 → Redis 入队 → Worker
  解析和模型分析 → 证据化报告 → 乐观版本编辑 → 通过事实门禁后导出 DOCX。
- **真实面试复盘**：文本或经明确同意的音频 → 转写/编辑说话人 → 确认最新逐字稿
  → 分批分析 → 整体及逐题报告 → 能力与学习闭环。修改逐字稿会使旧确认失效。
- **知识发布**：读取 `knowledge/` → 分块和稳定 ID → 创建版本化集合 → 结构/可选
  回归验证 → 原子切换稳定别名 → 清版本缓存 → 保留上一版本用于回滚。

## 3. 仓库地图与修改落点

| 路径 | 内容 | 常见修改 |
|---|---|---|
| `app/api/routers/` | HTTP 路由适配器 | 状态码、请求校验、鉴权依赖、响应 DTO |
| `app/api/schemas.py` | API Schema | 请求/响应字段 |
| `app/application/` | 应用服务 | 跨存储/模型的用例编排、事务与并发边界 |
| `app/*.py` | 领域、存储和基础设施适配器 | 计算规则、SQL、RAG、模型、观测 |
| `app/database.py` | SQLAlchemy 表元数据 | 配合 Alembic 修改 Schema |
| `app/main.py` | 组合根 | 依赖装配、中间件、路由注册；不要新增业务规则 |
| `frontend/src/api/` | 前端 API 客户端 | 契约调用、流式协议解析 |
| `frontend/src/stores/` | Pinia 状态 | 页面数据和异步状态 |
| `frontend/src/components/` | 组件 | 可复用 UI |
| `frontend/src/views/` | 页面壳 | 产品和管理后台布局 |
| `frontend/src/styles/` | 分区样式 | 设计 Token、页面响应式样式 |
| `migrations/versions/` | Alembic 历史 | 生产数据库变更 |
| `scripts/` | 管理、导入、评估、备份和 Worker 命令 | 运维入口 |
| `tests/` | 后端、契约、迁移、架构测试 | 后端行为证据 |
| `frontend/e2e/` | Playwright 验收 | 桌面/移动关键用户旅程 |
| `eval/` | RAG、Agent 和业务模型评估 | AI 行为回归 |
| `monitoring/` | Prometheus、告警、Grafana、OTEL | 运行信号 |
| `docs/` | 产品到运维全生命周期文档 | 与行为一起更新 |

依赖方向必须保持：

```text
API 适配器 -> 应用服务 -> 纯领域规则
                       <- 基础设施实现
```

纯计算模块不能引入 FastAPI、SQLAlchemy、Redis、Qdrant、HTTP 或模型 SDK；
`app/database.py` 不能依赖 API、Agent、检索或网络层；任何模块都不能反向导入
`app.main`。这些规则由 `tests/test_architecture.py` 执行检查。

## 4. 第一次本地启动

### 4.1 前置条件

- 推荐 Python **3.12**（开发文档最低 3.11，但镜像和 CI 使用 3.12）；
- Node.js **20.19+**、npm；
- Docker 和 Docker Compose；
- 真实聊天使用智谱 Coding Plan Key；
- 真实 Embedding/知识导入使用智谱标准 API Key。

默认自动化测试不要求真实模型凭据。先检查版本：

```bash
python3 --version
node --version
npm --version
docker --version
docker compose version
```

### 4.2 安装依赖

在仓库根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.txt
npm ci --prefix frontend
cp .env.example .env
```

只修改本地 `.env`，不要提交。第一次只需要理解这些配置组：

| 配置组 | 关键字段 | 本地建议 |
|---|---|---|
| 模型 | `ZHIPU_API_KEY`、`ZHIPU_MODEL` | 不做 Live 调用可暂不配置有效 Key |
| Embedding | `ZHIPU_EMBEDDING_API_KEY` | 不导入知识可暂不配置 |
| 数据库 | `DATABASE_URL`、`CONVERSATION_DB_PATH` | Compose 使用 PostgreSQL；单进程可用 SQLite |
| Redis/Qdrant | `REDIS_URL`、`QDRANT_URL`、别名 | Compose 会覆盖容器内地址 |
| 认证 | `AUTH_REQUIRED`、Token 时长 | 本地按任务选择；生产必须为 `true` |
| 可选功能 | `RESUME_FEATURE_ENABLED`、`REVIEW_FEATURE_ENABLED` | 默认关闭，按需求显式开 |
| 用户文件 | `USER_FILES_DIR` | App/Worker 必须指向共享持久目录 |
| 观测 | `JSON_LOGS`、`OTEL_ENABLED` | 本地可关闭 OTEL |

全部字段以[生成配置参考](generated/configuration.md)和
[`.env.example`](../.env.example)为准。

### 4.3 推荐：启动隔离 Compose 栈

```bash
make worktree-env
make stack-config
make stack-up
python -m scripts.worktree_env --root . --print
docker compose --env-file .env --env-file .env.worktree ps
```

每个 Worktree 会得到稳定且不同的 Compose project、主机端口、网络和卷。请使用
最后一条 `--print` 的实际端口，不要假设一定是 8000/3000。

Compose 中 App 容器启动时会先执行 `alembic upgrade head`；Worker 在 Redis、
PostgreSQL 和 Qdrant 健康后启动。验证：

```bash
curl -fsS http://127.0.0.1:<APP_HOST_PORT>/health
curl -fsS http://127.0.0.1:<APP_HOST_PORT>/ready
docker compose --env-file .env --env-file .env.worktree logs --since=10m app worker
```

停止当前 Worktree 栈：

```bash
make stack-down
```

`stack-down` 不带 `-v`，不会顺手删除持久卷。不要为了“重来一次”随意删除卷。

### 4.4 前后端分开开发

先只启动依赖：

```bash
docker compose up -d postgres redis qdrant
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

第二个终端：

```bash
source .venv/bin/activate
npm --prefix frontend run dev
```

Vite 默认在 `5173`，把 `/api`、`/health`、`/ready` 和 `/metrics` 代理到
`localhost:8000`。浏览器开发入口用 `http://localhost:5173`，OpenAPI 用
`http://localhost:8000/docs`。

知识问答需要知识内容时，把获准的 `.md`/`.txt` 放入 `knowledge/`，配置
Embedding 后再执行：

```bash
python -m scripts.ingest
```

此操作会调用外部 Embedding 并修改 Qdrant 服务别名，不是普通单元测试步骤。

## 5. 开发一个变更的标准流程

### 5.1 动手前

1. 阅读根目录 `AGENTS.md`、[架构总纲](../ARCHITECTURE.md)和相关设计文档。
2. 在[功能契约](product-specs/feature-contract.json)找对应 feature ID、状态和验证。
3. 检查[活动执行计划](exec-plans/active/)与[技术债](tech-debt-tracker.md)。
4. 查看当前工作区变化，确认哪些是别人的工作；不要混入无关清理。
5. 写清“期望行为”和最小验收标准。跨模块、改正确性边界或无法短时完成时建立
   执行计划。

### 5.2 选择正确层

- 只改 HTTP 字段/状态码：路由和 Schema，同时更新 API 测试。
- 改完整用例：放 `app/application/`，路由只负责适配。
- 改纯计算/状态规则：放独立领域模块，并写无外部依赖的单元测试。
- 改数据库：元数据 + Alembic Revision + 迁移测试 + 历史数据回填验证。
- 新增模型调用：必须走 `app/model_gateway.py`，定义超时、重试、指标、成本和安全
  错误；Prompt/Schema/模型要版本化，复杂输出走 `agent_contracts.py` 有界结构化边界。
- 新增模型工具：公开外发先过确定性DLP；检索正文标记为不可信证据；审计只保存安全
  元数据；产生变更时先预览并使用所有者/内容绑定确认。
- 改用户资源：所有读写都带服务端解析的 `user_id`，测试另一用户越权失败。
- 改可重试写入：在功能契约中定义幂等键或乐观并发语义。
- 改前端：同步覆盖加载、空、失败、权限不足、小屏和键盘状态。

### 5.3 数据库变更

不要只改 `app/database.py`。正确步骤：

1. 修改元数据和存储行为；
2. 在 `migrations/versions/` 新建连续 Alembic Revision；
3. 对既有数据定义回填/兼容行为；
4. 更新功能契约、数据字典来源、中文镜像和测试；
5. 至少执行：

```bash
alembic upgrade head
pytest -q tests/test_migrations.py
```

PostgreSQL 专项行为需配置隔离的 `TEST_POSTGRES_URL`。生产发布优先向前兼容；
Alembic downgrade 不等于无损回滚。

### 5.4 文档和契约

行为变化必须同步：

- `docs/product-specs/feature-contract.json`：功能状态和可执行验证；
- 架构/设计文档：边界、替代方案或持久决策；
- 运维/安全文档：新增信号、故障方式、数据流或恢复步骤；
- 生成参考和中文镜像：运行 `make docs-generate`，不要手改 `docs/generated/` 或
  `docs/zh-CN/`。

只有存在可执行 verification reference 时，feature 才能标记为 `passing`。

## 6. 测试与质量门禁

### 6.1 从小到大运行

```bash
# 单个后端测试
pytest -q tests/<relevant_file>.py

# 架构、Harness 契约、可复现性
make harness-static

# 编译和全部后端测试
make backend-check

# 前端工具链、类型、单测、构建和 Bundle 预算
make frontend-check

# Playwright 桌面和移动验收
make e2e

# 仓库级完整门禁
make harness-check
```

前端聚焦命令：

```bash
npm --prefix frontend run type-check
npm --prefix frontend test
npm --prefix frontend run test:component
npm --prefix frontend run build
```

### 6.2 测试环境边界

- 默认后端测试使用隔离 SQLite；
- PostgreSQL 行为需要 `TEST_POSTGRES_URL`；
- Redis 集成测试必须指向明确的测试实例；
- Playwright 使用临时 SQLite 和 Worktree 独立端口；
- Live 模型/RAG 评估需要凭据、成本确认和数据外发审批；
- 测试不得删除/替换正在服务的 Qdrant 集合。

交付时记录命令、退出状态和未运行项。常见完整证据模板：

```text
Focused: pytest -q tests/test_xxx.py -> passed
Static:  make harness-static -> passed
Full:    make harness-check -> blocked: Docker unavailable
Risk:    E2E and Compose integration not verified locally
```

## 7. 产品使用手册

### 7.1 普通用户

1. 进入产品工作区，注册或登录。
2. 在“今日训练”设置目标岗位、方向和可选 JD。
3. 使用 AI 问答创建会话；查看流式回答、声明证据和知识来源，按需点赞/点踩；在历史页
   搜索、重命名或归档。
4. 在模拟面试选择主题、难度和题数；逐题回答、查看评分/参考答案；中途离开后可恢复。
5. 在能力画像查看分数、置信度、趋势和薄弱项；在学习计划生成、确认并执行个性化训练
   计划，按回忆结果和难度复习任务。
6. 在设置中管理头像、主题、提醒、密码、恢复码，以及训练记忆的确认、拒绝、纠正和删除。

简历功能开启后：

1. 上传可提取文本的 PDF/DOCX；扫描 PDF 不会自动 OCR。
2. 等待 Worker 完成分析，查看六维评分、关键词、问题及证据。
3. 编辑优化稿；解决事实警告和待补充内容后导出 DOCX。
4. 选择已完成分析版本，创建“简历定向”模拟面试。

复盘功能开启后：

1. 可直接粘贴文本逐字稿；文本流程不需要转写服务。
2. 上传音频前必须阅读并逐次确认外部转写；没有完整配置时音频入口不可用。
3. 校正片段和说话人，确认最新版本，再发起分析。
4. 修改已确认逐字稿后，必须重新确认和分析。

### 7.2 管理员

管理员使用独立 `/admin` 登录面，不与产品登录混用。创建初始管理员：

```bash
python -m scripts.create_admin --username <admin-name> --password '<strong-password>'
```

不要把真实密码留在 Shell 历史；生产应通过受控 Secret/运维流程执行。

管理后台主要能力：

- 查看系统资源、依赖探针和 Worker 心跳；
- 查看用户和角色；
- 查询脱敏审计、权威聊天/面试交互和请求关联执行时间线；
- 查看部署发布台账；
- 管理知识文件、发起后台导入、查看状态和回滚服务别名。

管理员能看见跨用户内容不等于可以复制到 Issue/日志；读取本身也会被审计。

### 7.3 API 使用

开发环境可从 `/docs` 查看 OpenAPI；所有现有路由见
[API 路由参考](generated/api-routes.md)。认证开启时，产品用户使用 Bearer Token；
管理员 Token 只能从管理员登录接口取得。`APP_API_KEY` 只保护服务端 `/ready` 运维
探针，不得进入浏览器；用户API仍由身份、角色和所有权校验保护。

聊天流采用 NDJSON 协议，前端解析逻辑在 `frontend/src/api/chat.ts`，协议设计见
[流式协议](architecture/STREAMING-PROTOCOL.md)。不要把普通 JSON 客户端直接套在
流式接口上。

## 8. 日常运维

### 8.1 每日/每班检查

```bash
docker compose ps
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready
docker compose logs --since=15m app worker
```

同时检查：

- HTTP 错误率、延迟和依赖错误是否突增；
- Worker 心跳、任务积压、重试和终态失败；
- PostgreSQL、Qdrant 和用户文件卷容量；
- 当前 Qdrant 稳定别名目标和最近知识发布结果；
- 最近备份是否成功、恢复演练是否过期；
- 模型错误、Token 用量和成本；
- 最近部署、迁移、配置或知识版本变化。

`/health` 只表示进程存活；`/ready` 才检查数据库、Qdrant 和启用时的 Redis。
`/metrics` 只供 Prometheus，不能直接暴露公网。

### 8.2 日志、指标和 Trace

- 本地看 `app`、`worker` 日志；生产优先用集中日志平台；
- 指标来源在 `app/operations.py`，规则在 `monitoring/alerts.yml`；
- Grafana Dashboard 在 `monitoring/grafana/dashboards/`；
- OTEL 配置在 `monitoring/otel-collector.yml`；
- 用 request ID 关联日志、Trace、审计和工具执行；
- 不搜索、输出或截图用户正文、Token、Key、连接串和私人知识。

### 8.3 Worker 与任务

Worker 处理：

- `knowledge_import`
- `resume_analysis`
- `interview_transcription`
- `interview_review_analysis`

任务具有认领、租约、心跳、确认、重试和最大尝试次数。任务不推进时检查 Worker
心跳、Redis、任务所有者/租约/尝试次数、共享文件卷和外部提供方。不要直接清空队列
或手改数据库状态。

### 8.4 备份

先做无副作用计划检查：

```bash
python -m scripts.backup --dry-run
```

受控创建备份：

```bash
python -m scripts.backup --output backups
```

范围包括 PostgreSQL Dump、Qdrant Snapshot 元数据、用户文件及哈希 Manifest。
备份继承最高数据分级，不能提交或放入开放目录。

校验备份而不恢复：

```bash
python -m scripts.restore backups/<timestamp>
```

`--confirm` 会覆盖目标 PostgreSQL，并替换用户文件目录，是破坏性操作；只有在明确
环境、停写、备份当前状态、获批维护窗口后执行。Qdrant 需按 Manifest 恢复到独立
集合，验证后切别名，脚本不会自动覆盖当前集合。完整步骤见
[备份恢复手册](operations/BACKUP-RESTORE.md)。

### 8.5 知识库运维

发布前确认文件有权处理、Embedding 外发获批、Qdrant 容量和回归阈值正确。失败候选
不应影响当前别名。需要回滚时从管理接口选择受管理历史版本，只移动稳定别名：

```text
GET  /api/admin/knowledge/status
POST /api/admin/knowledge/rollback
{"collection_name":"<managed-version>"}
```

历史集合清理前确认它不是当前目标，也不是计划回滚目标。

## 9. 发布、回滚与事故

### 9.1 发布最短清单

1. 明确目标环境、不可变制品摘要、负责人、窗口和回滚方案；
2. 完成质量门禁、审批和备份；
3. 记录当前应用版本、Alembic Revision、Qdrant 别名和核心数据计数；
4. Canary 使用同一制品，单一迁移执行者运行 `alembic upgrade head`；
5. 启动 App/Worker，等待 `/ready`，执行认证、核心流程和管理只读冒烟；
6. 观察错误、延迟、任务和依赖，再扩大；
7. 用 `scripts.record_release` 的稳定 release ID 幂等记录最终结果。

出现迁移失败、持续未就绪、越权/秘密泄露、错误显著升高、重复业务结果或知识别名
指向未验证集合时，立即停止扩大。

### 9.2 回滚判断

应用、Schema、配置和知识是四个不同回滚面：

- 应用问题：切回兼容的上一不可变 App/Worker 制品；
- 数据库问题：优先保留新 Schema 并回滚兼容应用或向前修复；
- 配置问题：回退配置前确认与当前 Schema/数据兼容；
- 知识问题：切换稳定别名，不删除集合；
- Secret 泄露：轮换并撤销相关 Token，不能只是改回旧值。

详细步骤见[部署手册](release/DEPLOYMENT-RUNBOOK.md)和
[回滚手册](release/ROLLBACK-RUNBOOK.md)。

### 9.3 事故响应

```text
用户症状
 -> health / readiness
 -> 请求与依赖指标
 -> App / Worker 日志和 Trace
 -> PostgreSQL / Redis / Qdrant / 用户文件卷
 -> 模型 / Embedding / 搜索 / 转写提供方
 -> 最近部署、迁移、配置或知识版本
```

跨用户泄露、数据破坏、全站不可用或 Secret 泄露按 SEV-1：停止变更、限制访问、
保存证据、指定指挥和沟通责任。任何事故都要记录时间线、假设、操作和结果；恢复后
更新测试、门禁和运行手册。

## 10. 常见故障速查

| 现象 | 先检查 | 不要做 |
|---|---|---|
| `/ready` 503 | 返回的依赖类别、数据库连接/Revision、Qdrant 别名、Redis、最近变更 | 只重启后宣布恢复 |
| 聊天/面试持续 409 | 幂等键与正文、回合状态、`Retry-After`、生成开始时间 | 直接改库抢占 generating |
| Worker 不推进 | Worker 心跳、Redis、队列名、租约、尝试次数、共享卷、提供方 | 清空队列掩盖失败 |
| RAG 无结果 | 别名目标、Embedding 模型/维度、阈值、K、重排开关 | 删除服务集合重新建 |
| 简历长期处理中 | 功能开关、Worker、任务状态、模型超时、共享卷权限/容量 | 重复上传制造新资源 |
| DOCX 导出拒绝 | 事实警告、待补充项、编辑版本冲突 | 绕过事实门禁 |
| 音频无法转写 | 转写开关、完整提供方配置、用户本次同意、格式/大小/限流 | 把音频传到 Issue |
| 复盘无法分析 | 最新逐字稿是否确认、说话人、是否存在候选人回答 | 手改终态 |
| 登录失败 | 产品/管理员入口、Token 撤销、系统时间、有效期 | 记录完整 Token |
| 端口冲突 | `.env.worktree` 和 `scripts.worktree_env --print` | 硬改共享固定端口 |

更完整分支见[故障排查](operations/TROUBLESHOOTING.md)。

## 11. 安全和数据处理底线

| 等级 | 示例 | 工程要求 |
|---|---|---|
| Restricted | 密码、Token、API Key、恢复码、数据库 Dump | 不进 Git/Issue/日志/Trace；最小访问、加密和轮换 |
| Confidential | 对话、简历、JD、音频、逐字稿、回答、私人知识、向量 | 用户/角色隔离；受控外发；备份与删除审计 |
| Internal | 脱敏审计、指标、内部配置和架构 | 限内部访问；指标保持低基数 |
| Public | 公开 README、无秘密 API 说明 | 发布前仍需审查 |

新增资源时必须回答：谁拥有、谁可读写、管理员能力是什么、如何删除、如何审计、
是否外发。授权测试至少覆盖匿名、当前用户、另一用户、普通用户访问管理接口和管理员
成功场景。

## 12. 建议的接手节奏

### 第一天：跑起来并建立地图

- 阅读本手册、根 README、架构总纲和功能契约；
- 启动 Worktree 隔离栈，验证 `/health`、`/ready` 和主要页面；
- 从浏览器走一遍登录、今日训练、聊天、模拟面试、能力画像；
- 对照 API 路由参考找到前端调用、路由、应用服务和存储实现。

### 第一周：完成一个小闭环

- 选择无 Schema/外部数据流变化的小问题；
- 先写或找到失败测试，再做最小修改；
- 跑聚焦测试、前后端相关门禁和 `make harness-check`；
- 同步契约/文档，用代码评审反馈校准对架构边界的理解；
- 跟随一次非生产知识发布或 Worker 任务，观察完整状态链路。

### 独立值守前

- 能解释健康与就绪区别、任务租约、聊天/面试幂等、Qdrant 别名发布；
- 能在不查看用户正文的情况下用指标、request ID、日志和 Trace 定位问题；
- 完成一次隔离环境备份校验和恢复演练；
- 跟随一次 Canary 发布和应用/知识回滚演练；
- 知道 SEV-1 停止条件、升级路径和证据保护规则。

## 13. 命令速查

```bash
# 环境与启动
python3 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.txt
npm ci --prefix frontend
make stack-up
python -m scripts.worktree_env --root . --print

# 本地开发
uvicorn app.main:app --reload --port 8000
npm --prefix frontend run dev

# 数据库
alembic current
alembic heads
alembic upgrade head
pytest -q tests/test_migrations.py

# 验证
make harness-static
make backend-check
make frontend-check
make e2e
make harness-check

# 运行
docker compose ps
docker compose logs --since=15m app worker
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready

# 受控管理
python -m scripts.create_admin --username <name> --password '<password>'
python -m scripts.ingest
python -m scripts.backup --dry-run
python -m scripts.restore backups/<timestamp>
python -m scripts.generate_docs

# 停止
make stack-down
```

## 14. 遇到文档不一致时

先用测试、数据库约束和实际代码建立事实，再在同一个变更中更新过时文档。不要因为
README 写了某行为就绕过验证，也不要只修代码而留下错误运行步骤。架构性分歧记录在
设计文档/决策日志；未完成边界问题登记技术债；生产事故同步更新运行手册和复盘。
