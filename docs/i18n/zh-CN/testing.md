# 测试与验证

## 验证层级

迭代时选择能够证明变更的最小检查，完成时运行任务范围要求的门禁。

| 范围 | 命令 | 覆盖内容 |
|---|---|---|
| 单个后端区域 | `pytest -q tests/<relevant_file>.py` | 聚焦Python行为 |
| 本地迭代 | `make dev-check` | 编译、架构、工具链基线和前端类型 |
| 架构或文档 | `make harness-static` | 依赖规则、功能契约、必需文档和内部链接 |
| 后端仓库 | `make backend-check` | 编译和后端测试套件 |
| 无外部服务的后端 | `make backend-fast-check` | 编译并运行未标记为 `integration` 的测试 |
| 前端仓库 | `make frontend-check` | 工具链、类型、单测、生产构建和Bundle预算 |
| 浏览器验收 | `make e2e` | Playwright产品流程 |
| Pull Request | `make pr-check` | 确定性仓库、后端、前端、构建、Bundle和空库Migration检查 |
| Main或发布候选 | `make harness-check` | 上述完整检查，包括浏览器验收 |

分支和Pull Request的快速CI在一个Job中运行 `make pr-check`，并取消同一
分支已被新提交取代的运行。Main、Nightly和手动深度验证再加入浏览器验收、
Python/npm依赖审计、容器构建和High/Critical漏洞扫描。发布验证会对精确的
Tag源码独立运行完整Harness。

## 外部服务与成本检查

下列检查有意放在默认本地门禁之外：

- PostgreSQL专项测试需要 `TEST_POSTGRES_URL`。
- 真实Qdrant检查需要可销毁或明确批准的目标。
- `python -m scripts.evaluate_rag` 使用已配置的Embedding/检索服务。
- `python -m scripts.evaluate_chunks --llm-rerank` 会把候选私人知识正文发送给模型
  提供方并产生费用。
- `python -m scripts.evaluate_answers` 评估版本化回答质量数据集。

如果测试可能删除或替换集合，绝不能指向正在服务的Qdrant集合。未经数据提供方审批，
不得把私人知识发送给公开搜索或模型服务。

## 产品契约证据

`docs/product-specs/feature-contract.json` 把产品行为标记为 `passing` 或 `planned`。

- `passing` 功能至少包含一个仓库验证引用。
- `planned` 功能链接到具体缺口，通常是技术债跟踪器。
- 文件存在只是最小可追踪条件；对应测试必须真正执行功能声称的行为。

修改功能时，在同一变更中更新步骤和证据。

## 保持输出简洁

成功的后端和前端测试使用Quiet或Dot Reporter。只有深度验证失败时才上传
浏览器HTML和Trace产物。迭代时优先运行能证明变更的最小聚焦检查；已有命令和
结果摘要时，不要粘贴完整的成功CI日志。

## 结果报告

记录：

- 精确命令；
- 可获得时的通过、失败和跳过数量；
- 不可用的外部服务或凭据；
- 是否以较弱的聚焦检查替代了必要门禁。

不得把未运行的检查描述为通过，也不得静默用SQLite检查代替要求的PostgreSQL验证。

## 后端测试分类

新测试使用 [`tests/README.md`](../tests/README.md) 记录的分类：单元、应用、
契约、集成、架构、Migration和显式故障注入。现有扁平测试路径继续保持兼容；只有在
对应实现区域同时发生变更时才逐步移动文件。
