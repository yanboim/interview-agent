# Worktree栈隔离

## 命名空间

Compose默认按项目名为容器、网络和命名卷加前缀。固定 `container_name` 会绕过隔离，
因此已移除；`COMPOSE_PROJECT_NAME` 生成为
`interview-agent-<worktree-name>-<path-hash>`。

## 宿主端口

生成器按解析后的Worktree路径分配确定性端口块，显式输出应用、PostgreSQL、Redis、
Qdrant HTTP/gRPC、Prometheus、Grafana和Playwright端口。容器间URL继续使用服务DNS
名和固定内部端口。

运维人员可覆盖任意生成值。生成过程原子化并拒绝不安全后缀。本地 `.env.worktree`
不包含凭据。

## 命令

`make worktree-env` 创建或刷新本地环境文件。`make stack-up`、
`make stack-config` 和 `make stack-down` 使用该文件调用Compose。除非运维人员显式
使用 `--volumes`，Teardown不会删除卷。
