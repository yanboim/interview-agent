import argparse
import json
from pathlib import Path

from app.evaluation import hit_at_k, reciprocal_rank
from app.config import get_settings
from app.rag import get_dense_vector_store, get_vector_store
from app.reranker import rerank_documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval quality.")
    parser.add_argument("--dataset", type=Path, default=Path("eval/questions.jsonl"))
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument(
        "--dense-threshold",
        type=float,
        default=get_settings().dense_relevance_min_score,
    )
    args = parser.parse_args()

    cases = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    store = get_vector_store()
    dense_store = get_dense_vector_store()
    positive_hits = 0
    reciprocal_rank_sum = 0.0
    positive_count = 0
    negative_count = 0
    false_rejections = 0
    false_acceptances = 0

    for case in cases:
        relevant = set(case["relevant_sources"])
        dense_results = dense_store.similarity_search_with_score(
            case["question"],
            k=1,
        )
        dense_score = dense_results[0][1] if dense_results else 0.0
        accepted = dense_score >= args.dense_threshold
        candidates = store.similarity_search_with_score(
            case["question"],
            k=max(args.k, 20 if args.rerank else args.k),
        )
        if args.rerank:
            ranked = rerank_documents(case["question"], candidates)
            sources = [
                document.metadata.get("filename", "")
                for document, _, _ in ranked[: args.k]
            ]
            top_score = ranked[0][1] if ranked else None
        else:
            sources = [
                document.metadata.get("filename", "")
                for document, _ in candidates[: args.k]
            ]
            top_score = candidates[0][1] if candidates else None

        if relevant:
            positive_count += 1
            false_rejections += int(not accepted)
            positive_hits += int(hit_at_k(sources, relevant))
            reciprocal_rank_sum += reciprocal_rank(sources, relevant)
        else:
            negative_count += 1
            false_acceptances += int(accepted)

        label = "positive" if relevant else "negative"
        print(
            json.dumps(
                {
                    "label": label,
                    "question": case["question"],
                    "dense_score": dense_score,
                    "accepted": accepted,
                    "top_score": top_score,
                    "sources": sources,
                },
                ensure_ascii=False,
            )
        )

    print(
        json.dumps(
            {
                "cases": len(cases),
                "positive_cases": positive_count,
                "negative_cases": negative_count,
                f"hit_rate@{args.k}": (
                    positive_hits / positive_count if positive_count else 0
                ),
                "mrr": (
                    reciprocal_rank_sum / positive_count
                    if positive_count
                    else 0
                ),
                "dense_threshold": args.dense_threshold,
                "false_rejection_rate": (
                    false_rejections / positive_count
                    if positive_count
                    else 0
                ),
                "false_acceptance_rate": (
                    false_acceptances / negative_count
                    if negative_count
                    else 0
                ),
                "gate_accuracy": (
                    1
                    - (false_rejections + false_acceptances) / len(cases)
                    if cases
                    else 0
                ),
                "rerank": args.rerank,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
