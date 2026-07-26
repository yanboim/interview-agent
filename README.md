# AI 面试教练 Agent

> 本轮产品体验 P0–P2 的实现与验收证据见
> [`P0_P2_COMPLETION.md`](P0_P2_COMPLETION.md)。

一个基于 FastAPI、LangChain/LangGraph 与 Qdrant 的 AI 面试教练。Agent
会按问题判断是否检索私人知识库，并将账号、用户会话、模拟面试和能力评分
持久化到 SQLite 或 PostgreSQL。

## 文档导航

- [项目文档总览](docs/README.md)：按开发、测试、运维和安全任务查找文档
- [架构边界](ARCHITECTURE.md)：运行拓扑、依赖方向和正确性约束
- [开发指南](docs/development.md)：本地环境、变更流程和数据库迁移
- [测试指南](docs/testing.md)：验证层级、外部依赖和验收证据
- [可靠性与运行手册](docs/reliability/README.md)：健康检查、故障响应、备份与回滚
- [安全模型](docs/security/README.md)：信任边界、身份、密钥和外部数据流
- [文档维护规范](docs/documentation-guide.md)：文档职责、生命周期和评审清单

## 架构

```text
Client -> FastAPI auth/RBAC -> Interview Agent -> Qdrant knowledge tool
               |                 |
               +-> SQL database  +-> LangGraph request state
```

## 快速开始

要求 Python 3.12、Docker，以及可用的智谱 API Key。对话模型使用
GLM-5.2，向量模型使用智谱 Embedding-2，不需要 OpenAI Key。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.txt
cp .env.example .env
# 编辑 .env，填写 ZHIPU_API_KEY
docker compose up -d
python -m scripts.ingest
uvicorn app.main:app --reload --port 8000
```

打开 `http://localhost:8000` 使用可视化聊天界面，接口文档位于
`http://localhost:8000/docs`。也可以直接调用：

```bash
curl -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <access-token>' \
  -H 'Idempotency-Key: 550e8400-e29b-41d4-a716-446655440001' \
  -d '{"user_id":"<登录返回的 user_id>","session_id":"demo-1","message":"请解释 RAG 的完整流程"}'
```

启用认证后，先在网页注册或调用 `POST /api/auth/register`；服务端会校验
`user_id` 必须与访问令牌中的身份一致。继续使用相同的
`user_id + session_id` 即可追问。前端默认使用
`POST /api/chat/stream` 获取 NDJSON 增量输出。`GET /health` 是存活探针；
`GET /ready` 会检查当前配置的数据库、Qdrant，以及启用时的 Redis；
`GET /metrics` 输出 Prometheus 文本指标。

`POST /api/chat` 和 `POST /api/chat/stream` 都要求携带
`Idempotency-Key`。浏览器会为一次发送生成请求键，并在失败或停止生成后的
同内容重试中复用。服务端先持久化聊天回合状态并原子占用会话，再调用模型；
同一会话不能并发生成。只有成功完成时，用户消息和助手消息才会在一个事务中
写入历史，因此模型失败或客户端断连不会留下孤立用户消息。已完成的同键重试
直接重放持久化答案。

生成中的重复请求返回 `409` 和 `Retry-After`。流式连接被取消时，服务端将
已生成片段记录到 `chat_turns` 的 `cancelled` 状态用于诊断，但不会把片段加入
正式消息历史；使用相同键和内容重试会重新从头生成。

产品区使用可恢复的深链路由：`/today`、`/chat/{session_id}`、
`/interviews/{interview_id}`、`/profile` 与 `/learning`。首次登录会引导设置
目标岗位和训练方向，“今日训练”负责串联模拟面试、薄弱点复习与知识问答。
私人知识库被实际调用时，流式接口会发送结构化 `sources` 事件并展示来源。
服务密钥由部署环境统一管理，不向普通用户显示或要求用户配置。

## 模拟面试与能力报告

网页侧边栏可以直接进入模拟面试。后端会逐题生成问题，并从技术准确性、原理
深度、表达结构和工程实践四个维度评分。面试报告汇总平均分、主要薄弱点和针对
最低维度的学习计划，所有结果均写入当前配置的 SQLite 或 PostgreSQL。

