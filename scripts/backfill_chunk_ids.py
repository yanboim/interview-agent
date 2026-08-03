"""回填历史知识分块的稳定 ID，使旧集合也能用幂等分块标识重算。"""

from qdrant_client import QdrantClient, models

from app.chunks import stable_chunk_id
from app.config import get_settings


def main() -> None:
    settings = get_settings()
    client = QdrantClient(url=settings.qdrant_url, timeout=60)
    offset = None
    updated = 0

    while True:
        points, offset = client.scroll(
            collection_name=settings.qdrant_collection,
            limit=128,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        operations = []
        for point in points:
            payload = point.payload or {}
            content = str(payload.get("page_content", ""))
            metadata = dict(payload.get("metadata") or {})
            source = str(metadata.get("source", ""))
            metadata["chunk_id"] = stable_chunk_id(source, content)
            operations.append(
                models.SetPayloadOperation(
                    set_payload=models.SetPayload(
                        payload={"metadata": metadata},
                        points=[point.id],
                    )
                )
            )

        for start in range(0, len(operations), 32):
            batch = operations[start : start + 32]
            client.batch_update_points(
                collection_name=settings.qdrant_collection,
                update_operations=batch,
                wait=True,
            )
            updated += len(batch)
            print(f"已回填：{updated}", flush=True)

        if offset is None:
            break

    print(f"稳定 chunk_id 回填完成：{updated} 个分块")


if __name__ == "__main__":
    main()
