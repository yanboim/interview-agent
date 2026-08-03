"""提供给 Agent 的受控工具：执行鉴权、审计、安全检索和变更确认协议。"""

import json
import hashlib
import logging
import time
from functools import lru_cache

import httpx
from langchain.tools import tool

from app.agent_safety import (
    classify_public_search_query,
    content_fingerprint,
    safe_audit_summary,
)
from app.config import get_settings
from app.knowledge_search import _search_interview_knowledge as _search_knowledge
from app.learning_tools import (
    confirm_learning_plan,
    learning_plan_preview,
    learning_progress,
)
from app.lexical_reranker import lexical_rerank_documents
from app.llm_reranker import llm_rerank_documents
from app.rag import (
    get_dense_vector_store,
    get_serving_knowledge_target,
    get_vector_store,
)
from app.reranker import rerank_documents
from app.operations import RedisRuntime
from app.public_web_search import execute_public_web_search
from app.storage import ConversationStore
from app.tool_context import get_tool_identity

logger = logging.getLogger(__name__)


@lru_cache
def _get_tool_store() -> ConversationStore:
    settings = get_settings()
    return ConversationStore(
        settings.database_url or settings.conversation_db_path,
        auto_create_schema=settings.auto_create_schema,
    )


@lru_cache
def _get_redis_runtime() -> RedisRuntime:
    settings = get_settings()
    return RedisRuntime(settings.redis_url, settings.redis_queue_name)


def _run_audited(
    tool_name: str,
    input_metadata: dict[str, object],
    callback,
) -> str:
    identity = get_tool_identity()
    started = time.monotonic()
    status = "success"
    result_summary = safe_audit_summary({"outcome": "returned"})
    try:
        return str(callback())
    except Exception as exc:
        status = "error"
        result_summary = safe_audit_summary(
            {"outcome": "error", "error_type": type(exc).__name__}
        )
        raise
    finally:
        if identity.user_id != "anonymous":
            try:
                _get_tool_store().record_tool_audit(
                    user_id=identity.user_id,
                    role=identity.role,
                    tool_name=tool_name,
                    input_summary=safe_audit_summary(input_metadata),
                    status=status,
                    duration_ms=int(
                        (time.monotonic() - started) * 1000
                    ),
                    result_summary=result_summary,
                    request_id=identity.request_id or None,
                    interaction_type=identity.interaction_type or None,
                    interaction_id=identity.interaction_id or None,
                )
            except Exception:
                logger.warning("Tool audit write failed.", exc_info=True)


def _search_interview_knowledge(
    query: str, *, collection_name: str | None = None
) -> str:
    """Compatibility seam forwarding injected retrieval dependencies."""
    return _search_knowledge(
        query,
        collection_name=collection_name,
        settings_provider=get_settings,
        dense_store_provider=get_dense_vector_store,
        vector_store_provider=get_vector_store,
        cross_reranker=rerank_documents,
        llm_reranker=llm_rerank_documents,
        lexical_reranker=lexical_rerank_documents,
        sleep=time.sleep,
    )


@tool
def search_interview_knowledge(query: str) -> str:
    """查询私人面试知识库，返回带来源和检索分数的相关资料。"""
    settings = get_settings()
    runtime = _get_redis_runtime()
    try:
        _, knowledge_version = get_serving_knowledge_target()
    except Exception:
        logger.warning("Knowledge version resolution failed.", exc_info=True)
        knowledge_version = settings.qdrant_collection
    cache_key = (
        f"interview-agent:rag:{knowledge_version}:"
        + hashlib.sha256(query.strip().encode("utf-8")).hexdigest()
    )

    def execute() -> str:
        try:
            cached = runtime.get(cache_key)
        except Exception:
            cached = None
        if cached:
            return cached
        result = _search_interview_knowledge(
            query,
            collection_name=knowledge_version,
        )
        try:
            runtime.set(
                cache_key,
                result,
                settings.redis_cache_ttl_seconds,
            )
        except Exception:
            logger.warning("Redis RAG cache write failed.", exc_info=True)
        return result

    return _run_audited(
        "search_interview_knowledge",
        {
            "query_sha256": content_fingerprint(query),
            "query_length": len(query),
            "knowledge_version": str(knowledge_version)[:128],
        },
        execute,
    )


