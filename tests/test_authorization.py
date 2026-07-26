import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.main as main_module
from app.auth import AuthenticatedUser, TokenPair


def test_authenticated_user_cannot_claim_another_user(monkeypatch):
    monkeypatch.setattr(main_module.settings, "auth_required", True)
    request = SimpleNamespace(
        state=SimpleNamespace(
            current_user=AuthenticatedUser(
                user_id="actual-user",
                username="candidate",
                role="user",
            )
        )
    )

    assert main_module.resolve_user_id(request, "actual-user") == "actual-user"
    with pytest.raises(HTTPException) as exc_info:
        main_module.resolve_user_id(request, "another-user")
    assert exc_info.value.status_code == 403


def test_legacy_local_mode_uses_claimed_user(monkeypatch):
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    request = SimpleNamespace(state=SimpleNamespace())

    assert main_module.resolve_user_id(request, " local-user ") == "local-user"


def test_admin_role_is_required():
    request = SimpleNamespace(
        state=SimpleNamespace(
            current_user=AuthenticatedUser(
                user_id="user-1",
                username="candidate",
                role="user",
            )
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        main_module.require_role(request, {"admin"})
    assert exc_info.value.status_code == 403

    request.state.current_user = AuthenticatedUser(
        user_id="admin-1",
        username="admin",
        role="admin",
    )
    assert main_module.require_role(request, {"admin"}).role == "admin"


def test_admin_can_trigger_knowledge_import(monkeypatch):
    request = SimpleNamespace(
        state=SimpleNamespace(
            current_user=AuthenticatedUser(
                user_id="admin-1",
                username="admin",
                role="admin",
            )
        )
    )
    monkeypatch.setattr(
        main_module,
        "ingest_knowledge",
        lambda: {
            "documents": 3,
            "chunks": 12,
            "collection": "interview_knowledge",
        },
    )
    async def run_inline(function, *args):
        return function(*args)

    monkeypatch.setattr(main_module.asyncio, "to_thread", run_inline)

    result = asyncio.run(main_module.admin_import_knowledge(request))

    assert result == {
        "operator": "admin",
        "status": "completed",
        "documents": 3,
        "chunks": 12,
        "collection": "interview_knowledge",
    }


def test_user_and_admin_login_surfaces_are_separated(monkeypatch):
    async def run_inline(function, *args):
        return function(*args)

    monkeypatch.setattr(main_module.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(main_module.conversation_store, "initialize", lambda: None)
    monkeypatch.setattr(
        main_module.auth_service,
        "login_user",
        lambda *_: (_ for _ in ()).throw(
            main_module.AuthSurfaceError("管理员账号请使用独立管理入口")
        ),
    )
    with pytest.raises(HTTPException) as user_login_error:
        asyncio.run(
            main_module.login(
                main_module.AuthCredentials(username="operator", password="password-123"),
            )
        )
    assert user_login_error.value.status_code == 403

    monkeypatch.setattr(
        main_module.auth_service,
        "login_admin",
        lambda *_: (_ for _ in ()).throw(
            main_module.AuthSurfaceError("该账号不是管理员")
        ),
    )
    with pytest.raises(HTTPException) as admin_login_error:
        asyncio.run(
            main_module.admin_login(
                main_module.AuthCredentials(username="candidate", password="password-123"),
            )
        )
    assert admin_login_error.value.status_code == 403


def test_admin_login_accepts_only_admin_credentials(monkeypatch):
    async def run_inline(function, *args):
        return function(*args)

    pair = TokenPair(
        access_token="admin-access",
        refresh_token="admin-refresh",
        expires_in=3600,
        user=AuthenticatedUser("admin-1", "operator", "admin"),
    )
    monkeypatch.setattr(main_module.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(main_module.conversation_store, "initialize", lambda: None)
    monkeypatch.setattr(main_module.auth_service, "login_admin", lambda *_: pair)

    response = asyncio.run(
        main_module.admin_login(
            main_module.AuthCredentials(username="operator", password="password-123"),
        )
    )

    assert response["user"] == {
        "user_id": "admin-1",
        "username": "operator",
        "role": "admin",
    }
