"""Agent/RAG 评估指标与报告聚合纯函数，供脚本和测试共同复用。"""

from collections.abc import Sequence
from math import log2


def reciprocal_rank(
    retrieved_sources: Sequence[str],
    relevant_sources: set[str],
) -> float:
    """计算首个相关结果位置的倒数排名（RR）。

    用于衡量检索/重排把正确来源提前的能力；越靠前得分越高，相关结果
    出现在第 ``rank`` 位时得 ``1/rank``。

    参数:
        retrieved_sources: 按预测相关性排序后返回的来源标识序列。
        relevant_sources: 该问题的标注正确来源集合。

    返回:
        首个相关来源的倒数排名；没有任何相关来源命中时返回 ``0.0``。
    """
    for rank, source in enumerate(retrieved_sources, start=1):
        if source in relevant_sources:
            return 1.0 / rank
    return 0.0


def hit_at_k(
    retrieved_sources: Sequence[str],
    relevant_sources: set[str],
) -> bool:
    """判断检索结果中是否至少命中一个正确来源。

    作为召回能力的二值指标，常与 ``ndcg_at_k`` 配合评估检索质量。

    参数:
        retrieved_sources: 检索返回的来源标识序列。
        relevant_sources: 标注正确来源集合。

    返回:
        任一返回来源属于正确集合时为 ``True``，否则 ``False``。
    """
    return any(source in relevant_sources for source in retrieved_sources)


def ndcg_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str],
    k: int,
) -> float:
    """计算前 ``k`` 位的归一化折损累计增益（nDCG@k）。

    位置越靠后，命中所带来的增益被 ``1/log2(rank+1)`` 折扣越多，
    以此区分「相关项排在前列」与「排在后段」。归一化用理想排序的
    DCG，使结果落在 ``[0, 1]``。

    参数:
        retrieved_ids: 按预测相关性排序的来源标识序列。
        relevant_ids: 标注正确来源集合。
        k: 仅评估前 ``k`` 个结果。

    返回:
        nDCG@k；当理想 DCG 为 0（前 k 无正确来源）时返回 ``0.0``。
    """
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
    """计算引用的精确率与召回率。

    用于评估回答所附声明级证据是否指向正确来源。引用为空时精确率记
    ``0.0``，正确来源为空时召回率记 ``1.0``（无遗漏）。

    参数:
        citations: 回答实际引用的来源标识序列。
        relevant_sources: 标注正确来源集合。

    返回:
        ``{"citation_precision": float, "citation_recall": float}``，
        两值均落在 ``[0, 1]``。
    """
    cited = set(citations)
    correct = len(cited & relevant_sources)
    return {
        "citation_precision": correct / len(cited) if cited else 0.0,
        "citation_recall": (
            correct / len(relevant_sources) if relevant_sources else 1.0
        ),
    }


def claim_support_rate(supported_claims: Sequence[bool]) -> float:
    """计算声明被证据支持的比例（忠实度 / faithfulness）。

    衡量回答中每个断言是否能被检索到的事实支撑，抑制幻觉。

    参数:
        supported_claims: 各断言是否被证据支持的布尔序列。

    返回:
        被支持的断言占比；输入为空时返回 ``0.0``。
    """
    if not supported_claims:
        return 0.0
    return sum(bool(value) for value in supported_claims) / len(
        supported_claims
    )
