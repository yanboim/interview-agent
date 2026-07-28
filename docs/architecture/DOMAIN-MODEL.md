# 领域模型

## 聚合与所有权

```text
User
├── Profile
├── AuthTokens
├── Conversations
│   ├── Messages
│   └── ChatTurns
├── Interviews
│   └── InterviewTurns
│       └── AnswerAttempts
├── LearningTasks
├── ProductEvents
└── ToolAuditLogs
```

`User`是所有产品数据的所有权根。服务端认证身份决定用户，客户端传入的
`user_id`仅用于兼容和一致性校验。

## 会话

`Conversation`由用户和稳定 `session_id` 标识，包含标题、归档状态、摘要及摘要
覆盖位置。`Message`是完成后的正式历史。`ChatTurn`是一次可重试生成命令，具有
幂等键、内容摘要、状态、所有者令牌和持久化结果。

典型状态：

```text
pending -> generating -> completed
                    ├-> failed
                    `-> cancelled
```

同一会话最多一个生成中的回合。用户消息和助手消息仅在完成时一起物化。

## 面试

`Interview`保存主题、难度、总题数、状态和归档信息。`InterviewTurn`保存题目、
回答、四维评分、反馈及提交生命周期。`AnswerAttempt`保存用户主动重答形成的历史
尝试。

网络重试复用同一幂等命令；主动重答创建新的尝试，两者语义不同。

## 能力与学习

能力画像是从已评分面试回合派生的读取模型，不单独作为权威表。`LearningTask`
保存薄弱维度、行动、状态、到期时间、复习次数和下次复习时间。活跃任务按业务键
去重。

## 知识发布

知识文件是管理员管理的输入。物理Qdrant集合是不可变候选/历史版本，稳定别名表示
当前服务版本。发布任务拥有幂等键、领取所有者、租约、尝试次数和终态。

知识集合不是用户业务数据聚合的一部分，但其内容属于私有数据边界。
