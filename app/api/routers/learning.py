"""能力画像与学习任务 HTTP 适配器。"""

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.execution import run_sync
from app.api.runtime import get_runtime
from app.api.schemas import (
    AgentRunCreateRequest,
    AgentRunRecoveryRequest,
    LearningTaskGenerateRequest,
    LearningTaskReviewRequest,
    LearningTaskUpdateRequest,
    UserIdentityRequest,
)
from app.api.security import resolve_user_id
from app.api.security import require_role
from app.application.agent_run_service import AgentRunConflict
from app.capability import build_capability_profile
from app.learning import build_learning_candidates
from app.operations import request_metrics

router = APIRouter()


def _run_or_404(run: dict[str, object] | None) -> dict[str, object]:
    if run is None:
        raise HTTPException(status_code=404, detail="Agent 工作流不存在")
    return run


@router.post("/api/agent-runs/training-program", status_code=201)
async def propose_training_program(
    request: Request,
    payload: AgentRunCreateRequest,
    idempotency_key: str = Header(
        min_length=1, max_length=128, alias="Idempotency-Key"
    ),
) -> dict[str, object]:
    user_id = resolve_user_id(request, payload.user_id)
    try:
        run = await run_sync(
            get_runtime().agent_run_service.propose_training_program,
            user_id=user_id,
            topic=payload.topic,
            idempotency_key=idempotency_key.strip(),
        )
        request_metrics.observe_product("workflow_proposed")
        return run
    except (AgentRunConflict, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/agent-runs")
async def list_agent_runs(request: Request, user_id: str) -> list[dict[str, object]]:
    user_id = resolve_user_id(request, user_id)
    return await run_sync(get_runtime().agent_run_service.list_runs, user_id=user_id)


@router.get("/api/agent-runs/{run_id}")
async def inspect_agent_run(
    request: Request, run_id: str, user_id: str
) -> dict[str, object]:
    user_id = resolve_user_id(request, user_id)
    return _run_or_404(await run_sync(
        get_runtime().agent_run_service.inspect, user_id=user_id, run_id=run_id
    ))


@router.get("/api/agent-runs/{run_id}/events")
async def stream_agent_run_events(
    request: Request, run_id: str, user_id: str
) -> StreamingResponse:
    user_id = resolve_user_id(request, user_id)
    run = _run_or_404(await run_sync(
        get_runtime().agent_run_service.inspect, user_id=user_id, run_id=run_id
    ))

    async def event_stream():
        for event in run["events"]:
            yield f"event: {event['event']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _transition_agent_run(
    request: Request,
    run_id: str,
    payload: UserIdentityRequest,
    transition: str,
) -> dict[str, object]:
    user_id = resolve_user_id(request, payload.user_id)
    method = getattr(get_runtime().agent_run_service, transition)
    try:
        run = _run_or_404(await run_sync(method, user_id=user_id, run_id=run_id))
        request_metrics.observe_product(f"workflow_transition_{transition}")
        if run.get("status") == "completed":
            request_metrics.observe_product("workflow_completed")
        return run
    except AgentRunConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/agent-runs/{run_id}/confirm")
async def confirm_agent_run(
    request: Request, run_id: str, payload: UserIdentityRequest
) -> dict[str, object]:
    return await _transition_agent_run(request, run_id, payload, "confirm")


@router.post("/api/agent-runs/{run_id}/retry")
async def retry_agent_run(
    request: Request, run_id: str, payload: UserIdentityRequest
) -> dict[str, object]:
    return await _transition_agent_run(request, run_id, payload, "retry")


@router.post("/api/agent-runs/{run_id}/cancel")
async def cancel_agent_run(
    request: Request, run_id: str, payload: UserIdentityRequest
) -> dict[str, object]:
    return await _transition_agent_run(request, run_id, payload, "cancel")


@router.post("/api/admin/agent-runs/recover")
async def recover_agent_runs(
    request: Request, payload: AgentRunRecoveryRequest
) -> dict[str, int]:
    require_role(request, {"admin"})
    recovered = await run_sync(
        get_runtime().agent_run_service.recover_stale,
        stale_seconds=payload.stale_seconds,
    )
    return {"recovered_steps": recovered}


@router.get("/api/admin/agent-runs/{run_id}")
async def inspect_agent_run_for_admin(
    request: Request, run_id: str
) -> dict[str, object]:
    require_role(request, {"admin"})
    return _run_or_404(await run_sync(
        get_runtime().agent_run_service.inspect_for_admin, run_id=run_id
    ))


