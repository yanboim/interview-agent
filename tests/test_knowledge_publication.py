"""知识发布（版本化、验证、别名切换、回滚）的测试。"""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from qdrant_client import models

from app import knowledge_ingestion as ingest
from app.knowledge_publication import (
    KnowledgePublicationConflict,
    KnowledgePublicationError,
    alias_target,
    build_collection_version,
    knowledge_status,
    publication_lock,
    resolve_serving_knowledge,
    rollback_knowledge,
    switch_serving_alias,
)
from app.operations import RedisRuntime


def settings(**overrides):
    values = {
        "qdrant_url": "http://qdrant:6333",
        "qdrant_collection": "interview_knowledge",
        "qdrant_collection_alias": "interview_knowledge_current",
        "knowledge_publish_lock_seconds": 3600,
        "redis_url": "",
        "redis_queue_name": "jobs",
        "ingest_run_evaluation": False,
        "reranker_enabled": False,
        "lexical_reranker_enabled": False,
        "llm_reranker_enabled": False,
        "rag_regression_min_ndcg": 0.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeQdrantClient:
    def __init__(
        self,
        *,
        collections: dict[str, int] | None = None,
        aliases: dict[str, str] | None = None,
    ) -> None:
        self.collections = dict(collections or {})
        self.aliases = dict(aliases or {})
        self.deleted: list[str] = []
        self.alias_updates: list[list[object]] = []

    def get_aliases(self):
        return SimpleNamespace(
            aliases=[
                models.AliasDescription(
                    alias_name=name,
                    collection_name=collection,
                )
                for name, collection in self.aliases.items()
            ]
        )

    def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def get_collections(self):
        return SimpleNamespace(
            collections=[
                models.CollectionDescription(name=name)
                for name in self.collections
            ]
        )

    def update_collection_aliases(self, operations):
        self.alias_updates.append(list(operations))
        next_aliases = dict(self.aliases)
        for operation in operations:
            if isinstance(operation, models.DeleteAliasOperation):
                next_aliases.pop(operation.delete_alias.alias_name, None)
            if isinstance(operation, models.CreateAliasOperation):
                next_aliases[operation.create_alias.alias_name] = (
                    operation.create_alias.collection_name
                )
        self.aliases = next_aliases
        return True

    def count(self, collection_name: str, exact: bool = True):
        return SimpleNamespace(count=self.collections[collection_name])

    def get_collection(self, collection_name: str):
        return SimpleNamespace(points_count=self.collections[collection_name])

    def delete_collection(self, collection_name: str):
        self.deleted.append(collection_name)
        self.collections.pop(collection_name, None)
        return True


def test_serving_alias_falls_back_to_legacy_collection() -> None:
    current_settings = settings()
    client = FakeQdrantClient(collections={"interview_knowledge": 10})

    assert resolve_serving_knowledge(client, current_settings) == (
        "interview_knowledge",
        "interview_knowledge",
    )

    client.collections["interview_knowledge__v_new"] = 12
    client.aliases["interview_knowledge_current"] = "interview_knowledge__v_new"
    assert resolve_serving_knowledge(client, current_settings) == (
        "interview_knowledge_current",
        "interview_knowledge__v_new",
    )


def test_alias_switch_replaces_target_in_one_operation_batch() -> None:
    current_settings = settings()
    client = FakeQdrantClient(
        collections={"interview_knowledge__v_old": 10, "interview_knowledge__v_new": 12},
        aliases={"interview_knowledge_current": "interview_knowledge__v_old"},
    )

    previous = switch_serving_alias(
        client,
        current_settings,
        "interview_knowledge__v_new",
    )

    assert previous == "interview_knowledge__v_old"
    assert alias_target(client, "interview_knowledge_current") == (
        "interview_knowledge__v_new"
    )
    assert len(client.alias_updates) == 1
    assert len(client.alias_updates[0]) == 2


def test_alias_switch_uses_real_qdrant_alias_operations() -> None:
    from qdrant_client import QdrantClient

    current_settings = settings()
    client = QdrantClient(":memory:")
    old_version = "interview_knowledge__v_old"
    new_version = "interview_knowledge__v_new"
    vector_config = models.VectorParams(
        size=2,
        distance=models.Distance.COSINE,
    )
    client.create_collection(old_version, vectors_config=vector_config)
    client.create_collection(new_version, vectors_config=vector_config)

    assert switch_serving_alias(client, current_settings, old_version) is None
    assert (
        switch_serving_alias(client, current_settings, new_version)
        == old_version
    )
    assert alias_target(client, "interview_knowledge_current") == new_version
    assert client.collection_exists(old_version)


def test_redis_publication_lock_rejects_contention_and_uses_owner_token() -> None:
    current_settings = settings(redis_url="redis://redis:6379/0")
    runtime = MagicMock(spec=RedisRuntime)
    runtime.acquire_lock.return_value = False

    with pytest.raises(KnowledgePublicationConflict):
        with publication_lock(
            settings=current_settings,
            runtime=runtime,
            owner_token="job-1",
        ):
            raise AssertionError("lock body must not run")

    runtime.acquire_lock.assert_called_once_with(
        "interview-agent:knowledge-publish:interview_knowledge_current",
        "job-1",
        3600,
    )
    runtime.release_lock.assert_not_called()


def test_rollback_accepts_only_managed_existing_versions() -> None:
    current_settings = settings()
    client = FakeQdrantClient(
        collections={
            "interview_knowledge__v_old": 10,
            "interview_knowledge__v_new": 12,
            "unmanaged": 1,
        },
        aliases={"interview_knowledge_current": "interview_knowledge__v_new"},
    )
    runtime = RedisRuntime("", "jobs")

    result = rollback_knowledge(
        "interview_knowledge__v_old",
        client=client,
        runtime=runtime,
        settings=current_settings,
    )

    assert result["previous_version"] == "interview_knowledge__v_new"
    assert result["current_version"] == "interview_knowledge__v_old"
    with pytest.raises(KnowledgePublicationError):
        rollback_knowledge(
            "unmanaged",
            client=client,
            runtime=runtime,
            settings=current_settings,
        )


def test_knowledge_status_lists_versions_and_current_target() -> None:
    current_settings = settings()
    client = FakeQdrantClient(
        collections={
            "interview_knowledge": 8,
            "interview_knowledge__v_20260725": 10,
            "interview_knowledge__v_20260726": 12,
        },
        aliases={
            "interview_knowledge_current": "interview_knowledge__v_20260726"
        },
    )

    result = knowledge_status(client=client, settings=current_settings)

    assert result["current_version"] == "interview_knowledge__v_20260726"
    assert result["versions"] == [
        "interview_knowledge__v_20260726",
        "interview_knowledge__v_20260725",
    ]
    assert result["legacy_exists"] is True


def test_ingest_publishes_valid_candidate_without_deleting_legacy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "rag.md").write_text(
        "# RAG\n\n检索增强生成内容。",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    current_settings = settings()
    client = FakeQdrantClient(collections={"interview_knowledge": 5})
    embeddings = MagicMock()
    sparse_embeddings = MagicMock()
    monkeypatch.setattr(ingest, "get_settings", lambda: current_settings)
    monkeypatch.setattr(ingest, "get_embeddings", lambda: embeddings)
    monkeypatch.setattr(ingest, "get_sparse_embeddings", lambda: sparse_embeddings)
    monkeypatch.setattr(ingest, "clear_vector_store_caches", lambda: None)

    def create_candidate(**kwargs):
        client.collections[kwargs["collection_name"]] = len(kwargs["documents"])

    monkeypatch.setattr(
        ingest.QdrantVectorStore,
        "from_documents",
        create_candidate,
    )

    result = ingest.ingest_knowledge(
        job_id="job-123",
        client=client,
        runtime=RedisRuntime("", "jobs"),
    )

    assert result["previous_version"] == "interview_knowledge"
    assert result["version"].startswith("interview_knowledge__v_")
    assert client.aliases["interview_knowledge_current"] == result["version"]
    assert "interview_knowledge" in client.collections
    assert client.deleted == []


def test_ingest_failure_removes_only_candidate_and_keeps_serving_version(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "rag.md").write_text("# RAG\n\n内容", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    current_settings = settings()
    old_version = "interview_knowledge__v_old"
    client = FakeQdrantClient(
        collections={old_version: 5},
        aliases={"interview_knowledge_current": old_version},
    )
    monkeypatch.setattr(ingest, "get_settings", lambda: current_settings)
    monkeypatch.setattr(ingest, "get_embeddings", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        ingest,
        "get_sparse_embeddings",
        MagicMock(return_value=MagicMock()),
    )

    def create_candidate(**kwargs):
        client.collections[kwargs["collection_name"]] = len(kwargs["documents"])

    monkeypatch.setattr(
        ingest.QdrantVectorStore,
        "from_documents",
        create_candidate,
    )
    monkeypatch.setattr(
        ingest,
        "validate_candidate_collection",
        MagicMock(side_effect=KnowledgePublicationError("invalid candidate")),
    )

    with pytest.raises(KnowledgePublicationError):
        ingest.ingest_knowledge(
            job_id="job-failed",
            client=client,
            runtime=RedisRuntime("", "jobs"),
        )

    assert client.aliases["interview_knowledge_current"] == old_version
    assert old_version in client.collections
    assert len(client.deleted) == 1
    assert client.deleted[0].startswith("interview_knowledge__v_")


def test_collection_version_is_stable_format() -> None:
    version = build_collection_version(
        settings(),
        job_id="job:unsafe/value",
        now=datetime(2026, 7, 26, tzinfo=UTC),
    )
    assert version == "interview_knowledge__v_20260726T000000000000Z_job-unsafe-value"
