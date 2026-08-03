"""显式 Workflow V2 与可选单 Agent 模式的 Chat 执行适配器。"""

import asyncio
from collections.abc import AsyncIterator, Callable
from time import monotonic
from typing import Any

from langchain_core.messages import AIMessageChunk, ToolMessage

from app.agent_budget import agent_execution_budget
from app.application.chat_execution import (
    ChatExecutionEvent,
    ChatExecutionEvidence,
    ChatExecutionRequest,
    ChatExecutionResult,
)
from app.application.chat_workflow import (
    ChatWorkflowPlan,
    ChatWorkflowPlanner,
    ChatWorkflowRouteRequest,
)
from app.chat_evidence import extract_message_text
from app.model_routing import model_for_purpose
from app.operations import request_metrics


ROUTE_LABELS = {
    "evaluator": "回答评估",
    "knowledge": "知识讲解",
    "interviewer": "模拟面试",
    "planner": "训练计划",
}

# A provider coroutine can ignore cancellation while its HTTP client finishes
# unwinding.  Keep detached tasks strongly referenced until they settle so
# their late exception cannot become an unobserved-task warning.  The parent
# chat turn is fenced independently by ChatTurnService and must not wait on
# such a task forever.
_DETACHED_ROUTE_TASKS: set[asyncio.Task[Any]] = set()


def _consume_detached_route_task(task: asyncio.Task[Any]) -> None:
    _DETACHED_ROUTE_TASKS.discard(task)
    try:
        task.exception()
    except BaseException:
        # CancelledError and a late provider exception are both intentionally
        # consumed after the owning chat request has already failed.
        pass


