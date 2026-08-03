"""部署发版记录簿（幂等写入）的测试。"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routers import admin as admin_routes
from app.auth import AuthenticatedUser
from app.storage import ConversationStore
from scripts.record_release import _key_values


def _record(
    store: ConversationStore,
    *,
    release_id: str = "production-v1",
    status: str = "succeeded",
    started_at: str = "2026-07-28T15:30:00+00:00",
) -> dict[str, object]:
    return store.record_deployment_release(
        release_id=release_id,
        version="v1",
        title="头像与历史体验修复",
        summary="管理员可查看真实生产部署。",
        environment="production",
        status=status,
        commit_sha="abcdef1234567890",
        changes=["修复头像设置", "修复返回历史空白"],
        verification={"health": "passed", "mobile": "passed"},
        app_image="sha256:app",
        worker_image="sha256:worker",
        migration_revision="20260728_0013",
        recovery_point="20260728T153029Z",
        triggered_by="operator",
        started_at=started_at,
        completed_at="2026-07-28T15:34:00+00:00",
    )


def test_release_recording_is_idempotent_and_structured(tmp_path):
    store = ConversationStore(tmp_path / "releases.db")
    store.initialize()

    created = _record(store, status="deploying")
    updated = _record(store, status="succeeded")
    rows = store.list_deployment_releases()

    assert created["status"] == "deploying"
    assert updated["status"] == "succeeded"
    assert len(rows) == 1
    assert rows[0]["changes"] == ["修复头像设置", "修复返回历史空白"]
    assert rows[0]["verification"] == {
        "health": "passed",
        "mobile": "passed",
    }


def test_release_listing_is_reverse_chronological_and_filterable(tmp_path):
    store = ConversationStore(tmp_path / "releases.db")
    store.initialize()
    _record(
        store,
        release_id="production-old",
        started_at="2026-07-27T10:00:00+00:00",
    )
    _record(
        store,
        release_id="production-new",
        status="failed",
        started_at="2026-07-28T10:00:00+00:00",
    )

    rows = store.list_deployment_releases(environment="production")
    failed = store.list_deployment_releases(status="failed")

    assert [row["release_id"] for row in rows] == [
        "production-new",
        "production-old",
    ]
    assert [row["release_id"] for row in failed] == ["production-new"]


def test_admin_release_endpoint_requires_admin(tmp_path, monkeypatch):
    store = ConversationStore(tmp_path / "releases.db")
    store.initialize()
    _record(store)
    monkeypatch.setattr(
        admin_routes,
        "get_runtime",
        lambda: SimpleNamespace(conversation_store=store),
    )
    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(admin_routes, "run_sync", run_inline)
    user_request = SimpleNamespace(
        state=SimpleNamespace(
            current_user=AuthenticatedUser("user-1", "candidate", "user")
        )
    )
    admin_request = SimpleNamespace(
        state=SimpleNamespace(
            current_user=AuthenticatedUser("admin-1", "operator", "admin")
        )
    )

    with pytest.raises(HTTPException) as denied:
        asyncio.run(admin_routes.admin_releases(user_request))
    result = asyncio.run(admin_routes.admin_releases(admin_request))

    assert denied.value.status_code == 403
    assert result[0]["release_id"] == "production-v1"


def test_verification_argument_requires_name_value_pairs():
    assert _key_values(["health=passed", "mobile=passed"]) == {
        "health": "passed",
        "mobile": "passed",
    }
    with pytest.raises(ValueError):
        _key_values(["health"])
