from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient

from app.config import get_settings
from app.knowledge_publication import resolve_serving_knowledge
from app.model_gateway import create_embeddings


@lru_cache
def get_embeddings() -> Any:
    settings = get_settings()
    return create_embeddings(settings=settings)


@lru_cache
def get_sparse_embeddings() -> Any:
    from langchain_qdrant import FastEmbedSparse

    settings = get_settings()
    return FastEmbedSparse(model_name=settings.sparse_embedding_model)


def get_serving_knowledge_target() -> tuple[str, str]:
    settings = get_settings()
    client = QdrantClient(
        url=settings.qdrant_url,
        check_compatibility=False,
    )
    resolved = resolve_serving_knowledge(client, settings)
    if not resolved:
        raise RuntimeError("Qdrant 中没有可用的知识库 collection")
    return resolved


def get_knowledge_version() -> str:
    return get_serving_knowledge_target()[1]


@lru_cache
def _get_vector_store_cached(
    query_name: str,
    physical_version: str,
) -> Any:
    from langchain_qdrant import QdrantVectorStore, RetrievalMode

    settings = get_settings()
    return QdrantVectorStore.from_existing_collection(
        embedding=get_embeddings(),
        sparse_embedding=get_sparse_embeddings(),
        retrieval_mode=RetrievalMode.HYBRID,
        collection_name=query_name,
        url=settings.qdrant_url,
    )


def get_vector_store(collection_name: str | None = None) -> Any:
    if collection_name:
        return _get_vector_store_cached(collection_name, collection_name)
    query_name, physical_version = get_serving_knowledge_target()
    return _get_vector_store_cached(query_name, physical_version)


@lru_cache
def _get_dense_vector_store_cached(
    query_name: str,
    physical_version: str,
) -> Any:
    """Connect to the dense leg for relevance gating and diagnostics."""
    from langchain_qdrant import QdrantVectorStore, RetrievalMode

    settings = get_settings()
    return QdrantVectorStore.from_existing_collection(
        embedding=get_embeddings(),
        retrieval_mode=RetrievalMode.DENSE,
        collection_name=query_name,
        url=settings.qdrant_url,
    )


def get_dense_vector_store(collection_name: str | None = None) -> Any:
    if collection_name:
        return _get_dense_vector_store_cached(collection_name, collection_name)
    query_name, physical_version = get_serving_knowledge_target()
    return _get_dense_vector_store_cached(query_name, physical_version)


def clear_vector_store_caches() -> None:
    _get_vector_store_cached.cache_clear()
    _get_dense_vector_store_cached.cache_clear()


# Preserve the existing public cache-clear contract used by retry and tests.
get_vector_store.cache_clear = clear_vector_store_caches  # type: ignore[attr-defined]
get_dense_vector_store.cache_clear = clear_vector_store_caches  # type: ignore[attr-defined]