首次提交某题答案时必须携带 8–128 字符的 `Idempotency-Key`。浏览器会为当前
答案生成请求键，并在请求失败后的重试中复用；服务端在任何评分模型调用之前
通过数据库条件更新领取待答回合。并发提交只允许一个请求进入评分，成功后的
同键重试直接返回已持久化结果，不会重复创建答案记录或下一题：

```bash
curl -X POST \
  'http://localhost:8000/api/interviews/<interview_id>/answer' \
  -H 'Authorization: Bearer <access-token>' \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000' \
  -d '{"user_id":"<user_id>","answer":"我的回答"}'
```

同一请求键不能配合不同答案使用。评分仍在进行时返回 `409` 和
`Retry-After`；调用方应稍后使用完全相同的键和答案重试。

“能力画像”会进一步聚合当前账号的全部已评分面试，展示综合分、四维能力、
场次趋势、主题对比、薄弱点频次、最近训练和高频问题。可以通过页面筛选主题，
也可以直接调用：

```bash
curl 'http://localhost:8000/api/capability-profile?user_id=<user_id>&topic=RAG' \
  -H 'Authorization: Bearer <access-token>'
```

画像使用现有评分数据实时计算，不需要额外 migration；历史面试会自动纳入。

## 面试历史与学习计划

“模拟面试”页面会列出账号下的历史训练。未完成面试可以从服务端恢复，已完成
面试可以查看逐题回答、评分与反馈；面试也可以归档、取消归档或永久删除。

“学习计划”会把能力画像中的最低维度和高频薄弱点转换为可执行任务。任务支持
待开始、进行中和已完成状态，可以调整截止日期并记录复习。每次复习后，系统按
1、3、7、14、30、60 天的间隔安排下一次复习。

主要接口：

```text
GET    /api/interviews
GET    /api/interviews/{interview_id}
POST   /api/interviews/{interview_id}/resume
POST   /api/interviews/{interview_id}/archive
DELETE /api/interviews/{interview_id}

PATCH  /api/conversations/{session_id}

GET    /api/learning-tasks
POST   /api/learning-tasks/generate
PATCH  /api/learning-tasks/{task_id}
POST   /api/learning-tasks/{task_id}/review
DELETE /api/learning-tasks/{task_id}
```

相关表结构由 migration `20260724_0003` 管理。生产数据库升级后再启动新版本：

```bash
alembic upgrade head
```

## 容器部署

完整启动 FastAPI 与 Qdrant：

```bash
make worktree-env
make stack-config
make stack-up
python -m scripts.ingest
```

`.env.worktree` 根据当前 worktree 的绝对路径生成，不包含密钥且不会提交。它为
Compose project、容器/网络/命名卷前缀、所有宿主端口和 Playwright 分配稳定的
隔离值，因此两个 worktree 可以同时运行。容器内仍使用 `postgres:5432`、
`redis:6379` 和 `qdrant:6333` 等固定服务地址。查看实际端口：

```bash
python -m scripts.worktree_env --root . --print
```

停止当前 worktree 的栈使用 `make stack-down`；该命令保留命名卷。只有在明确
确认当前项目数据不再需要时，才额外使用 Compose 的 `--volumes` 删除数据。
传统的 `docker compose up` 仍使用 8000、5432、6379 等默认端口，适合只运行
一个 worktree 的场景。

Compose 生产配置同时启动 PostgreSQL，并在 FastAPI 启动前执行
`alembic upgrade head`。本地开发仍可保留 SQLite。将现有 SQLite 历史迁移到
一个已经执行 migration 的空 PostgreSQL 数据库：

```bash
python -m scripts.migrate_sqlite_to_postgres \
  --source data/interview-agent.db \
  --target 'postgresql+psycopg://user:password@localhost:5432/interview_agent'
```

迁移工具在目标库非空时会停止，完成后会核对每张业务表的记录数量。

