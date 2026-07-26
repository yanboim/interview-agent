from uuid import UUID

from app.chunks import stable_chunk_id


def test_stable_chunk_id_is_deterministic_uuid() -> None:
    first = stable_chunk_id("knowledge/java.md", "JVM 内容")
    second = stable_chunk_id("knowledge/java.md", "JVM 内容")

    assert first == second
    assert str(UUID(first)) == first


def test_stable_chunk_id_changes_with_source_or_content() -> None:
    base = stable_chunk_id("a.md", "content")

    assert stable_chunk_id("b.md", "content") != base
    assert stable_chunk_id("a.md", "different") != base
