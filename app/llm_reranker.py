"""受统一模型网关保护的 LLM 重排器；解析失败时安全回退原始顺序。"""

import json
import re
from functools import lru_cache

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from app.config import get_settings
from app.model_gateway import PolicyChatOpenAI, create_chat_model


RetrievedDocument = tuple[Document, float]
RerankedDocument = tuple[Document, float, float]
_JSON_ARRAY = re.compile(r"\[[\s\d,]*\]")


@lru_cache
def get_llm_reranker() -> PolicyChatOpenAI:
    """构建并缓存用于重排的对话模型实例（经统一模型网关创建）。

    返回:
        低温（``temperature=0``）的 ``PolicyChatOpenAI`` 实例，输出受限为短序号。

    异常:
        RuntimeError: 未配置 ``ZHIPU_API_KEY`` 时抛出。
    """
    settings = get_settings()
    if not settings.zhipu_api_key:
        raise RuntimeError("未配置 ZHIPU_API_KEY，无法使用 GLM 重排。")
    return create_chat_model(
        "llm_reranker",
        temperature=0,
        max_tokens=300,
        settings=settings,
    )


def parse_ranking(content: str, candidate_count: int) -> list[int]:
    """从模型输出文本中解析出候选序号的去重排序。

    模型可能输出多余解释文字，故用正则只截取首个整数数组。序号需落在
    ``[1, candidate_count]`` 且去重，确保后续可安全地作为重排依据。

    参数:
        content: 模型原始输出文本。
        candidate_count: 候选总数，用于序号范围校验。

    返回:
        合法且去重的序号列表；解析失败或无合法值时返回空列表。
    """
    match = _JSON_ARRAY.search(content)
    if not match:
        return []
    try:
        values = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []

    ranking = []
    seen = set()
    for value in values:
        if (
            isinstance(value, int)
            and 1 <= value <= candidate_count
            and value not in seen
        ):
            ranking.append(value)
            seen.add(value)
    return ranking


def llm_rerank_documents(
    query: str,
    candidates: list[RetrievedDocument],
) -> list[RerankedDocument]:
    """用对话模型按「直接回答能力」对候选重排。

    把候选正文摘要与查询送入重排模型，让其输出按相关度排序的序号数组，
    再据此派生归一化分数。解析失败或序号不全时，用原始顺序补全缺失项，
    因此模型异常不会丢弃候选——这是「安全回退原始顺序」的设计。

    参数:
        query: 用户查询。
        candidates: ``(文档, 原始检索分数)`` 候选列表。

    返回:
        ``(文档, 重排分数, 原始检索分数)`` 三元组列表，按重排分数降序。
        重排分数由排名位置 ``1 - (rank-1)/count`` 派生，落在 ``[0, 1]``。
        输入为空时返回空列表。
    """
    if not candidates:
        return []

    candidate_text = "\n\n".join(
        (
            f"[{index}] 来源：{document.metadata.get('filename', '未知')}\n"
            f"{document.page_content[:700]}"
        )
        for index, (document, _) in enumerate(candidates, start=1)
    )
    response = get_llm_reranker().invoke(
        [
            SystemMessage(
                content=(
                    "你是 RAG 检索重排器。按照候选内容对用户问题的直接回答能力"
                    "从高到低排序。优先选择主题精确、包含具体原理或操作细节的内容，"
                    "降低仅因关键词重合但主题不同、模板化或泛化内容的排名。"
                    "只输出 JSON 整数数组，例如 [3,1,2]，不要输出解释。"
                )
            ),
            HumanMessage(
                content=(
                    f"用户问题：{query}\n\n候选知识块：\n{candidate_text}\n\n"
                    "请返回所有候选编号的相关性排序。"
                )
            ),
        ]
    )
    content = response.content if isinstance(response.content, str) else ""
    ranking = parse_ranking(content, len(candidates))
    ranking.extend(
        index
        for index in range(1, len(candidates) + 1)
        if index not in ranking
    )

    count = len(ranking)
    return [
        (
            candidates[index - 1][0],
            1.0 - (rank - 1) / max(1, count),
            candidates[index - 1][1],
        )
        for rank, index in enumerate(ranking, start=1)
    ]