生产环境可在 `.env` 中设置 `APP_API_KEY`。启用后，所有 `/api/*` 和
`/ready` 请求都必须携带 `X-API-Key: <key>`；`/metrics` 保留给内部
Prometheus 抓取，不应直接暴露到公网。用户身份令牌继续使用
`Authorization: Bearer <access-token>`。Redis 为多实例提供共享限流，Redis
临时不可用时自动退回单实例内存限流。当前 `user_id` 已用于数据隔离；当
`AUTH_REQUIRED=true` 时，服务端会校验访问令牌中的用户身份并拒绝伪造的
`user_id`。

创建第一个管理员账号：

```bash
python -m scripts.create_admin \
  --username admin \
  --password '请使用至少十位的强密码'
```

普通注册只能创建 `user` 角色；管理员账号通过脚本独立创建，并从 `/admin`
使用专用登录入口。用户工作区与后台使用不同的浏览器会话存储，普通用户凭据
无法登录后台，管理员凭据也无法进入用户工作区；`/api/admin/*` 接口仍会在
服务端强制校验 `admin` 角色。
管理员可以通过 `GET /api/admin/system-summary` 查看运行数据，通过
`POST /api/admin/knowledge/import` 触发知识库重建。导入会创建独立的版本
collection，校验通过后才将稳定别名原子切换到新版本；当前版本在切换前持续
服务，旧版本保留用于回滚。

## 导入知识库

将 UTF-8 或 GB18030 编码的 `.md`、`.txt` 文件放入 `knowledge/`，然后运行
`python -m scripts.ingest`。导入程序会创建
`QDRANT_COLLECTION__v_<时间>_<任务>` 物理版本，完成结构校验和已配置的检索
回归门禁后，一次性切换 `QDRANT_COLLECTION_ALIAS`。失败的候选版本会被清理，
不会删除或替换正在服务的版本。

首次升级时若稳定别名尚不存在，读取会继续使用原
`QDRANT_COLLECTION`，首次成功发布后再切换到别名。生产环境应配置 Redis，
以便多个 API/Worker 实例通过带 TTL 的分布式锁串行发布。

Embedding 使用智谱标准 API 的 `embedding-2` 模型（固定 1024 维）。Coding
Plan Key 与智谱标准 API Key 可能不通用，因此建议通过
`ZHIPU_EMBEDDING_API_KEY` 单独配置。更换 Embedding 模型后必须重新运行导入，
否则向量维度或向量空间不一致会导致检索失败。

## 配置

配置见 `.env.example`。GLM Coding Plan 使用 OpenAI 兼容端点
`https://open.bigmodel.cn/api/coding/paas/v4`；如果使用按量计费的标准 API，
将 `ZHIPU_API_BASE` 改为 `https://open.bigmodel.cn/api/paas/v4`。

向量接口始终使用标准 API 地址
`https://open.bigmodel.cn/api/paas/v4`，对应配置为
`ZHIPU_EMBEDDING_API_BASE`。

智谱官方将 Coding Plan 限定为受支持的 Coding Agent，自建网站、机器人和 SaaS
应使用标准 API。上线或公开提供本服务前，请使用标准端点并确认对应计费规则。

Python 依赖的人工评审入口是 `requirements.in`，生产与 CI 只安装
`requirements.txt` 中的精确版本和制品哈希。更新依赖时使用固定 Python 3.12
镜像重新解析并运行门禁：

```bash
make lock-python
make harness-check
```

评审时同时检查直接依赖变化、传递版本/哈希变化和安全审计结果。Dockerfile 与
Compose 外部镜像使用“版本标签 + Linux/amd64 manifest digest”；升级镜像时应
从官方注册表核对新摘要，并与版本变更放在同一次评审中。

`RETRIEVAL_CANDIDATE_K` 控制混合检索候选数，
`RETRIEVAL_FINAL_K` 控制最终返回分块数。会话、消息、模拟面试和账号已持久化；
聊天请求由 `CHAT_CONTEXT_TOKEN_BUDGET` 限制模型上下文，超出窗口的较早消息会
压缩到持久化摘要中，`CHAT_SUMMARY_TOKEN_BUDGET` 控制摘要上限；原始消息不会
被删除。Agent 单次执行状态仍由 LangGraph 在请求期间维护。生产部署应启用
`AUTH_REQUIRED=true`、PostgreSQL、Redis，并把 Qdrant 和监控端口限制在内部
网络。

