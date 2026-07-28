# 数据库变更规范

## 设计

- 明确表/列所有权、空值、默认、唯一和外键；
- 评估SQLite与PostgreSQL差异；
- 大表变更考虑锁、回填、索引和多版本应用兼容；
- 保留用户隔离条件和幂等约束。

## Migration

1. 在 `migrations/versions/` 创建单一目的Revision。
2. 定义Upgrade和可行的Downgrade。
3. 对历史行进行确定性回填。
4. 新应用不得依赖运行时 `create_all` 完成生产升级。
5. 测试空库至Head、上一支持Revision至Head和数据保持。

## 发布

- 发布前备份并记录当前Revision；
- 一个受控执行者运行 `alembic upgrade head`；
- Migration完成后再接流量；
- 发布后验证Revision、核心计数、约束和代表性读写。

## 回滚

Downgrade不是默认安全方案。若新版本已写入旧Schema无法表达的数据，优先保持新
Schema并回滚到兼容应用或向前修复。执行破坏性Downgrade或恢复前必须批准并验证
目标。
