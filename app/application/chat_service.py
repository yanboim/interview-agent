import hashlib
from typing import Any, Protocol
from uuid import uuid4

from app.chat_context import validate_current_message


class ChatTurnRepository(Protocol):
    def begin_chat_turn(self, **kwargs: Any) -> dict[str, object]: ...

    def complete_chat_turn(self, **kwargs: Any) -> None: ...

    def terminate_chat_turn(self, **kwargs: Any) -> bool: ...


class ChatTurnError(RuntimeError):
    """Base application error for chat-turn lifecycle operations."""


class ChatTurnConflict(ChatTurnError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ChatTurnService:
    def __init__(
        self,
        repository: ChatTurnRepository,
        *,
        context_token_budget: int = 12000,
        summary_token_budget: int = 2000,
    ) -> None:
        if summary_token_budget >= context_token_budget:
            raise ValueError(
                "chat summary token budget must be smaller than context budget"
            )
        self.repository = repository
        self.context_token_budget = context_token_budget
        self.summary_token_budget = summary_token_budget

    def begin(
        self,
        *,
        user_id: str,
        session_id: str,
        content: str,
        idempotency_key: str,
    ) -> dict[str, object]:
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
            context_token_budget=self.context_token_budget,
            summary_token_budget=self.summary_token_budget,
        )
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
        return {**result, "messages": history}

    def complete(
        self,
        claim: dict[str, object],
        *,
        user_id: str,
        session_id: str,
        answer: str,
        metadata: dict[str, object],
    ) -> None:
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
        return self.repository.terminate_chat_turn(
            turn_id=str(claim["turn_id"]),
            claim_token=str(claim["claim_token"]),
            status="cancelled",
            partial_answer=partial_answer,
            error=error,
        )
