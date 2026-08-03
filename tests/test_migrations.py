"""Alembic 迁移建表与修订连续性的测试。"""

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.config import get_settings


def test_initial_migration_creates_schema(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("alembic.ini")

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {
        "conversations",
        "messages",
        "chat_turns",
        "interviews",
        "interview_turns",
        "users",
        "auth_tokens",
        "learning_tasks",
        "tool_audit_logs",
        "user_profiles",
        "interview_answer_attempts",
        "product_events",
        "deployment_releases",
        "resume_documents",
        "resume_analyses",
        "interview_reviews",
        "interview_review_turns",
        "audit_events",
        "execution_traces",
            "agent_action_confirmations",
            "coaching_memories",
            "agent_runs",
            "agent_steps",
            "assistant_feedback",
            "evaluation_candidates",
        "alembic_version",
    }.issubset(set(inspector.get_table_names()))
    assert "metadata_json" in {
        column["name"] for column in inspector.get_columns("messages")
    }
    turn_columns = {
        column["name"] for column in inspector.get_columns("interview_turns")
    }
    assert {
        "reference_answer",
        "submission_status",
        "idempotency_key",
        "answer_digest",
        "claim_token",
        "result_json",
        "submission_error",
        "processing_started_at",
        "assessment_prompt_version",
        "assessment_schema_version",
        "assessment_model_version",
    }.issubset(turn_columns)
    assert {
        "request_id",
        "interaction_type",
        "interaction_id",
    }.issubset(
        {
            column["name"]
            for column in inspector.get_columns("tool_audit_logs")
        }
    )
    assert "archived_at" in {
        column["name"] for column in inspector.get_columns("conversations")
    }
    assert {
        "next_chat_turn_index",
        "active_chat_turn_id",
        "chat_summary",
        "chat_summary_through_message_id",
    }.issubset(
        {
            column["name"]
            for column in inspector.get_columns("conversations")
        }
    )
    assert {
        "reminder_enabled",
        "reminder_time",
        "reminder_timezone",
        "avatar_data_url",
    }.issubset(
        {column["name"] for column in inspector.get_columns("user_profiles")}
    )
    assert "recovery_code_hash" in {
        column["name"] for column in inspector.get_columns("users")
    }
    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    release_columns = {
        column["name"]
        for column in inspector.get_columns("deployment_releases")
    }
    assert {
        "release_id",
        "version",
        "environment",
        "status",
        "changes_json",
        "verification_json",
        "app_image",
        "migration_revision",
    }.issubset(release_columns)
    resume_columns = {
        column["name"]
        for column in inspector.get_columns("resume_analyses")
    }
    assert {
        "analysis_id",
        "resume_id",
        "status",
        "claim_token",
        "report_json",
        "draft_json",
        "warnings_json",
        "revision",
    }.issubset(resume_columns)
    interview_columns = {
        column["name"]
        for column in inspector.get_columns("interviews")
    }
    assert {
        "source_type",
        "source_resume_id",
        "source_analysis_id",
        "source_display_name",
        "resume_context_json",
            "question_prompt_version",
            "question_schema_version",
            "question_model_version",
    }.issubset(interview_columns)
    review_columns = {
        column["name"]
        for column in inspector.get_columns("interview_reviews")
    }
    assert {
        "review_id",
        "input_type",
        "status",
        "transcript_json",
        "transcript_revision",
        "confirmed_revision",
        "claim_token",
        "report_json",
        "schema_version",
    }.issubset(review_columns)
    confirmation_columns = {
        column["name"]
        for column in inspector.get_columns("agent_action_confirmations")
    }
    assert {
        "confirmation_id",
        "user_id",
        "action_type",
        "payload_digest",
        "status",
        "expires_at",
        "consumed_at",
    }.issubset(confirmation_columns)
    trace_columns = {
        column["name"] for column in inspector.get_columns("execution_traces")
    }
    assert {"prompt_version", "schema_version", "model_version"}.issubset(
        trace_columns
    )
    memory_columns = {
        column["name"] for column in inspector.get_columns("coaching_memories")
    }
    assert {
        "memory_id",
        "user_id",
        "kind",
        "content",
        "status",
        "source_type",
        "source_revision",
        "expires_at",
    }.issubset(memory_columns)
    run_columns = {
        column["name"] for column in inspector.get_columns("agent_runs")
    }
    assert {
        "run_id",
        "user_id",
        "status",
        "idempotency_key",
        "input_digest",
        "proposal_json",
        "result_json",
    }.issubset(run_columns)
    step_columns = {
        column["name"] for column in inspector.get_columns("agent_steps")
    }
    assert {
        "step_id",
        "run_id",
        "step_type",
        "status",
        "idempotency_key",
        "claim_owner",
        "claimed_at",
        "attempt_count",
        "result_json",
    }.issubset(step_columns)
    learning_columns = {
        column["name"] for column in inspector.get_columns("learning_tasks")
    }
    assert {
        "recall_outcome",
        "difficulty_rating",
        "lapse_count",
        "review_confidence",
    }.issubset(learning_columns)
    feedback_columns = {
        column["name"] for column in inspector.get_columns("assistant_feedback")
    }
    assert {
        "feedback_id",
        "user_id",
        "turn_id",
        "rating",
        "reason_code",
        "comment",
        "prompt_version",
        "schema_version",
        "model_version",
        "source_ids_json",
    }.issubset(feedback_columns)
    assert revision == "20260731_0021"
    get_settings.cache_clear()


def test_admin_observability_migration_can_rollback(
    tmp_path,
    monkeypatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'observability-rollback.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "20260728_0012")
    engine = create_engine(database_url)

    command.downgrade(config, "20260728_0011")

    inspector = inspect(engine)
    assert "audit_events" not in inspector.get_table_names()
    assert "execution_traces" not in inspector.get_table_names()
    assert {
        "request_id",
        "interaction_type",
        "interaction_id",
    }.isdisjoint(
        {
            column["name"]
            for column in inspector.get_columns("tool_audit_logs")
        }
    )
    command.upgrade(config, "20260728_0012")
    assert {
        "audit_events",
        "execution_traces",
    }.issubset(set(inspect(engine).get_table_names()))
    get_settings.cache_clear()


def test_answer_lifecycle_migration_backfills_existing_turns(
    tmp_path,
    monkeypatch,
):
    database_url = f"sqlite:///{tmp_path / 'backfill.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "20260725_0007")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO interviews "
                "(user_id, interview_id, topic, level, total_questions, "
                "status, created_at, updated_at) VALUES "
                "('user-1', 'interview-1', 'RAG', '高级', 2, "
                "'active', 'now', 'now')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO interview_turns "
                "(user_id, interview_id, turn_index, question, answer, "
                "created_at, updated_at) VALUES "
                "('user-1', 'interview-1', 1, '已答题', '答案', 'now', 'now'), "
                "('user-1', 'interview-1', 2, '待答题', NULL, 'now', 'now')"
            )
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        statuses = connection.execute(
            text(
                "SELECT turn_index, submission_status "
                "FROM interview_turns ORDER BY turn_index"
            )
        ).all()
    assert statuses == [(1, "completed"), (2, "pending")]
    get_settings.cache_clear()


def test_chat_lifecycle_migration_derives_legacy_sequence(
    tmp_path,
    monkeypatch,
):
    database_url = f"sqlite:///{tmp_path / 'chat-backfill.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "20260726_0008")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO conversations "
                "(user_id, session_id, title, mode, created_at, updated_at) "
                "VALUES ('user-1', 'session-1', '历史', 'chat', 'now', 'now')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO messages "
                "(user_id, session_id, role, content, created_at) VALUES "
                "('user-1', 'session-1', 'user', '第一问', 'now'), "
                "('user-1', 'session-1', 'assistant', '第一答', 'now'), "
                "('user-1', 'session-1', 'user', '第二问', 'now'), "
                "('user-1', 'session-1', 'assistant', '第二答', 'now')"
            )
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        next_index = connection.execute(
            text(
                "SELECT next_chat_turn_index FROM conversations "
                "WHERE user_id = 'user-1' AND session_id = 'session-1'"
            )
        ).scalar_one()
    assert next_index == 3
    get_settings.cache_clear()


def test_chat_context_migration_preserves_history_and_defaults_summary(
    tmp_path,
    monkeypatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'context-backfill.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "20260726_0009")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO conversations "
                "(user_id, session_id, title, mode, next_chat_turn_index, "
                "created_at, updated_at) VALUES "
                "('user-1', 'session-1', '历史', 'chat', 2, 'now', 'now')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO messages "
                "(user_id, session_id, role, content, created_at) VALUES "
                "('user-1', 'session-1', 'user', '保留的问题', 'now'), "
                "('user-1', 'session-1', 'assistant', '保留的回答', 'now')"
            )
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        summary = connection.execute(
            text(
                "SELECT chat_summary, chat_summary_through_message_id "
                "FROM conversations WHERE user_id = 'user-1'"
            )
        ).one()
        message_count = connection.execute(
            text("SELECT COUNT(*) FROM messages")
        ).scalar_one()
    assert summary == ("", None)
    assert message_count == 2
    get_settings.cache_clear()
