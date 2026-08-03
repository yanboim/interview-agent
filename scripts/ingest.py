"""知识导入命令入口；可复用实现位于 ``app.knowledge_ingestion``。"""

from app.knowledge_ingestion import ingest_knowledge, load_documents

__all__ = ["ingest_knowledge", "load_documents"]


def main() -> None:
    result = ingest_knowledge()
    print(
        f"知识库导入完成：{result['documents']} 个文档，"
        f"{result['chunks']} 个分块"
    )
    print(f"Collection：{result['collection']}")


if __name__ == "__main__":
    main()
