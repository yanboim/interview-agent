import json
import hashlib
import logging
import re
import time
from datetime import UTC, datetime
from functools import lru_cache
from urllib.parse import urlparse

import httpx
from langchain.tools import tool

from app.capability import build_capability_profile
from app.config import get_settings
from app.learning import build_learning_candidates
from app.lexical_reranker import lexical_rerank_documents
from app.llm_reranker import llm_rerank_documents
from app.rag import (
    get_dense_vector_store,
    get_serving_knowledge_target,
    get_vector_store,
)
from app.reranker import rerank_documents
from app.operations import RedisRuntime, request_metrics
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


def _run_audited(tool_name: str, input_summary: str, callback) -> str:
    identity = get_tool_identity()
    started = time.monotonic()
    status = "success"
    result = ""
    try:
        result = str(callback())
        return result
    except Exception as exc:
        status = "error"
        result = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if identity.user_id != "anonymous":
            try:
                _get_tool_store().record_tool_audit(
                    user_id=identity.user_id,
                    role=identity.role,
                    tool_name=tool_name,
                    input_summary=input_summary,
                    status=status,
                    duration_ms=int(
                        (time.monotonic() - started) * 1000
                    ),
                    result_summary=result,
                    request_id=identity.request_id or None,
                    interaction_type=identity.interaction_type or None,
                    interaction_id=identity.interaction_id or None,
                )
            except Exception:
                logger.warning("Tool audit write failed.", exc_info=True)


def _search_interview_knowledge(
    query: str,
    *,
    collection_name: str | None = None,
) -> str:
    query = query.strip()
    if not query:
        return "查询内容不能为空。"

    last_error: Exception | None = None
    scored_documents = []
    for attempt in range(1, 3):
        try:
            settings = get_settings()
            with request_metrics.dependency("embedding_qdrant"):
                dense_results = (
                    get_dense_vector_store(
                        collection_name
                    ).similarity_search_with_score(
                        query=query,
                        k=1,
                    )
                )
            if (
                not dense_results
                or dense_results[0][1] < settings.dense_relevance_min_score
            ):
                return "知识库中没有达到语义相关度阈值的资料。"

            with request_metrics.dependency("embedding_qdrant"):
                scored_documents = (
                    get_vector_store(collection_name).similarity_search_with_score(
                        query=query,
                        k=settings.retrieval_candidate_k,
                        score_threshold=(
                            settings.retrieval_min_score
                            if settings.retrieval_min_score > 0
                            else None
                        ),
                    )
                )
            break
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Knowledge retrieval attempt %s failed for query length %s",
                attempt,
                len(query),
                exc_info=True,
            )
            get_vector_store.cache_clear()
            get_dense_vector_store.cache_clear()
            if attempt == 1:
                time.sleep(0.5)

    if last_error is not None and not scored_documents:
        return (
            f"知识库查询失败（{type(last_error).__name__}）。"
            "请明确告知用户本次未使用私人知识库。"
        )

    if not scored_documents:
        return "知识库中没有检索到相关内容。"

    settings = get_settings()
    if settings.reranker_enabled:
        reranked_documents = rerank_documents(query, scored_documents)
        score_type = "cross_encoder"
    elif settings.llm_reranker_enabled:
        try:
            reranked_documents = llm_rerank_documents(
                query,
                scored_documents,
            )
            score_type = "llm"
        except Exception:
            logger.warning("GLM reranking failed; using retrieval order.", exc_info=True)
            reranked_documents = [
                (document, score, score)
                for document, score in scored_documents
            ]
            score_type = "retrieval"
    elif settings.lexical_reranker_enabled:
        lexical_documents = lexical_rerank_documents(
            query,
            scored_documents,
            retrieval_weight=settings.lexical_retrieval_weight,
        )
        reranked_documents = [
            (document, combined_score, retrieval_score)
            for document, combined_score, retrieval_score, _ in lexical_documents
        ]
        score_type = "lexical"
    else:
        reranked_documents = [
            (document, score, score)
            for document, score in scored_documents
        ]
        score_type = "retrieval"

    relevant_documents = [
        item
        for item in reranked_documents
        if item[1] >= settings.reranker_min_score
    ]
    if not relevant_documents:
        return "知识库中没有达到相关度阈值的资料。"

    results = []
    final_documents = relevant_documents[: settings.retrieval_final_k]
    for index, (document, reranker_score, retrieval_score) in enumerate(
        final_documents,
        start=1,
    ):
        source = document.metadata.get("source", "未知来源")
        score_lines = f"RRF 分数：{retrieval_score:.4f}\n"
        if score_type == "cross_encoder":
            score_lines += f"重排分数：{reranker_score:.4f}\n"
        elif score_type == "llm":
            score_lines += f"GLM 重排分数：{reranker_score:.4f}\n"
        elif score_type == "lexical":
            score_lines += f"轻量重排分数：{reranker_score:.4f}\n"
        results.append(
            f"[资料 {index}]\n"
            f"来源：{source}\n"
            f"{score_lines}"
            f"内容：{document.page_content.strip()}"
        )
    return "\n\n".join(results)


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
        query[:500],
        execute,
    )


