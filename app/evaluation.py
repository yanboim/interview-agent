from collections.abc import Sequence
from math import log2


def reciprocal_rank(
    retrieved_sources: Sequence[str],
    relevant_sources: set[str],
) -> float:
    for rank, source in enumerate(retrieved_sources, start=1):
        if source in relevant_sources:
            return 1.0 / rank
    return 0.0


def hit_at_k(
    retrieved_sources: Sequence[str],
    relevant_sources: set[str],
) -> bool:
    return any(source in relevant_sources for source in retrieved_sources)


def ndcg_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str],
    k: int,
) -> float:
    gains = [
        1.0 if item in relevant_ids else 0.0
        for item in retrieved_ids[:k]
    ]
    dcg = sum(
        gain / log2(rank + 1)
        for rank, gain in enumerate(gains, start=1)
    )
    ideal_hits = min(len(relevant_ids), k)
    ideal_dcg = sum(
        1.0 / log2(rank + 1)
        for rank in range(1, ideal_hits + 1)
    )
    return dcg / ideal_dcg if ideal_dcg else 0.0


def citation_scores(
    citations: Sequence[str],
    relevant_sources: set[str],
) -> dict[str, float]:
    cited = set(citations)
    correct = len(cited & relevant_sources)
    return {
        "citation_precision": correct / len(cited) if cited else 0.0,
        "citation_recall": (
            correct / len(relevant_sources) if relevant_sources else 1.0
        ),
    }


def claim_support_rate(supported_claims: Sequence[bool]) -> float:
    if not supported_claims:
        return 0.0
    return sum(bool(value) for value in supported_claims) / len(
        supported_claims
    )
