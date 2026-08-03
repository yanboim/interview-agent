"""RAG 检索评测能力；命令脚本和知识发布流程共享此实现。"""

import json
from pathlib import Path
from typing import Any

from app.evaluation import hit_at_k, ndcg_at_k, reciprocal_rank
from app.lexical_reranker import lexical_rerank_documents
from app.llm_reranker import llm_rerank_documents
from app.rag import get_vector_store
from app.reranker import rerank_documents


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def evaluate(
    cases: list[dict[str, Any]],
    *,
    k: int,
    rerank: bool,
    lexical_rerank: bool,
    llm_rerank: bool,
    collection_name: str | None = None,
) -> dict[str, Any]:
    store = get_vector_store(collection_name)
    details: list[dict[str, Any]] = []
    hits = 0
    top1_hits = 0
    reciprocal_rank_sum = 0.0
    ndcg_sum = 0.0

    for case in cases:
        relevant = set(case["relevant_chunk_ids"])
        candidate_k = max(k, 20 if rerank or lexical_rerank or llm_rerank else k)
        candidates = store.similarity_search_with_score(case["question"], k=candidate_k)

        if rerank:
            reranked = rerank_documents(case["question"], candidates)
            ranked = [
                {
                    "chunk_id": document.metadata.get("chunk_id", ""),
                    "source": document.metadata.get("filename", ""),
                    "score": rerank_score,
                    "retrieval_score": retrieval_score,
                }
                for document, rerank_score, retrieval_score in reranked[:k]
            ]
        elif llm_rerank:
            reranked = llm_rerank_documents(case["question"], candidates)
            ranked = [
                {
                    "chunk_id": document.metadata.get("chunk_id", ""),
                    "source": document.metadata.get("filename", ""),
                    "score": rerank_score,
                    "retrieval_score": retrieval_score,
                }
                for document, rerank_score, retrieval_score in reranked[:k]
            ]
        elif lexical_rerank:
            reranked = lexical_rerank_documents(case["question"], candidates)
            ranked = [
                {
                    "chunk_id": document.metadata.get("chunk_id", ""),
                    "source": document.metadata.get("filename", ""),
                    "score": combined_score,
                    "retrieval_score": retrieval_score,
                    "lexical_score": lexical_score,
                }
                for document, combined_score, retrieval_score, lexical_score in reranked[:k]
            ]
        else:
            ranked = [
                {
                    "chunk_id": document.metadata.get("chunk_id", ""),
                    "source": document.metadata.get("filename", ""),
                    "score": score,
                }
                for document, score in candidates[:k]
            ]

        chunk_ids = [item["chunk_id"] for item in ranked]
        rank = next(
            (
                index
                for index, chunk_id in enumerate(chunk_ids, start=1)
                if chunk_id in relevant
            ),
            None,
        )
        hit = hit_at_k(chunk_ids, relevant)
        rr = reciprocal_rank(chunk_ids, relevant)
        hits += int(hit)
        top1_hits += int(rank == 1)
        reciprocal_rank_sum += rr
        ndcg_sum += ndcg_at_k(chunk_ids, relevant, k)
        details.append(
            {
                "question": case["question"],
                "expected_source": case.get("expected_source"),
                "relevant_chunk_ids": sorted(relevant),
                "rank": rank,
                "hit": hit,
                "retrieved": ranked,
            }
        )

    count = len(cases)
    return {
        "summary": {
            "cases": count,
            "k": k,
            "top1_accuracy": top1_hits / count if count else 0.0,
            f"hit_rate@{k}": hits / count if count else 0.0,
            "mrr": reciprocal_rank_sum / count if count else 0.0,
            f"ndcg@{k}": ndcg_sum / count if count else 0.0,
            "rerank": rerank,
            "lexical_rerank": lexical_rerank,
            "llm_rerank": llm_rerank,
        },
        "details": details,
    }
