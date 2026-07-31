# 开发指南

## 前置条件

- Python 3.11或更高版本
- Node.js 20和npm
- Docker与Compose
- 只有调用真实模型时才需要智谱API Key
- 只有执行真实Embedding或知识导入时才需要智谱标准API Key

默认自动化测试不需要真实模型凭据。PostgreSQL集成测试要求
`TEST_POSTGRES_URL`；真实Qdrant和模型评估需要外部服务或会产生费用，因此必须显式
执行。

## 本地设置

在仓库根目录运行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.txt
npm ci --prefix frontend
cp .env.example .env
```

`.env` 只能保留在本地。最小化启动应用时，配置必要模型Key、启动依赖、执行迁移、
导入知识并启动API：

```bash
docker compose up -d postgres redis qdrant
alembic upgrade head
python -m scripts.ingest
uvicorn app.main:app --reload --port 8000
```

在第二个终端进行前端开发：

```bash
npm --prefix frontend run dev
```

完整Compose拓扑和运维命令见[根README](../README.md)。配置名称和安全占位值见
[`.env.example`](../.env.example)。

## 仓库边界

- `app/main.py` 是组合根和遗留路由宿主。新业务规则放入应用或领域服务，路由保持为
  适配器。
- 纯计算不得导入FastAPI、SQLAlchemy、Redis、Qdrant、HTTP客户端或模型SDK。
- `app/database.py` 只定义Schema元数据，不依赖API、Agent、检索或网络层。
- 数据库Schema变更必须包含Alembic迁移和迁移测试。
- 用户数据访问使用服务端从认证信息解析的 `user_id`。
- 外部模型调用必须位于现有适配器之后，并定义超时、错误、指标和成本行为。

改变依赖或正确性边界前阅读[ARCHITECTURE.md](../ARCHITECTURE.md)。

## 变更流程

1. 阅读 `AGENTS.md`、架构文档、相关功能契约、活动计划、技术债条目和当前工作区变更。
2. 说明预期行为和最小验收标准。
3. 非简单工作创建或更新[执行计划](exec-plans/README.md)。
4. 完成最小且完整的变更，保留无关工作。
5. 在同一变更中按需更新测试、产品契约、设计记录、运维和安全文档。
6. 迭代时运行聚焦检查，最后运行任务范围要求的仓库门禁。
7. 在计划中记录验证，并将完成计划移动到 `completed/`。

没有可执行验证引用时不得把功能标记为 `passing`。除非任务明确要求且凭据和数据处理
审批齐备，否则不得运行真实模型或RAG评估。

## 数据库变更

在 `migrations/versions/` 下创建Revision，更新存储行为，并增加同时覆盖Schema和
用例的测试。至少验证：

```bash
alembic upgrade head
pytest -q tests/test_migrations.py
```

PostgreSQL特有行为使用 `TEST_POSTGRES_URL`。运行时 `create_all` 只用于本地和隔离
测试；生产Schema演进由Alembic负责。

## 交付前

按[测试指南](testing.md)运行与变更匹配的验证。仓库范围行为变更要求：

```bash
make harness-check
```

如果必要检查无法运行，必须报告缺失的具体依赖以及实际已运行的检查。
