# Interview Agent仓库指南

本文件是Coding Agent的入口。它提供地图和强制门禁，不是完整手册。

## 首先阅读

1. 阅读 [ARCHITECTURE.md](ARCHITECTURE.md)，了解系统边界和依赖规则。
2. 阅读
   [docs/product-specs/feature-contract.json](docs/product-specs/feature-contract.json)，
   了解机器可验证产品行为。
3. 非简单工作阅读 [docs/exec-plans/README.md](docs/exec-plans/README.md)，并创建或
   更新执行计划。
4. 扩展已知技术债区域前检查
   [docs/tech-debt-tracker.md](docs/tech-debt-tracker.md)。
5. 安装、部署和运维命令见 [README.md](README.md)。

仓库是系统事实来源。实现和文档冲突时，先验证行为，在同一变更中更新二者；如果差异
属于架构问题，还要记录设计决策。

## 仓库地图

- `app/`：FastAPI后端、Agent编排、领域计算和基础设施适配器。
- `frontend/`：Vue应用、组件测试和Playwright E2E测试。
- `migrations/`：Alembic Schema历史；生产Schema变更必须位于此处。
- `scripts/`：导入、评估、备份、恢复、迁移和Worker入口。
- `tests/`：后端单元、契约、迁移和集成测试。
- `eval/`：版本化RAG与Agent评估数据集和报告。
- `monitoring/`：Prometheus、Grafana、OpenTelemetry和告警配置。
- `docs/`：产品契约、设计记录、执行计划、可靠性、安全和生成参考。

## 工作循环

1. 从本指南、架构文档、相关产品契约、活动执行计划和当前Diff恢复上下文。
2. 说明预期行为和最小验收标准。
3. 完成最小且完整的变更，不混入无关清理。
4. 随实现增加或更新测试与仓库文档。
5. 迭代时运行聚焦检查或 `make dev-check`。
6. 宣布分支就绪前运行 `make pr-check`。Main和发布候选运行
   `make harness-check`；修改浏览器关键旅程时，交付前还需运行聚焦 `make e2e`。
7. 更新执行计划和技术债跟踪器；把完成计划移入 `docs/exec-plans/completed/`。

没有可执行验证引用时，不得在功能契约中把功能标记为 `passing`。文档变化后运行
`make docs-generate` 同步中文镜像，并使用 `make docs-check` 验证。

## 架构门禁

- `app/main.py` 是当前组合根和遗留路由宿主。不得在其中增加新业务规则；规则应放入
  应用/领域服务，路由保持适配器。
- 纯计算模块不得导入FastAPI、SQLAlchemy、Redis、Qdrant、HTTP客户端或模型SDK。
  强制模块列表位于 `tests/test_architecture.py`。
- `app/database.py` 只定义Schema元数据，不得依赖API、Agent、检索或网络层。
- 应用模块不得导入 `app.main`；依赖朝领域代码流动，不能反向指向组合根。
- 数据库变更必须包含Alembic迁移和迁移测试。
- 外部模型调用必须位于Agent/面试/重排适配器之后；新调用点必须定义超时、错误、指标
  和成本行为。
- 用户资源读写必须包含服务端解析的 `user_id`。
- 可重试写端点必须在产品契约中定义幂等或并发行为。
- 知识导入必须保留当前服务集合，直到替代集合通过验证。

当前例外和目标模块边界见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 安全规则

- 绝不提交 `.env`、凭据、Token、数据库Dump或用户数据。
- 绝不通过公开搜索工具暴露私人知识正文。
- 绝不把删除或替换Qdrant集合当作附带测试动作。
- 恢复操作只有在运维人员明确确认后才可执行破坏性步骤。
- 不得为通过测试削弱认证、授权、CSP、审计或Secret扫描。
- 保留工作区中已有的用户变更和无关工作。

## 验证

- 聚焦后端测试：`pytest -q tests/<relevant_file>.py`
- 本地快速静态反馈：`make dev-check`
- 确定性Pull Request门禁：`make pr-check`
- 后端套件：`pytest -q`
- 前端单测/类型/构建：`make frontend-check`
- Harness契约和架构：`make harness-static`
- Main/发布门禁（含浏览器E2E）：`make harness-check`
- 外部服务PostgreSQL检查要求 `TEST_POSTGRES_URL`。
- Live模型和RAG评估会产生费用；除非任务需要且凭据已配置，否则不得运行。

必要检查无法运行时，报告缺失的精确依赖和已实际执行的检查。不得静默替换为更弱验证。
