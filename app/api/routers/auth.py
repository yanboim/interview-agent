"""认证 HTTP 适配器：注册、登录、刷新、撤销与密码恢复。"""

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
    """返回当前启用的 Agent 拓扑（直接路由/多 Agent 灰度等）供前端展示。"""
    return agent_topology()


@router.get("/api/config")
async def public_config() -> dict[str, object]:
    """返回前端需要的非敏感公开配置（鉴权开关、功能开关、转写提供方等）。"""
    settings = get_runtime().settings
    return {
        "auth_required": settings.auth_required,
        "resume_feature_enabled": settings.resume_feature_enabled,
        "review_feature_enabled": settings.review_feature_enabled,
        "transcription_enabled": settings.transcription_enabled,
        "transcription_provider_name": settings.transcription_provider_name,
    }


@router.post("/api/auth/register")
async def register(credentials: AuthCredentials) -> dict[str, object]:
    """注册新账号并返回登录令牌对（含首次生成的恢复码）。

    异常:
        HTTPException 409: 用户名已存在或密码不符合策略。
    """
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
    """产品用户登录并签发访问/刷新令牌。

    异常:
        HTTPException 401: 用户名或密码错误。
        HTTPException 403: 账号被禁用。
    """
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
    """用刷新令牌换取新的访问/刷新令牌对。

    异常:
        HTTPException 401: 刷新令牌无效或已过期。
    """
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
    """撤销当前访问令牌与可选的刷新令牌，登出当前会话。"""
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
    """已登录用户修改密码，成功后吊销其他会话。

    异常:
        HTTPException 422: 新密码与当前密码相同。
        HTTPException 400: 当前密码错误或新密码不符合策略。
    """
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
    """用恢复码重置密码并生成新的恢复码。

    异常:
        HTTPException 400: 恢复码无效或新密码不符合策略。
    """
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
    """重新生成当前用户的恢复码（旧恢复码失效）。"""
    current = require_role(request, {"user", "admin"})
    recovery_code = await run_sync(
        get_runtime().auth_service.generate_recovery_code,
        user_id=current.user_id,
    )
    return {"recovery_code": recovery_code}


@router.get("/api/auth/me")
async def current_user(request: Request) -> dict[str, str]:
    """返回当前登录用户的基本信息（ID、用户名、角色）。

    异常:
        HTTPException 401: 未登录或令牌无效。
    """
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