@router.get("/api/capability-profile")
async def capability_profile(
    request: Request,
    user_id: str,
    topic: str | None = None,
) -> dict[str, object]:
    user_id = resolve_user_id(request, user_id)
    clean_topic = topic.strip() if topic else None
    if clean_topic and len(clean_topic) > 200:
        raise HTTPException(status_code=422, detail="topic 不合法")
    store = get_runtime().conversation_store
    rows, profile = await asyncio.gather(
        run_sync(store.get_capability_rows, user_id=user_id),
        run_sync(store.get_user_profile, user_id=user_id),
    )
    capability = build_capability_profile(rows, topic=clean_topic)
    request_metrics.set_product_gauge(
        "score_confidence", float(capability["calibration"]["confidence"])
    )
    average = float(capability["summary"]["average_score"])
    sample_count = int(capability["summary"]["answered_questions"])
    confidence = min(1.0, sample_count / 10)
    job_match = round(average * 10 * (0.65 + confidence * 0.35))
    weaknesses = capability["weaknesses"]
    capability["job_readiness"] = {
        "score": job_match,
        "confidence": (
            "high"
            if sample_count >= 10
            else "medium"
            if sample_count >= 5
            else "low"
        ),
        "target_role": (profile or {}).get("target_role") or None,
        "has_job_description": bool((profile or {}).get("job_description")),
        "priorities": [
            {
                "label": item["label"],
                "reason": f"已在 {item['count']} 次回答中出现",
            }
            for item in weaknesses[:3]
        ],
    }
    return capability


@router.get("/api/learning-tasks")
async def list_learning_tasks(
    request: Request,
    user_id: str,
    status: Literal["todo", "in_progress", "completed"] | None = None,
) -> list[dict[str, object]]:
    user_id = resolve_user_id(request, user_id)
    return await run_sync(
        get_runtime().conversation_store.list_learning_tasks,
        user_id=user_id,
        status=status,
    )


@router.post("/api/learning-tasks/generate")
async def generate_learning_tasks(
    request: Request,
    payload: LearningTaskGenerateRequest,
) -> dict[str, object]:
    user_id = resolve_user_id(request, payload.user_id)
    store = get_runtime().conversation_store
    rows = await run_sync(store.get_capability_rows, user_id=user_id)
    profile = build_capability_profile(rows, topic=payload.topic)
    candidates = build_learning_candidates(profile)
    if not candidates:
        raise HTTPException(status_code=409, detail="暂无可生成学习任务的评分数据")
    tasks = await run_sync(
        store.create_learning_tasks, user_id=user_id, candidates=candidates
    )
    return {
        "generated_from": {
            "topic": profile["filter"]["topic"],
            "answered_questions": profile["summary"]["answered_questions"],
        },
        "tasks": tasks,
    }


@router.patch("/api/learning-tasks/{task_id}")
async def update_learning_task(
    request: Request,
    task_id: str,
    payload: LearningTaskUpdateRequest,
) -> dict[str, object]:
    user_id = resolve_user_id(request, payload.user_id)
    if payload.status is None and payload.due_at is None:
        raise HTTPException(status_code=422, detail="没有需要更新的字段")
    task = await run_sync(
        get_runtime().conversation_store.update_learning_task,
        user_id=user_id,
        task_id=task_id,
        status=payload.status,
        due_at=payload.due_at.isoformat() if payload.due_at else None,
    )
    if not task:
        raise HTTPException(status_code=404, detail="学习任务不存在")
    request_metrics.observe_product(f"review_recall_{payload.outcome}")
    return task


@router.post("/api/learning-tasks/{task_id}/review")
async def review_learning_task(
    request: Request,
    task_id: str,
    payload: LearningTaskReviewRequest,
) -> dict[str, object]:
    user_id = resolve_user_id(request, payload.user_id)
    task = await run_sync(
        get_runtime().conversation_store.review_learning_task,
        user_id=user_id,
        task_id=task_id,
        outcome=payload.outcome,
        difficulty=payload.difficulty,
    )
    if not task:
        raise HTTPException(status_code=404, detail="学习任务不存在")
    return task


@router.delete("/api/learning-tasks/{task_id}")
async def delete_learning_task(
    request: Request,
    task_id: str,
    user_id: str,
) -> dict[str, bool]:
    user_id = resolve_user_id(request, user_id)
    deleted = await run_sync(
        get_runtime().conversation_store.delete_learning_task,
        user_id=user_id,
        task_id=task_id,
    )
    return {"deleted": deleted}
