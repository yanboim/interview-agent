# 备份与恢复

## 备份范围

- PostgreSQL自定义格式Dump；
- Qdrant Snapshot元数据；
- 备份Manifest：创建时间、目标、集合和Snapshot响应；
- 应用制品、Alembic Revision和配置版本应在发布记录中另行保存。

Redis缓存可重建；后台任务是否可以丢失取决于业务阶段，生产恢复计划必须显式评估。

## 创建

先检查计划：

```bash
python -m scripts.backup --dry-run
```

确认生产 `DATABASE_URL`、目标目录、磁盘、Qdrant和维护策略后：

```bash
python -m scripts.backup --output backups
```

备份目录不得提交Git或暴露给未授权用户。

## 验证

默认恢复命令只校验Manifest和Dump存在，不改变数据库：

```bash
python -m scripts.restore backups/<timestamp>
```

进一步验证包括校验和、可读取性、Revision记录和隔离环境恢复演练。

## PostgreSQL恢复

`--confirm` 会使用 `pg_restore --clean --if-exists` 覆盖目标：

```bash
python -m scripts.restore backups/<timestamp> --confirm
```

执行前必须：

- 明确目标不是错误环境；
- 停止应用写入；
- 保存目标当前状态；
- 获得维护窗口和破坏性操作批准；
- 记录恢复后的迁移和数据校验计划。

## Qdrant恢复

脚本不自动恢复Qdrant。按Manifest中的Snapshot在独立集合恢复，验证结构和检索后，
再通过受管理别名切换。不要直接覆盖当前集合或删除服务版本。

## 恢复验收

- 数据库可连接且Revision正确；
- 核心表计数和关键抽样一致；
- 用户隔离、登录、聊天/面试读取正常；
- Qdrant别名指向已验证版本；
- `/ready` 成功；
- 恢复时间、数据缺口和后续迁移被记录。
