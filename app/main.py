"""FastAPI 组合根：装配进程依赖、安装中间件与静态路由，保留旧调用方兼容别名。"""

import asyncio
import logging
import secrets
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from qdrant_client import QdrantClient

from app.agent import get_single_interview_agent
from app.api.agent_io import extract_message_text, extract_sources
from app.api.execution import run_sync
from app.api.errors import unavailable_http_error
from app.api.routers import admin as admin_routes
from app.api.routers import auth as auth_routes
from app.api.routers import chat as chat_routes
from app.api.routers import conversations as conversation_routes
from app.api.routers import interviews as interview_routes
from app.api.routers import interview_reviews as interview_review_routes
from app.api.routers import learning as learning_routes
from app.api.routers import profile as profile_routes
from app.api.routers import resumes as resume_routes
from app.api.runtime import ApiRuntime, configure_runtime
from app.api.security_policy import deployment_api_key_required
from app.api.schemas import *  # noqa: F403 - compatibility exports
from app.api.security import require_role, resolve_user_id, token_pair_response
from app.application.chat_service import ChatTurnService
from app.application.chat_use_case import ChatUseCase
from app.chat_agent_executor import RoutedChatAgentExecutor
from app.application.agent_run_service import AgentRunService
from app.agent_context_service import AgentContextService
from app.application.execution import SyncExecutor
from app.application.interview_service import (
    InterviewAnswerService,
    InterviewStartService,
)
from app.interview_engine import get_interview_capabilities
from app.application.interview_review_service import InterviewReviewService
from app.application.resume_service import ResumeService
from app.auth import AuthService, AuthSurfaceError
from app.config import get_settings
from app.knowledge_publication import (
    knowledge_status,
    require_serving_knowledge,
    resolve_serving_knowledge,
    rollback_knowledge,
)
from app.knowledge_ingestion import ingest_knowledge
from app.logging_config import configure_logging, reset_request_id, set_request_id
from app.multi_agent import assess_answer, generate_question
from app.model_routing import model_for_purpose
from app.operations import RedisRuntime, SharedRateLimiter, request_metrics
from app.request_audit import audit_api_request
from app.storage import ConversationStore
from app.system_resources import create_system_resource_center
from app.transcription import HttpTranscriptionProvider
from app.telemetry import configure_telemetry
from app.user_files import LocalUserFileStore

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI 面试教练 Agent",
    description="基于 LangChain、LangGraph 和 Qdrant 的面试智能体",
    version="0.1.0",
)

WEB_DIRECTORY = Path(__file__).parent / "web"
settings = get_settings()
_dist_candidate = Path(settings.frontend_dist or Path(__file__).parent.parent / "frontend" / "dist")
FRONTEND_DIST = _dist_candidate if (_dist_candidate / "index.html").exists() else None
STATIC_DIRECTORY = FRONTEND_DIST if FRONTEND_DIST else WEB_DIRECTORY
app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY, check_dir=False), name="static")
configure_logging(settings.log_level, settings.json_logs)
conversation_store = ConversationStore(
    settings.database_url or settings.conversation_db_path,
    auto_create_schema=settings.auto_create_schema,
)
interview_capabilities = get_interview_capabilities()
interview_answer_service = InterviewAnswerService(
    conversation_store,
    capabilities=interview_capabilities,
    assessment_prompt_version=settings.interview_assessment_prompt_version,
    assessment_schema_version="assessment-v1",
    model_version=model_for_purpose(settings, "evaluator"),
)
interview_start_service = InterviewStartService(
    conversation_store,
    capabilities=interview_capabilities,
    prompt_version=settings.interview_question_prompt_version,
    schema_version="question-text-v1",
    model_version=model_for_purpose(settings, "interviewer"),
)
chat_turn_service = ChatTurnService(
    conversation_store,
    context_token_budget=settings.chat_context_token_budget,
    summary_token_budget=settings.chat_summary_token_budget,
    context_service=AgentContextService(
        conversation_store,
        token_budget=settings.agent_context_reserve_tokens,
    ),
    agent_context_reserve_tokens=settings.agent_context_reserve_tokens,
)
chat_agent_executor = RoutedChatAgentExecutor(
    settings, lambda: get_single_interview_agent()
)
sync_executor = SyncExecutor()
chat_use_case = ChatUseCase(
    turn_service=chat_turn_service, agent_executor=chat_agent_executor,
    sync_executor=sync_executor, trace_repository=conversation_store,
    metrics=request_metrics, settings=settings,
)
agent_run_service = AgentRunService(conversation_store)
auth_service = AuthService(
    conversation_store.engine,
    access_token_minutes=settings.access_token_minutes,
    refresh_token_days=settings.refresh_token_days,
)
redis_runtime = RedisRuntime(settings.redis_url, settings.redis_queue_name)
user_files = LocalUserFileStore(
    settings.user_files_dir,
    max_upload_bytes=settings.resume_max_upload_bytes,
)
resume_service = ResumeService(
    conversation_store,
    user_files,
    settings,
    enqueue=redis_runtime.enqueue,
)
interview_review_service = InterviewReviewService(
    conversation_store,
    user_files,
    settings,
    enqueue=redis_runtime.enqueue,
    transcription_provider=HttpTranscriptionProvider(settings),
)
system_resource_center = create_system_resource_center(
    settings,
    database_check=conversation_store.check_connection,
    redis_check=redis_runtime.check,
    redis_enabled=bool(redis_runtime.client),
    worker_check=lambda: redis_runtime.check_worker_heartbeat(
        max_age_seconds=max(3, settings.worker_heartbeat_ttl_seconds)
    ),
    qdrant_check=require_serving_knowledge,
)
rate_limiter = SharedRateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds, redis_runtime)
runtime = ApiRuntime(
    settings=settings,
    conversation_store=conversation_store,
    auth_service=auth_service,
    redis_runtime=redis_runtime,
    rate_limiter=rate_limiter,
    chat_use_case=chat_use_case,
    agent_run_service=agent_run_service,
    interview_answer_service=interview_answer_service,
    interview_start_service=interview_start_service,
    interview_review_service=interview_review_service,
    resume_service=resume_service,
    sync_executor=sync_executor,
    generate_question=generate_question,
    assess_answer=assess_answer,
    ingest_knowledge=ingest_knowledge,
    knowledge_status=knowledge_status,
    rollback_knowledge=rollback_knowledge,
    require_serving_knowledge=require_serving_knowledge,
    system_resource_center=system_resource_center,
)
configure_runtime(runtime)
for router in (
    auth_routes.router,
    profile_routes.router,
    admin_routes.router,
    chat_routes.router,
    conversation_routes.router,
    interview_routes.router,
    interview_review_routes.router,
    learning_routes.router,
    resume_routes.router,
):
    app.include_router(router)

