from types import SimpleNamespace
from unittest.mock import MagicMock

from app.storage import ConversationStore
from app.tool_context import reset_tool_identity, set_tool_identity
from app.tools import (
    _get_tool_store,
    get_learning_progress,
    search_public_web,
)


def test_learning_progress_tool_uses_authenticated_identity(tmp_path, monkeypatch):
    store = ConversationStore(tmp_path / "tools.db")
    monkeypatch.setattr("app.tools._get_tool_store", lambda: store)
    token = set_tool_identity("user-a", "user")
    try:
        result = get_learning_progress.invoke({"topic": ""})
    finally:
        reset_tool_identity(token)

    assert '"answered_questions": 0' in result
    audits = store.list_tool_audits(user_id="user-a")
    assert audits[0]["tool_name"] == "get_learning_progress"
    assert audits[0]["status"] == "success"


def test_web_search_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(
        "app.tools.get_settings",
        lambda: SimpleNamespace(
            web_search_enabled=False,
            web_search_api_key="",
        ),
    )
    result = search_public_web.invoke({"query": "最新 Java LTS"})
    assert result == "联网搜索未启用。"


def test_web_search_returns_traceable_sources(monkeypatch):
    settings = SimpleNamespace(
        web_search_enabled=True,
        web_search_api_key="test-key",
        web_search_api_url="https://search.example/api",
        web_search_max_results=3,
        web_search_timeout_seconds=5,
    )
    response = MagicMock()
    response.json.return_value = {
        "results": [
            {
                "title": "Java",
                "url": "https://example.com/java",
                "content": "最新版本信息",
            }
        ]
    }
    monkeypatch.setattr("app.tools.get_settings", lambda: settings)
    post = MagicMock(return_value=response)
    monkeypatch.setattr("app.tools.httpx.post", post)

    result = search_public_web.invoke({"query": "最新 Java LTS"})

    assert "https://example.com/java" in result
    assert "抓取时间" in result
    post.assert_called_once()


def test_web_search_blocks_likely_secrets(monkeypatch):
    monkeypatch.setattr(
        "app.tools.get_settings",
        lambda: SimpleNamespace(
            web_search_enabled=True,
            web_search_api_key="test-key",
            web_search_api_url="https://search.example/api",
            web_search_max_results=3,
            web_search_timeout_seconds=5,
        ),
    )
    try:
        search_public_web.invoke(
            {"query": "查一下 sk-abcdefghijklmnopqrstuvwxyz"}
        )
    except ValueError as exc:
        assert "密钥或令牌" in str(exc)
    else:
        raise AssertionError("secret-bearing query should be rejected")
