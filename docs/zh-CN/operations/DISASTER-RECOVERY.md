# 灾难恢复

## 当前状态

仓库提供PostgreSQL备份/恢复、Qdrant Snapshot元数据、版本化知识回滚和不可变发布
制品。正式RPO、RTO、跨区域复制、备份保留和轮换尚未由业务批准，因此不能声称
具体恢复承诺。

## 灾难场景

| 场景 | 首选恢复 |
|---|---|
| 应用制品故障 | 回滚到上一已知良好镜像 |
| 数据库不可用 | 恢复服务或切换受控副本；必要时从验证备份恢复 |
| Redis丢失 | 重建缓存/限流；评估未完成任务并安全重建 |
| Qdrant损坏 | 从受管理历史版本或Snapshot恢复并切换别名 |
| 模型提供方不可用 | 失败关闭受影响功能、保留可重试状态，不伪造回答 |
| Secret泄露 | 轮换、撤销、限制访问、审计和安全事件响应 |
| 整个环境丢失 | 从IaC/Compose参考、不可变制品、Secret、数据库备份和知识Snapshot重建 |

## 恢复顺序

```text
network and secrets
 -> PostgreSQL
 -> Redis
 -> Qdrant serving version
 -> migrations
 -> app and worker
 -> readiness
 -> core business validation
 -> traffic
```

## 演练

至少定期在非生产环境演练：

- PostgreSQL从备份恢复；
- Qdrant Snapshot恢复到新集合并切换测试别名；
- 上一制品回滚；
- Redis任务所有者过期后的恢复；
- Secret轮换和Token撤销；
- 无外部模型时的错误与用户恢复体验。

每次演练记录实际恢复时间、数据缺口、失败步骤和行动项。只有基于多次演练和业务
影响评估，才能批准RPO/RTO。
