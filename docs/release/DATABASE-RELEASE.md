# 数据库发布

## 准备

- 记录当前Revision和目标Head；
- 阅读每个待执行Migration；
- 评估锁、耗时、历史回填、空间和多版本兼容；
- 创建并验证生产备份；
- 定义失败停止条件和应用兼容回滚。

## 执行

一个受控执行者运行：

```bash
alembic current
alembic heads
alembic upgrade head
```

应用接流量前确认Revision、核心表、约束、索引和代表性数据。大规模回填应拆为可观测
步骤，不在不可控启动超时中完成。

## 回滚

优先向前修复或保持新Schema回滚兼容应用。Downgrade前确认新数据不会丢失；从备份
恢复会覆盖目标，必须进入事故/维护窗口流程。
