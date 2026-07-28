import asyncio
import json
import logging
import time
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request

from app.api.execution import run_sync
from app.api.runtime import get_runtime
from app.api.schemas import (
    InterviewAnswerRequest,
    InterviewArchiveRequest,
    InterviewStartRequest,
    UserIdentityRequest,
)
from app.api.security import resolve_user_id
from app.application.interview_service import (
    InterviewAnswerConflict,
    InterviewAnswerNotFound,
)
from app.interview_engine import build_report

logger = logging.getLogger(__name__)
router = APIRouter()


async def _record_interview_trace(
    http_request: Request,
    *,
    user_id: str,
    interaction_id: str,
    status: str,
    duration_ms: int,
    detail: dict[str, object],
) -> None:
    try:
        await run_sync(
            get_runtime().conversation_store.record_execution_trace,
            request_id=str(getattr(http_request.state, "request_id", "")),
            user_id=user_id,
            interaction_type="interview",
            interaction_id=interaction_id,
            stage="assessment",
            status=status,
            duration_ms=duration_ms,
            detail=detail,
        )
    except Exception:
        logger.warning(
            "Interview execution trace write failed.",
            exc_info=True,
        )


@router.get("/api/interviews")
async def list_interviews(
    request: Request,
    user_id: str,
    include_archived: bool = False,
) -> list[dict[str, object]]:
    user_id = resolve_user_id(request, user_id)
    return await run_sync(
        get_runtime().conversation_store.list_interviews,
        user_id=user_id,
        include_archived=include_archived,
    )


@router.get("/api/interviews/{interview_id}")
async def interview_detail(
    request: Request,
    interview_id: str,
    user_id: str,
) -> dict[str, object]:
    user_id = resolve_user_id(request, user_id)
    store = get_runtime().conversation_store
    interview = await run_sync(
        store.get_interview, user_id=user_id, interview_id=interview_id
    )
    if not interview:
        raise HTTPException(status_code=404, detail="模拟面试不存在")
    turns = await run_sync(
        store.get_interview_turns,
        user_id=user_id,
        interview_id=interview_id,
    )
    pending = next(
        (turn for turn in reversed(turns) if not turn.get("answer")), None
    )
    return {
        "interview": interview,
        "turns": turns,
        "pending_turn": pending,
        "report": build_report(turns),
    }


@router.post("/api/interviews/{interview_id}/resume")
async def resume_interview(
    request: Request,
    interview_id: str,
    payload: UserIdentityRequest,
) -> dict[str, object]:
    user_id = resolve_user_id(request, payload.user_id)
    store = get_runtime().conversation_store
    interview = await run_sync(
        store.get_interview, user_id=user_id, interview_id=interview_id
    )
    if not interview:
        raise HTTPException(status_code=404, detail="模拟面试不存在")
    if interview.get("archived_at"):
        raise HTTPException(status_code=409, detail="请先取消归档再继续")
    if interview["status"] != "active":
        raise HTTPException(status_code=409, detail="该面试已经完成")
    turns = await run_sync(
        store.get_interview_turns,
        user_id=user_id,
        interview_id=interview_id,
    )
    pending = next(
        (turn for turn in reversed(turns) if not turn.get("answer")), None
    )
    if not pending:
        raise HTTPException(status_code=409, detail="没有待回答的问题")
    return {
        "interview_id": interview_id,
        "topic": interview["topic"],
        "level": interview["level"],
        "question_count": interview["total_questions"],
        "turn_index": pending["turn_index"],
        "question": pending["question"],
        "status": "active",
    }


@router.post("/api/interviews/{interview_id}/archive")
async def archive_interview(
    request: Request,
    interview_id: str,
    payload: InterviewArchiveRequest,
) -> dict[str, bool]:
    user_id = resolve_user_id(request, payload.user_id)
    changed = await run_sync(
        get_runtime().conversation_store.archive_interview,
        user_id=user_id,
        interview_id=interview_id,
        archived=payload.archived,
    )
    if not changed:
        raise HTTPException(status_code=404, detail="模拟面试不存在")
    return {"archived": payload.archived}


@router.delete("/api/interviews/{interview_id}")
async def delete_interview(
    request: Request,
    interview_id: str,
    user_id: str,
) -> dict[str, bool]:
    user_id = resolve_user_id(request, user_id)
    deleted = await run_sync(
        get_runtime().conversation_store.delete_interview,
        user_id=user_id,
        interview_id=interview_id,
    )
    return {"deleted": deleted}


@router.post("/api/interviews/start")
async def start_interview(
    request: InterviewStartRequest,
    http_request: Request,
) -> dict[str, object]:
    runtime = get_runtime()
    interview_id = str(uuid4())
    user_id = resolve_user_id(http_request, request.user_id)
    try:
        question = await run_sync(
            runtime.generate_question,
            topic=request.topic,
            level=request.level,
            turn_index=1,
            previous_turns=[],
        )
        await run_sync(
            runtime.conversation_store.create_interview,
            user_id=user_id,
            interview_id=interview_id,
            topic=request.topic,
            level=request.level,
            total_questions=request.question_count,
            first_question=question,
        )
    except Exception as exc:
        logger.exception("Failed to start interview %s", interview_id)
        raise HTTPException(
            status_code=500, detail=f"模拟面试启动失败：{exc}"
        ) from exc
    return {
        "interview_id": interview_id,
        "topic": request.topic,
        "level": request.level,
        "question_count": request.question_count,
        "turn_index": 1,
        "question": question,
        "status": "active",
    }


