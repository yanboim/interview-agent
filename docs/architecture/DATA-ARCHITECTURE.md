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
| `interviews` | 面试配置、状态和归档 | `user_id` |
| `interview_turns` | 问题、答案、评分和提交生命周期 | 面试 |
| `interview_answer_attempts` | 主动重答历史 | 面试回合 |
| `learning_tasks` | 学习行动和复习调度 | `user_id` |
| `tool_audit_logs` | 工具调用审计 | 用户/角色 |
| `product_events` | 产品行为和客户端错误 | `user_id` |

准确列、约束和索引以 `app/database.py` 和Alembic迁移为准。

## 事务边界

- 存储使用同步SQLAlchemy Core；
- 一个Store mutation拥有一个 `engine.begin()`；
- 读取拥有一个 `engine.connect()`；
- 模型、Embedding、Qdrant和公开网络调用不在数据库事务中；
- 外部调用前通过条件更新领取业务命令，完成时由所有者令牌条件提交；
- 唯一约束、外键和内容摘要补充应用校验。

## 数据一致性

- 用户所有权条件必须出现在读取和变更中；
- 幂等键按相应业务作用域唯一；
- 已完成命令保存原始响应用于重放；
- 能力画像只聚合当前用户已评分数据；
- 数据库迁移对历史回合进行显式回填，不依赖运行时猜测。

## 非关系数据

- Redis：限流计数、RAG缓存、发布锁和后台任务。缓存可丢失，锁和任务使用所有者
  Token、租约或确认语义；
- Qdrant：版本化Dense/Sparse向量和来源元数据，通过稳定别名发布；
- 文件系统：知识源文件、前端产物、备份清单；生产持久内容需要挂载卷；
- 日志/指标/Trace：不得存放令牌、完整私人知识或不受控用户正文。

## 生命周期

- 用户主动删除会话或面试时只删除其拥有的数据及关联记录；
- Token在刷新、退出、改密或恢复密码时撤销；
- Qdrant历史版本当前需人工容量管理，不得删除别名当前目标；
- 备份包含PostgreSQL dump和Qdrant snapshot元数据，恢复需分别确认；
- 正式数据保留期限和用户数据导出/删除SLA尚待产品与隐私审批。