@tool
def get_learning_progress(topic: str = "") -> str:
    """查询当前用户的跨场次能力画像和学习任务进度，可按主题筛选。"""
    identity = get_tool_identity()

    def execute() -> str:
        store = _get_tool_store()
        rows = store.get_capability_rows(user_id=identity.user_id)
        profile = build_capability_profile(rows, topic=topic or None)
        tasks = store.list_learning_tasks(user_id=identity.user_id)
        task_counts = {
            status: sum(1 for item in tasks if item["status"] == status)
            for status in ("todo", "in_progress", "completed")
        }
        return json.dumps(
            {
                "summary": profile["summary"],
                "dimension_scores": profile["dimension_scores"],
                "weaknesses": profile["weaknesses"][:5],
                "learning_tasks": task_counts,
            },
            ensure_ascii=False,
        )

    return _run_audited("get_learning_progress", topic[:200], execute)


@tool
def create_personal_learning_plan(topic: str = "") -> str:
    """根据当前用户的能力画像生成去重后的私人学习任务。"""
    identity = get_tool_identity()

    def execute() -> str:
        store = _get_tool_store()
        rows = store.get_capability_rows(user_id=identity.user_id)
        profile = build_capability_profile(rows, topic=topic or None)
        candidates = build_learning_candidates(profile)
        if not candidates:
            return "暂无足够的面试评分，无法生成学习计划。"
        tasks = store.create_learning_tasks(
            user_id=identity.user_id,
            candidates=candidates,
        )
        return json.dumps(
            {
                "task_count": len(tasks),
                "tasks": [
                    {
                        "dimension": item["dimension"],
                        "weakness": item["weakness"],
                        "status": item["status"],
                        "due_at": item["due_at"],
                    }
                    for item in tasks
                ],
            },
            ensure_ascii=False,
        )

    return _run_audited(
        "create_personal_learning_plan",
        topic[:200],
        execute,
    )


def _safe_web_query(query: str) -> str:
    clean_query = " ".join(query.split())
    if not clean_query:
        raise ValueError("联网搜索内容不能为空")
    if len(clean_query) > 500:
        raise ValueError("联网搜索内容过长")
    secret_patterns = (
        r"\bsk-[A-Za-z0-9_-]{12,}\b",
        r"\bBearer\s+[A-Za-z0-9._-]{12,}\b",
        r"\b[A-Fa-f0-9]{32,}\b",
    )
    if any(re.search(pattern, clean_query) for pattern in secret_patterns):
        raise ValueError("查询疑似包含密钥或令牌，已阻止外发")
    return clean_query


@tool
def search_public_web(query: str) -> str:
    """搜索公开互联网资料。仅用于需要最新信息且私人知识库不足的情况。"""
    settings = get_settings()

    def execute() -> str:
        if not settings.web_search_enabled:
            return "联网搜索未启用。"
        if not settings.web_search_api_key:
            return "联网搜索已启用，但未配置 WEB_SEARCH_API_KEY。"
        clean_query = _safe_web_query(query)
        response = httpx.post(
            settings.web_search_api_url,
            json={
                "api_key": settings.web_search_api_key,
                "query": clean_query,
                "max_results": settings.web_search_max_results,
                "search_depth": "advanced",
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout=settings.web_search_timeout_seconds,
        )
        response.raise_for_status()
        fetched_at = datetime.now(UTC).isoformat()
        results = []
        for item in response.json().get("results", []):
            url = str(item.get("url", "")).strip()
            if urlparse(url).scheme not in {"http", "https"}:
                continue
            results.append(
                {
                    "title": str(item.get("title", "")).strip(),
                    "url": url,
                    "snippet": str(item.get("content", "")).strip()[:1200],
                    "fetched_at": fetched_at,
                }
            )
        if not results:
            return "公开网络未返回可引用结果。"
        return "\n\n".join(
            f"[网络来源 {index}]\n标题：{item['title']}\n"
            f"链接：{item['url']}\n抓取时间：{item['fetched_at']}\n"
            f"摘要：{item['snippet']}"
            for index, item in enumerate(results, start=1)
        )

    return _run_audited("search_public_web", query[:500], execute)
