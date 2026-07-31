"""HTTP 适配器依赖容器；路由仅从这里取得已组装的服务和基础设施。"""

from dataclasses import dataclass
from typing import Any, Callable

from app.application.chat_service import ChatTurnService
from app.application.agent_run_service import AgentRunService
from app.application.execution import SyncExecutor
from app.application.interview_service import (
    InterviewAnswerService,
    InterviewStartService,
)
from app.application.interview_review_service import InterviewReviewService
from app.application.resume_service import ResumeService
from app.auth import AuthService
from app.config import Settings
from app.operations import RedisRuntime, SharedRateLimiter
from app.storage import ConversationStore
from app.system_resources import SystemResourceCenter


@dataclass(slots=True)
class ApiRuntime:
    """Process-scoped dependencies used by API adapters."""

    settings: Settings
    conversation_store: ConversationStore
    auth_service: AuthService
    redis_runtime: RedisRuntime
    rate_limiter: SharedRateLimiter
    chat_turn_service: ChatTurnService
    agent_run_service: AgentRunService
    interview_answer_service: InterviewAnswerService
    interview_start_service: InterviewStartService
    interview_review_service: InterviewReviewService
    resume_service: ResumeService
    sync_executor: SyncExecutor
    get_interview_agent: Callable[[], Any]
    generate_question: Callable[..., Any]
    assess_answer: Callable[..., Any]
    ingest_knowledge: Callable[..., Any]
    knowledge_status: Callable[..., Any]
    rollback_knowledge: Callable[..., Any]
    require_serving_knowledge: Callable[..., Any]
    system_resource_center: SystemResourceCenter


_runtime: ApiRuntime | None = None


def configure_runtime(runtime: ApiRuntime) -> None:
    global _runtime
    _runtime = runtime


def get_runtime() -> ApiRuntime:
    if _runtime is None:
        raise RuntimeError("API runtime has not been configured")
    return _runtime
