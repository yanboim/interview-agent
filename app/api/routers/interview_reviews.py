"""真实面试复盘 HTTP 适配器，区分文本、音频同意、转写确认与分析阶段。"""

from fastapi import (
    APIRouter,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)

from app.api.execution import run_sync
from app.api.runtime import get_runtime
from app.api.schemas import (
    InterviewReviewConfirmRequest,
    InterviewReviewTextRequest,
    InterviewReviewTranscriptUpdateRequest,
)
from app.api.security import current_product_user_id
from app.application.interview_review_service import (
    InterviewReviewConflict,
    InterviewReviewNotFound,
    InterviewReviewUnavailable,
)
from app.user_files import UnsupportedUserFile, UserFileTooLarge

router = APIRouter()


def _require_enabled() -> None:
    if not get_runtime().settings.review_feature_enabled:
        raise HTTPException(status_code=404, detail="面试复盘尚未启用")


def _raise_review_error(exc: Exception) -> None:
    if isinstance(exc, InterviewReviewNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, InterviewReviewConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, InterviewReviewUnavailable):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, UserFileTooLarge):
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    if isinstance(exc, UnsupportedUserFile):
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


def _idempotency_header() -> Header:
    return Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )


@router.post("/api/interview-reviews/text", status_code=status.HTTP_201_CREATED)
async def create_text_review(
    payload: InterviewReviewTextRequest,
    request: Request,
    idempotency_key: str = _idempotency_header(),
) -> dict[str, object]:
    _require_enabled()
    try:
        return await run_sync(
            get_runtime().interview_review_service.create_text,
            user_id=current_product_user_id(request),
            transcript=payload.transcript,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        _raise_review_error(exc)
        raise


@router.post("/api/interview-reviews/audio", status_code=status.HTTP_202_ACCEPTED)
async def create_audio_review(
    request: Request,
    file: UploadFile = File(...),
    external_processing_consent: bool = Form(...),
    idempotency_key: str = _idempotency_header(),
) -> dict[str, object]:
    _require_enabled()
    try:
        return await run_sync(
            get_runtime().interview_review_service.create_audio,
            user_id=current_product_user_id(request),
            original_filename=file.filename or "audio",
            source=file.file,
            external_processing_consent=external_processing_consent,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        _raise_review_error(exc)
        raise
    finally:
        await file.close()


@router.get("/api/interview-reviews")
async def list_reviews(request: Request) -> list[dict[str, object]]:
    _require_enabled()
    return await run_sync(
        get_runtime().interview_review_service.list,
        user_id=current_product_user_id(request),
    )


@router.get("/api/interview-reviews/{review_id}")
async def get_review(review_id: str, request: Request) -> dict[str, object]:
    _require_enabled()
    try:
        return await run_sync(
            get_runtime().interview_review_service.get,
            user_id=current_product_user_id(request),
            review_id=review_id,
        )
    except Exception as exc:
        _raise_review_error(exc)
        raise


@router.patch("/api/interview-reviews/{review_id}/transcript")
async def update_transcript(
    review_id: str,
    payload: InterviewReviewTranscriptUpdateRequest,
    request: Request,
) -> dict[str, object]:
    _require_enabled()
    try:
        return await run_sync(
            get_runtime().interview_review_service.update_transcript,
            user_id=current_product_user_id(request),
            review_id=review_id,
            expected_revision=payload.expected_revision,
            segments_payload=payload.segments,
        )
    except Exception as exc:
        _raise_review_error(exc)
        raise


@router.post(
    "/api/interview-reviews/{review_id}/confirm-and-analyze",
    status_code=status.HTTP_202_ACCEPTED,
)
async def confirm_and_analyze(
    review_id: str,
    payload: InterviewReviewConfirmRequest,
    request: Request,
    idempotency_key: str = _idempotency_header(),
) -> dict[str, object]:
    _require_enabled()
    try:
        return await run_sync(
            get_runtime().interview_review_service.confirm_and_analyze,
            user_id=current_product_user_id(request),
            review_id=review_id,
            expected_revision=payload.expected_revision,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        _raise_review_error(exc)
        raise


@router.post("/api/interview-reviews/{review_id}/retry")
async def retry_review(review_id: str, request: Request) -> dict[str, object]:
    _require_enabled()
    try:
        return await run_sync(
            get_runtime().interview_review_service.retry,
            user_id=current_product_user_id(request),
            review_id=review_id,
        )
    except Exception as exc:
        _raise_review_error(exc)
        raise


@router.delete("/api/interview-reviews/{review_id}")
async def delete_review(review_id: str, request: Request) -> dict[str, bool]:
    _require_enabled()
    deleted = await run_sync(
        get_runtime().interview_review_service.delete,
        user_id=current_product_user_id(request),
        review_id=review_id,
    )
    return {"deleted": deleted}
