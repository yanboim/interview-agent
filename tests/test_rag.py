from unittest.mock import MagicMock, patch

from langchain_qdrant import RetrievalMode

from app.rag import get_dense_vector_store, get_embeddings, get_vector_store
from app.tools import search_interview_knowledge


@patch("app.rag.OpenAIEmbeddings")
@patch("app.rag.get_settings")
def test_zhipu_embedding_configuration(
    settings: MagicMock,
    openai_embeddings: MagicMock,
) -> None:
    settings.return_value.zhipu_embedding_api_key = "embedding-key"
    settings.return_value.zhipu_api_key = "chat-key"
    settings.return_value.zhipu_embedding_model = "embedding-2"
    settings.return_value.zhipu_embedding_api_base = (
        "https://open.bigmodel.cn/api/paas/v4"
    )
    get_embeddings.cache_clear()

    embeddings = get_embeddings()

    assert embeddings is openai_embeddings.return_value
    openai_embeddings.assert_called_once_with(
        model="embedding-2",
        api_key="embedding-key",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        check_embedding_ctx_length=False,
        chunk_size=8,
    )
    get_embeddings.cache_clear()


@patch("langchain_qdrant.QdrantVectorStore.from_existing_collection")
@patch("app.rag.get_sparse_embeddings")
@patch("app.rag.get_embeddings")
@patch("app.rag.get_settings")
def test_vector_store_uses_current_embedding_parameter(
    settings: MagicMock,
    embeddings: MagicMock,
    sparse_embeddings: MagicMock,
    from_existing_collection: MagicMock,
) -> None:
    settings.return_value.qdrant_collection = "interview_knowledge"
    settings.return_value.qdrant_url = "http://localhost:6333"
    get_vector_store.cache_clear()

    vector_store = get_vector_store()

    assert vector_store is from_existing_collection.return_value
    from_existing_collection.assert_called_once_with(
        embedding=embeddings.return_value,
        sparse_embedding=sparse_embeddings.return_value,
        retrieval_mode=RetrievalMode.HYBRID,
        collection_name="interview_knowledge",
        url="http://localhost:6333",
    )
    get_vector_store.cache_clear()


@patch("app.tools.time.sleep")
@patch("app.tools.rerank_documents")
@patch("app.tools.get_dense_vector_store")
@patch("app.tools.get_settings")
@patch("app.tools.get_vector_store")
def test_retrieval_retries_once(
    vector_store: MagicMock,
    settings: MagicMock,
    dense_vector_store: MagicMock,
    rerank_documents: MagicMock,
    sleep: MagicMock,
) -> None:
    document = MagicMock()
    document.page_content = "RAG 内容"
    document.metadata = {"source": "knowledge/rag.md"}
    first_store = MagicMock()
    first_store.similarity_search.side_effect = RuntimeError("temporary error")
    second_store = MagicMock()
    second_store.similarity_search_with_score.return_value = [(document, 0.75)]
    vector_store.side_effect = [first_store, second_store]
    dense_vector_store.return_value.similarity_search_with_score.return_value = [
        (document, 0.7)
    ]
    first_store.similarity_search_with_score.side_effect = RuntimeError(
        "temporary error"
    )
    settings.return_value.retrieval_candidate_k = 20
    settings.return_value.retrieval_final_k = 4
    settings.return_value.retrieval_min_score = 0.0
    settings.return_value.dense_relevance_min_score = 0.4
    settings.return_value.reranker_enabled = True
    settings.return_value.lexical_reranker_enabled = True
    settings.return_value.lexical_retrieval_weight = 0.35
    settings.return_value.reranker_min_score = 0.0
    rerank_documents.return_value = [(document, 0.9, 0.75)]

    result = search_interview_knowledge.invoke({"query": "RAG"})

    assert "knowledge/rag.md" in result
    assert vector_store.call_count == 2
    vector_store.cache_clear.assert_called_once()
    dense_vector_store.cache_clear.assert_called_once()
    sleep.assert_called_once_with(0.5)


@patch("app.tools.get_dense_vector_store")
@patch("app.tools.get_settings")
def test_retrieval_rejects_low_dense_relevance(
    settings: MagicMock,
    dense_vector_store: MagicMock,
) -> None:
    document = MagicMock()
    dense_vector_store.return_value.similarity_search_with_score.return_value = [
        (document, 0.25)
    ]
    settings.return_value.dense_relevance_min_score = 0.4

    result = search_interview_knowledge.invoke({"query": "红烧肉怎么做"})

    assert "没有达到语义相关度阈值" in result


@patch("app.tools.lexical_rerank_documents")
@patch("app.tools.get_dense_vector_store")
@patch("app.tools.get_settings")
@patch("app.tools.get_vector_store")
def test_retrieval_uses_lightweight_reranker(
    vector_store: MagicMock,
    settings: MagicMock,
    dense_vector_store: MagicMock,
    lexical_rerank: MagicMock,
) -> None:
    document = MagicMock()
    document.page_content = "自动配置内容"
    document.metadata = {"source": "knowledge/spring-boot.md"}
    dense_vector_store.return_value.similarity_search_with_score.return_value = [
        (document, 0.7)
    ]
    vector_store.return_value.similarity_search_with_score.return_value = [
        (document, 0.5)
    ]
    settings.return_value.retrieval_candidate_k = 20
    settings.return_value.retrieval_final_k = 4
    settings.return_value.retrieval_min_score = 0.0
    settings.return_value.dense_relevance_min_score = 0.4
    settings.return_value.reranker_enabled = False
    settings.return_value.llm_reranker_enabled = False
    settings.return_value.lexical_reranker_enabled = True
    settings.return_value.lexical_retrieval_weight = 0.35
    settings.return_value.reranker_min_score = 0.0
    lexical_rerank.return_value = [(document, 0.8, 0.5, 0.9)]

    result = search_interview_knowledge.invoke({"query": "自动配置"})

    lexical_rerank.assert_called_once()
    assert "轻量重排分数：0.8000" in result
