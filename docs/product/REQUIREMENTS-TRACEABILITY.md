# 需求追踪矩阵

## 追踪链

```text
产品目标 -> PRD用户故事 -> 功能契约ID -> API/领域 -> 测试证据 -> 发布/运行证据
```

| 产品领域 | PRD章节 | 功能契约示例 | 主要实现 | 主要证据 |
|---|---|---|---|---|
| 身份与隔离 | 账号与目标 | `auth-token-lifecycle`, `tenant-data-isolation` | auth/security/storage | auth、authorization测试 |
| 聊天 | AI问答 | `conversation-persistence`, `durable-chat-turn-lifecycle` | chat service/router | chat lifecycle、storage、前端API测试 |
| 面试 | 模拟面试 | `interview-lifecycle`, `idempotent-interview-answer` | interview service/router | interview、migration、E2E |
| 学习闭环 | 能力与学习 | `learning-review-cycle` | capability/learning | capability、learning、storage测试 |
| RAG | AI问答/管理 | `rag-relevance-and-traceability`, `atomic-knowledge-publication` | rag/publication/worker | RAG、知识发布、评估报告 |
| Agent | 平台能力 | `agent-routing-contract` | multi_agent/tools | multi-agent测试和路由报告 |
| 管理 | 管理故事 | `admin-knowledge-files`, `separate-product-admin-surfaces` | admin router | admin、authorization、E2E |
| 体验 | 页面范围 | `responsive-accessible-shell`, `conversation-history-workspace` | Vue工作区 | Playwright、axe、组件测试 |

## 维护规则

- 新需求先分配稳定产品标识或功能契约ID。
- `passing`必须引用真实执行行为的文件；文件存在不是充分证据。
- 破坏性API或数据变化附设计文档、迁移和发布说明。
- 发布计划记录实际Commit、制品、Revision和验证结果。
- 如果需求被取消或替代，保留决策和替代链接，不静默删除历史。