class RoutedChatAgentExecutor:
    """运行显式有界工作流；仅在多 Agent 关闭时使用单 Agent。"""

    def __init__(
        self,
        settings: Any,
        get_single_agent: Callable[[], Any],
        specialist_factories: dict[str, Callable[[], Any]] | None = None,
    ) -> None:
        self.settings = settings
        self.get_single_agent = get_single_agent
        self._specialist_factories = specialist_factories

    def _plan(self, request: ChatExecutionRequest) -> ChatWorkflowPlan:
        return ChatWorkflowPlanner(self.settings).plan(
            ChatWorkflowRouteRequest(
                message=request.message,
                user_id=request.user_id,
                role=request.role,
            )
        )

    def _factories(self) -> dict[str, Callable[[], Any]]:
        if self._specialist_factories is not None:
            return self._specialist_factories
        from app.multi_agent import (
            get_evaluator_agent,
            get_interviewer_agent,
            get_knowledge_agent,
            get_planner_agent,
        )

        return {
            "knowledge": get_knowledge_agent,
            "interviewer": get_interviewer_agent,
            "evaluator": get_evaluator_agent,
            "planner": get_planner_agent,
        }

    @staticmethod
    def _specialist_messages(task: str) -> list[Any]:
        from app.multi_agent import build_specialist_messages

        return build_specialist_messages(task)

    def _max_model_calls(self, plan: ChatWorkflowPlan) -> int | None:
        """Allocate bounded call capacity for every explicit specialist route."""
        if not plan.explicit_path:
            return None
        per_route = int(
            self.settings.agent_workflow_v2_max_model_calls_per_route
        )
        return per_route * len(plan.routes)

    @staticmethod
    def _workflow_metric_name(plan: ChatWorkflowPlan | None) -> str | None:
        if plan is None:
            return None
        if plan.explicit_path:
            return "chat-workflow-v2"
        return None

    @staticmethod
    def _normalize_result(result: dict[str, Any]) -> tuple[str, list[ChatExecutionEvidence]]:
        messages = list(result["messages"])
        structured = result.get("structured_response")
        if structured is None:
            answer = extract_message_text(messages[-1]).strip()
        elif isinstance(structured, dict):
            answer = str(structured.get("answer") or "").strip()
        else:
            answer = str(getattr(structured, "answer", "") or "").strip()
        if not answer:
            raise RuntimeError("specialist returned no answer")
        evidence = [
            ChatExecutionEvidence(
                tool_name=str(getattr(message, "name", "") or ""),
                content=extract_message_text(message),
            )
            for message in messages
            if isinstance(message, ToolMessage)
        ]
        return answer, evidence

    @staticmethod
    def _compose(results: list[tuple[str, str]]) -> str:
        if len(results) == 1:
            return results[0][1]
        return "\n\n".join(
            f"## {ROUTE_LABELS[route]}\n\n{answer}"
            for route, answer in results
        )

    @staticmethod
    async def _await_route_tasks(tasks: list[asyncio.Task[Any]]) -> list[Any]:
        """Await siblings without allowing cancellation cleanup to hang.

        Normal route failures get a short drain so sibling cancellation remains
        deterministic.  If the parent is already being cancelled by the
        request wall-clock timeout or a disconnected client, cancellation of
        an uncooperative provider task is handed off instead of being awaited
        indefinitely.  The turn owner is fenced before any late task can
        complete it, so this is not a time-based takeover.
        """
        try:
            return list(await asyncio.gather(*tasks))
        finally:
            pending = [task for task in tasks if not task.done()]
            if pending:
                for task in pending:
                    task.cancel()

                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    for task in pending:
                        _DETACHED_ROUTE_TASKS.add(task)
                        task.add_done_callback(_consume_detached_route_task)
                else:
                    done, still_pending = await asyncio.wait(
                        pending,
                        timeout=1.0,
                    )
                    for task in done:
                        _consume_detached_route_task(task)
                    for task in still_pending:
                        _DETACHED_ROUTE_TASKS.add(task)
                        task.add_done_callback(_consume_detached_route_task)

    async def _invoke_explicit_routes(
        self,
        routes: tuple[str, ...],
        factories: dict[str, Callable[[], Any]],
        request: ChatExecutionRequest,
    ) -> tuple[list[tuple[str, str]], list[ChatExecutionEvidence]]:
        tasks = [
            asyncio.create_task(
                factories[route]().ainvoke(
                    {"messages": self._specialist_messages(request.message)},
                    config={
                        "recursion_limit": self.settings.agent_recursion_limit
                    },
                ),
                name=f"workflow-v2-{route}",
            )
            for route in routes
        ]
        agent_results = await self._await_route_tasks(tasks)
        results: list[tuple[str, str]] = []
        evidence: list[ChatExecutionEvidence] = []
        for route, agent_result in zip(routes, agent_results, strict=True):
            answer, route_evidence = self._normalize_result(agent_result)
            results.append((route, answer))
            evidence.extend(route_evidence)
        return results, evidence

    async def _stream_explicit_routes(
        self,
        routes: tuple[str, ...],
        factories: dict[str, Callable[[], Any]],
        request: ChatExecutionRequest,
    ) -> AsyncIterator[ChatExecutionEvent]:
        # LangChain structured-output agents may expose the validated answer
        # only in ``structured_response`` after the graph completes; their
        # message stream can contain tool evidence but no answer chunks. Run
        # specialists concurrently to their validated final state, then emit
        # evidence and one deterministic answer chunk in route order.
        results, evidence = await self._invoke_explicit_routes(
            routes, factories, request
        )
        for item in evidence:
            yield ChatExecutionEvent(
                kind="evidence",
                tool_name=item.tool_name,
                content=item.content,
            )
        yield ChatExecutionEvent(kind="token", content=self._compose(results))

    async def invoke(self, request: ChatExecutionRequest) -> ChatExecutionResult:
        started_at = monotonic()
        plan: ChatWorkflowPlan | None = None
        run_budget = None
        outcome = "failed"
        try:
            plan = self._plan(request)
            with agent_execution_budget(
                self.settings,
                "chat",
                max_calls=self._max_model_calls(plan),
            ) as run_budget:
                with request_metrics.dependency("glm"):
                    if plan.explicit_path:
                        routes = plan.routes
                        factories = self._factories()
                        async with asyncio.timeout(
                            self.settings.chat_agent_timeout_seconds
                        ):
                            results, evidence = await self._invoke_explicit_routes(
                                routes, factories, request
                            )
                        purpose = "workflow_v2:" + "+".join(routes)
                        model_version = "+".join(
                            model_for_purpose(self.settings, route) for route in routes
                        )
                        request_metrics.observe_product("agent_workflow_v2_completed")
                        answer = self._compose(results)
                    else:
                        agent = self.get_single_agent()
                        purpose = "single_agent"
                        model_version = model_for_purpose(self.settings, purpose)
                        result = await asyncio.wait_for(
                            agent.ainvoke(
                                {"messages": request.messages},
                                config={
                                    "recursion_limit": (
                                        self.settings.agent_recursion_limit
                                    )
                                },
                            ),
                            timeout=self.settings.chat_agent_timeout_seconds,
                        )
                        answer, evidence = self._normalize_result(result)
            outcome = "completed"
        finally:
            if run_budget is not None:
                budget = run_budget.snapshot()
                request_metrics.observe_model_run(budget)
                workflow = self._workflow_metric_name(plan)
                if workflow is not None:
                    request_metrics.observe_workflow_run(
                        workflow,
                        outcome=outcome,
                        duration_seconds=monotonic() - started_at,
                        cost_usd=float(budget["cost_usd"]),
                    )
        return ChatExecutionResult(
            answer=answer,
            evidence=evidence,
            purpose=purpose,
            model_version=model_version,
            budget=budget,
        )

    async def _stream_agent(
        self,
        agent: Any,
        request: ChatExecutionRequest,
        *,
        specialist: bool = False,
    ) -> AsyncIterator[ChatExecutionEvent]:
        messages = (
            self._specialist_messages(request.message)
            if specialist
            else request.messages
        )
        async for message, _ in agent.astream(
            {"messages": messages},
            stream_mode="messages",
            config={"recursion_limit": self.settings.agent_recursion_limit},
        ):
            if isinstance(message, ToolMessage):
                yield ChatExecutionEvent(
                    kind="evidence",
                    tool_name=str(getattr(message, "name", "") or ""),
                    content=extract_message_text(message),
                )
            elif isinstance(message, AIMessageChunk):
                content = extract_message_text(message)
                if content:
                    yield ChatExecutionEvent(kind="token", content=content)

    async def stream(
        self, request: ChatExecutionRequest
    ) -> AsyncIterator[ChatExecutionEvent]:
        started_at = monotonic()
        plan: ChatWorkflowPlan | None = None
        run_budget = None
        outcome = "failed"
        try:
            plan = self._plan(request)
            with agent_execution_budget(
                self.settings,
                "chat",
                max_calls=self._max_model_calls(plan),
            ) as run_budget:
                with request_metrics.dependency("glm"):
                    async with asyncio.timeout(
                        self.settings.chat_agent_timeout_seconds
                    ):
                        if plan.explicit_path:
                            routes = plan.routes
                            factories = self._factories()
                            async for event in self._stream_explicit_routes(
                                routes, factories, request
                            ):
                                    yield event
                            purpose = "workflow_v2:" + "+".join(routes)
                            model_version = "+".join(
                                model_for_purpose(self.settings, route)
                                for route in routes
                            )
                            request_metrics.observe_product(
                                "agent_workflow_v2_completed"
                            )
                        else:
                            agent = self.get_single_agent()
                            purpose = "single_agent"
                            model_version = model_for_purpose(
                                self.settings, purpose
                            )
                            async for event in self._stream_agent(agent, request):
                                yield event
            outcome = "completed"
        except (asyncio.CancelledError, GeneratorExit):
            outcome = "cancelled"
            raise
        finally:
            if run_budget is not None:
                budget = run_budget.snapshot()
                request_metrics.observe_model_run(budget)
                workflow = self._workflow_metric_name(plan)
                if workflow is not None:
                    request_metrics.observe_workflow_run(
                        workflow,
                        outcome=outcome,
                        duration_seconds=monotonic() - started_at,
                        cost_usd=float(budget["cost_usd"]),
                    )
        yield ChatExecutionEvent(
            kind="completed",
            purpose=purpose,
            model_version=model_version,
            budget=budget,
        )