## 生产运行与监控

完整栈包含 FastAPI、Worker、PostgreSQL、Qdrant、Redis、OpenTelemetry
Collector、Prometheus 和 Grafana：

```bash
docker compose up -d --build
docker compose ps
```

- 应用：http://localhost:8000
- 就绪检查：http://localhost:8000/ready
- Prometheus：http://localhost:9090
- Grafana：http://localhost:3000

Grafana 初始账号默认是 `admin / change-me-now`，正式环境必须通过
`GRAFANA_ADMIN_USER` 和 `GRAFANA_ADMIN_PASSWORD` 修改。仪表盘会展示请求量、
错误量和 GLM、检索、Qdrant、Redis、数据库依赖指标。Prometheus 已预置依赖
错误增长及平均耗时超过 5 秒的告警规则。

知识库导入可以由管理员加入后台队列：

```text
POST /api/admin/jobs/knowledge-import
Idempotency-Key: <stable-command-id>
```

查看当前物理版本和可回滚版本：

```text
GET /api/admin/knowledge/status
```

将别名原子切换回一个仍存在的受管理版本：

```text
POST /api/admin/knowledge/rollback
{"collection_name":"interview_knowledge__v_<版本>"}
```

回滚不删除离开的版本。历史版本保留策略尚未自动化，运维侧应监控 Qdrant
容量，在制定并验证保留策略前不要手工删除当前别名指向的 collection。

服务支持从文件读取密钥，例如 `ZHIPU_API_KEY_FILE`、
`ZHIPU_EMBEDDING_API_KEY_FILE`、`WEB_SEARCH_API_KEY_FILE` 和
`APP_API_KEY_FILE`，便于挂载 Docker/Kubernetes secrets。

备份和恢复校验：

```bash
python -m scripts.backup --output backups
python -m scripts.restore backups/<时间戳>
```

第二条命令默认仅校验。实际数据库恢复会清理并覆盖目标数据库，必须在维护窗口
确认备份后显式添加 `--confirm`；Qdrant snapshot 仍需按 manifest 单独确认。

## 测试

```bash
pytest -q
TEST_POSTGRES_URL='postgresql+psycopg://...' pytest -q \
  tests/test_postgres_storage.py
```

## Agent Harness

仓库以 [`AGENTS.md`](AGENTS.md) 作为编码 Agent 的导航入口，以
[`ARCHITECTURE.md`](ARCHITECTURE.md) 定义模块和正确性边界，以
[`docs/product-specs/feature-contract.json`](docs/product-specs/feature-contract.json)
记录机器可读的功能验收状态。复杂变更应在 `docs/exec-plans/active/` 建立执行
计划，完成后移入 `completed/`。

运行完整的本地反馈闭环：

```bash
make harness-check
```

该命令依次检查 Harness 文档与架构约束、后端测试、前端类型和单元测试、生产
构建、包体预算及 Playwright 浏览器验收。PostgreSQL、真实 Qdrant 和模型评估
需要外部服务或产生调用成本，因此保持为显式验证，不包含在默认门禁中。

## RAG 检索评估

运行固定问题集的混合检索基线：

```bash
python -m scripts.evaluate_rag
```

启用本地 Cross-Encoder 重排后对比：

```bash
python -m scripts.evaluate_rag --rerank
```

当前固定集包含 50 个正负样本。已验证的混合检索基线保存在
`eval/reports/hybrid-baseline.json`。新增资料、修改分块策略或更换模型后，
必须重新运行评估并校准 `DENSE_RELEVANCE_MIN_SCORE`。

分块级评估使用人工标注的稳定 `chunk_id`，可识别“命中文件但未命中正确
知识块”的假命中：

```bash
python -m scripts.evaluate_chunks --k 10
python -m scripts.evaluate_chunks --k 10 --lexical-rerank
```

导入时会给每个 Markdown 分块继承父级标题上下文，同时保持稳定 `chunk_id`。
标题上下文评估报告位于
`eval/reports/chunk-heading-context.json`：当前 10 个分块级样本的 Top-1
为 50%，MRR 为 0.667。旧轻量词法重排与标题上下文叠加后会降分，因此默认
关闭。

