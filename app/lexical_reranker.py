"""不访问外部服务的词法重排器，用查询词覆盖度修正向量召回顺序。"""

import re
from collections.abc import Sequence

from langchain_core.documents import Document


_ASCII_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z0-9_.+#-]*")
_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")
_QUESTION_NOISE = {
    "什么",
    "如何",
    "怎么",
    "哪些",
    "为何",
    "为什么",
    "是否",
    "应该",
}


def lexical_units(text: str) -> set[str]:
    normalized = text.lower()
    units = set(_ASCII_TOKEN.findall(normalized))
    for run in _CJK_RUN.findall(normalized):
        units.update(
            run[index : index + 2]
            for index in range(max(0, len(run) - 1))
        )
    return units - _QUESTION_NOISE


def lexical_relevance(query: str, content: str) -> float:
    query_units = lexical_units(query)
    if not query_units:
        return 0.0

    content_units = lexical_units(content)
    first_line = next(
        (line for line in content.splitlines() if line.strip()),
        "",
    )
    heading_units = lexical_units(first_line[:240])
    body_coverage = len(query_units & content_units) / len(query_units)
    heading_coverage = len(query_units & heading_units) / len(query_units)
    return 0.65 * body_coverage + 0.35 * heading_coverage


def lexical_rerank_documents(
    query: str,
    candidates: Sequence[tuple[Document, float]],
    *,
    retrieval_weight: float = 0.35,
) -> list[tuple[Document, float, float, float]]:
    """Rerank using retrieval score plus query coverage in body and heading."""
    ranked = []
    for document, retrieval_score in candidates:
        lexical_score = lexical_relevance(query, document.page_content)
        combined_score = (
            retrieval_weight * retrieval_score
            + (1.0 - retrieval_weight) * lexical_score
        )
        ranked.append(
            (document, combined_score, retrieval_score, lexical_score)
        )
    return sorted(ranked, key=lambda item: item[1], reverse=True)
