"""Explicit, transport-neutral stage planning for chat workflow V2."""

from dataclasses import dataclass
from typing import Literal

from app.model_routing import explicit_workflow_routes


WorkflowPurpose = Literal[
    "single_agent", "workflow_v2", "knowledge", "interviewer",
    "evaluator", "planner"
]
SpecialistPurpose = Literal["knowledge", "interviewer", "evaluator", "planner"]
WORKFLOW_STAGES = (
    "guard",
    "context",
    "route",
    "execute",
    "verify",
    "compose",
    "persist",
)


@dataclass(frozen=True, slots=True)
class ChatWorkflowRouteRequest:
    message: str
    user_id: str
    role: str


@dataclass(frozen=True, slots=True)
class ChatWorkflowPlan:
    version: Literal["chat-workflow-v2"]
    purpose: WorkflowPurpose
    routes: tuple[SpecialistPurpose, ...]
    stages: tuple[str, ...]
    explicit_path: bool
    fallback_reason: str = ""


class ChatWorkflowPlanner:
    """Build a bounded code-defined plan; it never spends a model call."""

    def __init__(self, settings: object) -> None:
        self.settings = settings

    def plan(self, request: ChatWorkflowRouteRequest) -> ChatWorkflowPlan:
        if not bool(getattr(self.settings, "multi_agent_enabled", False)):
            return self._plan("single_agent", explicit=False, reason="multi_agent_off")

        routes = explicit_workflow_routes(request.message)
        purpose: WorkflowPurpose = routes[0] if len(routes) == 1 else "workflow_v2"
        return self._plan(purpose, explicit=True, routes=routes)

    @staticmethod
    def _plan(
        purpose: WorkflowPurpose,
        *,
        explicit: bool,
        reason: str = "",
        routes: tuple[SpecialistPurpose, ...] = (),
    ) -> ChatWorkflowPlan:
        return ChatWorkflowPlan(
            version="chat-workflow-v2",
            purpose=purpose,
            routes=routes,
            stages=WORKFLOW_STAGES,
            explicit_path=explicit,
            fallback_reason=reason,
        )
