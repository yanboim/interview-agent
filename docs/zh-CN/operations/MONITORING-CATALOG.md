# 监控目录

## 信号

| 范围 | 信号 | 用途 |
|---|---|---|
| HTTP | 请求数、状态、时长 | 可用性和延迟 |
| 依赖 | 数据库/Redis/Qdrant时长与错误 | 定位就绪和调用失败 |
| 模型 | 调用、错误、延迟、Token、Agent | 质量、容量和成本 |
| RAG | 检索、缓存、版本和拒绝 | 知识质量和依赖 |
| 任务 | 入队、领取、重试、失败、租约 | Worker健康 |
| 产品 | 漏斗、客户端错误、LCP | 体验与产品健康 |
| 基础设施 | CPU、内存、磁盘、连接、卷 | 容量和故障 |

## 来源

- Prometheus配置：`monitoring/prometheus.yml`
- 告警：`monitoring/alerts.yml`
- Grafana Dashboard：`monitoring/grafana/dashboards/interview-agent.json`
- OTLP：`monitoring/otel-collector.yml`
- 应用指标：`app/operations.py`

## 规则

- 标签低基数，不含用户输入、ID、Token或路径正文；
- 告警指向运行手册和责任范围；
- 发布前后比较错误、延迟、依赖和业务终态；
- 新关键业务状态必须具有日志或指标，不依赖人工查数据库。
