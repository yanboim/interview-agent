from dataclasses import dataclass
from typing import Any, Callable

from app.application.chat_service import ChatTurnService
from app.application.execution import SyncExecutor
from app.application.interview_service import InterviewAnswerService
from app.auth import AuthService
from app.config import Settings
from app.operations import RedisRuntime, SharedRateLimiter
from app.storage import ConversationStore


@dataclass(slots=True)
class ApiRuntime:
    """Process-scoped dependencies used by API adapters."""

    settings: Settings
    conversation_store: ConversationStore
    auth_service: AuthService
    redis_runtime: RedisRuntime
    rate_limiter: SharedRateLimiter
    chat_turn_service: ChatTurnService
    interview_answer_service: InterviewAnswerService
    sync_executor: SyncExecutor
    get_interview_agent: Callable[[], Any]
    generate_question: Callable[..., Any]
    assess_answer: Callable[..., Any]
    ingest_knowledge: Callable[..., Any]
    knowledge_status: Callable[..., Any]
    rollback_knowledge: Callable[..., Any]
    require_serving_knowledge: Callable[..., Any]


_runtime: ApiRuntime | None = None


def configure_runtime(runtime: ApiRuntime) -> None:
    global _runtime
    _runtime = runtime


def get_runtime() -> ApiRuntime:
    if _runtime is None:
        raise RuntimeError("API runtime has not been configured")
    return _runtime
