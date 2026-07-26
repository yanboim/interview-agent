import asyncio
from types import SimpleNamespace

from app.auth import AuthService, AuthenticatedUser
from app.main import (
    KnowledgeFileRequest,
    admin_delete_knowledge_file,
    admin_knowledge_files,
    admin_save_knowledge_file,
    admin_web_app,
)
from app.storage import ConversationStore


def admin_request():
    return SimpleNamespace(
        state=SimpleNamespace(
            current_user=AuthenticatedUser(
                user_id="admin-1",
                username="admin",
                role="admin",
            )
        )
    )


def test_admin_page_is_available():
    response = asyncio.run(admin_web_app())

    assert response.status_code == 200
    # 新前端为 Vue SPA,主应用与后台共用入口 index.html;/admin 路由在前端解析。
    assert "Interview Lab" in response.path.read_text(encoding="utf-8")


def test_admin_can_save_list_and_delete_knowledge_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = KnowledgeFileRequest(
        filename="admin-test.md",
        content="# 后台知识",
    )

    saved = asyncio.run(
        admin_save_knowledge_file(payload, admin_request())
    )
    files = asyncio.run(admin_knowledge_files(admin_request()))
    deleted = asyncio.run(
        admin_delete_knowledge_file("admin-test.md", admin_request())
    )

    assert saved["status"] == "saved"
    assert files[0]["filename"] == "admin-test.md"
    assert deleted["status"] == "deleted"
    assert not (tmp_path / "knowledge" / "admin-test.md").exists()


def test_user_listing_and_role_management(tmp_path):
    store = ConversationStore(tmp_path / "admin.db")
    store.initialize()
    auth = AuthService(store.engine)
    first_admin = auth.create_user(
        "first-admin",
        "a-secure-password",
        role="admin",
    )
    second_admin = auth.create_user(
        "second-admin",
        "a-secure-password",
        role="admin",
    )
    regular = auth.create_user(
        "regular-user",
        "a-secure-password",
        role="user",
    )

    promoted = store.update_user_role(
        user_id=regular.user_id,
        role="admin",
    )
    demoted = store.update_user_role(
        user_id=second_admin.user_id,
        role="user",
    )
    rows = store.list_users()

    assert promoted["role"] == "admin"
    assert demoted["role"] == "user"
    assert {row["user_id"] for row in rows} == {
        first_admin.user_id,
        second_admin.user_id,
        regular.user_id,
    }
