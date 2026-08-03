"""检索重排组合入口，用配置选择词法或模型重排实现。"""

from functools import lru_cache
from typing import Any

from langchain_core.documents import Document

from app.config import get_settings

RetrievedDocument = tuple[Document, float]
RerankedDocument = tuple[Document, float, float]


@lru_cache
def get_reranker() -> Any:
    """构建并缓存交叉编码器（cross-encoder）重排模型实例。

    默认 ``Xenova/bge-reranker-base`` 不在 fastembed 预置列表时，会调用
    ``add_custom_model`` 注册量化 ONNX 源，使其可被加载。结果以
    ``lru_cache`` 缓存，避免每次重排都重新加载模型权重。

    返回:
        fastembed ``TextCrossEncoder`` 实例，调用其 ``rerank`` 即可。
    """
    from fastembed.common.model_description import ModelSource
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    settings = get_settings()
    if settings.reranker_model == "Xenova/bge-reranker-base":
        supported = {
            item["model"]
            for item in TextCrossEncoder.list_supported_models()
        }
        if settings.reranker_model not in supported:
            TextCrossEncoder.add_custom_model(
                model=settings.reranker_model,
                sources=ModelSource(hf=settings.reranker_model),
                model_file="onnx/model_quantized.onnx",
                description="Quantized bilingual BGE cross-encoder reranker.",
                license="mit",
                size_in_gb=0.279,
            )
    return TextCrossEncoder(model_name=settings.reranker_model)


def rerank_documents(
    query: str,
    documents: list[RetrievedDocument],
) -> list[RerankedDocument]:
    """按交叉编码器相关性分数对候选文档重排。

    把查询与各候选正文送入交叉编码器打分，并保留原始检索分数。两阶段
    分数都返回，使检索与重排效果可独立观测与评估。

    参数:
        query: 用户查询文本。
        documents: ``(文档, 原始检索分数)`` 候选列表。

    返回:
        ``(文档, 重排分数, 原始检索分数)`` 三元组列表，按重排分数降序。
        输入为空时返回空列表。
    """
    if not documents:
        return []

    contents = [document.page_content for document, _ in documents]
    scores = list(get_reranker().rerank(query, contents))
    reranked = [
        (document, float(score), retrieval_score)
        for (document, retrieval_score), score in zip(
            documents,
            scores,
            strict=True,
        )
    ]
    return sorted(reranked, key=lambda item: item[1], reverse=True)
