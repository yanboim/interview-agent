"""HTTP 适配器依赖容器；路由仅从这里取得已组装的服务和基础设施。"""

from dataclasses import dataclass
from typing import Any, Callable

from app.application.chat_use_case import ChatUseCase
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
    """API 适配器使用的进程级依赖容器。

    由组合根 ``app.main`` 在启动时一次性组装，路由通过 ``get_runtime``
    取得已装配的服务、仓库与基础设施，使路由本身保持为薄适配器，不负责
    依赖构造。
    """

    settings: Settings
    conversation_store: ConversationStore
    auth_service: AuthService
    redis_runtime: RedisRuntime
    rate_limiter: SharedRateLimiter
    chat_use_case: ChatUseCase
    agent_run_service: AgentRunService
    interview_answer_service: InterviewAnswerService
    interview_start_service: InterviewStartService
    interview_review_service: InterviewReviewService
    resume_service: ResumeService
    sync_executor: SyncExecutor
    generate_question: Callable[..., Any]
    assess_answer: Callable[..., Any]
    ingest_knowledge: Callable[..., Any]
    knowledge_status: Callable[..., Any]
    rollback_knowledge: Callable[..., Any]
    require_serving_knowledge: Callable[..., Any]
    system_resource_center: SystemResourceCenter


_runtime: ApiRuntime | None = None


def configure_runtime(runtime: ApiRuntime) -> None:
    """由组合根在启动时调用，装配全局唯一依赖容器。"""
    global _runtime
    _runtime = runtime


def get_runtime() -> ApiRuntime:
    """返回已装配的依赖容器。

    异常:
        RuntimeError: 容器尚未被 ``configure_runtime`` 配置。
    """
    if _runtime is None:
        raise RuntimeError("API runtime has not been configured")
    return _runtime