也可以显式评估 GLM-5.2 列表式重排：

```bash
python -m scripts.evaluate_chunks --k 10 --llm-rerank
```

该模式会把候选知识块正文发送到配置的 GLM API，并增加延迟与模型调用成本，
所以 `LLM_RERANKER_ENABLED` 默认关闭。仅应在确认知识库内容允许发送给模型
提供方后启用。

chunk 评估报告还包含 `nDCG@K`。答案引用和忠实度评估：

```bash
python -m scripts.evaluate_answers
```

评估集位于 `eval/answer_quality.jsonl`，其中 `supported_claims` 应由人工逐条
标注，避免用生成模型自评代替基准真值。若希望每次知识库导入后自动执行回归：

```env
INGEST_RUN_EVALUATION=true
RAG_REGRESSION_MIN_NDCG=0.60
```

## Agent 工具与联网搜索

Agent 可以调用私人知识库、查询当前账号训练进度，以及从画像生成学习计划。
工具身份由服务端认证上下文注入；调用摘要和耗时写入 `tool_audit_logs`，
管理员可查询 `GET /api/admin/tool-audits`。

公开网络搜索默认关闭。启用 Tavily 兼容接口：

```env
WEB_SEARCH_ENABLED=true
WEB_SEARCH_API_KEY=替换为搜索服务Key
WEB_SEARCH_API_URL=https://api.tavily.com/search
```

只有需要最新信息且私人知识库不足时才应联网。查询会发送给第三方服务，系统会
拦截疑似密钥，但仍不应在问题中包含私人知识库正文或个人敏感信息。

## 多 Agent 架构

默认启用 P4 多 Agent 模式：

```text
用户请求
   │
   ▼
Supervisor
   ├── Knowledge Agent   私人 RAG / 公开网络
   ├── Interviewer Agent 出题 / 追问
   ├── Evaluator Agent   回答评分 / 改进建议
   └── Planner Agent     能力画像 / 长期计划
```

Supervisor 不直接承担专业任务，而是至少委派一个专业 Agent 后整合结果。需要
处理复合目标时可以顺序调用多个专业 Agent。模拟面试的出题和评分接口继续保持
原有协议，但分别计入 Interviewer 与 Evaluator 指标。

查看当前拓扑：

```text
GET /api/agent/topology
```

如需临时回退原单 Agent：

```env
MULTI_AGENT_ENABLED=false
```

Prometheus 指标按 Agent 区分：

```text
interview_agent_dependency_calls_total{dependency="agent_knowledge"}
interview_agent_dependency_duration_seconds_total{dependency="agent_evaluator"}
interview_agent_llm_input_tokens_total{agent="planner"}
interview_agent_llm_output_tokens_total{agent="supervisor"}
```

运行真实 GLM 首跳路由评估：

```bash
python -m scripts.evaluate_multi_agent
```

评估会产生模型调用。当前 `eval/agent_routing.jsonl` 包含 16 条均衡样本，最新
报告位于 `eval/reports/multi-agent-routing.json`，四类路由准确率均为 100%。

## 管理员后台

管理员登录后可访问：

```text
http://localhost:8000/admin
```

后台提供运行概览、知识库文件、产品用户只读列表和工具审计四个工作区。主要接口：

```text
GET   /api/admin/runtime
GET   /api/admin/system-summary
GET   /api/admin/users
GET   /api/admin/knowledge/files
PUT   /api/admin/knowledge/files
DELETE /api/admin/knowledge/files/{filename}
POST  /api/admin/jobs/knowledge-import
GET   /api/admin/knowledge/status
POST  /api/admin/knowledge/rollback
GET   /api/admin/jobs/{job_id}
GET   /api/admin/tool-audits
```

知识文件只接受不包含目录的 `.md` 和 `.txt` 文件名，单文件最大 1 MB。Compose
使用 `knowledge_data` 卷在应用和 Worker 间共享并持久化文件。保存或删除文件后
需要在后台点击“后台导入”，任务状态会持续显示到完成或失败。

产品用户只通过公开注册入口创建；管理员只通过运维脚本创建。后台不提供角色
转换操作，避免产品账号与运营账号在界面中互相转换。
