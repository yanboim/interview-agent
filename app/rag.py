from functools import lru_cache
from typing import Any

from langchain_openai import OpenAIEmbeddings

from app.config import get_settings


@lru_cache
def get_embeddings() -> OpenAIEmbeddings:
    settings = get_settings()
    api_key = settings.zhipu_embedding_api_key or settings.zhipu_api_key
    if not api_key:
        raise RuntimeError(
            "未配置 ZHIPU_EMBEDDING_API_KEY，请在 .env 中填写智谱标准 API Key。"
        )

    return OpenAIEmbeddings(
        model=settings.zhipu_embedding_model,
        api_key=api_key,
        base_url=settings.zhipu_embedding_api_base,
        check_embedding_ctx_length=False,
        chunk_size=8,
    )


@lru_cache
def get_sparse_embeddings() -> Any:
    from langchain_qdrant import FastEmbedSparse

    settings = get_settings()
    return FastEmbedSparse(model_name=settings.sparse_embedding_model)


@lru_cache
def get_vector_store() -> Any:
    from langchain_qdrant import QdrantVectorStore, RetrievalMode

    settings = get_settings()
    return QdrantVectorStore.from_existing_collection(
        embedding=get_embeddings(),
        sparse_embedding=get_sparse_embeddings(),
        retrieval_mode=RetrievalMode.HYBRID,
        collection_name=settings.qdrant_collection,
        url=settings.qdrant_url,
    )


@lru_cache
def get_dense_vector_store() -> Any:
    """Connect to the dense leg for relevance gating and diagnostics."""
    from langchain_qdrant import QdrantVectorStore, RetrievalMode

    settings = get_settings()
    return QdrantVectorStore.from_existing_collection(
        embedding=get_embeddings(),
        retrieval_mode=RetrievalMode.DENSE,
        collection_name=settings.qdrant_collection,
        url=settings.qdrant_url,
    )
