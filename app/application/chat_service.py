"""聊天回合应用服务：协调幂等领取、结果提交和失败释放，不直接执行模型调用。"""

import hashlib
from typing import Any, Protocol
from uuid import uuid4

from app.chat_context import validate_current_message
from app.agent_context_service import AgentContextService


class ChatTurnRepository(Protocol):
    """聊天回合持久化的最小契约（结构子类型协议）。

    实现是 ``app.storage.ConversationStore``。协议解耦使本服务可注入
    测试替身，不直接依赖 SQLAlchemy。
    """

    def begin_chat_turn(self, **kwargs: Any) -> dict[str, object]: ...

    def complete_chat_turn(self, **kwargs: Any) -> None: ...

    def terminate_chat_turn(self, **kwargs: Any) -> bool: ...


class ChatTurnError(RuntimeError):
    """聊天回合生命周期操作的应用层基类错误。"""


class ChatTurnConflict(ChatTurnError):
    """聊天回合的并发/状态冲突。

    ``retryable`` 标记客户端是否可稍后用相同幂等键重试。
    """

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ChatTurnService:
    """聊天回合生命周期协调：幂等领取、结果提交、失败/取消释放。

    本服务只做状态协调，不直接执行模型调用——流式生成由 API 适配器在领取
    之后执行，完成后回调 ``complete``/``fail``/``cancel``。模型调用因此
    始终在 Repository 的事务之外进行。
    """

    def __init__(
        self,
        repository: ChatTurnRepository,
        *,
        context_token_budget: int = 32000,
        summary_token_budget: int = 4000,
        context_service: AgentContextService | None = None,
        agent_context_reserve_tokens: int = 4000,
    ) -> None:
        """注入持久化仓库与上下文预算。

        参数:
            repository: 实现 ``ChatTurnRepository`` 的持久化适配器。
            context_token_budget: 进入模型的总上下文预算（字符/字节级估算）。
            summary_token_budget: 会话摘要预算，必须小于上下文预算。
            context_service: 可选的 Agent 上下文快照服务；提供时会在历史
                前注入系统上下文，并为其预留 token。
            agent_context_reserve_tokens: 为 Agent 系统上下文预留的额度。

        异常:
            ValueError: 摘要预算不小于上下文预算，或预留额度不小于上下文预算。
        """
        if summary_token_budget >= context_token_budget:
            raise ValueError(
                "chat summary token budget must be smaller than context budget"
            )
        self.repository = repository
        self.context_token_budget = context_token_budget
        self.summary_token_budget = summary_token_budget
        self.context_service = context_service
        self.agent_context_reserve_tokens = agent_context_reserve_tokens
        if context_service and agent_context_reserve_tokens >= context_token_budget:
            raise ValueError("agent context reserve must be smaller than chat budget")

    def begin(
        self,
        *,
        user_id: str,
        session_id: str,
        content: str,
        idempotency_key: str,
        role: str = "user",
    ) -> dict[str, object]:
        """开始一个聊天回合：校验预算 → 幂等领取 → 组装模型输入。

        先拒绝必然超预算的输入，避免创建注定无法完成的持久化回合；再用
        内容摘要与幂等键领取（重放相同内容直接返回已存结果）。领取成功后
        组装模型 ``messages``（含历史 + 当前请求），若启用 Agent 上下文
        服务则在其前注入系统上下文快照。

        参数:
            user_id: 服务端解析的当前用户 ID。
            session_id: 目标会话 ID。
            content: 用户输入内容。
            idempotency_key: 客户端幂等键；只允许重放相同内容。
            role: 当前消息角色，默认 ``"user"``。

        返回:
            含 ``turn_id``、``claim_token``（所有者令牌）、``messages``
            （发给模型的输入）、可选 ``context_snapshot`` 的字典。

        异常:
            ChatTurnConflict: 幂等键复用于不同内容 / 他请求正在生成
                （可重试）/ 当前会话已有生成中回合。
            ChatTurnError: 遇到未知领取状态。
        """
        # 先拒绝必然超预算的输入，避免创建一个注定无法完成的持久化回合。
        validate_current_message(content, self.context_token_budget)
        claim_token = str(uuid4())
        result = self.repository.begin_chat_turn(
            user_id=user_id,
            session_id=session_id,
            content=content,
            idempotency_key=idempotency_key,
            request_digest=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            turn_id=str(uuid4()),
            claim_token=claim_token,
            context_token_budget=(
                self.context_token_budget - self.agent_context_reserve_tokens
                if self.context_service
                else self.context_token_budget
            ),
            summary_token_budget=self.summary_token_budget,
        )
        # Repository 用结果枚举表达并发竞争，应用层再映射为稳定的领域错误。
        outcome = str(result["outcome"])
        if outcome == "completed":
            return result
        if outcome == "key_reused":
            raise ChatTurnConflict(
                "同一 Idempotency-Key 不能用于不同聊天内容"
            )
        if outcome == "in_progress":
            raise ChatTurnConflict(
                "该聊天回合正在生成，请稍后使用相同 Idempotency-Key 重试",
                retryable=True,
            )
        if outcome == "conflict":
            raise ChatTurnConflict("当前会话已有正在生成的聊天回合")
        if outcome != "claimed":
            raise ChatTurnError(f"未知聊天领取状态：{outcome}")
        history = [
            {
                "role": str(item["role"]),
                "content": str(item["content"]),
            }
            for item in result["history"]  # type: ignore[union-attr]
        ]
        history.append({"role": "user", "content": content})
        snapshot = None
        if self.context_service:
            snapshot = self.context_service.build(
                user_id=user_id,
                role=role,
                conversation_messages=history[:-1],
            )
            history.insert(
                0,
                {"role": "system", "content": snapshot.render_system_context()},
            )
        return {**result, "messages": history, "context_snapshot": snapshot}

    def complete(
        self,
        claim: dict[str, object],
        *,
        user_id: str,
        session_id: str,
        answer: str,
        metadata: dict[str, object],
    ) -> None:
        """成功完成一个聊天回合，把助手回复与元数据原子落库。

        用领取时返回的 ``claim_token`` 做条件提交，因此只有回合所有者
        能完成；迟到或并发的其他请求不会覆盖结果。

        参数:
            claim: ``begin`` 返回的领取信息（含 ``turn_id``、``claim_token``）。
            user_id / session_id: 当前用户与目标会话。
            answer: 助手回复正文。
            metadata: 引用、来源等需一并持久化的元数据。
        """
        self.repository.complete_chat_turn(
            user_id=user_id,
            session_id=session_id,
            turn_id=str(claim["turn_id"]),
            claim_token=str(claim["claim_token"]),
            answer=answer,
            metadata=metadata,
        )

    def fail(
        self,
        claim: dict[str, object],
        *,
        partial_answer: str,
        error: str,
    ) -> bool:
        """把回合标记为失败并保留部分回复，供安全重试。

        用 claim_token 做条件终止，仅所有者能标记失败。

        参数:
            claim: ``begin`` 返回的领取信息。
            partial_answer: 已生成的部分回复正文（可空）。
            error: 错误描述。

        返回:
            是否成功终止；为 ``False`` 表示该回合已被他方改变状态。
        """
        return self.repository.terminate_chat_turn(
            turn_id=str(claim["turn_id"]),
            claim_token=str(claim["claim_token"]),
            status="failed",
            partial_answer=partial_answer,
            error=error,
        )

    def cancel(
        self,
        claim: dict[str, object],
        *,
        partial_answer: str,
        error: str = "client disconnected",
    ) -> bool:
        """把回合标记为已取消（客户端断连等），释放会话生成锁。

        与 ``fail`` 共用底层条件终止，区别仅在终态 ``cancelled``，
        以便区分「出错」与「主动停止」并保留部分回复供重放。

        参数:
            claim: ``begin`` 返回的领取信息。
            partial_answer: 已生成的部分回复正文。
            error: 取消原因，默认客户端断连。

        返回:
            是否成功终止；为 ``False`` 表示该回合已被他方改变状态。
        """
        return self.repository.terminate_chat_turn(
            turn_id=str(claim["turn_id"]),
            claim_token=str(claim["claim_token"]),
            status="cancelled",
            partial_answer=partial_answer,
            error=error,
        )
