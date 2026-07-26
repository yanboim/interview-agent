import json
import re
from functools import lru_cache

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings


RetrievedDocument = tuple[Document, float]
RerankedDocument = tuple[Document, float, float]
_JSON_ARRAY = re.compile(r"\[[\s\d,]*\]")


@lru_cache
def get_llm_reranker() -> ChatOpenAI:
    settings = get_settings()
    if not settings.zhipu_api_key:
        raise RuntimeError("未配置 ZHIPU_API_KEY，无法使用 GLM 重排。")
    return ChatOpenAI(
        model=settings.zhipu_model,
        api_key=settings.zhipu_api_key,
        base_url=settings.zhipu_api_base,
        temperature=0,
        max_tokens=300,
    )


def parse_ranking(content: str, candidate_count: int) -> list[int]:
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
