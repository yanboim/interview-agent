# 数据架构

## 关系数据

| 表 | 主要职责 | 所有权/关联 |
|---|---|---|
| `users` | 账号、密码摘要、角色 | 身份根 |
| `auth_tokens` | Access/Refresh摘要和撤销 | `user_id` |
| `user_profiles` | 岗位、方向、JD、提醒和摘要游标 | `user_id` |
| `conversations` | 会话、标题、归档和摘要 | `user_id` |
| `messages` | 完成的用户/助手消息与来源元数据 | `user_id + session_id` |
| `chat_turns` | 聊天命令生命周期、幂等和结果 | 会话 |
| `assistant_feedback` | 回合点赞/点踩、原因和生成/证据版本 | `user_id + chat_turn` |
| `coaching_memories` | 待确认/已确认/已拒绝训练记忆及来源版本 | `user_id` |
| `interviews` | 面试配置、状态和归档 | `user_id` |
| `interview_turns` | 问题、答案、评分和提交生命周期 | 面试 |
| `interview_answer_attempts` | 主动重答历史 | 面试回合 |
| `resume_documents` | 简历原件元数据、存储键和解析状态 | `user_id` |
| `resume_analyses` | JD快照、评估、事实警告、优化稿和编辑版本 | 简历 |
| `interview_reviews` | 输入、逐字稿版本/确认、处理状态和报告 | `user_id` |
| `interview_review_turns` | 已确认真实面试问答和评分 | 复盘 |
| `learning_tasks` | 学习行动和复习调度 | `user_id` |
| `agent_action_confirmations` | 外发/变更预览、内容摘要、过期、领取和重放 | `user_id` |
| `agent_runs` | 持久Agent业务工作流状态、幂等和安全结果 | `user_id` |
| `agent_steps` | 运行步骤、领取、尝试、错误和结果重放 | Agent运行 |
| `evaluation_candidates` | 经隐私评审前保持内容最小化的负反馈候选 | 用户反馈 |
| `tool_audit_logs` | 工具调用审计 | 用户/角色 |
| `product_events` | 产品行为和客户端错误 | `user_id` |
| `audit_events` | API动作、目标、请求ID、结果和耗时 | 主体/角色 |
| `execution_traces` | 模型和工具阶段的安全关联元数据 | 请求/业务资源 |
| `deployment_releases` | 环境版本、验证结果和回滚证据 | 管理读取模型 |

准确列、约束和索引以 `app/database.py` 和Alembic迁移为准。

## 事务边界

- 存储使用同步SQLAlchemy Core；
- 一个Store mutation拥有一个 `engine.begin()`；
- 读取拥有一个 `engine.connect()`；
- 模型、Embedding、Qdrant和公开网络调用不在数据库事务中；
- 外部调用前通过条件更新领取业务命令，完成时由所有者令牌条件提交；
- Agent确认、运行和步骤使用所有者/内容绑定的条件领取；命令步骤效果、结果重放和
  终态原子提交，SSE只投影已持久化生命周期；
- `interview_reviews` 保存真实面试状态、逐字稿版本、确认版本和整体报告，
  `interview_review_turns` 原子保存已确认的候选人问答评分；音频仅在转写期间由
  用户文件存储键引用；
- 唯一约束、外键和内容摘要补充应用校验。

## 数据一致性

- 用户所有权条件必须出现在读取和变更中；
- 幂等键按相应业务作用域唯一；
- 已完成命令保存原始响应用于重放；
- 能力画像只聚合当前用户已评分数据；
- 只有已确认且来源仍有效的训练记忆进入Agent上下文；反馈、确认、运行和评估候选均
  按服务端用户身份隔离；
- 生成产物保存Prompt、Schema和模型版本；声明引用保存稳定证据ID而非正文副本；
- 数据库迁移对历史回合进行显式回填，不依赖运行时猜测。

## 非关系数据

- Redis：限流计数、RAG缓存、发布锁和后台任务。缓存可丢失，锁和任务使用所有者
  Token、租约或确认语义；
- Qdrant：版本化Dense/Sparse向量和来源元数据，通过稳定别名发布；
- 文件系统：知识源文件、前端产物、头像、简历原件和临时复盘音频；生产持久内容
  需要挂载卷，用户文件使用服务端存储键并经认证访问；
- 日志/指标/Trace：不得存放令牌、完整私人知识或不受控用户正文。

## 生命周期

- 用户主动删除会话或面试时只删除其拥有的数据及关联记录；
- 删除训练记忆会立即排除未来上下文，但不删除权威会话/面试历史；删除反馈不修改助手
  消息；确认记录和Agent运行按批准的业务/审计保留策略处理；
- 删除简历会清理原件和派生分析，但保留已创建面试的最小化上下文快照；音频在逐字稿
  成功持久化后删除，转写失败时只为受控重试暂存；
- Token在刷新、退出、改密或恢复密码时撤销；
- Qdrant历史版本当前需人工容量管理，不得删除别名当前目标；
- 备份包含PostgreSQL dump、Qdrant snapshot元数据和用户文件清单，数据库与用户文件
  按同一恢复批次验证；
- 正式数据保留期限和用户数据导出/删除SLA尚待产品与隐私审批。
