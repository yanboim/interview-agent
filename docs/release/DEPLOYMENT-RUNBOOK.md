# 部署运行手册

## 前提

- 明确目标环境、制品摘要和负责人；
- 质量门禁、审批、备份和回滚计划完成；
- 生产Secret不在命令历史或文档中显示；
- 确认维护窗口和外部服务状态。

## 部署前

```bash
python -m scripts.backup --dry-run
alembic current
alembic heads
```

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

## 停止条件

- Migration失败或历史数据校验不一致；
- 就绪持续失败；
- 跨用户访问、Token或秘密泄露；
- 错误/延迟显著超过已批准阈值；
- 聊天或面试出现重复提交结果；
- 知识别名指向未验证集合。

触发后停止扩大，保留现场证据并转入回滚或事故响应。
