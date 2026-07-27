from sqlalchemy import create_engine

from app.application.chat_service import ChatTurnService
from app.database import metadata
from app.storage import ConversationStore
from scripts.migrate_sqlite_to_postgres import migrate


def test_migrate_between_empty_databases(tmp_path):
    source_url = f"sqlite:///{tmp_path / 'source.db'}"
    target_url = f"sqlite:///{tmp_path / 'target.db'}"
    source = ConversationStore(source_url)
    service = ChatTurnService(source)
    claim = service.begin(
        user_id="user-1",
        session_id="session-1",
        content="迁移测试",
        idempotency_key="chat-command-1",
    )
    service.complete(
        claim,
        user_id="user-1",
        session_id="session-1",
        answer="迁移回答",
        metadata={},
    )
    target_engine = create_engine(target_url)
    metadata.create_all(target_engine)

    counts = migrate(source_url, target_url)

    target = ConversationStore(target_url, auto_create_schema=False)
    assert counts["messages"] == 2
    assert counts["chat_turns"] == 1
    messages = target.get_messages(
        user_id="user-1",
        session_id="session-1",
    )
    assert [message.content for message in messages] == [
        "迁移测试",
        "迁移回答",
    ]
