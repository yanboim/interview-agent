# 业务验收测试

| 场景 | 核心验收 | 主要证据 |
|---|---|---|
| 注册与令牌 | 刷新轮换、退出撤销、无明文Token | `tests/test_auth.py` |
| 租户隔离 | 第二用户不能读取、修改或删除第一用户资源 | `tests/test_authorization.py` |
| 目标与今日训练 | 资料持久化，建议使用账号数据 | 存储测试、产品E2E |
| 聊天 | 流式回答、完成原子化、失败/取消恢复、同键重放 | `tests/test_chat_lifecycle.py` |
| 会话历史 | 搜索、重命名、归档、恢复和删除按用户隔离 | `tests/test_storage.py` |
| 模拟面试 | 题目、回答、评分、下一题和报告持久化 | 面试/存储测试 |
| 面试幂等 | 并发只评分一次，同键重放，不同内容拒绝 | `tests/test_interview_idempotency.py` |
| 能力画像 | 跨场次聚合、主题筛选和异常历史容错 | `tests/test_capability.py` |
| 学习复习 | 去重、状态、复习次数和递增间隔 | `tests/test_learning.py` |
| 私人RAG | 低相关拒绝、来源保留、版本缓存隔离 | `tests/test_rag.py` |
| Agent路由 | 专用Agent工具存在，按Agent报告准确率 | 多Agent测试与评估 |
| 管理后台 | 独立登录、角色限制、安全知识文件 | 管理/授权测试 |
| 知识发布 | 候选失败不影响服务版本，可原子发布和回滚 | `tests/test_knowledge_publication.py` |
| 后台任务 | 领取、心跳、确认、重试、恢复和所有者隔离 | Worker/Redis测试 |
| 响应式与可访问 | 桌面/移动无溢出，无严重axe问题 | `frontend/e2e/` |

正式功能状态和全部引用以
[功能契约](../product-specs/feature-contract.json)为准。本表用于人工发布评审，
不能替代可执行契约。
