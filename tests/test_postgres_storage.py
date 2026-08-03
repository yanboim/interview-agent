"""PostgreSQL 持久化适配器的专项测试。"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.auth import AuthService
from app.database import (
    conversations,
    interviews,
    learning_tasks,
    tool_audit_logs,
    users,
)
from app.storage import ConversationStore


@pytest.mark.integration
def test_postgres_conversation_and_interview_round_trip():
    database_url = os.getenv("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is not configured")

    suffix = uuid4().hex
    user_id = f"integration-{suffix}"
    session_id = f"session-{suffix}"
    interview_id = f"interview-{suffix}"
    store = ConversationStore(database_url, auto_create_schema=False)
    auth = AuthService(store.engine)
    auth_user_id = None

    try:
        store.check_connection()
        token_pair = auth.register(
            f"integration-{suffix}",
            "integration-password-123",
        )
        auth_user_id = token_pair.user.user_id
        assert auth.resolve_access_token(token_pair.access_token) == token_pair.user
        refreshed = auth.refresh(token_pair.refresh_token)
        with pytest.raises(ValueError, match="刷新令牌无效或已过期"):
            auth.refresh(token_pair.refresh_token)
        assert auth.resolve_access_token(token_pair.access_token) == token_pair.user
        assert auth.resolve_access_token(refreshed.access_token) == token_pair.user

        store.append_message(
            user_id=user_id,
            session_id=session_id,
            role="user",
            content="PostgreSQL round trip",
        )
        assert store.get_messages(
            user_id=user_id,
            session_id=session_id,
        )[0].content == "PostgreSQL round trip"

        store.create_interview(
            user_id=user_id,
            interview_id=interview_id,
            topic="PostgreSQL",
            level="高级",
            total_questions=1,
            first_question="如何设计事务？",
        )
        status = store.save_interview_answer(
            user_id=user_id,
            interview_id=interview_id,
            turn_index=1,
            answer="明确隔离级别。",
            score=8.0,
            feedback="继续补充异常处理。",
            dimensions_json='{"accuracy": 8}',
            strengths_json='["准确"]',
            weaknesses_json='["异常处理"]',
            next_question=None,
        )
        assert status == "completed"
        assert store.get_interview(
            user_id=user_id,
            interview_id=interview_id,
        )["status"] == "completed"
        capability_rows = store.get_capability_rows(user_id=user_id)
        assert len(capability_rows) == 1
        assert capability_rows[0]["topic"] == "PostgreSQL"
        assert capability_rows[0]["score"] == 8.0
        tasks = store.create_learning_tasks(
            user_id=user_id,
            candidates=[
                {
                    "dimension": "工程实践",
                    "weakness": "异常处理",
                    "action": "补充异常场景。",
                }
            ],
            source_interview_id=interview_id,
        )
        assert len(tasks) == 1
        reviewed = store.review_learning_task(
            user_id=user_id,
            task_id=str(tasks[0]["task_id"]),
        )
        assert reviewed["review_count"] == 1
        store.record_tool_audit(
            user_id=user_id,
            role="user",
            tool_name="get_learning_progress",
            input_summary="PostgreSQL",
            status="success",
            duration_ms=12,
            result_summary="ok",
        )
        assert store.list_tool_audits(user_id=user_id)[0]["duration_ms"] == 12
    finally:
        with store.engine.begin() as connection:
            connection.execute(
                delete(tool_audit_logs).where(
                    tool_audit_logs.c.user_id == user_id
                )
            )
            connection.execute(
                delete(learning_tasks).where(
                    learning_tasks.c.user_id == user_id
                )
            )
            connection.execute(
                delete(interviews).where(interviews.c.user_id == user_id)
            )
            connection.execute(
                delete(conversations).where(conversations.c.user_id == user_id)
            )
            if auth_user_id:
                connection.execute(
                    delete(users).where(users.c.user_id == auth_user_id)
                )
