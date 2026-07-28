# 数据分级与处理

| 级别 | 数据示例 | 基本要求 |
|---|---|---|
| Restricted | 密码材料、Token、API密钥、恢复码、数据库Dump | 不记录、不提交；最小访问；加密存储/传输；轮换 |
| Confidential | 用户对话、面试回答、JD、评分、私人知识、向量 | 按用户/角色隔离；受控外发；备份保护；删除审计 |
| Internal | 审计摘要、内部指标、架构、运行配置 | 限内部访问；避免用户正文和高基数标签 |
| Public | 公开README、无秘密API说明、公开来源URL | 发布前审查，仍避免内部路径和凭据 |

## 处理规则

- Restricted数据不得进入Git、Issue、文档、截图、日志、Trace或指标；
- Confidential数据只用于完成已授权产品功能；
- 测试优先使用合成数据，不从生产复制；
- 发送给模型、Embedding或Search的内容必须符合批准的数据目的；
- 日志使用ID、状态、耗时和安全摘要，避免正文；
- 备份和Snapshot继承源数据的最高分级；
- 删除和保留策略覆盖数据库、Qdrant、备份、日志和第三方保留。

## 典型映射

- `.env`、`*_FILE`挂载内容：Restricted；
- `users`密码摘要和 `auth_tokens`摘要：Restricted；
- `messages`、`interview_turns`、`user_profiles`：Confidential；
- `knowledge/`及Qdrant正文/向量：Confidential；
- 聚合且无用户标识的低基数运行指标：Internal；
- 根README和公开产品文档：Public。

不确定时按更高等级处理并请求安全/数据负责人确认。
