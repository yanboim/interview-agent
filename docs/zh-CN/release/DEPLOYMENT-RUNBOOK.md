# 部署运行手册

## 前提

- 明确目标环境、制品摘要和负责人；
- 质量门禁、审批、备份和回滚计划完成；
- 生产Secret不在命令历史或文档中显示；
- 确认维护窗口和外部服务状态。

## 部署前

```bash
make production-preflight-check
python -m scripts.backup --dry-run
alembic current
alembic heads
```

预检失败必须在构建、迁移或重启前停止。输出仅含脱敏错误码；操作员应在批准的Secret管理
系统中轮换缺失、默认或弱凭据，重新分发并验证旧值失效，不得把新值粘贴到工单、日志或
发布台账。该目标当前同时验证Workflow V2生产路由显式启用；紧急回滚到 `off` 时不要用
生产发布目标覆盖回滚流程。

生产备份命令和存放策略按运维控制执行。记录现有应用版本、数据库Revision、当前
Qdrant别名目标和核心数据计数。

## 部署

1. 验证发布制品校验和。
2. 更新Canary实例到指定不可变制品。
3. 运行 `alembic upgrade head`，只允许一个受控迁移执行者。
4. 启动应用和Worker。
5. 等待依赖健康和应用就绪。
6. 执行Canary冒烟和指标观察。
7. 获批后使用同一制品更新其余实例。

Compose参考环境：

```bash
make worktree-env
make stack-config
make stack-up
docker compose ps
```

生产平台可使用不同编排方式，但启动顺序和验证要求不变。

### Workflow V2 稀疏检索预热

Workflow V2 放行前，在路由阶段仍为 `off` 或 `internal` 时预热 BM25 稀疏模型。默认
缓存目录是 `data/fastembed-cache`；Compose 将其置于持久化 `app_data` 卷，因此后续
重建 app 不会再次下载。预热输入必须是固定的非用户测试文本：

```bash
docker compose exec -T app python -c \
  'from app.rag import get_sparse_embeddings; get_sparse_embeddings().embed_query("面试知识库连接测试"); print("sparse_embedding_warmup=passed")'
```

预热失败时保持 Workflow V2 为 `off`，不得通过增加请求超时掩盖冷启动下载。自定义
部署必须把 `SPARSE_EMBEDDING_CACHE_DIR` 放在 app 可写且跨重建持久化的存储上。

## 部署后验证

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready
```

继续验证：

- 认证和角色隔离；
- 一个无副作用或测试账号的聊天/面试流程；
- 管理后台只读运行摘要；
- Worker未积压异常任务；
- 指标、Trace和日志正常；
- OTLP `/v1/traces` 与 `/v1/metrics` 均被 Collector 接受；
- 数据计数和Migration Revision符合预期。

## 自动记录发版结果

部署验证完成后，部署执行器必须使用同一个稳定的 `release-id` 写入最终结果。命令是
幂等的：部署开始时可以写入 `deploying`，结束后以相同ID更新为 `succeeded`、
`failed` 或 `rolled_back`，不会生成重复记录。

在应用容器内记录一次成功的生产发布：

```bash
python -m scripts.record_release \
  --release-id production-<deployment-id> \
  --version <version-or-short-commit> \
  --title "<release-title>" \
  --environment production \
  --status succeeded \
  --commit-sha <commit> \
  --change "<sanitized-change-summary>" \
  --verification health=passed \
  --verification readiness=passed \
  --verification browser=passed \
  --app-image <immutable-app-image> \
  --worker-image <immutable-worker-image> \
  --migration-revision <alembic-revision> \
  --recovery-point <recovery-point-id> \
  --triggered-by <operator-or-pipeline>
