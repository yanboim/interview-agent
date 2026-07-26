import pytest

from app.chat_context import (
    ChatContextBudgetExceeded,
    ContextMessage,
    estimate_message_tokens,
    plan_chat_context,
)


def message(message_id: int, role: str, content: str) -> ContextMessage:
    return ContextMessage(id=message_id, role=role, content=content)


def test_complete_history_passes_through_when_it_fits() -> None:
    plan = plan_chat_context(
        [
            message(1, "user", "first question"),
            message(2, "assistant", "first answer"),
        ],
        current_content="next",
        token_budget=200,
        summary_token_budget=60,
    )

    assert plan.history == (
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
    )
    assert plan.summary == ""
    assert plan.summary_through_message_id is None
    assert plan.truncated_messages == 0


def test_old_prefix_is_summarized_and_newest_messages_are_retained() -> None:
    messages = [
        message(1, "user", "a" * 30),
        message(2, "assistant", "b" * 30),
        message(3, "user", "c" * 30),
        message(4, "assistant", "d" * 30),
    ]

    plan = plan_chat_context(
        messages,
        current_content="next",
        token_budget=170,
        summary_token_budget=60,
    )

    assert plan.summary
    assert plan.summary_through_message_id == 2
    assert plan.truncated_messages == 2
    assert plan.history[0]["role"] == "system"
    assert plan.history[-2:] == (
        {"role": "user", "content": "c" * 30},
        {"role": "assistant", "content": "d" * 30},
    )
    assert plan.estimated_tokens <= 170


def test_durable_marker_prevents_resummarizing_covered_messages() -> None:
    first = plan_chat_context(
        [
            message(1, "user", "a" * 30),
            message(2, "assistant", "b" * 30),
            message(3, "user", "c" * 30),
            message(4, "assistant", "d" * 30),
        ],
        current_content="next",
        token_budget=170,
        summary_token_budget=60,
    )
    retried = plan_chat_context(
        [
            message(1, "user", "a" * 30),
            message(2, "assistant", "b" * 30),
            message(3, "user", "c" * 30),
            message(4, "assistant", "d" * 30),
        ],
        current_content="next",
        existing_summary=first.summary,
        summary_through_message_id=first.summary_through_message_id,
        token_budget=170,
        summary_token_budget=60,
    )

    assert retried.summary == first.summary
    assert retried.summary_through_message_id == 2
    assert retried.truncated_messages == 0
    assert retried.estimated_tokens <= 170


def test_current_message_over_budget_is_rejected() -> None:
    with pytest.raises(ChatContextBudgetExceeded, match="超过聊天上下文预算"):
        plan_chat_context(
            [],
            current_content="x" * 100,
            token_budget=50,
            summary_token_budget=20,
        )


def test_estimate_is_utf8_conservative() -> None:
    assert estimate_message_tokens("user", "你好") >= len(
        "user你好".encode("utf-8")
    )
