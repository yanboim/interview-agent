# 可靠性与运维

本文件说明当前运行模型和安全的首次响应动作。以命令为主的快速开始仍见
[根README](../root/README.md)。

## 运行依赖

| 组件 | 角色 | 当前失败行为 |
|---|---|---|
| FastAPI应用 | HTTP API和构建后的前端 | 进程失败会移除该副本 |
| PostgreSQL或SQLite | 用户、会话、面试、学习、审计等持久数据 | 配置的数据库不可用时就绪检查失败 |
| Redis | 共享限流、RAG缓存、发布锁和任务队列 | 限流回退到本地；已配置Redis但不可用时发布按失败关闭 |
| Qdrant | 版本化私人知识索引 | 就绪和知识检索失败；导入失败时上一个发布别名保持不变 |
| 智谱API | 聊天、面试、评分、Embedding和可选重排 | 模型网关执行超时、重试、并发、预算、安全错误和指标策略 |
| Worker | 长时间知识、简历、转写和复盘任务 | 进程心跳、所有者围栏Redis租约、重试、崩溃恢复和死信 |
| 用户文件卷 | 头像、简历和临时复盘音频 | API/Worker无法读取时相关处理失败，数据库所有权记录保持不变 |
| 可选转写服务 | 经用户确认的音频转写 | 未配置、未同意、超时或提供方失败时不生成逐字稿 |

## 健康与观测

- `GET /health` 表示进程存活。
- `GET /ready` 检查必要且已配置的依赖，用于控制流量准入。
- `GET /metrics` 暴露Prometheus格式的应用和依赖指标。
- 结构化JSON日志由 `JSON_LOGS` 和 `LOG_LEVEL` 控制。
- 通过 `OTEL_ENABLED` 和配置的OTLP Endpoint启用OpenTelemetry导出。
- 管理员系统资源中心提供经脱敏的依赖状态和带TTL的Worker新鲜度。

Compose包含Prometheus和Grafana。不得把Qdrant、Redis、PostgreSQL、Prometheus、
Grafana或OpenTelemetry Collector直接暴露公网。

## 首次响应Runbook

1. 确认影响范围：单一请求、单个副本还是整个服务。
2. 分别检查存活和就绪：

   ```bash
   curl -fsS http://localhost:8000/health
   curl -fsS http://localhost:8000/ready
   docker compose ps
   ```

3. 检查应用和受影响依赖日志，不得输出Secret或私人知识：

   ```bash
   docker compose logs --since=15m app worker
   ```

4. 在Prometheus/Grafana检查请求错误、依赖错误和延迟。
5. 如果事故由部署引起，停止提升并执行发布回滚；如果由知识发布引起，执行下方版本化
   知识回滚。
6. 记录时间线、受影响功能、缓解措施和后续技术债或设计工作。

不得把删除集合、清空数据库、轮换Secret或确认恢复操作当作诊断捷径。

## 知识发布与回滚

导入构建版本化Qdrant物理集合，验证结构、运行配置的回归门禁，再原子移动稳定别名。
失败候选不会替换服务版本。

通过认证管理员接口检查和回滚：

```text
GET  /api/admin/knowledge/status
POST /api/admin/knowledge/rollback
{"collection_name":"interview_knowledge__v_<version>"}
```

回滚只改变别名，不删除离开的版本。版本保留尚未自动化；应监控Qdrant容量，绝不能
手工删除当前服务别名指向的集合。

已接受设计见
[Qdrant版本化发布](../design-docs/qdrant-versioned-publication.md)。

## 备份与恢复

生产备份要求PostgreSQL `DATABASE_URL`、可访问的Qdrant以及配置的用户文件卷：

```bash
python -m scripts.backup --dry-run
python -m scripts.backup --output backups
```

备份目录包含PostgreSQL Dump、Qdrant Snapshot元数据、用户文件清单和Manifest。
不改变数据库即可验证备份：

```bash
python -m scripts.restore backups/<timestamp>
```

`--confirm` 会运行 `pg_restore --clean` 并覆盖配置的PostgreSQL数据库。只有在批准的
维护窗口、核对目标和备份后才能使用：

```bash
python -m scripts.restore backups/<timestamp> --confirm
```

恢复脚本不会自动恢复Qdrant。按Manifest中的Snapshot元数据操作，并单独确认目标集合。
数据库和用户文件应作为同一恢复批次验证。备份只有在非生产环境完成恢复演练后才算
得到证明。

## 运行限制

优先级结构问题见[技术债跟踪器](../tech-debt-tracker.md)，当前登记项均已完成。仍需
显式处理的残余运行限制：

- 进程硬崩溃可能使聊天或面试回合停留在 `generating`；外部模型调用具备围栏前禁止
  自动接管；
- Qdrant历史版本保留尚未自动化；
- 正式RPO、RTO、数据保留期限和容量目标尚未批准；
- 云端音频转写只可在完成提供方、地区、保留和成本审批的环境启用。

详细过程见[运维手册](../operations/README.md)和
[发布Runbook](../release/README.md)。
