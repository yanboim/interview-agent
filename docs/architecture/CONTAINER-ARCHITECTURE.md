# 容器与运行架构

## 当前拓扑

```text
Browser
  |
  v
app: FastAPI + built Vue
  |-- PostgreSQL: durable relational state
  |-- Redis: rate limit, cache, locks, durable jobs
  |-- Qdrant: private vector/sparse knowledge
  |-- Zhipu APIs: chat and embeddings
  `-- optional search provider

worker
  |-- Redis: claim/heartbeat/ack/retry jobs
  `-- Qdrant + embedding provider: knowledge publication

app -> OTEL Collector
Prometheus -> app /metrics
Grafana -> Prometheus
```

## 部署单元

- `app`：唯一HTTP入口、组合根、API路由和前端静态文件；
- `worker`：执行可恢复的知识导入任务；
- `postgres`：生产权威业务数据库；
- `redis`：跨实例协调和非权威缓存；
- `qdrant`：版本化私人知识索引；
- `otel-collector`、`prometheus`、`grafana`：观测组件。

当前是模块化单体加一个Worker，不计划在模块事务边界明确前拆分网络微服务。

## 网络和存储

Compose将宿主端口绑定到 `127.0.0.1`。生产环境还需要由部署平台提供TLS、入口
访问控制和私有服务网络。PostgreSQL、Redis、Qdrant和监控端口不得直接暴露公网。

持久卷分别承载数据库、Redis、Qdrant、Grafana、Prometheus、应用数据和知识文件。
容器更新不能隐式删除卷。

## 启动顺序

```text
dependencies healthy
  -> alembic upgrade head
  -> app accepts traffic
  -> /ready verifies configured database, Qdrant and Redis
```

Worktree环境通过 `make worktree-env` 生成稳定的Compose project和宿主端口，
避免两个工作区共享容器、网络或命名卷。
