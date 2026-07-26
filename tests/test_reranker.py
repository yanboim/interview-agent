from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from app.reranker import rerank_documents


@patch("app.reranker.get_reranker")
def test_rerank_documents_orders_by_cross_encoder_score(
    get_reranker: MagicMock,
) -> None:
    low = Document(page_content="低相关")
    high = Document(page_content="高相关")
    get_reranker.return_value.rerank.return_value = [0.1, 0.9]

    results = rerank_documents(
        "问题",
        [(low, 0.8), (high, 0.5)],
    )

    assert results == [(high, 0.9, 0.5), (low, 0.1, 0.8)]
