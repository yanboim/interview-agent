import asyncio
import json
import logging
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessageChunk, ToolMessage
from pydantic import BaseModel, Field, field_validator
from qdrant_client import QdrantClient

from app.agent import get_interview_agent
from app.auth import AuthService, AuthSurfaceError, AuthenticatedUser, TokenPair
from app.capability import build_capability_profile
from app.config import get_settings
from app.interview_engine import build_report
from app.learning import build_learning_candidates
from app.logging_config import (
    configure_logging,
    reset_request_id,
    set_request_id,
)
from app.operations import RedisRuntime, SharedRateLimiter, request_metrics
from app.multi_agent import (
    agent_topology,
    assess_answer,
    generate_question,
    record_message_token_usage,
    record_result_token_usage,
)
from app.storage import ConversationStore
from app.telemetry import configure_telemetry
from app.tool_context import reset_tool_identity, set_tool_identity
from scripts.ingest import ingest_knowledge

logger = logging.getLogger(__name__)


app = FastAPI(
    title="AI 面试教练 Agent",
    description="基于 LangChain、LangGraph 和 Qdrant 的面试智能体",
    version="0.1.0",
)

WEB_DIRECTORY = Path(__file__).parent / "web"
settings = get_settings()
# 前端产物目录:若配置了 frontend_dist 且存在,优先用新构建的 Vue 产物;
# 否则回退到旧的内嵌静态页 app/web/(向后兼容,便于渐进迁移)。
_dist_candidate = Path(settings.frontend_dist) if settings.frontend_dist else Path(__file__).parent.parent / "frontend" / "dist"
FRONTEND_DIST = _dist_candidate if (_dist_candidate / "index.html").exists() else None
# /static 挂载到产物根目录:Vite base="/static/" 产物内部引用为 /static/assets/xxx,
# 因此挂载点须是 dist 根(而非 dist/assets)。回退旧前端时 app/web/ 本身就是根。
STATIC_DIRECTORY = FRONTEND_DIST if FRONTEND_DIST else WEB_DIRECTORY
app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")
configure_logging(settings.log_level, settings.json_logs)
conversation_store = ConversationStore(
    settings.database_url or settings.conversation_db_path,
    auto_create_schema=settings.auto_create_schema,
)
auth_service = AuthService(
    conversation_store.engine,
    access_token_minutes=settings.access_token_minutes,
    refresh_token_days=settings.refresh_token_days,
)
redis_runtime = RedisRuntime(
    settings.redis_url,
    settings.redis_queue_name,
)
rate_limiter = SharedRateLimiter(
    settings.rate_limit_requests,
    settings.rate_limit_window_seconds,
    redis_runtime,
)
configure_telemetry(
    app,
    conversation_store.engine,
    enabled=settings.otel_enabled,
    service_name=settings.otel_service_name,
    endpoint=settings.otel_exporter_otlp_endpoint,
)


class ChatRequest(BaseModel):
    user_id: str = Field(default="anonymous", min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=10000)

    @field_validator("user_id", "session_id", "message")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value


class ChatResponse(BaseModel):
    user_id: str
    session_id: str
    answer: str


class HistoryMessage(BaseModel):
    role: str
    content: str
    created_at: str
    metadata: dict[str, object] = Field(default_factory=dict)


class UserProfileRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    target_role: str = Field(min_length=1, max_length=100)
    experience_level: Literal["初级", "中级", "高级", "专家"]
    focus_areas: str = Field(default="", max_length=300)
    interview_date: str | None = Field(default=None, max_length=40)
    job_description: str = Field(default="", max_length=10000)

    @field_validator(
        "user_id",
        "target_role",
        "focus_areas",
        "job_description",
    )
    @classmethod
    def clean_profile_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("interview_date")
    @classmethod
    def validate_interview_date(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("interview_date 必须是 ISO 日期") from exc
        return value


class ProductEventRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    event_name: str = Field(min_length=1, max_length=100)
    properties: dict[str, object] = Field(default_factory=dict)

    @field_validator("user_id", "event_name")
    @classmethod
    def clean_event_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_.-]*", value):
            raise ValueError("event_name 仅支持小写字母、数字、点、短横线和下划线")
        return value


class ConversationSummary(BaseModel):
    session_id: str
    title: str
    mode: str
    archived_at: str | None = None
    created_at: str
    updated_at: str


class InterviewStartRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    topic: str = Field(min_length=1, max_length=200)
    level: str = Field(default="高级", min_length=1, max_length=30)
    question_count: int = Field(default=5, ge=1, le=20)

    @field_validator("user_id", "topic", "level")
    @classmethod
    def clean_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value


class InterviewAnswerRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    answer: str = Field(min_length=1, max_length=20000)

    @field_validator("user_id", "answer")
    @classmethod
    def clean_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value


class UserIdentityRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)

    @field_validator("user_id")
    @classmethod
    def clean_user_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能只包含空白字符")
        return value


class InterviewArchiveRequest(UserIdentityRequest):
    archived: bool = True


class LearningTaskGenerateRequest(UserIdentityRequest):
    topic: str | None = Field(default=None, max_length=200)


class LearningTaskUpdateRequest(UserIdentityRequest):
    status: Literal["todo", "in_progress", "completed"] | None = None
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("due_at 必须包含时区")
        return value


class ConversationRenameRequest(UserIdentityRequest):
    title: str = Field(min_length=1, max_length=60)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("标题不能为空")
        return value


class ConversationArchiveRequest(UserIdentityRequest):
    session_ids: list[str] = Field(min_length=1, max_length=100)
    archived: bool = True

    @field_validator("session_ids")
    @classmethod
    def clean_session_ids(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if not cleaned or any(len(value) > 128 for value in cleaned):
            raise ValueError("session_ids 不合法")
        return list(dict.fromkeys(cleaned))


class AuthCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=10, max_length=200)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.strip().casefold()
        if not value or not all(
            character.isalnum() or character in "._-"
            for character in value
        ):
            raise ValueError("用户名只能包含字母、数字、点、下划线和短横线")
        return value


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=500)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=500)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=12, max_length=200)

    @field_validator("new_password")
    @classmethod
    def require_strong_password(cls, value: str) -> str:
        categories = (
            any(character.islower() for character in value),
            any(character.isupper() for character in value),
            any(character.isdigit() for character in value),
        )
        if sum(categories) < 2:
            raise ValueError("新密码需包含大小写字母、数字中的至少两类")
        return value


class ResetPasswordRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    recovery_code: str = Field(min_length=20, max_length=40)
    new_password: str = Field(min_length=12, max_length=200)

    @field_validator("username")
    @classmethod
    def normalize_reset_username(cls, value: str) -> str:
        return value.strip().casefold()

    @field_validator("recovery_code")
    @classmethod
    def normalize_recovery_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("new_password")
    @classmethod
    def require_strong_reset_password(cls, value: str) -> str:
        categories = (
            any(character.islower() for character in value),
            any(character.isupper() for character in value),
            any(character.isdigit() for character in value),
        )
        if sum(categories) < 2:
            raise ValueError("新密码需包含大小写字母、数字中的至少两类")
        return value


class ReminderPreferencesRequest(UserIdentityRequest):
    enabled: bool
    reminder_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(min_length=1, max_length=64)


class AdminUserRoleRequest(BaseModel):
    role: Literal["user", "admin"]


class KnowledgeFileRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=1_000_000)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        filename = value.strip()
        if (
            Path(filename).name != filename
            or filename in {".", ".."}
            or Path(filename).suffix.lower() not in {".md", ".txt"}
        ):
            raise ValueError("仅支持安全的 .md 或 .txt 文件名")
        return filename


@app.middleware("http")
async def operational_controls(request: Request, call_next):
    started_at = request_metrics.start()
    status_code = 500
    try:
        protected = (
            request.url.path.startswith("/api/")
            or request.url.path == "/ready"
        )
        if protected and settings.app_api_key:
            supplied = request.headers.get("x-api-key", "").strip()
            if not secrets.compare_digest(supplied, settings.app_api_key):
                status_code = 401
                return JSONResponse(
                    status_code=401,
                    content={"detail": "缺少或无效的 API Key"},
                )

        public_auth_paths = {
            "/api/config",
            "/api/auth/register",
            "/api/auth/login",
            "/api/admin/auth/login",
            "/api/auth/refresh",
            "/api/auth/reset-password",
        }
        if (
            settings.auth_required
            and request.url.path.startswith("/api/")
            and request.url.path not in public_auth_paths
        ):
            authorization = request.headers.get("authorization", "")
            access_token = (
                authorization.removeprefix("Bearer ").strip()
                if authorization.startswith("Bearer ")
                else ""
            )
            await asyncio.to_thread(conversation_store.initialize)
            current_user = await asyncio.to_thread(
                auth_service.resolve_access_token,
                access_token,
            )
            if not current_user:
                status_code = 401
                return JSONResponse(
                    status_code=401,
                    content={"detail": "登录状态无效或已过期"},
                )
            request.state.current_user = current_user

        if request.url.path.startswith("/api/"):
            client_host = request.client.host if request.client else "unknown"
            allowed, retry_after = rate_limiter.allow(client_host)
            if not allowed:
                status_code = 429
                return JSONResponse(
                    status_code=429,
                    content={"detail": "请求过于频繁，请稍后重试"},
                    headers={"Retry-After": str(retry_after)},
                )

        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        request_metrics.finish(started_at, status_code)


@app.middleware("http")
async def request_context_and_security(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "").strip()
    if not request_id or len(request_id) > 128:
        request_id = str(uuid4())
    request.state.request_id = request_id
    token = set_request_id(request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
        logger.info(
            "request_completed method=%s path=%s status=%s",
            request.method,
            request.url.path,
            response.status_code,
        )
        return response
    finally:
        reset_request_id(token)


def token_pair_response(pair: TokenPair) -> dict[str, object]:
    response: dict[str, object] = {
        "access_token": pair.access_token,
        "refresh_token": pair.refresh_token,
        "token_type": "bearer",
        "expires_in": pair.expires_in,
        "user": {
            "user_id": pair.user.user_id,
            "username": pair.user.username,
            "role": pair.user.role,
        },
    }
    if pair.recovery_code:
        response["recovery_code"] = pair.recovery_code
    return response


def resolve_user_id(request: Request, claimed_user_id: str) -> str:
    if not settings.auth_required:
        return claimed_user_id.strip()
    current_user: AuthenticatedUser = request.state.current_user
    if claimed_user_id.strip() != current_user.user_id:
        raise HTTPException(status_code=403, detail="不能访问其他用户的数据")
    return current_user.user_id


def require_role(
    request: Request,
    allowed_roles: set[str],
) -> AuthenticatedUser:
    current_user = getattr(request.state, "current_user", None)
    if not current_user:
        raise HTTPException(status_code=401, detail="需要登录")
    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="权限不足")
    return current_user


def extract_message_text(message: Any) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, str):
                texts.append(block)
            elif isinstance(block, dict) and block.get("text"):
                texts.append(str(block["text"]))
        return "\n".join(texts)
    return str(content)


def extract_sources(tool_name: str, content: str) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    web_pattern = re.compile(
        r"标题：(?P<label>[^\n]+)\n"
        r"链接：(?P<url>[^\n]+)\n"
        r"抓取时间：(?P<fetched_at>[^\n]+)\n"
        r"摘要：(?P<snippet>.*?)(?=\n\n\[网络来源|\Z)",
        re.DOTALL,
    )
    for match in web_pattern.finditer(content):
        sources.append(
            {
                "label": match.group("label").strip(),
                "kind": "public",
                "url": match.group("url").strip(),
                "fetched_at": match.group("fetched_at").strip(),
                "snippet": match.group("snippet").strip()[:300],
            }
        )
    if tool_name == "search_interview_knowledge" or "来源：" in content:
        for label in re.findall(r"^来源：(.+)$", content, re.MULTILINE):
            clean_label = label.strip()
            if clean_label:
                content_match = re.search(
                    rf"^来源：{re.escape(clean_label)}$\n.*?^内容：(.*?)(?=\n\n\[资料|\Z)",
                    content,
                    re.MULTILINE | re.DOTALL,
                )
                source = {"label": clean_label, "kind": "private"}
                if content_match:
                    source["snippet"] = content_match.group(1).strip()[:300]
                sources.append(source)
    unique: dict[tuple[str, str, str], dict[str, str]] = {}
    for source in sources:
        key = (
            source["kind"],
            source["label"],
            source.get("url", ""),
        )
        unique[key] = source
    return list(unique.values())


