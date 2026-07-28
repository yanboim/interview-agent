# 环境说明

| 环境 | 目的 | 数据 | 外部服务 | 发布方式 |
|---|---|---|---|---|
| Local | 开发与聚焦测试 | SQLite或本地Compose | 默认替身；显式Live | Worktree隔离 |
| CI | 可重复验证 | 临时数据库/服务 | 不使用生产Secret | GitHub Actions |
| Canary | 生产前小范围验证 | 生产级隔离或受控数据 | 生产等价配置 | 环境审批 |
| Production | 用户流量 | PostgreSQL、Redis、Qdrant持久卷 | 已批准提供方 | 受控部署 |

## Local

- `.env`不提交；
- `make worktree-env` 生成不含秘密的 `.env.worktree`；
- 两个Worktree使用不同Compose project、端口、网络和卷；
- SQLite适合快速开发，不替代PostgreSQL专项验证。

## CI

- Python 3.12、Node 20；
- 哈希锁定Python依赖和npm lockfile；
- 执行静态、后端、前端、E2E、审计和镜像扫描；
- 不应访问生产数据库、知识集合或真实用户数据。

## Canary

- 使用与生产相同的不可变制品和迁移路径；
- 独立入口或小比例流量；
- 具备与生产等价的健康、日志、指标和Trace；
- 通过后才能扩大，失败时可独立回滚。

## Production

- `AUTH_REQUIRED=true`；
- PostgreSQL、Redis和Qdrant使用私有网络和持久存储；
- Secret使用平台或文件挂载，不保存在镜像和仓库；
- 外部模型与搜索的数据处理已批准；
- 迁移、备份、发布和恢复均有审计证据。

环境间不能复制真实用户数据到低环境，除非经过批准、最小化和不可逆脱敏。
