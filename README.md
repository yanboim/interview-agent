# AI 面试教练 Interview Agent

Interview Agent 是一个面向技术岗位求职者的持续训练工作台。它使用 FastAPI、
Vue、PostgreSQL/SQLite、Redis、Qdrant 和可配置的大模型，把岗位目标、知识问答、
模拟面试、能力画像和间隔复习连接成可持久化、可恢复的训练闭环。

模型回答和评分用于学习辅助，不代表真实招聘结论。

## 核心能力

- 账号注册、登录、刷新、退出、改密、恢复码和管理员独立登录；
- 目标岗位、方向、JD、提醒偏好和今日训练建议；
- 流式AI问答、私人知识来源、可选公开搜索和会话历史；
- 可恢复模拟面试、四维评分、重答、报告和安全幂等重试；
- 跨场次能力画像、趋势、薄弱点、学习任务和间隔复习；
- 管理员用户/审计/知识管理、自动发版记录、版本化知识发布和回滚；
- Redis可恢复任务、模型策略网关、指标、日志、Trace和CI/CD门禁。

已交付行为和验证证据以
[机器可读功能契约](docs/product-specs/feature-contract.json)为准。

## 系统概览

```text
Browser
  -> FastAPI + Vue
       |-- PostgreSQL / SQLite: users, conversations, interviews, learning
       |-- Redis: rate limits, cache, locks, durable jobs
       |-- Qdrant: versioned private knowledge
       |-- Zhipu APIs: chat and embeddings
       `-- optional public search

Worker -> Redis jobs -> knowledge validation -> Qdrant alias publication
```

详细设计见[架构总纲](ARCHITECTURE.md)和
[系统架构文档](docs/architecture/README.md)。

## 快速开始

要求：

- Python 3.12
- Node.js 20
- Docker与Compose
- 运行真实问答时使用智谱API Key

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.txt
npm ci --prefix frontend
cp .env.example .env
```

编辑 `.env`，至少为需要的真实模型/Embedding调用配置相应Key。启动隔离开发栈：

```bash
make worktree-env
make stack-config
make stack-up
```

查看当前Worktree分配的端口：

```bash
python -m scripts.worktree_env --root . --print
```

传统单工作区也可以运行：

```bash
docker compose up -d --build
```

应用默认入口为 `http://localhost:8000`，OpenAPI为
`http://localhost:8000/docs`。实际端口可能被Worktree环境覆盖。

本地分别运行后端和前端见[开发指南](docs/development.md)。

## 健康与验证

- `GET /health`：进程存活；
- `GET /ready`：当前数据库、Qdrant以及启用时的Redis；
- `GET /metrics`：Prometheus指标，不应直接暴露公网。

常用验证：

```bash
make harness-static
make backend-check
make frontend-check
make e2e
make harness-check
```

`make harness-check` 是仓库级本地门禁。PostgreSQL专项、真实Qdrant和Live模型评估
需要显式环境或可能产生费用，不在默认门禁中。详见
[测试策略](docs/quality/TEST-STRATEGY.md)。

## 知识库

把允许处理的 `.md` 或 `.txt` 文件放入 `knowledge/`，然后运行：

```bash
python -m scripts.ingest
```

导入会构建新的版本化集合，完成结构和已配置的检索回归验证后，原子切换稳定别名。
失败候选不会替换正在服务的知识版本。Embedding会把知识分块发送给配置的提供方；
启用前确认数据处理要求。

设计和操作见：

- [RAG架构](docs/architecture/RAG-ARCHITECTURE.md)
- [知识发布设计](docs/design-docs/qdrant-versioned-publication.md)
- [运维手册](docs/operations/OPERATIONS-MANUAL.md)

## 生产要求

生产至少应：

- 使用 `AUTH_REQUIRED=true`、PostgreSQL、Redis和强Secret；
- 通过可信入口提供TLS并限制Origin/Host；
- 将数据库、Redis、Qdrant和监控组件限制在私有网络；
- 在应用接流量前运行 `alembic upgrade head`；
- 使用不可变制品和已验证备份；
- 对外部模型、Embedding、重排和搜索的数据流完成审批；
- 按Canary、部署验证和回滚手册发布。

发布与运维入口：

- [发布流程](docs/release/RELEASE-PROCESS.md)
- [部署手册](docs/release/DEPLOYMENT-RUNBOOK.md)
- [回滚手册](docs/release/ROLLBACK-RUNBOOK.md)
- [备份恢复](docs/operations/BACKUP-RESTORE.md)
- [事故响应](docs/operations/INCIDENT-RESPONSE.md)

## 文档导航

| 主题 | 入口 |
|---|---|
| 全部文档 | [文档中心](docs/README.md) |
| 产品愿景与PRD | [产品文档](docs/product/README.md) |
| 原型与用户流程 | [UX文档](docs/ux/README.md) |
| 系统架构 | [架构文档](docs/architecture/README.md) |
| 开发生命周期 | [SDLC](docs/sdlc/README.md) |
| 测试与质量 | [质量体系](docs/quality/README.md) |
| 发布与环境 | [发布文档](docs/release/README.md) |
| 日常运维与恢复 | [运维文档](docs/operations/README.md) |
| 安全、隐私和数据 | [安全模型](docs/security/README.md) |
| 贡献流程 | [CONTRIBUTING.md](CONTRIBUTING.md) |

## 安全提示

不要提交 `.env`、Token、API Key、凭据、数据库Dump、备份、用户数据或私人知识
正文。Live评估、LLM重排和公开搜索可能将数据发送给第三方，必须显式启用并确认
数据允许外发。

详细要求见[安全模型](docs/security/README.md)和
[数据分级](docs/security/DATA-CLASSIFICATION.md)。
