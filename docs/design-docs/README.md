# 设计文档

持久提案和已接受设计决策保存在这里。设计文档应说明上下文、决策、替代方案、后果、
迁移和验证；小型实现细节应记录在执行计划中。

## 已接受设计

- [聊天上下文预算与持久摘要](chat-context-budget.md)
- [聊天用例边界](chat-use-case-boundary.md)
- [持久聊天回合生命周期](durable-chat-turn-lifecycle.md)
- [持久Redis任务](durable-redis-jobs.md)
- [前端工具链审计门禁](frontend-toolchain-audit.md)
- [面试答案幂等](interview-answer-idempotency.md)
- [模型策略网关](model-policy-gateway.md)
- [模块化API组合](modular-api-composition.md)
- [Qdrant版本化知识发布](qdrant-versioned-publication.md)
- [可复现构建输入](reproducible-builds.md)
- [仓库边界演进决策](repository-boundary-evolution.md)
- [同步持久化边界](synchronous-persistence-boundary.md)
- [Worktree栈隔离](worktree-stack-isolation.md)
- [用户敏感文件与异步处理](user-sensitive-file-processing.md)
- [简历与面试训练闭环](resume-interview-review-loop.md)

以上设计已由迁移、应用服务、API、前端和测试落地。2026-07-31 Agent安全、证据、
记忆、持久工作流、反馈质量和模型路由边界记录在
[根架构文档](../../ARCHITECTURE.md)及其
[完成计划](../exec-plans/completed/2026-07-30-agent-application-hardening.md)中；后续改变
这些跨模块边界时应提炼新的持久设计文档。当前行为以
[根架构文档](../../ARCHITECTURE.md)、设计决策和状态为 `passing` 的产品契约为准；
后续改变所有权、文件生命周期、外发或状态机语义时需要更新对应设计。
