# 功能地图

## 产品用户能力

| 领域 | 当前能力 | 主要入口 | 权威证据 |
|---|---|---|---|
| 身份 | 注册、登录、刷新、退出、改密、恢复码 | `/api/auth/*` | `tests/test_auth.py` |
| 目标与账号 | 岗位、方向、JD、头像、提醒偏好 | `/api/profile*` | 资料/偏好/存储测试 |
| 今日训练 | 基于目标和到期事项推荐下一步 | `/api/today-plan` | 路由及前端E2E |
| 聊天 | 流式问答、来源、持久历史、幂等重试 | `/api/chat*` | `tests/test_chat_lifecycle.py` |
| 历史 | 搜索、打开、重命名、归档、恢复、删除 | `/api/conversations*` | `tests/test_storage.py` |
| 面试 | 开始、答题、评分、重答、恢复、归档、报告 | `/api/interviews*` | 面试和存储测试 |
| 能力 | 跨场次维度、趋势、主题和薄弱点 | `/api/capability-profile` | `tests/test_capability.py` |
| 学习 | 生成任务、修改状态、复习和删除 | `/api/learning-tasks*` | `tests/test_learning.py` |
| 简历 | 上传、岗位评估、证据化改写、编辑和DOCX导出 | `/api/resumes*` | 简历服务/API/备份/E2E |
| 定向面试 | 基于简历项目和JD差距进行文字模拟面试 | `/api/interviews/start` | 定向面试与评估测试 |
| 面试复盘 | 音频/文本、逐字稿确认、逐题复盘和学习闭环 | `/api/interview-reviews*` | 复盘/转写/Worker/E2E |

详细范围见
[简历驱动的面试训练与面试复盘](RESUME-INTERVIEW-REVIEW.md)。

## 管理员能力

| 领域 | 当前能力 | 主要入口 |
|---|---|---|
| 独立身份 | 管理员专用登录和浏览器会话 | `/api/admin/auth/login` |
| 用户管理 | 用户列表和角色调整 | `/api/admin/users*` |
| 运行信息 | 系统摘要、资源、配置、依赖和Worker心跳 | `/api/admin/resources` |
| 审计分析 | 活动审计、权威交互、执行追踪、工具和产品事件 | `/api/admin/audit-events` |
| 发布历史 | 部署执行器写入的Canary/生产结果账本 | `/api/admin/releases` |
| 知识文件 | 安全文件名下的列出、保存和删除 | `/api/admin/knowledge/files*` |
| 知识发布 | 导入、任务状态、版本状态和回滚 | `/api/admin/knowledge/*` |

## 平台能力

- SQLite/PostgreSQL持久化和Alembic迁移；
- Redis限流、缓存、发布锁和可恢复后台任务；
- Qdrant版本化知识集合与稳定别名；
- 模型策略网关、上下文预算和多Agent路由；
- Prometheus指标、结构化日志和OpenTelemetry；
- Worktree隔离Compose环境；
- CI、依赖审计、镜像扫描和发布制品。

每项产品行为的正式状态以
[机器可读功能契约](../product-specs/feature-contract.json)为准。
