"""一次已准入聊天 Agent 执行的传输无关契约。"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal, Protocol


@dataclass(frozen=True, slots=True)
class ChatExecutionRequest:
    message: str
    user_id: str
    role: str
    messages: list[Any]


@dataclass(frozen=True, slots=True)
class ChatExecutionEvidence:
    tool_name: str
    content: str


@dataclass(frozen=True, slots=True)
class ChatExecutionResult:
    answer: str
    evidence: list[ChatExecutionEvidence]
    purpose: str
    model_version: str
    budget: dict[str, object]


@dataclass(frozen=True, slots=True)
class ChatExecutionEvent:
    kind: Literal["token", "evidence", "completed"]
    content: str = ""
    tool_name: str = ""
    purpose: str = ""
    model_version: str = ""
    budget: dict[str, object] | None = None


class ChatAgentExecutor(Protocol):
    async def invoke(self, request: ChatExecutionRequest) -> ChatExecutionResult: ...

    def stream(self, request: ChatExecutionRequest) -> AsyncIterator[ChatExecutionEvent]: ...