def _resolve_index_html() -> Path:
    """返回前端入口 HTML 路径:优先新 Vue 产物,否则旧静态页。"""
    if FRONTEND_DIST:
        return FRONTEND_DIST / "index.html"
    return WEB_DIRECTORY / "index.html"


@app.get("/", include_in_schema=False)
async def web_app() -> FileResponse:
    return FileResponse(_resolve_index_html())


@app.get("/admin", include_in_schema=False)
async def admin_web_app() -> FileResponse:
    # 新前端是 SPA,主应用与后台共用同一个 index.html;/admin 路由在前端解析。
    if FRONTEND_DIST:
        return FileResponse(FRONTEND_DIST / "index.html")
    return FileResponse(WEB_DIRECTORY / "admin.html")


@app.get("/today", include_in_schema=False)
@app.get("/chat", include_in_schema=False)
@app.get("/chat/{session_id}", include_in_schema=False)
@app.get("/interviews", include_in_schema=False)
@app.get("/interviews/{interview_id}", include_in_schema=False)
@app.get("/profile", include_in_schema=False)
@app.get("/learning", include_in_schema=False)
async def main_web_app(
    session_id: str | None = None,
    interview_id: str | None = None,
) -> FileResponse:
    """Serve the SPA shell for product deep links."""
    return FileResponse(_resolve_index_html())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def readiness() -> dict[str, str]:
    try:
        with request_metrics.dependency("database"):
            await asyncio.to_thread(conversation_store.check_connection)
        with request_metrics.dependency("qdrant"):
            client = QdrantClient(
                url=settings.qdrant_url,
                timeout=5,
                check_compatibility=False,
            )
            exists = await asyncio.to_thread(
                client.collection_exists,
                settings.qdrant_collection,
            )
        if not exists:
            raise RuntimeError("Qdrant collection 不存在")
        if redis_runtime.client:
            with request_metrics.dependency("redis"):
                await asyncio.to_thread(redis_runtime.check)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"依赖未就绪：{exc}",
        ) from exc
    return {"status": "ready"}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    return request_metrics.render_prometheus()


@app.get("/api/agent/topology")
async def get_agent_topology() -> dict[str, object]:
    return agent_topology()


@app.get("/api/config")
async def public_config() -> dict[str, bool]:
    return {"auth_required": settings.auth_required}


