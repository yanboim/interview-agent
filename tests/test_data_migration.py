from sqlalchemy import create_engine

from app.database import metadata
from app.storage import ConversationStore
from scripts.migrate_sqlite_to_postgres import migrate


def test_migrate_between_empty_databases(tmp_path):
    source_url = f"sqlite:///{tmp_path / 'source.db'}"
    target_url = f"sqlite:///{tmp_path / 'target.db'}"
    source = ConversationStore(source_url)
    source.append_message(
        user_id="user-1",
        session_id="session-1",
        role="user",
        content="迁移测试",
    )
    target_engine = create_engine(target_url)
    metadata.create_all(target_engine)

    counts = migrate(source_url, target_url)

    target = ConversationStore(target_url, auto_create_schema=False)
    assert counts["messages"] == 1
    assert target.get_messages(
        user_id="user-1",
        session_id="session-1",
    )[0].content == "迁移测试"
