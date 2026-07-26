import logging
import re
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator
from uuid import uuid4

from qdrant_client import QdrantClient, models

from app.config import Settings, get_settings
from app.operations import RedisRuntime


_VERSION_COMPONENT = re.compile(r"[^A-Za-z0-9_-]+")
_LOCAL_PUBLICATION_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


class KnowledgePublicationError(RuntimeError):
    """Base error for safe knowledge publication operations."""


class KnowledgePublicationConflict(KnowledgePublicationError):
    """Raised when another publisher already owns the publication lock."""


def collection_version_prefix(settings: Settings) -> str:
    return f"{settings.qdrant_collection}__v_"


def build_collection_version(
    settings: Settings,
    *,
    job_id: str | None = None,
    now: datetime | None = None,
) -> str:
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S%fZ")
    raw_suffix = job_id or str(uuid4())
    suffix = _VERSION_COMPONENT.sub("-", raw_suffix).strip("-_")[:16] or "manual"
    return f"{collection_version_prefix(settings)}{timestamp}_{suffix}"


def alias_target(client: QdrantClient, alias_name: str) -> str | None:
    aliases = client.get_aliases().aliases
    return next(
        (
            str(alias.collection_name)
            for alias in aliases
            if alias.alias_name == alias_name
        ),
        None,
    )


def resolve_serving_knowledge(
    client: QdrantClient,
    settings: Settings,
) -> tuple[str, str] | None:
    """Return ``(query_name, physical_version)`` for the serving knowledge."""
    target = alias_target(client, settings.qdrant_collection_alias)
    if target:
        return settings.qdrant_collection_alias, target
    if client.collection_exists(settings.qdrant_collection):
        return settings.qdrant_collection, settings.qdrant_collection
    return None


def switch_serving_alias(
    client: QdrantClient,
    settings: Settings,
    collection_name: str,
) -> str | None:
    previous = alias_target(client, settings.qdrant_collection_alias)
    operations: list[
        models.CreateAliasOperation | models.DeleteAliasOperation
    ] = []
    if previous:
        operations.append(
            models.DeleteAliasOperation(
                delete_alias=models.DeleteAlias(
                    alias_name=settings.qdrant_collection_alias,
                )
            )
        )
    operations.append(
        models.CreateAliasOperation(
            create_alias=models.CreateAlias(
                collection_name=collection_name,
                alias_name=settings.qdrant_collection_alias,
            )
        )
    )
    client.update_collection_aliases(operations)
    return previous


def knowledge_status(
    client: QdrantClient | None = None,
    settings: Settings | None = None,
) -> dict[str, object]:
    current_settings = settings or get_settings()
    current_client = client or QdrantClient(
        url=current_settings.qdrant_url,
        check_compatibility=False,
    )
    resolved = resolve_serving_knowledge(current_client, current_settings)
    versions = sorted(
        (
            collection.name
            for collection in current_client.get_collections().collections
            if collection.name.startswith(collection_version_prefix(current_settings))
        ),
        reverse=True,
    )
    return {
        "alias": current_settings.qdrant_collection_alias,
        "serving_name": resolved[0] if resolved else None,
        "current_version": resolved[1] if resolved else None,
        "legacy_collection": current_settings.qdrant_collection,
        "legacy_exists": current_client.collection_exists(
            current_settings.qdrant_collection
        ),
        "versions": versions,
    }


def require_serving_knowledge() -> str:
    current_version = knowledge_status()["current_version"]
    if not current_version:
        raise KnowledgePublicationError("知识库版本不存在")
    return str(current_version)


@contextmanager
def publication_lock(
    *,
    settings: Settings,
    runtime: RedisRuntime,
    owner_token: str,
) -> Iterator[None]:
    key = f"interview-agent:knowledge-publish:{settings.qdrant_collection_alias}"
    using_redis = bool(settings.redis_url)
    if using_redis:
        if not runtime.acquire_lock(
            key,
            owner_token,
            settings.knowledge_publish_lock_seconds,
        ):
            raise KnowledgePublicationConflict("已有知识库发布任务正在执行")
    elif not _LOCAL_PUBLICATION_LOCK.acquire(blocking=False):
        raise KnowledgePublicationConflict("已有本地知识库发布任务正在执行")

    try:
        yield
    finally:
        if using_redis:
            try:
                runtime.release_lock(key, owner_token)
            except Exception:
                logger.exception(
                    "释放知识库发布锁失败，锁将在 TTL 到期后自动失效"
                )
        else:
            _LOCAL_PUBLICATION_LOCK.release()


def rollback_knowledge(
    collection_name: str,
    *,
    client: QdrantClient | None = None,
    runtime: RedisRuntime | None = None,
    settings: Settings | None = None,
) -> dict[str, object]:
    current_settings = settings or get_settings()
    if not collection_name.startswith(collection_version_prefix(current_settings)):
        raise KnowledgePublicationError("只能回滚到受管理的知识库版本")
    current_client = client or QdrantClient(
        url=current_settings.qdrant_url,
        check_compatibility=False,
    )
    if not current_client.collection_exists(collection_name):
        raise KnowledgePublicationError("目标知识库版本不存在")
    current_runtime = runtime or RedisRuntime(
        current_settings.redis_url,
        current_settings.redis_queue_name,
    )
    owner_token = f"rollback:{uuid4()}"
    with publication_lock(
        settings=current_settings,
        runtime=current_runtime,
        owner_token=owner_token,
    ):
        previous = switch_serving_alias(
            current_client,
            current_settings,
            collection_name,
        )
    return {
        "alias": current_settings.qdrant_collection_alias,
        "previous_version": previous,
        "current_version": collection_name,
        "status": "rolled_back",
    }


def validate_candidate_collection(
    client: QdrantClient,
    collection_name: str,
    *,
    expected_points: int,
) -> dict[str, int]:
    if not client.collection_exists(collection_name):
        raise KnowledgePublicationError("候选知识库 collection 未创建")
    count = int(client.count(collection_name, exact=True).count)
    if count != expected_points:
        raise KnowledgePublicationError(
            f"候选知识库分块数量不一致：expected={expected_points}, actual={count}"
        )
    info: Any = client.get_collection(collection_name)
    points_count = int(info.points_count or 0)
    if points_count != expected_points:
        raise KnowledgePublicationError(
            "候选知识库 collection 状态尚未完整："
            f"expected={expected_points}, points={points_count}"
        )
    return {"points": count}
