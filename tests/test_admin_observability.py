"""管理员可观测性（审计事件、执行追踪、交互观察）测试。"""

import json
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

import app.main as main_module
from app.api.routers import admin as admin_routes
from app.application.chat_service import ChatTurnService
from app.auth import AuthenticatedUser, AuthService
from app.storage import ConversationStore


def _request(role: str = "admin") -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(
            current_user=AuthenticatedUser(
                user_id=f"{role}-1",
                username=role,
                role=role,
            )
        )
    )


def test_audit_events_are_filterable_and_redact_sensitive_detail(
    tmp_path,
) -> None:
    store = ConversationStore(tmp_path / "audit.db")

    store.record_audit_event(
        request_id="request-1",
        actor_user_id="user-1",
        actor_username="alice",
        actor_role="user",
        action="update_profile",
        resource_type="profile",
        resource_id="user-1",
        outcome="success",
        method="PUT",
        path="/api/profile",
        status_code=200,
        duration_ms=12,
        detail={
            "path_parameters": {"user_id": "user-1"},
            "password": "must-not-appear",
            "authorization": "Bearer must-not-appear",
        },
    )

    rows = store.list_audit_events(
        user_id="user-1",
        outcome="success",
    )

    assert len(rows) == 1
    assert rows[0]["actor_username"] == "alice"
    assert rows[0]["request_id"] == "request-1"
    assert "must-not-appear" not in str(rows[0]["detail_json"])
    assert "[REDACTED]" in str(rows[0]["detail_json"])


def test_interactions_use_canonical_content_and_link_execution_trace(
    tmp_path,
) -> None:
    store = ConversationStore(tmp_path / "interactions.db")
    store.initialize()
    user = AuthService(store.engine).create_user(
        "alice",
        "Strong-password-2026!",
    )
    service = ChatTurnService(store)
    claim = service.begin(
        user_id=user.user_id,
        session_id="session-1",
        content="用户输入原文",
        idempotency_key="interaction-command-1",
    )
    service.complete(
        claim,
        user_id=user.user_id,
        session_id="session-1",
        answer="系统输出原文",
        metadata={"knowledge_used": True},
    )
    store.record_execution_trace(
        request_id="request-1",
        user_id=user.user_id,
        interaction_type="chat",
        interaction_id=str(claim["turn_id"]),
        stage="agent_execution",
        status="completed",
        duration_ms=321,
        detail={
            "model": "test-model",
            "prompt": "must-not-be-copied",
        },
    )
    store.record_tool_audit(
        user_id=user.user_id,
        role="user",
        tool_name="knowledge_search",
        input_summary="搜索摘要",
        status="success",
        duration_ms=10,
        result_summary="命中 1 个来源",
        request_id="request-1",
        interaction_type="chat",
        interaction_id=str(claim["turn_id"]),
    )

    interactions = store.list_admin_interactions(
        interaction_type="chat"
    )
    trace = store.list_execution_trace(
        interaction_type="chat",
        interaction_id=str(claim["turn_id"]),
    )

    assert interactions[0]["username"] == "alice"
    assert interactions[0]["input_text"] == "用户输入原文"
    assert interactions[0]["output_text"] == "系统输出原文"
    assert [item["stage"] for item in trace] == [
        "agent_execution",
        "tool:knowledge_search",
    ]
    assert "must-not-be-copied" not in json.dumps(trace)
    assert "[REDACTED]" in json.dumps(trace)


def test_interaction_filters_do_not_cross_users(tmp_path) -> None:
    store = ConversationStore(tmp_path / "filter.db")
    store.initialize()
    auth = AuthService(store.engine)
    alice = auth.create_user("alice", "Strong-password-2026!")
    bob = auth.create_user("bob", "Strong-password-2026!")
    service = ChatTurnService(store)
    for user, content in ((alice, "Alice input"), (bob, "Bob input")):
        claim = service.begin(
            user_id=user.user_id,
            session_id=f"session-{user.username}",
            content=content,
            idempotency_key=f"command-{user.username}",
        )
        service.complete(
            claim,
            user_id=user.user_id,
            session_id=f"session-{user.username}",
            answer=f"{user.username} output",
            metadata={},
        )

    rows = store.list_admin_interactions(user_id=alice.user_id)

    assert len(rows) == 1
    assert rows[0]["username"] == "alice"
    assert "Bob" not in json.dumps(rows)


def test_admin_interaction_endpoints_require_admin(
    tmp_path,
    monkeypatch,
) -> None:
    store = ConversationStore(tmp_path / "endpoint.db")
    store.initialize()
    monkeypatch.setattr(
        admin_routes,
        "get_runtime",
        lambda: SimpleNamespace(conversation_store=store),
    )

    async def direct_run(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(admin_routes, "run_sync", direct_run)

    assert asyncio.run(
        admin_routes.admin_interactions(_request())
    ) == []
    with pytest.raises(HTTPException) as error:
        asyncio.run(admin_routes.admin_interactions(_request("user")))
    assert error.value.status_code == 403


def test_api_middleware_records_authoritative_request_audit(
    monkeypatch,
) -> None:
    audit_write = MagicMock()
    monkeypatch.setattr(main_module.settings, "app_api_key", "")
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    monkeypatch.setattr(
        main_module.rate_limiter,
        "allow",
        lambda _client: (True, 0),
    )
    monkeypatch.setattr(
        main_module.conversation_store,
        "record_audit_event",
        audit_write,
    )

    async def direct_run(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(main_module, "run_sync", direct_run)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/config",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
            "scheme": "http",
            "root_path": "",
            "route": SimpleNamespace(
                path="/api/config",
                name="public_config",
            ),
        }
    )
    request.state.request_id = "request-audit-1"
    request.state.current_user = AuthenticatedUser(
        user_id="user-1",
        username="alice",
        role="user",
    )

    async def response_handler(_request):
        return JSONResponse({"auth_required": False})

    response = asyncio.run(
        main_module.operational_controls(request, response_handler)
    )

    assert response.status_code == 200
    audit_write.assert_called_once()
    payload = audit_write.call_args.kwargs
    assert payload["request_id"] == "request-audit-1"
    assert payload["action"] == "public_config"
    assert payload["path"] == "/api/config"
    assert payload["status_code"] == 200
