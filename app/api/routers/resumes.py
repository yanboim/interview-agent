"""简历上传、评估、优化稿编辑与导出的 HTTP 适配器。"""

from urllib.parse import quote

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
from fastapi.responses import Response

from app.api.execution import run_sync
from app.api.runtime import get_runtime
from app.api.schemas import ResumeAnalysisRequest, ResumeDraftUpdateRequest
from app.api.security import current_product_user_id
from app.application.resume_service import (
    ResumeConflict,
    ResumeNotFound,
    ResumeUnavailable,
)
from app.user_files import (
    UnsupportedUserFile,
    UserFileTooLarge,
)

router = APIRouter()


def _require_enabled() -> None:
    if not get_runtime().settings.resume_feature_enabled:
        raise HTTPException(status_code=404, detail="简历功能尚未启用")


def _raise_resume_error(exc: Exception) -> None:
    if isinstance(exc, ResumeNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ResumeConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ResumeUnavailable):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, UserFileTooLarge):
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    if isinstance(exc, UnsupportedUserFile):
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    raise exc


@router.post("/api/resumes", status_code=status.HTTP_202_ACCEPTED)
async def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    job_description: str = Form(default="", max_length=20_000),
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
) -> dict[str, object]:
    _require_enabled()
    user_id = current_product_user_id(request)
    try:
        return await run_sync(
            get_runtime().resume_service.create,
            user_id=user_id,
            original_filename=file.filename or "resume",
            source=file.file,
            job_description=job_description,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        _raise_resume_error(exc)
        raise
    finally:
        await file.close()


@router.get("/api/resumes")
async def list_resumes(request: Request) -> list[dict[str, object]]:
    _require_enabled()
    return await run_sync(
        get_runtime().resume_service.list,
        user_id=current_product_user_id(request),
    )


@router.get("/api/resumes/{resume_id}")
async def get_resume(
    resume_id: str,
    request: Request,
) -> dict[str, object]:
    _require_enabled()
    try:
        return await run_sync(
            get_runtime().resume_service.get,
            user_id=current_product_user_id(request),
            resume_id=resume_id,
        )
    except Exception as exc:
        _raise_resume_error(exc)
        raise


@router.post(
    "/api/resumes/{resume_id}/analyses",
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_resume_analysis(
    resume_id: str,
    payload: ResumeAnalysisRequest,
    request: Request,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
) -> dict[str, object]:
    _require_enabled()
    try:
        return await run_sync(
            get_runtime().resume_service.create_analysis,
            user_id=current_product_user_id(request),
            resume_id=resume_id,
            job_description=payload.job_description,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        _raise_resume_error(exc)
        raise


@router.patch("/api/resume-analyses/{analysis_id}/draft")
async def update_resume_draft(
    analysis_id: str,
    payload: ResumeDraftUpdateRequest,
    request: Request,
) -> dict[str, object]:
    _require_enabled()
    try:
        return await run_sync(
            get_runtime().resume_service.update_draft,
            user_id=current_product_user_id(request),
            analysis_id=analysis_id,
            expected_revision=payload.expected_revision,
            draft_payload=payload.draft,
        )
    except Exception as exc:
        _raise_resume_error(exc)
        raise


@router.get("/api/resume-analyses/{analysis_id}/export.docx")
async def export_resume_docx(
    analysis_id: str,
    request: Request,
) -> Response:
    _require_enabled()
    try:
        content, filename = await run_sync(
            get_runtime().resume_service.export_docx,
            user_id=current_product_user_id(request),
            analysis_id=analysis_id,
        )
    except Exception as exc:
        _raise_resume_error(exc)
        raise
    encoded = quote(filename)
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{encoded}"
            )
        },
    )


@router.delete("/api/resumes/{resume_id}")
async def delete_resume(
    resume_id: str,
    request: Request,
) -> dict[str, bool]:
    _require_enabled()
    deleted = await run_sync(
        get_runtime().resume_service.delete,
        user_id=current_product_user_id(request),
        resume_id=resume_id,
    )
    return {"deleted": deleted}
