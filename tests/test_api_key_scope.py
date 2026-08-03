from app.api.security_policy import deployment_api_key_required


def test_deployment_api_key_is_not_required_for_browser_auth_or_user_apis() -> None:
    assert not deployment_api_key_required("/api/auth/register")
    assert not deployment_api_key_required("/api/auth/login")
    assert not deployment_api_key_required("/api/admin/auth/login")
    assert not deployment_api_key_required("/api/auth/me")
    assert not deployment_api_key_required("/api/chat")


def test_deployment_api_key_remains_required_for_readiness() -> None:
    assert deployment_api_key_required("/ready")
