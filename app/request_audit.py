"""Sanitized authoritative HTTP activity auditing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
import time
from typing import Any

from fastapi import Request

from app.config import Settings
from app.storage import ConversationStore

logger = logging.getLogger(__name__)


async def audit_api_request(
    request: Request,
    *,
    status_code: int,
    started_at: float,
    settings: Settings,
    store: ConversationStore,
    execute: Callable[..., Awaitable[Any]],
) -> None:
    if not request.url.path.startswith("/api/"):
        return
    current_user = getattr(request.state, "current_user", None)
    if current_user is None and not (
        settings.auth_required and status_code in {401, 403}
    ):
        return

    route = request.scope.get("route")
    route_path = str(getattr(route, "path", request.url.path))
    route_name = str(getattr(route, "name", "unmatched_api_request"))
    path_parts = [
        part
        for part in route_path.split("/")
        if part and not part.startswith("{")
    ]
    resource_type = path_parts[1] if len(path_parts) > 1 else "api"
    path_parameters = {
        str(key): str(value)[:256]
        for key, value in request.path_params.items()
    }
    resource_id = next(iter(path_parameters.values()), None)
    outcome = (
        "denied"
        if status_code in {401, 403}
        else "error"
        if status_code >= 400
        else "success"
    )
    try:
        await execute(
            store.record_audit_event,
            request_id=str(getattr(request.state, "request_id", "")),
            actor_user_id=(
                current_user.user_id if current_user else None
            ),
            actor_username=(
                current_user.username if current_user else None
            ),
            actor_role=current_user.role if current_user else None,
            action=route_name,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            method=request.method,
            path=route_path,
            status_code=status_code,
            duration_ms=int((time.monotonic() - started_at) * 1000),
            detail={"path_parameters": path_parameters},
        )
    except Exception:
        logger.warning("Request audit write failed.", exc_info=True)
