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
| 账号体验 | 账号与目标 | `account-avatar-and-reminder-preferences` | profile router/settings | 资料偏好、存储、E2E |
| 管理观测 | 管理故事 | `admin-system-resource-center`, `admin-observability-and-audit` | admin/resources/audit | 资源、审计、迁移、管理UI |
| 发布治理 | 管理故事 | `admin-deployment-release-ledger` | release CLI/store/admin | 发布账本、迁移、E2E |
| 简历评估 | 简历训练闭环 | `resume-assessment-and-optimization` | 用户文件、简历服务、简历中心 | 文件/授权/迁移/评估/DOCX/E2E |
| 定向面试 | 简历训练闭环 | `resume-grounded-mock-interview` | 面试服务、出题器、面试页面 | 授权/问题质量/幂等/E2E |
| 面试复盘 | 简历训练闭环 | `real-interview-transcription-review` | 转写、复盘服务、复盘空间 | 转写/确认/评分/删除/隐私/E2E |

## 新训练闭环证据

| 产品领域 | 产品规格 | 功能契约 | 当前实现 | 执行证据 |
|---|---|---|---|---|
| 简历评估 | 简历驱动的面试训练与面试复盘 | `resume-assessment-and-optimization` | 简历应用服务与中心 | `tests/test_resume_*`, `frontend/e2e/resume.spec.ts` |
| 定向面试 | 简历驱动的面试训练与面试复盘 | `resume-grounded-mock-interview` | 现有面试服务与页面 | 定向面试测试、评估、E2E |
| 面试复盘 | 简历驱动的面试训练与面试复盘 | `real-interview-transcription-review` | 转写/复盘服务与空间 | 复盘/转写/Worker测试和E2E |

## 维护规则

- 新需求先分配稳定产品标识或功能契约ID。
- `passing`必须引用真实执行行为的文件；文件存在不是充分证据。
- 破坏性API或数据变化附设计文档、迁移和发布说明。
- 发布计划记录实际Commit、制品、Revision和验证结果。
- 如果需求被取消或替代，保留决策和替代链接，不静默删除历史。
