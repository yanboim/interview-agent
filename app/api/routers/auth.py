import asyncio

from fastapi import APIRouter, HTTPException, Request

from app.api.execution import run_sync
from app.api.runtime import get_runtime
from app.api.schemas import (
    AuthCredentials,
    ChangePasswordRequest,
    LogoutRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
)
from app.api.security import require_role, token_pair_response
from app.auth import AuthSurfaceError, AuthenticatedUser
from app.multi_agent import agent_topology

router = APIRouter()


@router.get("/api/agent/topology")
async def get_agent_topology() -> dict[str, object]:
    return agent_topology()


@router.get("/api/config")
async def public_config() -> dict[str, bool]:
    return {"auth_required": get_runtime().settings.auth_required}


@router.post("/api/auth/register")
async def register(credentials: AuthCredentials) -> dict[str, object]:
    runtime = get_runtime()
    await run_sync(runtime.conversation_store.initialize)
    try:
        pair = await run_sync(
            runtime.auth_service.register,
            credentials.username,
            credentials.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return token_pair_response(pair)


@router.post("/api/auth/login")
async def login(credentials: AuthCredentials) -> dict[str, object]:
    runtime = get_runtime()
    await run_sync(runtime.conversation_store.initialize)
    try:
        pair = await run_sync(
            runtime.auth_service.login_user,
            credentials.username,
            credentials.password,
        )
    except AuthSurfaceError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return token_pair_response(pair)


@router.post("/api/admin/auth/login")
async def admin_login(credentials: AuthCredentials) -> dict[str, object]:
    """后台使用独立入口登录，普通用户凭据不会获得后台会话。"""
    runtime = get_runtime()
    await run_sync(runtime.conversation_store.initialize)
    try:
        pair = await run_sync(
            runtime.auth_service.login_admin,
            credentials.username,
            credentials.password,
        )
    except AuthSurfaceError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return token_pair_response(pair)


@router.post("/api/auth/refresh")
async def refresh_access_token(
    payload: RefreshTokenRequest,
) -> dict[str, object]:
    runtime = get_runtime()
    await run_sync(runtime.conversation_store.initialize)
    try:
        pair = await run_sync(
            runtime.auth_service.refresh,
            payload.refresh_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return token_pair_response(pair)


@router.post("/api/auth/logout")
async def logout(request: Request, payload: LogoutRequest) -> dict[str, bool]:
    authorization = request.headers.get("authorization", "")
    access_token = (
        authorization.removeprefix("Bearer ").strip()
        if authorization.startswith("Bearer ")
        else ""
    )
    auth_service = get_runtime().auth_service
    if access_token:
        await run_sync(auth_service.revoke, access_token)
    if payload.refresh_token:
        await run_sync(auth_service.revoke, payload.refresh_token)
    return {"logged_out": True}


@router.post("/api/auth/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
) -> dict[str, bool]:
    current = require_role(request, {"user", "admin"})
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=422, detail="新密码不能与当前密码相同")
    try:
        await run_sync(
            get_runtime().auth_service.change_password,
            user_id=current.user_id,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"changed": True, "sessions_revoked": True}


@router.post("/api/auth/reset-password")
async def reset_password(payload: ResetPasswordRequest) -> dict[str, object]:
    try:
        replacement_code = await run_sync(
            get_runtime().auth_service.reset_password,
            username=payload.username,
            recovery_code=payload.recovery_code,
            new_password=payload.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "changed": True,
        "sessions_revoked": True,
        "recovery_code": replacement_code,
    }


@router.post("/api/auth/recovery-code")
async def regenerate_recovery_code(request: Request) -> dict[str, str]:
    current = require_role(request, {"user", "admin"})
    recovery_code = await run_sync(
        get_runtime().auth_service.generate_recovery_code,
        user_id=current.user_id,
    )
    return {"recovery_code": recovery_code}


@router.get("/api/auth/me")
async def current_user(request: Request) -> dict[str, str]:
    runtime = get_runtime()
    if runtime.settings.auth_required:
        user: AuthenticatedUser = request.state.current_user
    else:
        authorization = request.headers.get("authorization", "")
        token = authorization.removeprefix("Bearer ").strip()
        resolved = await run_sync(
            runtime.auth_service.resolve_access_token,
            token,
        )
        if not resolved:
            raise HTTPException(status_code=401, detail="登录状态无效或已过期")
        user = resolved
    return {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role,
    }