@router.post("/api/interviews/{interview_id}/answer")
async def answer_interview(
    interview_id: str,
    request: InterviewAnswerRequest,
    http_request: Request,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
) -> dict[str, object]:
    user_id = resolve_user_id(http_request, request.user_id)
    started_at = time.monotonic()
    try:
        result = await run_sync(
            get_runtime().interview_answer_service.submit,
            user_id=user_id,
            interview_id=interview_id,
            answer=request.answer,
            idempotency_key=idempotency_key,
        )
        await _record_interview_trace(
            http_request,
            user_id=user_id,
            interaction_id=(
                f"{interview_id}:{result.get('turn_index', 'unknown')}"
            ),
            status="completed",
            duration_ms=int((time.monotonic() - started_at) * 1000),
            detail={
                "model": get_runtime().settings.zhipu_model,
                "score": result.get("score"),
                "has_next_question": bool(result.get("next_question")),
            },
        )
        return result
    except InterviewAnswerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InterviewAnswerConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
            headers={"Retry-After": "1"} if exc.retryable else None,
        ) from exc
    except Exception as exc:
        await _record_interview_trace(
            http_request,
            user_id=user_id,
            interaction_id=f"{interview_id}:unknown",
            status="failed",
            duration_ms=int((time.monotonic() - started_at) * 1000),
            detail={"error_type": type(exc).__name__},
        )
        logger.exception("Failed to score interview %s", interview_id)
        raise HTTPException(status_code=500, detail=f"回答评分失败：{exc}") from exc


@router.post("/api/interviews/{interview_id}/turns/{turn_index}/retry")
async def retry_interview_answer(
    interview_id: str,
    turn_index: int,
    request: InterviewAnswerRequest,
    http_request: Request,
) -> dict[str, object]:
    runtime = get_runtime()
    user_id = resolve_user_id(http_request, request.user_id)
    store = runtime.conversation_store
    interview = await run_sync(
        store.get_interview, user_id=user_id, interview_id=interview_id
    )
    if not interview:
        raise HTTPException(status_code=404, detail="模拟面试不存在")
    if interview.get("archived_at"):
        raise HTTPException(status_code=409, detail="该面试已归档")
    turns = await run_sync(
        store.get_interview_turns,
        user_id=user_id,
        interview_id=interview_id,
    )
    current = next(
        (turn for turn in turns if int(turn["turn_index"]) == turn_index), None
    )
    if not current:
        raise HTTPException(status_code=404, detail="面试题不存在")
    if not current.get("answer"):
        raise HTTPException(status_code=409, detail="该题尚未完成首次回答")
    try:
        assessment = await run_sync(
            runtime.assess_answer,
            topic=str(interview["topic"]),
            level=str(interview["level"]),
            question=str(current["question"]),
            answer=request.answer,
        )
        comparison = await run_sync(
            store.retry_interview_answer,
            user_id=user_id,
            interview_id=interview_id,
            turn_index=turn_index,
            answer=request.answer,
            score=float(assessment["overall"]),
            feedback=str(assessment["feedback"]),
            dimensions_json=json.dumps(assessment["dimensions"], ensure_ascii=False),
            strengths_json=json.dumps(assessment["strengths"], ensure_ascii=False),
            weaknesses_json=json.dumps(assessment["weaknesses"], ensure_ascii=False),
            reference_answer=str(assessment["reference_answer"]),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "Failed to rescore interview %s turn %s", interview_id, turn_index
        )
        raise HTTPException(status_code=500, detail=f"重新评分失败：{exc}") from exc
    return {
        "interview_id": interview_id,
        "turn_index": turn_index,
        "score": assessment["overall"],
        "dimensions": assessment["dimensions"],
        "strengths": assessment["strengths"],
        "weaknesses": assessment["weaknesses"],
        "feedback": assessment["feedback"],
        "reference_answer": assessment["reference_answer"],
        "comparison": comparison,
        "status": interview["status"],
    }


@router.get("/api/interviews/{interview_id}/report")
async def interview_report(
    request: Request,
    interview_id: str,
    user_id: str,
) -> dict[str, object]:
    user_id = resolve_user_id(request, user_id)
    store = get_runtime().conversation_store
    interview = await run_sync(
        store.get_interview, user_id=user_id, interview_id=interview_id
    )
    if not interview:
        raise HTTPException(status_code=404, detail="模拟面试不存在")
    turns = await run_sync(
        store.get_interview_turns,
        user_id=user_id,
        interview_id=interview_id,
    )
    attempts = await run_sync(
        store.get_interview_answer_attempts,
        user_id=user_id,
        interview_id=interview_id,
    )
    return {
        "interview": interview,
        "turns": turns,
        "attempts": attempts,
        "report": build_report(turns),
    }
