"""私人知识检索适配器：组合稠密/稀疏检索、重排、相关性门槛和版本化缓存。"""

from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient

from app.config import get_settings
from app.knowledge_publication import resolve_serving_knowledge
from app.model_gateway import create_embeddings


@lru_cache
def get_embeddings() -> Any:
    """构建并缓存稠密向量 Embedding 客户端（经统一模型网关创建）。

    返回:
        经 ``model_gateway.create_embeddings`` 包装的 Embedding 实例。
    """
    settings = get_settings()
    return create_embeddings(settings=settings)


@lru_cache
def get_sparse_embeddings() -> Any:
    """构建并缓存稀疏（BM25）Embedding 客户端，用于混合检索。

    返回:
        ``FastEmbedSparse`` 实例，模型由 ``sparse_embedding_model`` 配置。
    """
    from langchain_qdrant import FastEmbedSparse

    settings = get_settings()
    return FastEmbedSparse(
        model_name=settings.sparse_embedding_model,
        cache_dir=str(settings.sparse_embedding_cache_dir),
    )


def get_serving_knowledge_target() -> tuple[str, str]:
    """解析当前对外服务的知识库别名与其物理版本。

    通过 ``resolve_serving_knowledge`` 从 Qdrant 别名解析出正在服务的
    物理集合，使检索始终命中通过发布流程原子切换后的稳定版本。

    返回:
        ``(别名(查询用集合名), 物理版本)``。

    异常:
        RuntimeError: 当前没有任何可用 collection（别名未指向任何版本）。
    """
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
    """返回当前对外服务的知识库物理版本号。"""
    return get_serving_knowledge_target()[1]


@lru_cache
def _get_vector_store_cached(
    query_name: str,
    physical_version: str,
) -> Any:
    """按 ``(别名, 物理版本)`` 缓存混合检索向量库实例。

    缓存键含物理版本，故知识发布切换别名指向新版本后，必须调用
    ``clear_vector_store_caches`` 清理旧缓存才能命中新集合。

    参数:
        query_name: 用于查询的集合名（别名）。
        physical_version: 别名当前指向的物理版本，仅作缓存键。

    返回:
        混合检索模式的 ``QdrantVectorStore`` 实例。
    """
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
    """获取混合检索向量库。

    不传 ``collection_name`` 时解析当前服务别名及其物理版本，并以两者为
    缓存键（发布切换后需清缓存）；显式传入时直接按该集合名构造。

    参数:
        collection_name: 显式集合名，通常用于评估或导入候选集合。

    返回:
        ``QdrantVectorStore``（混合检索）实例。
    """
    if collection_name:
        return _get_vector_store_cached(collection_name, collection_name)
    query_name, physical_version = get_serving_knowledge_target()
    return _get_vector_store_cached(query_name, physical_version)


@lru_cache
def _get_dense_vector_store_cached(
    query_name: str,
    physical_version: str,
) -> Any:
    """连接稠密检索支路，用于相关性门槛判定与诊断。

    相比混合检索，稠密检索只使用向量相似度，便于独立计算 ``score`` 与
    ``dense_relevance_min_score`` 门槛，判断检索结果是否真的相关。
    """
    from langchain_qdrant import QdrantVectorStore, RetrievalMode

    settings = get_settings()
    return QdrantVectorStore.from_existing_collection(
        embedding=get_embeddings(),
        retrieval_mode=RetrievalMode.DENSE,
        collection_name=query_name,
        url=settings.qdrant_url,
    )


def get_dense_vector_store(collection_name: str | None = None) -> Any:
    """获取稠密检索向量库（仅向量相似度支路）。

    参数:
        collection_name: 显式集合名；为空时解析当前服务别名。

    返回:
        ``QdrantVectorStore``（稠密检索）实例。
    """
    if collection_name:
        return _get_dense_vector_store_cached(collection_name, collection_name)
    query_name, physical_version = get_serving_knowledge_target()
    return _get_dense_vector_store_cached(query_name, physical_version)


def clear_vector_store_caches() -> None:
    """清除向量库实例缓存。

    在知识发布切换别名或导入新候选版本后必须调用，否则旧的物理版本
    实例会被继续复用，导致检索命中过期集合。
    """
    _get_vector_store_cached.cache_clear()
    _get_dense_vector_store_cached.cache_clear()


# Preserve the existing public cache-clear contract used by retry and tests.
get_vector_store.cache_clear = clear_vector_store_caches  # type: ignore[attr-defined]
get_dense_vector_store.cache_clear = clear_vector_store_caches  # type: ignore[attr-defined]
