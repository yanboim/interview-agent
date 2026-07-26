from functools import lru_cache
from typing import Any

from langchain_core.documents import Document

from app.config import get_settings

RetrievedDocument = tuple[Document, float]
RerankedDocument = tuple[Document, float, float]


@lru_cache
def get_reranker() -> Any:
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
    """Return documents ordered by cross-encoder score.

    Each result contains the document, reranker score, and original retrieval
    score so both stages remain observable.
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
