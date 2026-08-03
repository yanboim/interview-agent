# 监控目录

## 信号

| 范围 | 信号 | 用途 |
|---|---|---|
| HTTP | 请求数、状态、时长 | 可用性和延迟 |
| 依赖 | 数据库/Redis/Qdrant时长与错误 | 定位就绪和调用失败 |
| 模型 | 调用、错误、延迟、Token、Agent | 质量、容量和成本 |
| 模型路由 | 用途、阶段、调用/Token/成本预算、首Token、回退 | 质量/成本回归和回滚判断 |
| Agent安全 | DLP拒绝、确认预览/执行/过期、零容忍失败 | 外发和变更安全 |
| Agent运行 | 提议、待确认、步骤、完成、失败、取消、恢复 | 持久工作流可靠性 |
| Workflow V2 | 完成/失败/取消、时延直方图、累计成本 | 生产观察、回归判断和历史退役证据 |
| Agent质量 | 声明证据、反馈、评估候选、能力置信、复习结果 | 训练闭环质量 |
| RAG | 检索、缓存、版本和拒绝 | 知识质量和依赖 |
| 任务 | 入队、领取、重试、失败、租约 | Worker健康 |
| 产品 | 漏斗、客户端错误、LCP | 体验与产品健康 |
| 基础设施 | CPU、内存、磁盘、连接、卷 | 容量和故障 |

## 来源

- Prometheus配置：`monitoring/prometheus.yml`
- 告警：`monitoring/alerts.yml`
- Grafana Dashboard：`monitoring/grafana/dashboards/interview-agent.json`
- OTLP Trace 与 Metrics：`monitoring/otel-collector.yml`
- 应用指标：`app/operations.py`
- OTel 指标适配：`app/operational_metrics.py`

## Workflow V2生产观察

应用同时导出 `interview_agent_workflow_runs_total`、
`interview_agent_workflow_duration_seconds_*` 和
`interview_agent_workflow_cost_usd_total`。标签只包含固定工作流名和有界结果，不包含
用户、请求、会话、正文或Secret。当前显式路径使用 `chat-workflow-v2`。历史
Supervisor窗口使用 `chat-supervisor-v1`；保留该标签仅用于审计已采集的双窗口证据，
不是可配置的运行时拓扑。失败和取消也会计入尝试数；失败执行的模型成本仍会记录。

未来公开发布需要生产双窗口比较时，使用批准的、无内嵌凭据的Prometheus入口运行：

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

脚本使用版本化固定查询ID，分别按历史Supervisor基线窗口和Workflow V2候选窗口计算完成请求
数、完成率、p95和单次完成成本；两个窗口都必须至少24小时且100个完成请求。结果默认写入
忽略的 `.var/`。输出只是草稿：质量报告摘要、安全零容忍结果、`off`回滚台账和外部
审批仍保持未完成，因此草稿不能自行通过生产观察门禁。当前预发布退役由独立、已批准的
`workflow-v2-prerelease-acceptance.json` 证据约束。

## 后台入口配置

管理员侧边栏可以显示 Prometheus 和 Grafana 的“运维工具”入口。分别通过
`ADMIN_PROMETHEUS_URL` 和 `ADMIN_GRAFANA_URL` 配置管理员浏览器能够访问的
HTTP(S) 地址；留空时不显示对应入口。

- URL 不得内嵌用户名、密码或 Token；不安全的 URL 会被服务端丢弃；
- 生产环境应使用 VPN、零信任网关或独立认证反向代理提供地址；
- 配置入口不会改变 Compose 的回环端口绑定，也不会自动公开监控服务；
- 链接在新窗口打开，Grafana/Prometheus 自身的认证与授权仍然有效。

## 规则

- 标签低基数，不含用户输入、ID、Token或路径正文；
- `/metrics` 与管理员快照保留单实例即时视图；跨实例聚合和进程重启后的
  长期趋势使用 OTel Metrics/外部监控后端；
- 告警指向运行手册和责任范围；
- 发布前后比较错误、延迟、依赖和业务终态；
- 新关键业务状态必须具有日志或指标，不依赖人工查数据库。
