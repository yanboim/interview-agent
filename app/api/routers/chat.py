"""聊天 HTTP/NDJSON 适配器；完整回合协调由应用用例负责。"""

import json

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.execution import run_sync
from app.api.runtime import get_runtime
from app.api.schemas import (
    AssistantFeedbackRequest,
    ChatRequest,
    ChatResponse,
    EvaluationCandidateReviewRequest,
)
from app.api.security import require_role, resolve_user_id
from app.application.chat_service import ChatTurnConflict
from app.application.chat_use_case import (
    ChatCommand,
    ChatExecutionFailed,
    ChatExecutionTimeout,
    ChatExecutionUnavailable,
)
from app.chat_context import ChatContextBudgetExceeded
from app.operations import request_metrics

router = APIRouter()


@router.put("/api/chat/turns/{turn_id}/feedback")
async def save_assistant_feedback(
    turn_id: str,
    payload: AssistantFeedbackRequest,
    request: Request,
) -> dict[str, object]:
    user_id = resolve_user_id(request, payload.user_id)
    feedback = await run_sync(
        get_runtime().conversation_store.upsert_assistant_feedback,
        user_id=user_id,
        turn_id=turn_id,
        rating=payload.rating,
        reason_code=payload.reason_code,
        comment=payload.comment.strip() if payload.comment else None,
    )
    if not feedback:
        raise HTTPException(status_code=404, detail="可评价的助手回合不存在")
    request_metrics.observe_product("feedback_submitted")
    request_metrics.observe_product(f"feedback_{payload.rating}")
    return feedback


@router.delete("/api/chat/turns/{turn_id}/feedback")
async def delete_assistant_feedback(
    turn_id: str, user_id: str, request: Request
) -> dict[str, bool]:
    user_id = resolve_user_id(request, user_id)
    deleted = await run_sync(
        get_runtime().conversation_store.delete_assistant_feedback,
        user_id=user_id,
        turn_id=turn_id,
    )
    return {"deleted": deleted}


@router.get("/api/admin/evaluation-candidates")
async def list_evaluation_candidates(
    request: Request,
    status: str = "pending_privacy_review",
) -> list[dict[str, object]]:
    require_role(request, {"admin"})
    if status not in {"pending_privacy_review", "approved", "rejected"}:
        raise HTTPException(status_code=422, detail="候选状态不合法")
    return await run_sync(
        get_runtime().conversation_store.list_evaluation_candidates,
        status=status,
    )


@router.post("/api/admin/evaluation-candidates/{candidate_id}/review")
async def review_evaluation_candidate(
    candidate_id: str,
    payload: EvaluationCandidateReviewRequest,
    request: Request,
) -> dict[str, object]:
    reviewer = require_role(request, {"admin"})
    try:
        reviewed = await run_sync(
            get_runtime().conversation_store.review_evaluation_candidate,
            candidate_id=candidate_id,
            reviewer_id=reviewer.user_id,
            decision=payload.decision,
            approved_payload=payload.approved_payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not reviewed:
        raise HTTPException(status_code=404, detail="待审核评测候选不存在")
    return reviewed


def _command(
    payload: ChatRequest,
    request: Request,
    idempotency_key: str,
) -> ChatCommand:
    current_user = getattr(request.state, "current_user", None)
    return ChatCommand(
        user_id=resolve_user_id(request, payload.user_id),
        role=current_user.role if current_user else "user",
        session_id=payload.session_id,
        message=payload.message,
        idempotency_key=idempotency_key,
        request_id=str(getattr(request.state, "request_id", "")),
    )


def _map_admission_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ChatContextBudgetExceeded):
        return HTTPException(status_code=413, detail=str(exc))
    if isinstance(exc, ChatTurnConflict):
        return HTTPException(
            status_code=409,
            detail=str(exc),
            headers={"Retry-After": "1"} if exc.retryable else None,
        )
    raise exc


@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    http_request: Request,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
) -> ChatResponse:
    try:
        result = await get_runtime().chat_use_case.execute(
            _command(request, http_request, idempotency_key)
        )
    except (ChatContextBudgetExceeded, ChatTurnConflict) as exc:
        raise _map_admission_error(exc) from exc
    except ChatExecutionTimeout as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except ChatExecutionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ChatExecutionFailed as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(
        user_id=result.user_id,
        session_id=result.session_id,
        turn_id=result.turn_id,
        answer=result.answer,
    )


@router.post("/api/chat/stream")
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
) -> StreamingResponse:
    try:
        prepared = await get_runtime().chat_use_case.prepare_stream(
            _command(request, http_request, idempotency_key)
        )
    except (ChatContextBudgetExceeded, ChatTurnConflict) as exc:
        raise _map_admission_error(exc) from exc

    async def generate():
        async for event in get_runtime().chat_use_case.stream(prepared):
            yield json.dumps(
                {"type": event.kind, **event.payload},
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"X-Content-Type-Options": "nosniff"},
    )
