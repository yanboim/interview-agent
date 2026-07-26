import asyncio
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request

from app.api.execution import run_sync
from app.api.runtime import get_runtime
from app.api.schemas import (
    AdminUserRoleRequest,
    KnowledgeFileRequest,
    KnowledgeRollbackRequest,
)
from app.api.security import require_role
from app.knowledge_publication import (
    KnowledgePublicationConflict,
    KnowledgePublicationError,
)
from app.multi_agent import agent_topology
from app.operations import JobIdempotencyConflict, request_metrics

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/admin/system-summary")
async def admin_system_summary(request: Request) -> dict[str, object]:
    admin = require_role(request, {"admin"})
    counts = await run_sync(
        get_runtime().conversation_store.system_counts
    )
    return {"operator": admin.username, "role": admin.role, "counts": counts}


@router.get("/api/admin/runtime")
async def admin_runtime(request: Request) -> dict[str, object]:
    admin = require_role(request, {"admin"})
    runtime = get_runtime()
    dependencies: dict[str, dict[str, str]] = {}
    checks = (
        ("database", runtime.conversation_store.check_connection),
        ("redis", runtime.redis_runtime.check),
        ("qdrant", runtime.require_serving_knowledge),
    )
    for name, check in checks:
        try:
            await run_sync(check)
            dependencies[name] = {"status": "ok", "detail": "已连接"}
        except Exception as exc:
            dependencies[name] = {
                "status": "error",
                "detail": f"{type(exc).__name__}: {exc}"[:300],
            }
    metrics_snapshot = request_metrics.snapshot()
    settings = runtime.settings
    return {
        "operator": admin.username,
        "dependencies": dependencies,
        "agent": agent_topology(),
        "metrics": {
            "requests_total": metrics_snapshot.requests_total,
            "errors_total": metrics_snapshot.errors_total,
            "active_requests": metrics_snapshot.active_requests,
            "duration_seconds_total": round(
                metrics_snapshot.duration_seconds_total, 3
            ),
        },
        "features": {
            "auth_required": settings.auth_required,
            "multi_agent_enabled": settings.multi_agent_enabled,
            "web_search_enabled": settings.web_search_enabled,
            "reranker_enabled": settings.reranker_enabled,
            "redis_configured": bool(settings.redis_url),
        },
    }


@router.get("/api/admin/users")
async def admin_users(
    request: Request, limit: int = 200
) -> list[dict[str, object]]:
    require_role(request, {"admin"})
    return await run_sync(
        get_runtime().conversation_store.list_users, limit=limit
    )


@router.patch("/api/admin/users/{user_id}/role")
async def admin_update_user_role(
    user_id: str,
    payload: AdminUserRoleRequest,
    request: Request,
) -> dict[str, object]:
    admin = require_role(request, {"admin"})
    if admin.user_id == user_id and payload.role != "admin":
        raise HTTPException(status_code=409, detail="不能降级当前登录管理员")
    try:
        return await run_sync(
            get_runtime().conversation_store.update_user_role,
            user_id=user_id,
            role=payload.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/admin/tool-audits")
async def admin_tool_audits(
    request: Request,
    user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, object]]:
    require_role(request, {"admin"})
    return await run_sync(
        get_runtime().conversation_store.list_tool_audits,
        user_id=user_id,
        limit=limit,
    )


@router.get("/api/admin/product-events")
async def admin_product_events(
    request: Request,
    user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, object]]:
    require_role(request, {"admin"})
    return await run_sync(
        get_runtime().conversation_store.list_product_events,
        user_id=user_id,
        limit=limit,
    )


def list_knowledge_files() -> list[dict[str, object]]:
    knowledge_dir = Path("knowledge")
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    result = []
    for file_path in sorted(knowledge_dir.iterdir()):
        if not file_path.is_file() or file_path.suffix.lower() not in {".md", ".txt"}:
            continue
        stat = file_path.stat()
        result.append(
            {
                "filename": file_path.name,
                "size": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime)
                .astimezone()
                .isoformat(),
            }
        )
    return result


@router.get("/api/admin/knowledge/files")
async def admin_knowledge_files(request: Request) -> list[dict[str, object]]:
    require_role(request, {"admin"})
    return list_knowledge_files()


@router.put("/api/admin/knowledge/files")
async def admin_save_knowledge_file(
    payload: KnowledgeFileRequest,
    request: Request,
) -> dict[str, object]:
    admin = require_role(request, {"admin"})
    knowledge_dir = Path("knowledge")
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    target = knowledge_dir / payload.filename
    target.write_text(payload.content, encoding="utf-8")
    return {
        "operator": admin.username,
        "filename": target.name,
        "size": target.stat().st_size,
        "status": "saved",
    }


@router.delete("/api/admin/knowledge/files/{filename}")
async def admin_delete_knowledge_file(
    filename: str, request: Request
) -> dict[str, object]:
    admin = require_role(request, {"admin"})
    try:
        safe_name = KnowledgeFileRequest(
            filename=filename, content="validation"
        ).filename
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    target = Path("knowledge") / safe_name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="知识文件不存在")
    target.unlink()
    return {
        "operator": admin.username,
        "filename": safe_name,
        "status": "deleted",
    }


@router.post("/api/admin/knowledge/import")
async def admin_import_knowledge(request: Request) -> dict[str, object]:
    admin = require_role(request, {"admin"})
    try:
        result = await run_sync(get_runtime().ingest_knowledge)
    except KnowledgePublicationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("管理员触发知识库导入失败")
        raise HTTPException(
            status_code=503, detail=f"知识库导入失败：{exc}"
        ) from exc
    return {"operator": admin.username, "status": "completed", **result}


@router.get("/api/admin/knowledge/status")
async def admin_knowledge_status(request: Request) -> dict[str, object]:
    require_role(request, {"admin"})
    try:
        return await run_sync(get_runtime().knowledge_status)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"读取知识库版本失败：{exc}"
        ) from exc


@router.post("/api/admin/knowledge/rollback")
async def admin_knowledge_rollback(
    payload: KnowledgeRollbackRequest,
    request: Request,
) -> dict[str, object]:
    admin = require_role(request, {"admin"})
    try:
        result = await run_sync(
            get_runtime().rollback_knowledge, payload.collection_name
        )
    except KnowledgePublicationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KnowledgePublicationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"知识库回滚失败：{exc}"
        ) from exc
    return {"operator": admin.username, **result}


@router.post("/api/admin/jobs/knowledge-import")
async def enqueue_knowledge_import(
    request: Request,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
) -> dict[str, str]:
    admin = require_role(request, {"admin"})
    try:
        job_id = await run_sync(
            get_runtime().redis_runtime.enqueue,
            "knowledge_import",
            {"requested_by": admin.username},
            idempotency_key=idempotency_key,
            max_attempts=get_runtime().settings.job_max_attempts,
        )
    except JobIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"后台队列不可用：{exc}"
        ) from exc
    return {"job_id": job_id, "status": "queued"}


@router.get("/api/admin/jobs/{job_id}")
async def admin_job_status(job_id: str, request: Request) -> dict[str, str]:
    require_role(request, {"admin"})
    try:
        result = await run_sync(
            get_runtime().redis_runtime.get_job, job_id
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"后台队列不可用：{exc}"
        ) from exc
    if not result:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return result
