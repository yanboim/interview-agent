import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Request

from app.api.execution import run_sync
from app.api.runtime import get_runtime
from app.api.schemas import (
    LearningTaskGenerateRequest,
    LearningTaskUpdateRequest,
    UserIdentityRequest,
)
from app.api.security import resolve_user_id
from app.capability import build_capability_profile
from app.learning import build_learning_candidates

router = APIRouter()


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
    return task


@router.post("/api/learning-tasks/{task_id}/review")
async def review_learning_task(
    request: Request,
    task_id: str,
    payload: UserIdentityRequest,
) -> dict[str, object]:
    user_id = resolve_user_id(request, payload.user_id)
    task = await run_sync(
        get_runtime().conversation_store.review_learning_task,
        user_id=user_id,
        task_id=task_id,
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
