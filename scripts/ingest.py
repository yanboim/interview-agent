from pathlib import Path
import json

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.chunking import split_with_heading_context
from app.config import get_settings
from app.chunks import stable_chunk_id
from app.rag import get_embeddings, get_sparse_embeddings
from langchain_qdrant import RetrievalMode

SUPPORTED_SUFFIXES = {".md", ".txt"}


def load_documents(directory: Path) -> list[Document]:
    documents = []
    if not directory.exists():
        return documents

    for file_path in sorted(directory.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = file_path.read_text(encoding="gb18030", errors="ignore")
        if content.strip():
            documents.append(
                Document(
                    page_content=content,
                    metadata={"source": str(file_path), "filename": file_path.name},
                )
            )
    return documents


def ingest_knowledge() -> dict[str, object]:
    settings = get_settings()
    documents = load_documents(Path("knowledge"))
    if not documents:
        raise RuntimeError("knowledge 目录中没有找到 Markdown 或 TXT 文件。")

    chunks = split_with_heading_context(documents)
    chunk_ids = []
    for chunk in chunks:
        source = str(chunk.metadata.get("source", ""))
        stable_content = str(chunk.metadata.pop("_stable_content"))
        chunk_id = stable_chunk_id(source, stable_content)
        chunk.metadata["chunk_id"] = chunk_id
        chunk_ids.append(chunk_id)

    embeddings = get_embeddings()
    sparse_embeddings = get_sparse_embeddings()

    # Validate credentials and model access before replacing existing data.
    # This prevents a bad API key from deleting a usable collection first.
    embeddings.embed_query("面试知识库连接测试")
    sparse_embeddings.embed_query("面试知识库连接测试")

    client = QdrantClient(url=settings.qdrant_url)
    if client.collection_exists(settings.qdrant_collection):
        client.delete_collection(settings.qdrant_collection)

    QdrantVectorStore.from_documents(
        documents=chunks,
        ids=chunk_ids,
        embedding=embeddings,
        sparse_embedding=sparse_embeddings,
        retrieval_mode=RetrievalMode.HYBRID,
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection,
    )
    evaluation_summary = None
    if settings.ingest_run_evaluation:
        from app.rag import get_dense_vector_store, get_vector_store
        from scripts.evaluate_chunks import evaluate, load_cases

        get_vector_store.cache_clear()
        get_dense_vector_store.cache_clear()
        report = evaluate(
            load_cases(Path("eval/chunk_questions.jsonl")),
            k=10,
            rerank=settings.reranker_enabled,
            lexical_rerank=settings.lexical_reranker_enabled,
            llm_rerank=settings.llm_reranker_enabled,
        )
        output = Path("eval/reports/post-ingest-latest.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        evaluation_summary = report["summary"]
        ndcg = float(evaluation_summary.get("ndcg@10", 0.0))
        if ndcg < settings.rag_regression_min_ndcg:
            raise RuntimeError(
                "导入后 RAG 回归未达标："
                f"nDCG@10={ndcg:.4f} < "
                f"{settings.rag_regression_min_ndcg:.4f}"
            )
    return {
        "documents": len(documents),
        "chunks": len(chunks),
        "collection": settings.qdrant_collection,
        "evaluation": evaluation_summary,
    }


def main() -> None:
    result = ingest_knowledge()
    print(
        f"知识库导入完成：{result['documents']} 个文档，"
        f"{result['chunks']} 个分块"
    )
    print(f"Collection：{result['collection']}")


if __name__ == "__main__":
    main()