@tool
def get_learning_progress(topic: str = "") -> str:
    """查询当前用户的跨场次能力画像和学习任务进度，可按主题筛选。"""
    identity = get_tool_identity()

    def execute() -> str:
        return learning_progress(
            _get_tool_store(), user_id=identity.user_id, topic=topic
        )

    return _run_audited(
        "get_learning_progress",
        {
            "topic_sha256": content_fingerprint(topic),
            "topic_length": len(topic),
        },
        execute,
    )


@tool
def create_personal_learning_plan(topic: str = "") -> str:
    """预览私人学习计划；只返回待确认内容，不创建任务。"""
    identity = get_tool_identity()

    def execute() -> str:
        return learning_plan_preview(
            _get_tool_store(), user_id=identity.user_id, topic=topic
        )

    return _run_audited(
        "create_personal_learning_plan",
        {
            "topic_sha256": content_fingerprint(topic),
            "topic_length": len(topic),
        },
        execute,
    )


@tool
def confirm_personal_learning_plan(confirmation_id: str) -> str:
    """用户明确确认预览后，单次应用对应学习计划。"""
    identity = get_tool_identity()

    def execute() -> str:
        return confirm_learning_plan(
            _get_tool_store(),
            user_id=identity.user_id,
            confirmation_id=confirmation_id.strip(),
        )

    return _run_audited(
        "confirm_personal_learning_plan",
        {
            "confirmation_sha256": content_fingerprint(confirmation_id),
            "confirmation_length": len(confirmation_id),
        },
        execute,
    )


def _execute_public_web_search(clean_query: str, settings: object) -> str:
    return execute_public_web_search(clean_query, settings, post=httpx.post)


@tool
def search_public_web(query: str) -> str:
    """搜索公开互联网；含私人上下文的查询只生成待确认预览。"""
    settings = get_settings()
    identity = get_tool_identity()

    def execute() -> str:
        if not settings.web_search_enabled:
            return "联网搜索未启用。"
        if not settings.web_search_api_key:
            return "联网搜索已启用，但未配置 WEB_SEARCH_API_KEY。"
        clean_query, decision = classify_public_search_query(query)
        if decision == "confirmation":
            if identity.user_id == "anonymous":
                return "该联网查询可能包含私人上下文，请登录后预览并明确确认。"
            preview = _get_tool_store().create_public_search_preview(
                user_id=identity.user_id,
                query=clean_query,
            )
            return json.dumps(
                {
                    **preview,
                    "instruction": (
                        "尚未联网。请向用户展示完整查询；仅当用户在后续消息中"
                        "明确确认时，调用 confirm_public_web_search。"
                    ),
                },
                ensure_ascii=False,
            )
        return _execute_public_web_search(clean_query, settings)

    return _run_audited(
        "search_public_web",
        {
            "query_sha256": content_fingerprint(query),
            "query_length": len(query),
        },
        execute,
    )


@tool
def confirm_public_web_search(confirmation_id: str) -> str:
    """用户明确确认预览后，单次执行该用户对应的公开网络查询。"""
    settings = get_settings()
    identity = get_tool_identity()

    def execute() -> str:
        if not settings.web_search_enabled:
            return "联网搜索未启用。"
        if not settings.web_search_api_key:
            return "联网搜索已启用，但未配置 WEB_SEARCH_API_KEY。"
        if identity.user_id == "anonymous":
            return "请登录后确认联网查询。"
        clean_id = confirmation_id.strip()
        store = _get_tool_store()
        claim = store.claim_public_search_confirmation(
            user_id=identity.user_id,
            confirmation_id=clean_id,
        )
        if claim is None:
            return "未找到当前用户可确认的联网查询。"
        status = str(claim["status"])
        if status == "replay":
            return str(claim["result"])
        if status == "in_progress":
            return "该联网查询已确认并正在执行，请勿重复提交。"
        if status == "expired":
            return "该联网查询预览已过期，请重新生成预览。"
        if status == "cancelled":
            return "该联网查询上次执行失败或已取消，请重新生成预览。"
        if status != "claimed":
            return f"该联网查询当前状态为 {status}。"
        try:
            result = _execute_public_web_search(str(claim["query"]), settings)
        except Exception:
            store.cancel_public_search_confirmation(
                user_id=identity.user_id,
                confirmation_id=clean_id,
            )
            raise
        store.complete_public_search_confirmation(
            user_id=identity.user_id,
            confirmation_id=clean_id,
            result=result,
        )
        return result

    return _run_audited(
        "confirm_public_web_search",
        {
            "confirmation_sha256": content_fingerprint(confirmation_id),
            "confirmation_length": len(confirmation_id),
        },
        execute,
    )
