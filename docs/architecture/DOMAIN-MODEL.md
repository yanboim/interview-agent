# 领域模型

## 聚合与所有权

```text
User
├── Profile
├── AuthTokens
├── Conversations
│   ├── Messages
│   ├── ChatTurns
│   │   └── AssistantFeedback
│   └── CoachingMemories
├── Interviews
│   └── InterviewTurns
│       └── AnswerAttempts
├── ResumeDocuments
│   └── ResumeAnalyses
├── InterviewReviews
│   └── InterviewReviewTurns
├── LearningTasks
├── AgentActionConfirmations
├── AgentRuns
│   └── AgentSteps
├── EvaluationCandidates
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

`AssistantFeedback`绑定已完成助手回合和所有者，保存点赞/点踩、原因、可选文本以及
Prompt/Schema/模型/证据版本。负面反馈只先形成不含正文的 `EvaluationCandidate`；
隐私评审后才能补充脱敏评估载荷。

## Agent上下文与记忆

`CoachingMemory`是用户拥有的事实、偏好、目标或来源派生观察，状态为 `proposed`、
`confirmed` 或 `rejected`。只有confirmed且来源仍有效的记录进入不可变Agent上下文
快照；纠正会递增版本并回到proposed，删除立即从未来快照移除。

`AgentActionConfirmation`保存预览类型、所有者、内容摘要、过期时间、单次领取Token
和重放结果。它适用于公开搜索外发和学习计划变更，确认不能改变原预览内容。

## 持久Agent工作流

`AgentRun`是应用拥有的多步业务工作流，而不是LangGraph Checkpoint。运行状态为：

```text
proposed -> awaiting_confirmation -> running -> completed
                                      ├-> failed
                                      `-> cancelled
```

`AgentStep`使用 `pending -> claimed -> completed|failed|skipped`，并保存稳定幂等键、
输入摘要、领取所有者、尝试、安全错误和结果重放。命令步骤与业务效果在同一事务提交；
模型/工具网络调用始终位于事务外。

## 面试

`Interview`保存主题、难度、总题数、状态和归档信息。`InterviewTurn`保存题目、
回答、四维评分、反馈及提交生命周期。`AnswerAttempt`保存用户主动重答形成的历史
尝试。

网络重试复用同一幂等命令；主动重答创建新的尝试，两者语义不同。

面试可保存可空的简历分析来源和最小化上下文快照。快照使历史面试在简历删除后仍可
解释，但不复制完整简历正文。

## 简历

`ResumeDocument`保存用户原件、受控存储键、解析状态和删除生命周期。
`ResumeAnalysis`保存岗位/JD快照、结构化评分、证据、事实警告、完整优化稿、编辑
版本和处理状态。优化稿使用乐观版本；存在事实警告或占位符时不能导出DOCX。

## 真实面试复盘

`InterviewReview`保存文本或音频输入的处理状态、逐字稿、逐字稿版本、确认版本和
整体报告。`InterviewReviewTurn`只保存从已确认逐字稿中配对出的候选人问答及评分。
修改逐字稿会使旧确认失效；报告和评分回合在同一事务中提交。

## 能力与学习

能力画像是从已评分面试回合派生的读取模型，不单独作为权威表。`LearningTask`
保存薄弱维度、行动、状态、到期时间、复习次数、回忆结果、难度、遗忘次数、置信度
和下次复习时间。活跃任务按业务键去重，复习间隔在1–60天内确定性计算。

## 知识发布

知识文件是管理员管理的输入。物理Qdrant集合是不可变候选/历史版本，稳定别名表示
当前服务版本。发布任务拥有幂等键、领取所有者、租约、尝试次数和终态。

知识集合不是用户业务数据聚合的一部分，但其内容属于私有数据边界。

## 管理读取模型

`AuditEvent`记录请求主体、动作、安全目标、结果、耗时和请求ID；
`ExecutionTrace`记录模型/工具阶段的有界安全元数据；`DeploymentRelease`记录环境、
版本、验证结果和回滚证据。聊天和面试权威正文不复制到这些表。