configure_telemetry(
    app,
    conversation_store.engine,
    enabled=settings.otel_enabled,
    service_name=settings.otel_service_name,
    endpoint=settings.otel_exporter_otlp_endpoint,
)


@app.middleware("http")
async def operational_controls(request: Request, call_next):
    """运营控制中间件：API Key、会话鉴权、限流，并在结束时审计请求并记录指标。"""
    started_at = request_metrics.start()
    status_code = 500
    try:
        deployment_key_protected = deployment_api_key_required(request.url.path)
        if deployment_key_protected and settings.app_api_key:
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
            await run_sync(conversation_store.initialize)
            current_user = await run_sync(
                auth_service.resolve_access_token, access_token
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
        await audit_api_request(
            request,
            status_code=status_code,
            started_at=started_at,
            settings=settings,
            store=conversation_store,
            execute=run_sync,
        )
        request_metrics.finish(started_at, status_code)


@app.middleware("http")
async def request_context_and_security(request: Request, call_next):
    """请求上下文与安全头中间件：生成/透传 request_id 并统一注入安全响应头。"""
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
            "default-src 'self'; style-src 'self' 'unsafe-inline' "
            "https://fonts.googleapis.com; font-src 'self' "
            "https://fonts.gstatic.com; img-src 'self' data:; "
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


def _resolve_index_html() -> Path:
    """解析前端入口 index.html（优先 Vue 构建产物，回退旧静态页）。"""
    if FRONTEND_DIST:
        return FRONTEND_DIST / "index.html"
    return WEB_DIRECTORY / "index.html"


@app.get("/", include_in_schema=False)
async def web_app() -> FileResponse:
    return FileResponse(_resolve_index_html())


@app.get("/admin", include_in_schema=False)
async def admin_web_app() -> FileResponse:
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
@app.get("/resumes", include_in_schema=False)
@app.get("/resumes/{resume_id}", include_in_schema=False)
@app.get("/reviews", include_in_schema=False)
@app.get("/reviews/{review_id}", include_in_schema=False)
async def main_web_app(
    session_id: str | None = None, interview_id: str | None = None,
    resume_id: str | None = None, review_id: str | None = None,
) -> FileResponse:
    return FileResponse(_resolve_index_html())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def readiness() -> dict[str, str]:
    try:
        with request_metrics.dependency("database"):
            await run_sync(conversation_store.check_connection)
        with request_metrics.dependency("qdrant"):
            client = QdrantClient(
                url=settings.qdrant_url,
                timeout=5,
                check_compatibility=False,
            )
            serving = await run_sync(
                resolve_serving_knowledge, client, settings
            )
        if not serving:
            raise RuntimeError("Qdrant collection 不存在")
        if redis_runtime.client:
            with request_metrics.dependency("redis"):
                await run_sync(redis_runtime.check)
    except Exception as exc:
        logger.exception("Readiness dependency check failed")
        raise unavailable_http_error(dependency="应用依赖") from exc
    return {"status": "ready"}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    return request_metrics.render_prometheus()
# 旧调用方/测试直接从 app.main 导入函数名的兼容别名；新代码请从各 router 导入。
# 下列 async 别名在转交前先把运行时回调/服务复位，确保测试中的替换不会被绕过。
register, login, admin_login = auth_routes.register, auth_routes.login, auth_routes.admin_login
admin_knowledge_files = admin_routes.admin_knowledge_files
admin_save_knowledge_file = admin_routes.admin_save_knowledge_file
admin_delete_knowledge_file = admin_routes.admin_delete_knowledge_file
async def admin_import_knowledge(request: Request) -> dict[str, object]:
    runtime.ingest_knowledge = ingest_knowledge
    return await admin_routes.admin_import_knowledge(request)
async def admin_knowledge_status(request: Request) -> dict[str, object]:
    runtime.knowledge_status = knowledge_status
    return await admin_routes.admin_knowledge_status(request)
async def admin_knowledge_rollback(payload, request: Request) -> dict[str, object]:
    runtime.rollback_knowledge = rollback_knowledge
    return await admin_routes.admin_knowledge_rollback(payload, request)
async def chat(request, http_request: Request, idempotency_key: str):
    runtime.chat_use_case.turn_service = chat_turn_service
    return await chat_routes.chat(request, http_request, idempotency_key)
async def chat_stream(request, http_request: Request, idempotency_key: str):
    runtime.chat_use_case.turn_service = chat_turn_service
    return await chat_routes.chat_stream(request, http_request, idempotency_key)
async def answer_interview(interview_id, request, http_request, idempotency_key):
    runtime.interview_answer_service = interview_answer_service
    return await interview_routes.answer_interview(
        interview_id, request, http_request, idempotency_key
    )
