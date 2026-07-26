from uuid import UUID, uuid5

CHUNK_NAMESPACE = UUID("73873de7-6bd4-4ec4-bb25-e6871a6a40f3")


def stable_chunk_id(source: str, content: str) -> str:
    """Return a deterministic Qdrant-compatible UUID for a text chunk."""
    return str(uuid5(CHUNK_NAMESPACE, f"{source}\0{content}"))
