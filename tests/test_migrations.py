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
    assert "reference_answer" in {
        column["name"] for column in inspector.get_columns("interview_turns")
    }
    assert "archived_at" in {
        column["name"] for column in inspector.get_columns("conversations")
    }
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
    assert revision == "20260725_0007"
    get_settings.cache_clear()
