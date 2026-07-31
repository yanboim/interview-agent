# 面试答案幂等

## 上下文

原答案路由先读取pending回合、调用评分器、生成后续问题，最后才写入答案。因此并发
请求可能在持久状态变化前都调用两个模型。进程本地锁无法保护多实例部署。

## 决策

使用现有 `interview_turns.id` 作为持久回合身份，并增加：

- `submission_status`：`pending`、`generating`、`completed` 或 `failed`；
- `idempotency_key` 和 `answer_digest`；
- 标识有权提交请求的 `claim_token`；
- 包含精确成功API响应的 `result_json`；
- 用于诊断的 `submission_error` 和 `processing_started_at`。

API要求 `Idempotency-Key`。应用服务先让Store领取当前pending回合。Store通过条件数据
库更新，把 `pending`（或相同失败命令）改为 `generating`。只有胜出的领取可以调用
模型。

完成时条件更新已领取回合，并在同一事务内插入答案尝试、可选的一个后续回合、更新
面试状态和保存响应。限定在面试范围的唯一Key阻止一个命令Key指向两个回合。

## 请求结果

- 新pending命令：领取并运行模型。
- 相同Key和答案正在生成：返回冲突/重试响应，不调用模型。
- 回合生成中使用不同Key：返回冲突。
- 相同已完成Key和答案：原样返回 `result_json`。
- 相同Key但答案不同：作为幂等误用拒绝。
- 已处理模型失败：把所属领取标为 `failed`；相同Key和答案可再次领取。

不使用自动租约接管。重新领取仍在运行但缓慢的提供方调用可能破坏至多一次模型调用
保证。进程崩溃可能让回合停在 `generating`；恢复是后续显式运维问题。

## 后果

- 幂等保护首次答案提交，不保护有意重新评分端点。
- 客户端在结果不明确的失败后必须保留Key。
- 旧已回答行迁移为 `completed`，未回答行迁移为 `pending`。
- 由数据库而非Python锁决定领取赢家。