@app.post("/api/auth/register")
async def register(credentials: AuthCredentials) -> dict[str, object]:
    await asyncio.to_thread(conversation_store.initialize)
    try:
        pair = await asyncio.to_thread(
            auth_service.register,
            credentials.username,
            credentials.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return token_pair_response(pair)


@app.post("/api/auth/login")
async def login(credentials: AuthCredentials) -> dict[str, object]:
    await asyncio.to_thread(conversation_store.initialize)
    try:
        pair = await asyncio.to_thread(
            auth_service.login_user,
            credentials.username,
            credentials.password,
        )
    except AuthSurfaceError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return token_pair_response(pair)


@app.post("/api/admin/auth/login")
async def admin_login(credentials: AuthCredentials) -> dict[str, object]:
    """后台使用独立入口登录，普通用户凭据不会获得后台会话。"""
    await asyncio.to_thread(conversation_store.initialize)
    try:
        pair = await asyncio.to_thread(
            auth_service.login_admin,
            credentials.username,
            credentials.password,
        )
    except AuthSurfaceError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return token_pair_response(pair)


@app.post("/api/auth/refresh")
async def refresh_access_token(
    payload: RefreshTokenRequest,
) -> dict[str, object]:
    await asyncio.to_thread(conversation_store.initialize)
    try:
        pair = await asyncio.to_thread(
            auth_service.refresh,
            payload.refresh_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return token_pair_response(pair)


@app.post("/api/auth/logout")
async def logout(
    request: Request,
    payload: LogoutRequest,
) -> dict[str, bool]:
    authorization = request.headers.get("authorization", "")
    access_token = (
        authorization.removeprefix("Bearer ").strip()
        if authorization.startswith("Bearer ")
        else ""
    )
    if access_token:
        await asyncio.to_thread(auth_service.revoke, access_token)
    if payload.refresh_token:
        await asyncio.to_thread(auth_service.revoke, payload.refresh_token)
    return {"logged_out": True}


@app.post("/api/auth/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
) -> dict[str, bool]:
    current = require_role(request, {"user", "admin"})
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=422, detail="新密码不能与当前密码相同")
    try:
        await asyncio.to_thread(
            auth_service.change_password,
            user_id=current.user_id,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"changed": True, "sessions_revoked": True}


@app.post("/api/auth/reset-password")
async def reset_password(
    payload: ResetPasswordRequest,
) -> dict[str, object]:
    try:
        replacement_code = await asyncio.to_thread(
            auth_service.reset_password,
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


@app.post("/api/auth/recovery-code")
async def regenerate_recovery_code(request: Request) -> dict[str, str]:
    current = require_role(request, {"user", "admin"})
    recovery_code = await asyncio.to_thread(
        auth_service.generate_recovery_code,
        user_id=current.user_id,
    )
    return {"recovery_code": recovery_code}


@app.get("/api/auth/me")
async def current_user(request: Request) -> dict[str, str]:
    if settings.auth_required:
        user: AuthenticatedUser = request.state.current_user
    else:
        authorization = request.headers.get("authorization", "")
        token = authorization.removeprefix("Bearer ").strip()
        resolved = await asyncio.to_thread(
            auth_service.resolve_access_token,
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


@app.get("/api/profile")
async def user_profile(
    request: Request,
    user_id: str,
) -> dict[str, object]:
    user_id = resolve_user_id(request, user_id)
    profile = await asyncio.to_thread(
        conversation_store.get_user_profile,
        user_id=user_id,
    )
    return profile or {
        "user_id": user_id,
        "target_role": "",
        "experience_level": "高级",
        "focus_areas": "",
        "interview_date": None,
        "job_description": "",
        "created_at": None,
        "updated_at": None,
    }


@app.put("/api/profile")
async def update_user_profile(
    payload: UserProfileRequest,
    request: Request,
) -> dict[str, object]:
    user_id = resolve_user_id(request, payload.user_id)
    return await asyncio.to_thread(
        conversation_store.upsert_user_profile,
        user_id=user_id,
        target_role=payload.target_role,
        experience_level=payload.experience_level,
        focus_areas=payload.focus_areas,
        interview_date=payload.interview_date,
        job_description=payload.job_description,
    )


@app.get("/api/reminders/preferences")
async def reminder_preferences(
    request: Request,
    user_id: str,
) -> dict[str, object]:
    user_id = resolve_user_id(request, user_id)
    profile = await asyncio.to_thread(
        conversation_store.get_user_profile,
        user_id=user_id,
    )
    return {
        "enabled": bool(profile and profile.get("reminder_enabled")),
        "reminder_time": (
            str(profile.get("reminder_time")) if profile else "09:00"
        ),
        "timezone": (
            str(profile.get("reminder_timezone")) if profile else "UTC"
        ),
    }


@app.put("/api/reminders/preferences")
async def update_reminder_preferences(
    payload: ReminderPreferencesRequest,
    request: Request,
) -> dict[str, object]:
    user_id = resolve_user_id(request, payload.user_id)
    try:
        ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="无效的 IANA 时区") from exc
    profile = await asyncio.to_thread(
        conversation_store.update_reminder_preferences,
        user_id=user_id,
        enabled=payload.enabled,
        reminder_time=payload.reminder_time,
        timezone=payload.timezone,
    )
    return {
        "enabled": bool(profile["reminder_enabled"]),
        "reminder_time": profile["reminder_time"],
        "timezone": profile["reminder_timezone"],
    }


@app.get("/api/reminders/due")
async def due_reminders(
    request: Request,
    user_id: str,
) -> dict[str, object]:
    user_id = resolve_user_id(request, user_id)
    profile, tasks = await asyncio.gather(
        asyncio.to_thread(conversation_store.get_user_profile, user_id=user_id),
        asyncio.to_thread(conversation_store.list_learning_tasks, user_id=user_id),
    )
    if not profile or not profile.get("reminder_enabled"):
        return {"due": False, "items": []}
    timezone = ZoneInfo(str(profile.get("reminder_timezone") or "UTC"))
    now = datetime.now(UTC).astimezone(timezone)
    reminder_time = str(profile.get("reminder_time") or "09:00")
    time_reached = now.strftime("%H:%M") >= reminder_time
    due_items = [
        {
            "type": "learning_task",
            "id": task["task_id"],
            "title": task["weakness"],
            "action": task["action"],
        }
        for task in tasks
        if task["status"] != "completed"
        and datetime.fromisoformat(str(task["due_at"])).astimezone(timezone)
        <= now
    ]
    return {
        "due": bool(time_reached and due_items),
        "items": due_items if time_reached else [],
        "local_date": now.date().isoformat(),
    }


@app.get("/api/today-plan")
async def today_plan(
    request: Request,
    user_id: str,
) -> dict[str, object]:
    user_id = resolve_user_id(request, user_id)
    profile, tasks, interview_rows, interviews_list = await asyncio.gather(
        asyncio.to_thread(conversation_store.get_user_profile, user_id=user_id),
        asyncio.to_thread(conversation_store.list_learning_tasks, user_id=user_id),
        asyncio.to_thread(conversation_store.get_capability_rows, user_id=user_id),
        asyncio.to_thread(conversation_store.list_interviews, user_id=user_id),
    )
    active = next(
        (item for item in interviews_list if item["status"] == "active"),
        None,
    )
    now = datetime.now(UTC)
    due_tasks = [
        task
        for task in tasks
        if task["status"] != "completed"
        and datetime.fromisoformat(str(task["due_at"])) <= now
    ]
    weakness_counts: dict[str, int] = {}
    for row in interview_rows:
        for weakness in json.loads(str(row.get("weaknesses_json") or "[]")):
            label = str(weakness)
            weakness_counts[label] = weakness_counts.get(label, 0) + 1
    top_weakness = (
        max(weakness_counts, key=weakness_counts.get)
        if weakness_counts
        else ""
    )
    target = str((profile or {}).get("target_role") or "")
    focus = str((profile or {}).get("focus_areas") or target)
    if active:
        recommendation = {
            "type": "resume_interview",
            "title": f"继续 {active['topic']} 模拟面试",
            "reason": "完成进行中的训练，避免上下文中断。",
            "href": f"/interviews/{active['interview_id']}",
        }
    elif due_tasks:
        recommendation = {
            "type": "review",
            "title": f"复习：{due_tasks[0]['weakness']}",
            "reason": "该任务已到复习时间，优先巩固遗忘风险最高的内容。",
            "href": "/learning",
        }
    else:
        recommendation = {
            "type": "new_interview",
            "title": f"训练 {focus or '目标岗位核心能力'}",
            "reason": (
                f"结合高频薄弱点“{top_weakness}”生成针对性问题。"
                if top_weakness
                else f"依据 {target or '你的目标岗位'} 与 JD 生成首轮基线训练。"
            ),
            "href": "/interviews",
        }
    return {
        "recommendation": recommendation,
        "top_weakness": top_weakness or None,
        "target_role": target or None,
        "has_job_description": bool((profile or {}).get("job_description")),
        "due_count": len(due_tasks),
    }


@app.post("/api/product-events", status_code=202)
async def record_product_event(
    payload: ProductEventRequest,
    request: Request,
) -> dict[str, bool]:
    user_id = resolve_user_id(request, payload.user_id)
    if len(
        json.dumps(payload.properties, ensure_ascii=False, default=str)
    ) > 8192:
        raise HTTPException(status_code=422, detail="事件属性不能超过 8KB")
    await asyncio.to_thread(
        conversation_store.record_product_event,
        user_id=user_id,
        event_name=payload.event_name,
        session_id=payload.session_id,
        properties=payload.properties,
    )
    return {"accepted": True}


@app.get("/api/admin/system-summary")
async def admin_system_summary(request: Request) -> dict[str, object]:
    admin = require_role(request, {"admin"})
    counts = await asyncio.to_thread(conversation_store.system_counts)
    return {
        "operator": admin.username,
        "role": admin.role,
        "counts": counts,
    }


@app.get("/api/admin/runtime")
async def admin_runtime(request: Request) -> dict[str, object]:
    admin = require_role(request, {"admin"})
    dependencies: dict[str, dict[str, str]] = {}
    checks = (
        ("database", conversation_store.check_connection),
        ("redis", redis_runtime.check),
        (
            "qdrant",
            lambda: QdrantClient(
                url=settings.qdrant_url,
                timeout=5,
                check_compatibility=False,
            ).get_collection(settings.qdrant_collection),
        ),
    )
    for name, check in checks:
        try:
            await asyncio.to_thread(check)
            dependencies[name] = {"status": "ok", "detail": "已连接"}
        except Exception as exc:
            dependencies[name] = {
                "status": "error",
                "detail": f"{type(exc).__name__}: {exc}"[:300],
            }
    metrics_snapshot = request_metrics.snapshot()
    return {
        "operator": admin.username,
        "dependencies": dependencies,
        "agent": agent_topology(),
        "metrics": {
            "requests_total": metrics_snapshot.requests_total,
            "errors_total": metrics_snapshot.errors_total,
            "active_requests": metrics_snapshot.active_requests,
            "duration_seconds_total": round(
                metrics_snapshot.duration_seconds_total,
                3,
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


@app.get("/api/admin/users")
async def admin_users(
    request: Request,
    limit: int = 200,
) -> list[dict[str, object]]:
    require_role(request, {"admin"})
    return await asyncio.to_thread(
        conversation_store.list_users,
        limit=limit,
    )


@app.patch("/api/admin/users/{user_id}/role")
async def admin_update_user_role(
    user_id: str,
    payload: AdminUserRoleRequest,
    request: Request,
) -> dict[str, object]:
    admin = require_role(request, {"admin"})
    if admin.user_id == user_id and payload.role != "admin":
        raise HTTPException(status_code=409, detail="不能降级当前登录管理员")
    try:
        return await asyncio.to_thread(
            conversation_store.update_user_role,
            user_id=user_id,
            role=payload.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/admin/tool-audits")
async def admin_tool_audits(
    request: Request,
    user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, object]]:
    require_role(request, {"admin"})
    return await asyncio.to_thread(
        conversation_store.list_tool_audits,
        user_id=user_id,
        limit=limit,
    )


@app.get("/api/admin/product-events")
async def admin_product_events(
    request: Request,
    user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, object]]:
    require_role(request, {"admin"})
    return await asyncio.to_thread(
        conversation_store.list_product_events,
        user_id=user_id,
        limit=limit,
    )


def list_knowledge_files() -> list[dict[str, object]]:
    knowledge_dir = Path("knowledge")
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    result = []
    for file_path in sorted(knowledge_dir.iterdir()):
        if (
            not file_path.is_file()
            or file_path.suffix.lower() not in {".md", ".txt"}
        ):
            continue
        stat = file_path.stat()
        result.append(
            {
                "filename": file_path.name,
                "size": stat.st_size,
                "updated_at": datetime.fromtimestamp(
                    stat.st_mtime,
                ).astimezone().isoformat(),
            }
        )
    return result


@app.get("/api/admin/knowledge/files")
async def admin_knowledge_files(
    request: Request,
) -> list[dict[str, object]]:
    require_role(request, {"admin"})
    return list_knowledge_files()


@app.put("/api/admin/knowledge/files")
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


@app.delete("/api/admin/knowledge/files/{filename}")
async def admin_delete_knowledge_file(
    filename: str,
    request: Request,
) -> dict[str, object]:
    admin = require_role(request, {"admin"})
    try:
        safe_name = KnowledgeFileRequest(
            filename=filename,
            content="validation",
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


@app.post("/api/admin/knowledge/import")
async def admin_import_knowledge(request: Request) -> dict[str, object]:
    admin = require_role(request, {"admin"})
    try:
        result = await asyncio.to_thread(ingest_knowledge)
    except Exception as exc:
        logger.exception("管理员触发知识库导入失败")
        raise HTTPException(
            status_code=503,
            detail=f"知识库导入失败：{exc}",
        ) from exc
    return {
        "operator": admin.username,
        "status": "completed",
        **result,
    }


@app.post("/api/admin/jobs/knowledge-import")
async def enqueue_knowledge_import(request: Request) -> dict[str, str]:
    admin = require_role(request, {"admin"})
    try:
        job_id = await asyncio.to_thread(
            redis_runtime.enqueue,
            "knowledge_import",
            {"requested_by": admin.username},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"后台队列不可用：{exc}",
        ) from exc
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/admin/jobs/{job_id}")
async def admin_job_status(
    job_id: str,
    request: Request,
) -> dict[str, str]:
    require_role(request, {"admin"})
    try:
        result = await asyncio.to_thread(redis_runtime.get_job, job_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"后台队列不可用：{exc}",
        ) from exc
    if not result:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return result


async def prepare_messages(
    request: ChatRequest,
    user_id: str,
) -> list[dict[str, str]]:
    await asyncio.to_thread(
        conversation_store.append_message,
        user_id=user_id,
        session_id=request.session_id,
        role="user",
        content=request.message,
    )
    messages = await asyncio.to_thread(
        conversation_store.get_messages,
        user_id=user_id,
        session_id=request.session_id,
    )
    return [
        {"role": message.role, "content": message.content}
        for message in messages
    ]


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    http_request: Request,
) -> ChatResponse:
    user_id = resolve_user_id(http_request, request.user_id)
    current_user = getattr(http_request.state, "current_user", None)
    identity_token = set_tool_identity(
        user_id,
        current_user.role if current_user else "user",
    )
    try:
        messages = await prepare_messages(request, user_id)
        with request_metrics.dependency("glm"):
            result = await get_interview_agent().ainvoke(
                {"messages": messages},
            )
        record_result_token_usage(
            result,
            "supervisor" if settings.multi_agent_enabled else "single_agent",
        )
        answer = extract_message_text(result["messages"][-1])
        sources: list[dict[str, str]] = []
        for result_message in result["messages"]:
            if not isinstance(result_message, ToolMessage):
                continue
            sources.extend(
                extract_sources(
                    str(getattr(result_message, "name", "") or ""),
                    extract_message_text(result_message),
                )
            )
        source_map = {
            (
                source["kind"],
                source["label"],
                source.get("url", ""),
            ): source
            for source in sources
        }
        metadata_payload = {
            "knowledge_used": any(
                source["kind"] == "private" for source in source_map.values()
            ),
            "sources": list(source_map.values()),
        }
        await asyncio.to_thread(
            conversation_store.append_message,
            user_id=user_id,
            session_id=request.session_id,
            role="assistant",
            content=answer,
            metadata_json=(
                json.dumps(metadata_payload, ensure_ascii=False)
                if source_map
                else None
            ),
        )
        return ChatResponse(
            user_id=user_id,
            session_id=request.session_id,
            answer=answer,
        )
    except Exception as exc:
        logger.exception("Agent execution failed for session %s", request.session_id)
        raise HTTPException(status_code=500, detail=f"Agent 执行失败：{exc}") from exc
    finally:
        reset_tool_identity(identity_token)


@app.post("/api/chat/stream")
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
) -> StreamingResponse:
    user_id = resolve_user_id(http_request, request.user_id)

    async def generate():
        answer_parts: list[str] = []
        source_map: dict[tuple[str, str, str], dict[str, str]] = {}
        knowledge_used = False
        current_user = getattr(http_request.state, "current_user", None)
        identity_token = set_tool_identity(
            user_id,
            current_user.role if current_user else "user",
        )
        try:
            messages = await prepare_messages(request, user_id)
            with request_metrics.dependency("glm"):
                async for message, _ in get_interview_agent().astream(
                    {"messages": messages},
                    stream_mode="messages",
                ):
                    if isinstance(message, ToolMessage):
                        tool_name = str(getattr(message, "name", "") or "")
                        tool_content = extract_message_text(message)
                        for source in extract_sources(tool_name, tool_content):
                            key = (
                                source["kind"],
                                source["label"],
                                source.get("url", ""),
                            )
                            source_map[key] = source
                            knowledge_used = (
                                knowledge_used
                                or source["kind"] == "private"
                            )
                        continue
                    if not isinstance(message, AIMessageChunk):
                        continue
                    record_message_token_usage(
                        message,
                        (
                            "supervisor"
                            if settings.multi_agent_enabled
                            else "single_agent"
                        ),
                    )
                    text = extract_message_text(message)
                    if not text:
                        continue
                    answer_parts.append(text)
                    yield (
                        json.dumps(
                            {"type": "token", "content": text},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

            answer = "".join(answer_parts)
            if not answer:
                answer = "Agent 没有返回文本内容。"
            metadata_payload = {
                "knowledge_used": knowledge_used,
                "sources": list(source_map.values()),
            }
            if knowledge_used or source_map:
                yield (
                    json.dumps(
                        {
                            "type": "sources",
                            **metadata_payload,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            await asyncio.to_thread(
                conversation_store.append_message,
                user_id=user_id,
                session_id=request.session_id,
                role="assistant",
                content=answer,
                metadata_json=(
                    json.dumps(metadata_payload, ensure_ascii=False)
                    if source_map
                    else None
                ),
            )
            yield (
                json.dumps(
                    {
                        "type": "done",
                        "user_id": user_id,
                        "session_id": request.session_id,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        except Exception as exc:
            logger.exception(
                "Streaming agent execution failed for session %s",
                request.session_id,
            )
            yield (
                json.dumps(
                    {"type": "error", "detail": f"Agent 执行失败：{exc}"},
                    ensure_ascii=False,
                )
                + "\n"
            )
        finally:
            reset_tool_identity(identity_token)

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@app.get(
    "/api/conversations",
    response_model=list[ConversationSummary],
)
async def list_conversations(
    request: Request,
    user_id: str,
    include_archived: bool = False,
) -> list[dict[str, str | None]]:
    user_id = resolve_user_id(request, user_id)
    if not user_id or len(user_id) > 128:
        raise HTTPException(status_code=422, detail="user_id 不合法")
    return await asyncio.to_thread(
        conversation_store.list_conversations,
        user_id,
        include_archived=include_archived,
    )


@app.post("/api/conversations/archive")
async def archive_conversations(
    payload: ConversationArchiveRequest,
    request: Request,
) -> dict[str, int]:
    user_id = resolve_user_id(request, payload.user_id)
    updated = await asyncio.to_thread(
        conversation_store.archive_conversations,
        user_id=user_id,
        session_ids=payload.session_ids,
        archived=payload.archived,
    )
    return {"updated": updated}


@app.get(
    "/api/conversations/{session_id}/messages",
    response_model=list[HistoryMessage],
)
async def conversation_messages(
    request: Request,
    session_id: str,
    user_id: str,
) -> list[HistoryMessage]:
    user_id = resolve_user_id(request, user_id)
    messages = await asyncio.to_thread(
        conversation_store.get_messages,
        user_id=user_id,
        session_id=session_id.strip(),
    )
    return [
        HistoryMessage(
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            metadata=message.metadata,
        )
        for message in messages
    ]


@app.delete("/api/conversations/{session_id}")
async def delete_conversation(
    request: Request,
    session_id: str,
    user_id: str,
) -> dict[str, bool]:
    user_id = resolve_user_id(request, user_id)
    deleted = await asyncio.to_thread(
        conversation_store.delete_conversation,
        user_id=user_id,
        session_id=session_id.strip(),
    )
    return {"deleted": deleted}


@app.patch("/api/conversations/{session_id}", response_model=ConversationSummary)
async def rename_conversation(
    request: Request,
    session_id: str,
    payload: ConversationRenameRequest,
) -> dict[str, str]:
    user_id = resolve_user_id(request, payload.user_id)
    renamed = await asyncio.to_thread(
        conversation_store.rename_conversation,
        user_id=user_id,
        session_id=session_id.strip(),
        title=payload.title,
    )
    if not renamed:
        raise HTTPException(status_code=404, detail="会话不存在")
    return renamed


@app.get("/api/interviews")
async def list_interviews(
    request: Request,
    user_id: str,
    include_archived: bool = False,
) -> list[dict[str, object]]:
    user_id = resolve_user_id(request, user_id)
    return await asyncio.to_thread(
        conversation_store.list_interviews,
        user_id=user_id,
        include_archived=include_archived,
    )


@app.get("/api/interviews/{interview_id}")
async def interview_detail(
    request: Request,
    interview_id: str,
    user_id: str,
) -> dict[str, object]:
    user_id = resolve_user_id(request, user_id)
    interview = await asyncio.to_thread(
        conversation_store.get_interview,
        user_id=user_id,
        interview_id=interview_id,
    )
    if not interview:
        raise HTTPException(status_code=404, detail="模拟面试不存在")
    turns = await asyncio.to_thread(
        conversation_store.get_interview_turns,
        user_id=user_id,
        interview_id=interview_id,
    )
    pending = next(
        (turn for turn in reversed(turns) if not turn.get("answer")),
        None,
    )
    return {
        "interview": interview,
        "turns": turns,
        "pending_turn": pending,
        "report": build_report(turns),
    }


@app.post("/api/interviews/{interview_id}/resume")
async def resume_interview(
    request: Request,
    interview_id: str,
    payload: UserIdentityRequest,
) -> dict[str, object]:
    user_id = resolve_user_id(request, payload.user_id)
    interview = await asyncio.to_thread(
        conversation_store.get_interview,
        user_id=user_id,
        interview_id=interview_id,
    )
    if not interview:
        raise HTTPException(status_code=404, detail="模拟面试不存在")
    if interview.get("archived_at"):
        raise HTTPException(status_code=409, detail="请先取消归档再继续")
    if interview["status"] != "active":
        raise HTTPException(status_code=409, detail="该面试已经完成")
    turns = await asyncio.to_thread(
        conversation_store.get_interview_turns,
        user_id=user_id,
        interview_id=interview_id,
    )
    pending = next(
        (turn for turn in reversed(turns) if not turn.get("answer")),
        None,
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


@app.post("/api/interviews/{interview_id}/archive")
async def archive_interview(
    request: Request,
    interview_id: str,
    payload: InterviewArchiveRequest,
) -> dict[str, bool]:
    user_id = resolve_user_id(request, payload.user_id)
    changed = await asyncio.to_thread(
        conversation_store.archive_interview,
        user_id=user_id,
        interview_id=interview_id,
        archived=payload.archived,
    )
    if not changed:
        raise HTTPException(status_code=404, detail="模拟面试不存在")
    return {"archived": payload.archived}


@app.delete("/api/interviews/{interview_id}")
async def delete_interview(
    request: Request,
    interview_id: str,
    user_id: str,
) -> dict[str, bool]:
    user_id = resolve_user_id(request, user_id)
    deleted = await asyncio.to_thread(
        conversation_store.delete_interview,
        user_id=user_id,
        interview_id=interview_id,
    )
    return {"deleted": deleted}


@app.post("/api/interviews/start")
async def start_interview(
    request: InterviewStartRequest,
    http_request: Request,
) -> dict[str, object]:
    interview_id = str(uuid4())
    user_id = resolve_user_id(http_request, request.user_id)
    try:
        question = await asyncio.to_thread(
            generate_question,
            topic=request.topic,
            level=request.level,
            turn_index=1,
            previous_turns=[],
        )
        await asyncio.to_thread(
            conversation_store.create_interview,
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
            status_code=500,
            detail=f"模拟面试启动失败：{exc}",
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


@app.post("/api/interviews/{interview_id}/answer")
async def answer_interview(
    interview_id: str,
    request: InterviewAnswerRequest,
    http_request: Request,
) -> dict[str, object]:
    user_id = resolve_user_id(http_request, request.user_id)
    interview = await asyncio.to_thread(
        conversation_store.get_interview,
        user_id=user_id,
        interview_id=interview_id,
    )
    if not interview:
        raise HTTPException(status_code=404, detail="模拟面试不存在")
    if interview.get("archived_at"):
        raise HTTPException(status_code=409, detail="该面试已归档")
    if interview["status"] != "active":
        raise HTTPException(status_code=409, detail="模拟面试已经结束")

    turns = await asyncio.to_thread(
        conversation_store.get_interview_turns,
        user_id=user_id,
        interview_id=interview_id,
    )
    current = next(
        (turn for turn in reversed(turns) if not turn.get("answer")),
        None,
    )
    if not current:
        raise HTTPException(status_code=409, detail="没有待回答的问题")

    try:
        assessment = await asyncio.to_thread(
            assess_answer,
            topic=str(interview["topic"]),
            level=str(interview["level"]),
            question=str(current["question"]),
            answer=request.answer,
        )
        turn_index = int(current["turn_index"])
        next_question = None
        if turn_index < int(interview["total_questions"]):
            completed_turns = [
                *turns[:-1],
                {**current, "answer": request.answer},
            ]
            next_question = await asyncio.to_thread(
                generate_question,
                topic=str(interview["topic"]),
                level=str(interview["level"]),
                turn_index=turn_index + 1,
                previous_turns=completed_turns,
            )

        status = await asyncio.to_thread(
            conversation_store.save_interview_answer,
            user_id=user_id,
            interview_id=interview_id,
            turn_index=turn_index,
            answer=request.answer,
            score=float(assessment["overall"]),
            feedback=str(assessment["feedback"]),
            dimensions_json=json.dumps(
                assessment["dimensions"],
                ensure_ascii=False,
            ),
            strengths_json=json.dumps(
                assessment["strengths"],
                ensure_ascii=False,
            ),
            weaknesses_json=json.dumps(
                assessment["weaknesses"],
                ensure_ascii=False,
            ),
            reference_answer=str(assessment["reference_answer"]),
            next_question=next_question,
        )
    except Exception as exc:
        logger.exception("Failed to score interview %s", interview_id)
        raise HTTPException(status_code=500, detail=f"回答评分失败：{exc}") from exc

    return {
        "interview_id": interview_id,
        "turn_index": turn_index,
        "score": assessment["overall"],
        "dimensions": assessment["dimensions"],
        "strengths": assessment["strengths"],
        "weaknesses": assessment["weaknesses"],
        "feedback": assessment["feedback"],
        "reference_answer": assessment["reference_answer"],
        "next_question": next_question,
        "status": status,
    }


@app.post(
    "/api/interviews/{interview_id}/turns/{turn_index}/retry"
)
async def retry_interview_answer(
    interview_id: str,
    turn_index: int,
    request: InterviewAnswerRequest,
    http_request: Request,
) -> dict[str, object]:
    user_id = resolve_user_id(http_request, request.user_id)
    interview = await asyncio.to_thread(
        conversation_store.get_interview,
        user_id=user_id,
        interview_id=interview_id,
    )
    if not interview:
        raise HTTPException(status_code=404, detail="模拟面试不存在")
    if interview.get("archived_at"):
        raise HTTPException(status_code=409, detail="该面试已归档")
    turns = await asyncio.to_thread(
        conversation_store.get_interview_turns,
        user_id=user_id,
        interview_id=interview_id,
    )
    current = next(
        (turn for turn in turns if int(turn["turn_index"]) == turn_index),
        None,
    )
    if not current:
        raise HTTPException(status_code=404, detail="面试题不存在")
    if not current.get("answer"):
        raise HTTPException(status_code=409, detail="该题尚未完成首次回答")

    try:
        assessment = await asyncio.to_thread(
            assess_answer,
            topic=str(interview["topic"]),
            level=str(interview["level"]),
            question=str(current["question"]),
            answer=request.answer,
        )
        comparison = await asyncio.to_thread(
            conversation_store.retry_interview_answer,
            user_id=user_id,
            interview_id=interview_id,
            turn_index=turn_index,
            answer=request.answer,
            score=float(assessment["overall"]),
            feedback=str(assessment["feedback"]),
            dimensions_json=json.dumps(
                assessment["dimensions"],
                ensure_ascii=False,
            ),
            strengths_json=json.dumps(
                assessment["strengths"],
                ensure_ascii=False,
            ),
            weaknesses_json=json.dumps(
                assessment["weaknesses"],
                ensure_ascii=False,
            ),
            reference_answer=str(assessment["reference_answer"]),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "Failed to rescore interview %s turn %s",
            interview_id,
            turn_index,
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


@app.get("/api/interviews/{interview_id}/report")
async def interview_report(
    request: Request,
    interview_id: str,
    user_id: str,
) -> dict[str, object]:
    user_id = resolve_user_id(request, user_id)
    interview = await asyncio.to_thread(
        conversation_store.get_interview,
        user_id=user_id,
        interview_id=interview_id,
    )
    if not interview:
        raise HTTPException(status_code=404, detail="模拟面试不存在")
    turns = await asyncio.to_thread(
        conversation_store.get_interview_turns,
        user_id=user_id,
        interview_id=interview_id,
    )
    attempts = await asyncio.to_thread(
        conversation_store.get_interview_answer_attempts,
        user_id=user_id,
        interview_id=interview_id,
    )
    return {
        "interview": interview,
        "turns": turns,
        "attempts": attempts,
        "report": build_report(turns),
    }


@app.get("/api/capability-profile")
async def capability_profile(
    request: Request,
    user_id: str,
    topic: str | None = None,
) -> dict[str, object]:
    user_id = resolve_user_id(request, user_id)
    clean_topic = topic.strip() if topic else None
    if clean_topic and len(clean_topic) > 200:
        raise HTTPException(status_code=422, detail="topic 不合法")
    rows, profile = await asyncio.gather(
        asyncio.to_thread(
            conversation_store.get_capability_rows,
            user_id=user_id,
        ),
        asyncio.to_thread(
            conversation_store.get_user_profile,
            user_id=user_id,
        ),
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
            "high" if sample_count >= 10 else "medium" if sample_count >= 5 else "low"
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


@app.get("/api/learning-tasks")
async def list_learning_tasks(
    request: Request,
    user_id: str,
    status: Literal["todo", "in_progress", "completed"] | None = None,
) -> list[dict[str, object]]:
    user_id = resolve_user_id(request, user_id)
    return await asyncio.to_thread(
        conversation_store.list_learning_tasks,
        user_id=user_id,
        status=status,
    )


@app.post("/api/learning-tasks/generate")
async def generate_learning_tasks(
    request: Request,
    payload: LearningTaskGenerateRequest,
) -> dict[str, object]:
    user_id = resolve_user_id(request, payload.user_id)
    rows = await asyncio.to_thread(
        conversation_store.get_capability_rows,
        user_id=user_id,
    )
    profile = build_capability_profile(rows, topic=payload.topic)
    candidates = build_learning_candidates(profile)
    if not candidates:
        raise HTTPException(
            status_code=409,
            detail="暂无可生成学习任务的评分数据",
        )
    tasks = await asyncio.to_thread(
        conversation_store.create_learning_tasks,
        user_id=user_id,
        candidates=candidates,
    )
    return {
        "generated_from": {
            "topic": profile["filter"]["topic"],
            "answered_questions": profile["summary"]["answered_questions"],
        },
        "tasks": tasks,
    }


@app.patch("/api/learning-tasks/{task_id}")
async def update_learning_task(
    request: Request,
    task_id: str,
    payload: LearningTaskUpdateRequest,
) -> dict[str, object]:
    user_id = resolve_user_id(request, payload.user_id)
    if payload.status is None and payload.due_at is None:
        raise HTTPException(status_code=422, detail="没有需要更新的字段")
    task = await asyncio.to_thread(
        conversation_store.update_learning_task,
        user_id=user_id,
        task_id=task_id,
        status=payload.status,
        due_at=payload.due_at.isoformat() if payload.due_at else None,
    )
    if not task:
        raise HTTPException(status_code=404, detail="学习任务不存在")
    return task


@app.post("/api/learning-tasks/{task_id}/review")
async def review_learning_task(
    request: Request,
    task_id: str,
    payload: UserIdentityRequest,
) -> dict[str, object]:
    user_id = resolve_user_id(request, payload.user_id)
    task = await asyncio.to_thread(
        conversation_store.review_learning_task,
        user_id=user_id,
        task_id=task_id,
    )
    if not task:
        raise HTTPException(status_code=404, detail="学习任务不存在")
    return task


@app.delete("/api/learning-tasks/{task_id}")
async def delete_learning_task(
    request: Request,
    task_id: str,
    user_id: str,
) -> dict[str, bool]:
    user_id = resolve_user_id(request, user_id)
    deleted = await asyncio.to_thread(
        conversation_store.delete_learning_task,
        user_id=user_id,
        task_id=task_id,
    )
    return {"deleted": deleted}