```

生产编排层应把此命令作为部署后验证的最后一步调用。参数只能包含脱敏摘要，不得写入
Secret、连接串、Token、原始日志或用户数据。记录失败不得改变真实部署结果，需由发布
流程报警并补写。

## Workflow V2观察与Supervisor退役

Workflow V2进入生产后，保留 `off` 回滚路径并收集独立生产观察报告。以
`eval/reports/workflow-v2-production-observation.template.json` 为结构模板，但不得把
模板或内部确定性报告标记为生产证据。先在 `off` 阶段为保留的Supervisor收集至少24小时
且100个完成请求的生产基线，再为同一候选Workflow V2收集同样规模的生产观察窗口；记录
质量、完成率、p95、单次完成训练成本和零容忍安全失败，并完成一次 `off` 回滚演练。
报告只保存指标来源、稳定查询ID和脱敏质量报告的SHA-256，不保存用户正文或原始日志；
回滚演练必须另有状态为 `rolled_back` 的生产发布台账记录。

窗口结束后先从Prometheus生成不具审批效力的运维指标草稿：

```bash
python -m scripts.collect_workflow_observation \
  --prometheus-url https://<approved-metrics-host> \
  --release-id production-<deployment-id> \
  --release-version <version> \
  --baseline-started-at <SUPERVISOR-ISO-8601> \
  --baseline-ended-at <SUPERVISOR-ISO-8601> \
  --started-at <ISO-8601> \
  --ended-at <ISO-8601>
```

固定查询对 `chat-supervisor-v1` 与 `chat-workflow-v2` 分别计算完成请求数、完成率、p95和
单次成本，并要求两个窗口都达到门槛。草稿中的质量、安全、回滚与审批字段故意保持未完成；
必须由相应独立证据补齐，不得把草稿直接重命名为正式观察报告。

指标草稿达到窗口与流量门槛后，可将通过的脱敏Agent质量报告和已验证回滚发布ID合并为
待审材料：

```bash
python -m scripts.prepare_workflow_observation_review \
  --draft .var/workflow-v2-production-observation.draft.json \
  --quality-report eval/reports/agent-stack-ci.json \
  --rollback-release-id production-<rollback-exercise-id>
```

该命令会校验所有质量分组和零容忍失败、写入质量报告SHA-256，并强制保留
`approval.status=pending`。它不能生成批准人、批准时间或工单，也不能替代对生产指标、
安全事件和回滚台账的独立复核。

获得外部发布批准并确认报告 `release_id`/`release_version` 与成功生产发布台账一致后，
运行：

```bash
make workflow-retirement-check
```

只有输出 `workflow_retirement_gate=approved` 才能在后续独立变更中删除Supervisor。
缺报告、短窗口、样本不足、指标回退、无回滚证据、自我批准或台账不匹配都会失败关闭。

### 首次公开发布前的独立验收路径

尚未公开发布、没有代表性真实流量的环境不得制造100个请求并把它们声明为生产观察。
这类环境可使用独立的预发布门禁；正式公开发布路径的双24小时/双100请求规则保持不变。

预发布证据以
`eval/reports/workflow-v2-prerelease-acceptance.template.json` 为结构，必须同时满足：

- 确定性应用栈评测至少230项全部通过，零容忍失败为0；
- 至少6个隔离的真实模型请求全部完成，覆盖knowledge、interviewer、evaluator、planner，
  且至少2个为多意图；
- 报告不含用户正文，验收账号按精确用户名和`user_id`完成清理并核验归零；
- 当前app/worker使用不可变镜像ID，回滚app/worker tar分别记录SHA-256；
- 当前发布台账为`succeeded`，回滚演练台账为`rolled_back`；
- 项目所有者在真实模型验收结束后审批完整证据，自动化或Codex不得自我批准。

证据齐备后运行：

```bash
make workflow-prerelease-retirement-check
```

只有输出`workflow_prerelease_gate=approved`才可移除Supervisor兼容拓扑。移除后，`off`
配置不再构成代码内回退；回滚必须校验并重新部署门禁中固定的上一版镜像制品。

当前仓库已通过该门禁并移除Supervisor运行拓扑。上述生产双窗口命令继续保留，用于
审计退休前证据或在部署旧兼容制品时重建可比基线；当前镜像不会发出新的
`chat-supervisor-v1`运行样本，也不会读取已退休的rollout变量。

## 停止条件

- Migration失败或历史数据校验不一致；
- 就绪持续失败；
- 跨用户访问、Token或秘密泄露；
- 错误/延迟显著超过已批准阈值；
- 聊天或面试出现重复提交结果；
- 知识别名指向未验证集合。

触发后停止扩大，保留现场证据并转入回滚或事故响应。
