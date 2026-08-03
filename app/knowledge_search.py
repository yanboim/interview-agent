"""Private knowledge retrieval and reranking capability."""

import logging
import time

from app.agent_safety import wrap_untrusted_evidence
from app.chunks import stable_chunk_id
from app.config import get_settings
from app.lexical_reranker import lexical_rerank_documents
from app.llm_reranker import llm_rerank_documents
from app.operations import request_metrics
from app.rag import get_dense_vector_store, get_vector_store
from app.reranker import rerank_documents

logger = logging.getLogger(__name__)

def _search_interview_knowledge(
    query: str,
    *,
    collection_name: str | None = None,
    settings_provider=get_settings,
    dense_store_provider=get_dense_vector_store,
    vector_store_provider=get_vector_store,
    cross_reranker=rerank_documents,
    llm_reranker=llm_rerank_documents,
    lexical_reranker=lexical_rerank_documents,
    sleep=time.sleep,
) -> str:
    query = query.strip()
    if not query:
        return "查询内容不能为空。"

    last_error: Exception | None = None
    scored_documents = []
    for attempt in range(1, 3):
        try:
            settings = settings_provider()
            with request_metrics.dependency("embedding_qdrant"):
                dense_results = (
                    dense_store_provider(
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
                    vector_store_provider(collection_name).similarity_search_with_score(
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
            vector_store_provider.cache_clear()
            dense_store_provider.cache_clear()
            if attempt == 1:
                sleep(0.5)

    if last_error is not None and not scored_documents:
        return (
            f"知识库查询失败（{type(last_error).__name__}）。"
            "请明确告知用户本次未使用私人知识库。"
        )

    if not scored_documents:
        return "知识库中没有检索到相关内容。"

    settings = settings_provider()
    if settings.reranker_enabled:
        reranked_documents = cross_reranker(query, scored_documents)
        score_type = "cross_encoder"
    elif settings.llm_reranker_enabled:
        try:
            reranked_documents = llm_reranker(
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
        lexical_documents = lexical_reranker(
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
        evidence_id = str(
            document.metadata.get("chunk_id")
            or stable_chunk_id(str(source), document.page_content)
        )
        score_lines = f"RRF 分数：{retrieval_score:.4f}\n"
        if score_type == "cross_encoder":
            score_lines += f"重排分数：{reranker_score:.4f}\n"
        elif score_type == "llm":
            score_lines += f"GLM 重排分数：{reranker_score:.4f}\n"
        elif score_type == "lexical":
            score_lines += f"轻量重排分数：{reranker_score:.4f}\n"
        evidence = (
            f"[资料 {index}]\n"
            f"证据ID：{evidence_id}\n"
            f"来源：{source}\n"
            f"{score_lines}"
            f"内容：{document.page_content.strip()}"
        )
        results.append(
            wrap_untrusted_evidence(
                evidence,
                evidence_type="private_knowledge",
                evidence_id=evidence_id,
            )
        )
    return "\n\n".join(results)
