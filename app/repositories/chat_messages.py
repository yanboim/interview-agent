"""Chat message persistence slice with owner-scoped transaction boundaries."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, insert, select, update

from app.database import conversations, messages


@dataclass(frozen=True)
class StoredMessage:
    role: str
    content: str
    created_at: str
    metadata: dict[str, object]


class ChatMessageRepositoryMixin:
    """Message operations composed into ``ConversationStore`` during migration."""

    engine: Any

    def initialize(self) -> None: ...

    def append_message(
        self,
        *,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        mode: str = "chat",
        metadata_json: str | None = None,
    ) -> None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        title = content.replace("\n", " ").strip()[:60] or "新会话"
        with self.engine.begin() as connection:
            result = connection.execute(
                update(conversations)
                .where(
                    conversations.c.user_id == user_id,
                    conversations.c.session_id == session_id,
                )
                .values(
                    updated_at=now,
                    **(
                        {
                            "next_chat_turn_index": (
                                conversations.c.next_chat_turn_index + 1
                            )
                        }
                        if role == "user"
                        else {}
                    ),
                )
            )
            if result.rowcount == 0:
                connection.execute(
                    insert(conversations).values(
                        user_id=user_id,
                        session_id=session_id,
                        title=title,
                        mode=mode,
                        next_chat_turn_index=2 if role == "user" else 1,
                        created_at=now,
                        updated_at=now,
                    )
                )
            connection.execute(
                insert(messages).values(
                    user_id=user_id,
                    session_id=session_id,
                    role=role,
                    content=content,
                    metadata_json=metadata_json,
                    created_at=now,
                )
            )

    def get_messages(
        self, *, user_id: str, session_id: str
    ) -> list[StoredMessage]:
        self.initialize()
        statement = (
            select(
                messages.c.role,
                messages.c.content,
                messages.c.metadata_json,
                messages.c.created_at,
            )
            .where(
                messages.c.user_id == user_id,
                messages.c.session_id == session_id,
            )
            .order_by(messages.c.id)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            StoredMessage(
                role=str(row["role"]),
                content=str(row["content"]),
                created_at=str(row["created_at"]),
                metadata=(
                    json.loads(str(row["metadata_json"]))
                    if row["metadata_json"]
                    else {}
                ),
            )
            for row in rows
        ]

    def list_conversations(
        self, user_id: str, *, include_archived: bool = False
    ) -> list[dict[str, str | None]]:
        self.initialize()
        statement = (
            select(
                conversations.c.session_id,
                conversations.c.title,
                conversations.c.mode,
                conversations.c.archived_at,
                conversations.c.created_at,
                conversations.c.updated_at,
            )
            .where(conversations.c.user_id == user_id)
            .order_by(conversations.c.updated_at.desc())
        )
        if not include_archived:
            statement = statement.where(conversations.c.archived_at.is_(None))
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            {
                key: (str(value) if value is not None else None)
                for key, value in row.items()
            }
            for row in rows
        ]

    def archive_conversations(
        self, *, user_id: str, session_ids: list[str], archived: bool
    ) -> int:
        self.initialize()
        if not session_ids:
            return 0
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            result = connection.execute(
                update(conversations)
                .where(
                    conversations.c.user_id == user_id,
                    conversations.c.session_id.in_(session_ids),
                )
                .values(archived_at=now if archived else None, updated_at=now)
            )
        return int(result.rowcount or 0)

    def delete_conversation(self, *, user_id: str, session_id: str) -> bool:
        self.initialize()
        with self.engine.begin() as connection:
            result = connection.execute(
                delete(conversations).where(
                    conversations.c.user_id == user_id,
                    conversations.c.session_id == session_id,
                )
            )
        return bool(result.rowcount)

    def rename_conversation(
        self, *, user_id: str, session_id: str, title: str
    ) -> dict[str, str] | None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            result = connection.execute(
                update(conversations)
                .where(
                    conversations.c.user_id == user_id,
                    conversations.c.session_id == session_id,
                )
                .values(title=title.strip()[:60], updated_at=now)
            )
            if not result.rowcount:
                return None
            row = connection.execute(
                select(
                    conversations.c.session_id,
                    conversations.c.title,
                    conversations.c.mode,
                    conversations.c.created_at,
                    conversations.c.updated_at,
                ).where(
                    conversations.c.user_id == user_id,
                    conversations.c.session_id == session_id,
                )
            ).mappings().first()
        return {key: str(value) for key, value in row.items()} if row else None
