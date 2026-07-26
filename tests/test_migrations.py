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
    }.issubset(turn_columns)
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
    assert revision == "20260726_0010"
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
