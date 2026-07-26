import pytest

from app.auth import AuthService, AuthSurfaceError, hash_password, verify_password
from app.storage import ConversationStore


def test_password_hash_is_salted_and_verifiable():
    first_hash, first_salt = hash_password("correct horse battery staple")
    second_hash, second_salt = hash_password("correct horse battery staple")

    assert first_hash != second_hash
    assert first_salt != second_salt
    assert verify_password(
        "correct horse battery staple",
        first_hash,
        first_salt,
    )
    assert not verify_password("wrong password", first_hash, first_salt)


def test_register_login_refresh_and_revoke(tmp_path):
    store = ConversationStore(tmp_path / "auth.db")
    store.initialize()
    auth = AuthService(
        store.engine,
        access_token_minutes=1,
        refresh_token_days=1,
    )

    registered = auth.register("Engineer", "a-secure-password")
    assert registered.user.username == "engineer"
    assert auth.resolve_access_token(registered.access_token) == registered.user

    logged_in = auth.login("ENGINEER", "a-secure-password")
    refreshed = auth.refresh(logged_in.refresh_token)
    assert refreshed.user == registered.user
    assert auth.resolve_access_token(refreshed.access_token) == registered.user

    auth.revoke(refreshed.access_token)
    assert auth.resolve_access_token(refreshed.access_token) is None


def test_user_and_admin_login_surfaces_are_separated_before_token_issue(tmp_path):
    store = ConversationStore(tmp_path / "surface-login.db")
    store.initialize()
    auth = AuthService(store.engine)
    user = auth.create_user("candidate", "User-Secure-Password1", role="user")
    admin = auth.create_user("operator", "Admin-Secure-Password1", role="admin")

    assert auth.login_user("candidate", "User-Secure-Password1").user == user
    assert auth.login_admin("operator", "Admin-Secure-Password1").user == admin

    with pytest.raises(AuthSurfaceError, match="独立管理入口"):
        auth.login_user("operator", "Admin-Secure-Password1")
    with pytest.raises(AuthSurfaceError, match="不是管理员"):
        auth.login_admin("candidate", "User-Secure-Password1")


def test_change_password_revokes_sessions(tmp_path):
    store = ConversationStore(tmp_path / "password-change.db")
    store.initialize()
    auth = AuthService(store.engine)
    registered = auth.register("engineer", "Old-Secure-Password1")

    auth.change_password(
        user_id=registered.user.user_id,
        current_password="Old-Secure-Password1",
        new_password="New-Secure-Password2",
    )

    assert auth.resolve_access_token(registered.access_token) is None
    assert auth.login("engineer", "New-Secure-Password2").user == registered.user


def test_recovery_code_resets_password_once_and_rotates(tmp_path):
    store = ConversationStore(tmp_path / "password-recovery.db")
    store.initialize()
    auth = AuthService(store.engine)
    registered = auth.register("engineer", "Old-Secure-Password1")
    assert registered.recovery_code

    replacement_code = auth.reset_password(
        username="ENGINEER",
        recovery_code=str(registered.recovery_code).lower(),
        new_password="New-Secure-Password2",
    )

    assert auth.resolve_access_token(registered.access_token) is None
    assert auth.login("engineer", "New-Secure-Password2").user == registered.user
    try:
        auth.reset_password(
            username="engineer",
            recovery_code=str(registered.recovery_code),
            new_password="Another-Secure-Password3",
        )
    except ValueError as exc:
        assert "恢复码无效" in str(exc)
    else:
        raise AssertionError("旧恢复码不应重复使用")
    assert replacement_code != registered.recovery_code
