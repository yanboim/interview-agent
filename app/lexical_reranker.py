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
    """提取查询/正文中的词法单元集合，用于离线词法相关性计算。

    ASCII 词作为整体单元；CJK 连续串按二元（bigram）切分，模拟无分词
    器时的中文匹配。常见提问噪声词（「什么/如何」等）被剔除，避免它们
    干扰覆盖度计算。

    返回:
        小写化后的词法单元集合。
    """
    normalized = text.lower()
    units = set(_ASCII_TOKEN.findall(normalized))
    for run in _CJK_RUN.findall(normalized):
        units.update(
            run[index : index + 2]
            for index in range(max(0, len(run) - 1))
        )
    return units - _QUESTION_NOISE


def lexical_relevance(query: str, content: str) -> float:
    """计算查询与正文的词法相关性得分（无模型、离线）。

    综合「正文覆盖度」与「首行（标题）覆盖度」，给标题更重权重，因为
    标题命中通常意味着主题精确匹配。

    参数:
        query: 用户查询。
        content: 候选文档正文。

    返回:
        ``0.65 * 正文覆盖度 + 0.35 * 标题覆盖度``，落在 ``[0, 1]``。
        查询无可识别单元时返回 ``0.0``。
    """
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
    """用「检索分数 + 查询覆盖度」对候选重排，无需外部模型。

    把稠密检索分数与 ``lexical_relevance`` 的词法覆盖度按权重线性组合，
    修正纯向量召回可能出现的「语义相近但主题不同」排序问题。

    参数:
        query: 用户查询。
        candidates: ``(文档, 原始检索分数)`` 候选序列。
        retrieval_weight: 检索分数权重，余下权重分配给词法分数。

    返回:
        ``(文档, 组合分数, 原始检索分数, 词法分数)`` 四元组列表，
        按组合分数降序。
    """
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
