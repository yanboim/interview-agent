import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    and_,
    create_engine,
    delete,
    event,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.chat_context import ContextMessage, plan_chat_context
from app.database import (
    audit_events,
    auth_tokens,
    chat_turns,
    conversations,
    deployment_releases,
    execution_traces,
    interview_answer_attempts,
    interview_turns,
    interviews,
    learning_tasks,
    messages,
    metadata,
    normalize_database_url,
    product_events,
    tool_audit_logs,
    user_profiles,
    users,
)

_SENSITIVE_AUDIT_KEYS = {
    "answer",
    "api_key",
    "authorization",
    "content",
    "message",
    "password",
    "prompt",
    "recovery_code",
    "refresh_token",
    "secret",
    "token",
}


def _sanitize_observability_detail(
    value: object,
    *,
    key: str = "",
) -> object:
    normalized = key.casefold().replace("-", "_")
    if any(part in normalized for part in _SENSITIVE_AUDIT_KEYS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(child_key): _sanitize_observability_detail(
                child_value,
                key=str(child_key),
            )
            for child_key, child_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_observability_detail(item, key=key)
            for item in value[:100]
        ]
    if isinstance(value, str):
        return value[:500]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:500]


@dataclass(frozen=True)
class StoredMessage:
    role: str
    content: str
    created_at: str
    metadata: dict[str, object]


class ConversationStore:
    def __init__(
        self,
        database: str | Path,
        *,
        auto_create_schema: bool = True,
    ) -> None:
        self.database_url = normalize_database_url(database)
        self.auto_create_schema = auto_create_schema
        if self.database_url.startswith("sqlite:///"):
            sqlite_path = Path(self.database_url.removeprefix("sqlite:///"))
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
            connect_args=(
                {"check_same_thread": False}
                if self.database_url.startswith("sqlite:")
                else {}
            ),
        )
        if self.database_url.startswith("sqlite:"):
            @event.listens_for(self.engine, "connect")
            def enable_sqlite_foreign_keys(
                dbapi_connection,
                _connection_record,
            ) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.close()
        # This lock only avoids duplicate local create_all work. Business
        # transitions rely exclusively on database transactions/constraints.
        self._initialization_lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        with self._initialization_lock:
            if self._initialized:
                return
            if self.auto_create_schema:
                metadata.create_all(self.engine)
            self._initialized = True

    def check_connection(self) -> None:
        self.initialize()
        with self.engine.connect() as connection:
            connection.execute(select(1))
            connection.execute(select(conversations.c.user_id).limit(1))

    def system_counts(self) -> dict[str, int]:
        self.initialize()
        tables = {
            "users": users,
            "conversations": conversations,
            "messages": messages,
            "chat_turns": chat_turns,
            "interviews": interviews,
            "interview_turns": interview_turns,
            "learning_tasks": learning_tasks,
            "tool_audit_logs": tool_audit_logs,
            "audit_events": audit_events,
            "execution_traces": execution_traces,
            "user_profiles": user_profiles,
            "interview_answer_attempts": interview_answer_attempts,
            "product_events": product_events,
            "deployment_releases": deployment_releases,
        }
        now = datetime.now(UTC).isoformat()
        with self.engine.connect() as connection:
            counts = {
                name: int(
                    connection.execute(
                        select(func.count()).select_from(table)
                    ).scalar_one()
                )
                for name, table in tables.items()
            }
            counts["active_tokens"] = int(
                connection.execute(
                    select(func.count())
                    .select_from(auth_tokens)
                    .where(
                        auth_tokens.c.revoked_at.is_(None),
                        auth_tokens.c.expires_at > now,
                    )
                ).scalar_one()
            )
            return counts

    def list_users(self, *, limit: int = 200) -> list[dict[str, object]]:
        self.initialize()
        statement = (
            select(
                users.c.user_id,
                users.c.username,
                users.c.role,
                users.c.created_at,
                users.c.updated_at,
                func.count(func.distinct(conversations.c.session_id)).label(
                    "conversation_count"
                ),
                func.count(func.distinct(interviews.c.interview_id)).label(
                    "interview_count"
                ),
            )
            .select_from(
                users.outerjoin(
                    conversations,
                    conversations.c.user_id == users.c.user_id,
                ).outerjoin(
                    interviews,
                    interviews.c.user_id == users.c.user_id,
                )
            )
            .group_by(
                users.c.user_id,
                users.c.username,
                users.c.role,
                users.c.created_at,
                users.c.updated_at,
            )
            .order_by(users.c.created_at.desc())
            .limit(max(1, min(limit, 500)))
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def update_user_role(self, *, user_id: str, role: str) -> dict[str, object]:
        if role not in {"user", "admin"}:
            raise ValueError("不支持的用户角色")
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            current = connection.execute(
                select(users.c.role).where(users.c.user_id == user_id)
            ).scalar_one_or_none()
            if current is None:
                raise ValueError("用户不存在")
            if current == "admin" and role != "admin":
                admin_count = connection.execute(
                    select(func.count())
                    .select_from(users)
                    .where(users.c.role == "admin")
                ).scalar_one()
                if int(admin_count) <= 1:
                    raise ValueError("不能降级系统中最后一个管理员")
            connection.execute(
                update(users)
                .where(users.c.user_id == user_id)
                .values(role=role, updated_at=now)
            )
            row = connection.execute(
                select(
                    users.c.user_id,
                    users.c.username,
                    users.c.role,
                    users.c.created_at,
                    users.c.updated_at,
                ).where(users.c.user_id == user_id)
            ).mappings().one()
        return dict(row)

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
        self,
        *,
        user_id: str,
        session_id: str,
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

    def begin_chat_turn(
        self,
        *,
        user_id: str,
        session_id: str,
        content: str,
        idempotency_key: str,
        request_digest: str,
        turn_id: str,
        claim_token: str,
        context_token_budget: int,
        summary_token_budget: int,
    ) -> dict[str, object]:
        """Claim the session before a chat model invocation."""
        self.initialize()
        now = datetime.now(UTC).isoformat()
        title = content.replace("\n", " ").strip()[:60] or "新会话"

        try:
            with self.engine.begin() as connection:
                exists = connection.execute(
                    select(conversations.c.session_id).where(
                        conversations.c.user_id == user_id,
                        conversations.c.session_id == session_id,
                    )
                ).first()
                if not exists:
                    connection.execute(
                        insert(conversations).values(
                            user_id=user_id,
                            session_id=session_id,
                            title=title,
                            mode="chat",
                            next_chat_turn_index=1,
                            created_at=now,
                            updated_at=now,
                        )
                    )
        except IntegrityError:
            # Another replica created the same conversation first.
            pass

        with self.engine.begin() as connection:
            existing = connection.execute(
                select(chat_turns).where(
                    chat_turns.c.user_id == user_id,
                    chat_turns.c.session_id == session_id,
                    chat_turns.c.idempotency_key == idempotency_key,
                )
            ).mappings().first()
            if existing:
                if existing["request_digest"] != request_digest:
                    return {"outcome": "key_reused"}
                status = str(existing["status"])
                if status == "completed":
                    return {
                        "outcome": "completed",
                        "turn_id": str(existing["turn_id"]),
                        "answer": str(existing["assistant_content"] or ""),
                        "metadata": (
                            json.loads(str(existing["metadata_json"]))
                            if existing["metadata_json"]
                            else {}
                        ),
                    }
                if status in {"pending", "generating"}:
                    return {"outcome": "in_progress"}
                if status not in {"failed", "cancelled"}:
                    return {"outcome": "conflict"}

                active = connection.execute(
                    update(conversations)
                    .where(
                        conversations.c.user_id == user_id,
                        conversations.c.session_id == session_id,
                        conversations.c.active_chat_turn_id.is_(None),
                    )
                    .values(
                        active_chat_turn_id=existing["turn_id"],
                        updated_at=now,
                    )
                )
                if active.rowcount != 1:
                    return {"outcome": "conflict"}
                claimed = connection.execute(
                    update(chat_turns)
                    .where(
                        chat_turns.c.turn_id == existing["turn_id"],
                        chat_turns.c.status.in_(("failed", "cancelled")),
                        chat_turns.c.request_digest == request_digest,
                    )
                    .values(
                        status="generating",
                        claim_token=claim_token,
                        assistant_content=None,
                        metadata_json=None,
                        error=None,
                        updated_at=now,
                    )
                )
                if claimed.rowcount != 1:
                    raise ValueError("chat turn claim lost")
                claimed_turn_id = str(existing["turn_id"])
                turn_index = int(existing["turn_index"])
            else:
                activated = connection.execute(
                    update(conversations)
                    .where(
                        conversations.c.user_id == user_id,
                        conversations.c.session_id == session_id,
                        conversations.c.active_chat_turn_id.is_(None),
                    )
                    .values(
                        active_chat_turn_id=turn_id,
                        next_chat_turn_index=(
                            conversations.c.next_chat_turn_index + 1
                        ),
                        updated_at=now,
                    )
                )
                if activated.rowcount != 1:
                    return {"outcome": "conflict"}
                next_index = connection.execute(
                    select(conversations.c.next_chat_turn_index).where(
                        conversations.c.user_id == user_id,
                        conversations.c.session_id == session_id,
                    )
                ).scalar_one()
                turn_index = int(next_index) - 1
                connection.execute(
                    insert(chat_turns).values(
                        turn_id=turn_id,
                        user_id=user_id,
                        session_id=session_id,
                        turn_index=turn_index,
                        idempotency_key=idempotency_key,
                        request_digest=request_digest,
                        request_content=content,
                        status="pending",
                        created_at=now,
                        updated_at=now,
                    )
                )
                claimed = connection.execute(
                    update(chat_turns)
                    .where(
                        chat_turns.c.turn_id == turn_id,
                        chat_turns.c.status == "pending",
                    )
                    .values(
                        status="generating",
                        claim_token=claim_token,
                        updated_at=now,
                    )
                )
                if claimed.rowcount != 1:
                    raise ValueError("chat turn claim lost")
                claimed_turn_id = turn_id

            conversation = connection.execute(
                select(
                    conversations.c.chat_summary,
                    conversations.c.chat_summary_through_message_id,
                ).where(
                    conversations.c.user_id == user_id,
                    conversations.c.session_id == session_id,
                )
            ).mappings().one()
            history = connection.execute(
                select(messages.c.id, messages.c.role, messages.c.content)
                .where(
                    messages.c.user_id == user_id,
                    messages.c.session_id == session_id,
                    *(
                        (
                            messages.c.id
                            > conversation[
                                "chat_summary_through_message_id"
                            ],
                        )
                        if conversation["chat_summary_through_message_id"]
                        is not None
                        else ()
                    ),
                )
                .order_by(messages.c.id)
            ).mappings().all()
            context = plan_chat_context(
                (
                    ContextMessage(
                        id=int(row["id"]),
                        role=str(row["role"]),
                        content=str(row["content"]),
                    )
                    for row in history
                ),
                current_content=content,
                existing_summary=str(conversation["chat_summary"] or ""),
                summary_through_message_id=(
                    int(conversation["chat_summary_through_message_id"])
                    if conversation["chat_summary_through_message_id"]
                    is not None
                    else None
                ),
                token_budget=context_token_budget,
                summary_token_budget=summary_token_budget,
            )
            if (
                context.summary_through_message_id
                != conversation["chat_summary_through_message_id"]
                or context.summary != str(conversation["chat_summary"] or "")
            ):
                connection.execute(
                    update(conversations)
                    .where(
                        conversations.c.user_id == user_id,
                        conversations.c.session_id == session_id,
                    )
                    .values(
                        chat_summary=context.summary,
                        chat_summary_through_message_id=(
                            context.summary_through_message_id
                        ),
                        updated_at=now,
                    )
                )
            return {
                "outcome": "claimed",
                "turn_id": claimed_turn_id,
                "turn_index": turn_index,
                "claim_token": claim_token,
                "history": list(context.history),
                "context_estimated_tokens": context.estimated_tokens,
                "context_truncated_messages": context.truncated_messages,
            }

    def complete_chat_turn(
        self,
        *,
        user_id: str,
        session_id: str,
        turn_id: str,
        claim_token: str,
        answer: str,
        metadata: dict[str, object],
    ) -> None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        metadata_json = (
            json.dumps(metadata, ensure_ascii=False)
            if metadata
            else None
        )
        with self.engine.begin() as connection:
            turn = connection.execute(
                select(
                    chat_turns.c.request_content,
                    chat_turns.c.turn_index,
                ).where(
                    chat_turns.c.turn_id == turn_id,
                    chat_turns.c.user_id == user_id,
                    chat_turns.c.session_id == session_id,
                    chat_turns.c.status == "generating",
                    chat_turns.c.claim_token == claim_token,
                )
            ).mappings().first()
            if not turn:
                raise ValueError("chat turn claim lost")

            completed = connection.execute(
                update(chat_turns)
                .where(
                    chat_turns.c.turn_id == turn_id,
                    chat_turns.c.status == "generating",
                    chat_turns.c.claim_token == claim_token,
                )
                .values(
                    status="completed",
                    claim_token=None,
                    assistant_content=answer,
                    metadata_json=metadata_json,
                    error=None,
                    updated_at=now,
                )
            )
            if completed.rowcount != 1:
                raise ValueError("chat turn claim lost")
            connection.execute(
                insert(messages),
                [
                    {
                        "user_id": user_id,
                        "session_id": session_id,
                        "role": "user",
                        "content": str(turn["request_content"]),
                        "metadata_json": None,
                        "created_at": now,
                    },
                    {
                        "user_id": user_id,
                        "session_id": session_id,
                        "role": "assistant",
                        "content": answer,
                        "metadata_json": metadata_json,
                        "created_at": now,
                    },
                ],
            )
            released = connection.execute(
                update(conversations)
                .where(
                    conversations.c.user_id == user_id,
                    conversations.c.session_id == session_id,
                    conversations.c.active_chat_turn_id == turn_id,
                )
                .values(active_chat_turn_id=None, updated_at=now)
            )
            if released.rowcount != 1:
                raise ValueError("chat session ownership lost")

    def terminate_chat_turn(
        self,
        *,
        turn_id: str,
        claim_token: str,
        status: str,
        partial_answer: str,
        error: str,
    ) -> bool:
        if status not in {"failed", "cancelled"}:
            raise ValueError("invalid terminal chat status")
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            turn = connection.execute(
                select(
                    chat_turns.c.user_id,
                    chat_turns.c.session_id,
                ).where(
                    chat_turns.c.turn_id == turn_id,
                    chat_turns.c.status == "generating",
                    chat_turns.c.claim_token == claim_token,
                )
            ).mappings().first()
            if not turn:
                return False
            changed = connection.execute(
                update(chat_turns)
                .where(
                    chat_turns.c.turn_id == turn_id,
                    chat_turns.c.status == "generating",
                    chat_turns.c.claim_token == claim_token,
                )
                .values(
                    status=status,
                    claim_token=None,
                    assistant_content=partial_answer,
                    error=error[:1000],
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                return False
            released = connection.execute(
                update(conversations)
                .where(
                    conversations.c.user_id == turn["user_id"],
                    conversations.c.session_id == turn["session_id"],
                    conversations.c.active_chat_turn_id == turn_id,
                )
                .values(active_chat_turn_id=None, updated_at=now)
            )
            if released.rowcount != 1:
                raise ValueError("chat session ownership lost")
        return True

    def get_chat_turn(
        self,
        *,
        user_id: str,
        session_id: str,
        turn_id: str,
    ) -> dict[str, object] | None:
        self.initialize()
        with self.engine.connect() as connection:
            row = connection.execute(
                select(chat_turns).where(
                    chat_turns.c.user_id == user_id,
                    chat_turns.c.session_id == session_id,
                    chat_turns.c.turn_id == turn_id,
                )
            ).mappings().first()
        return dict(row) if row else None

    def list_conversations(
        self,
        user_id: str,
        *,
        include_archived: bool = False,
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
        self,
        *,
        user_id: str,
        session_ids: list[str],
        archived: bool,
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
                .values(
                    archived_at=now if archived else None,
                    updated_at=now,
                )
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
        self,
        *,
        user_id: str,
        session_id: str,
        title: str,
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
        return (
            {key: str(value) for key, value in row.items()}
            if row
            else None
        )

    def create_interview(
        self,
        *,
        user_id: str,
        interview_id: str,
        topic: str,
        level: str,
        total_questions: int,
        first_question: str,
    ) -> None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                insert(interviews).values(
                    user_id=user_id,
                    interview_id=interview_id,
                    topic=topic,
                    level=level,
                    total_questions=total_questions,
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
            connection.execute(
                insert(interview_turns).values(
                    user_id=user_id,
                    interview_id=interview_id,
                    turn_index=1,
                    question=first_question,
                    created_at=now,
                    updated_at=now,
                )
            )

    def get_interview(
        self,
        *,
        user_id: str,
        interview_id: str,
    ) -> dict[str, object] | None:
        self.initialize()
        statement = select(interviews).where(
            interviews.c.user_id == user_id,
            interviews.c.interview_id == interview_id,
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return dict(row) if row else None

    def list_interviews(
        self,
        *,
        user_id: str,
        include_archived: bool = False,
    ) -> list[dict[str, object]]:
        self.initialize()
        statement = (
            select(
                interviews.c.interview_id,
                interviews.c.topic,
                interviews.c.level,
                interviews.c.total_questions,
                interviews.c.status,
                interviews.c.archived_at,
                interviews.c.created_at,
                interviews.c.updated_at,
                func.count(interview_turns.c.answer).label(
                    "answered_questions"
                ),
                func.avg(interview_turns.c.score).label("average_score"),
            )
            .select_from(
                interviews.outerjoin(
                    interview_turns,
                    (interviews.c.user_id == interview_turns.c.user_id)
                    & (
                        interviews.c.interview_id
                        == interview_turns.c.interview_id
                    ),
                )
            )
            .where(interviews.c.user_id == user_id)
            .group_by(
                interviews.c.interview_id,
                interviews.c.topic,
                interviews.c.level,
                interviews.c.total_questions,
                interviews.c.status,
                interviews.c.archived_at,
                interviews.c.created_at,
                interviews.c.updated_at,
            )
            .order_by(interviews.c.updated_at.desc())
        )
        if not include_archived:
            statement = statement.where(interviews.c.archived_at.is_(None))
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        result = []
        for row in rows:
            item = dict(row)
            item["answered_questions"] = int(
                item["answered_questions"] or 0
            )
            item["average_score"] = (
                round(float(item["average_score"]), 2)
                if item["average_score"] is not None
                else None
            )
            result.append(item)
        return result

    def archive_interview(
        self,
        *,
        user_id: str,
        interview_id: str,
        archived: bool = True,
    ) -> bool:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            result = connection.execute(
                update(interviews)
                .where(
                    interviews.c.user_id == user_id,
                    interviews.c.interview_id == interview_id,
                )
                .values(
                    archived_at=now if archived else None,
                    updated_at=now,
                )
            )
        return bool(result.rowcount)

    def delete_interview(
        self,
        *,
        user_id: str,
        interview_id: str,
    ) -> bool:
        self.initialize()
        with self.engine.begin() as connection:
            result = connection.execute(
                delete(interviews).where(
                    interviews.c.user_id == user_id,
                    interviews.c.interview_id == interview_id,
                )
            )
        return bool(result.rowcount)

    def get_interview_turns(
        self,
        *,
        user_id: str,
        interview_id: str,
    ) -> list[dict[str, object]]:
        self.initialize()
        statement = (
            select(
                interview_turns.c.turn_index,
                interview_turns.c.question,
                interview_turns.c.answer,
                interview_turns.c.score,
                interview_turns.c.feedback,
                interview_turns.c.dimensions_json,
                interview_turns.c.strengths_json,
                interview_turns.c.weaknesses_json,
                interview_turns.c.reference_answer,
                interview_turns.c.created_at,
                interview_turns.c.updated_at,
            )
            .where(
                interview_turns.c.user_id == user_id,
                interview_turns.c.interview_id == interview_id,
            )
            .order_by(interview_turns.c.turn_index)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def get_user_profile(self, *, user_id: str) -> dict[str, object] | None:
        self.initialize()
        with self.engine.connect() as connection:
            row = connection.execute(
                select(user_profiles).where(user_profiles.c.user_id == user_id)
            ).mappings().first()
        return dict(row) if row else None

    def upsert_user_profile(
        self,
        *,
        user_id: str,
        target_role: str,
        experience_level: str,
        focus_areas: str,
        interview_date: str | None,
        job_description: str,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        values = {
            "target_role": target_role,
            "experience_level": experience_level,
            "focus_areas": focus_areas,
            "interview_date": interview_date or None,
            "job_description": job_description,
            "updated_at": now,
        }
        with self.engine.begin() as connection:
            result = connection.execute(
                update(user_profiles)
                .where(user_profiles.c.user_id == user_id)
                .values(**values)
            )
            if not result.rowcount:
                connection.execute(
                    insert(user_profiles).values(
                        user_id=user_id,
                        created_at=now,
                        **values,
                    )
                )
            row = connection.execute(
                select(user_profiles).where(user_profiles.c.user_id == user_id)
            ).mappings().one()
        return dict(row)

    def update_reminder_preferences(
        self,
        *,
        user_id: str,
        enabled: bool,
        reminder_time: str,
        timezone: str,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        values = {
            "reminder_enabled": enabled,
            "reminder_time": reminder_time,
            "reminder_timezone": timezone,
            "updated_at": now,
        }
        with self.engine.begin() as connection:
            result = connection.execute(
                update(user_profiles)
                .where(user_profiles.c.user_id == user_id)
                .values(**values)
            )
            if not result.rowcount:
                connection.execute(
                    insert(user_profiles).values(
                        user_id=user_id,
                        target_role="",
                        experience_level="高级",
                        focus_areas="",
                        job_description="",
                        created_at=now,
                        **values,
                    )
                )
            row = connection.execute(
                select(user_profiles).where(user_profiles.c.user_id == user_id)
            ).mappings().one()
        return dict(row)

    def update_profile_avatar(
        self,
        *,
        user_id: str,
        avatar_data_url: str | None,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        values = {
            "avatar_data_url": avatar_data_url,
            "updated_at": now,
        }
        with self.engine.begin() as connection:
            result = connection.execute(
                update(user_profiles)
                .where(user_profiles.c.user_id == user_id)
                .values(**values)
            )
            if not result.rowcount:
                connection.execute(
                    insert(user_profiles).values(
                        user_id=user_id,
                        target_role="",
                        experience_level="高级",
                        focus_areas="",
                        job_description="",
                        created_at=now,
                        **values,
                    )
                )
            row = connection.execute(
                select(user_profiles).where(user_profiles.c.user_id == user_id)
            ).mappings().one()
        return dict(row)

    def record_product_event(
        self,
        *,
        user_id: str,
        event_name: str,
        session_id: str | None,
        properties: dict[str, object],
    ) -> None:
        self.initialize()
        with self.engine.begin() as connection:
            connection.execute(
                insert(product_events).values(
                    event_id=str(uuid4()),
                    user_id=user_id,
                    session_id=session_id,
                    event_name=event_name,
                    properties_json=json.dumps(
                        properties,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    created_at=datetime.now(UTC).isoformat(),
                )
            )

    def list_product_events(
        self,
        *,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        self.initialize()
        statement = select(product_events)
        if user_id:
            statement = statement.where(product_events.c.user_id == user_id)
        statement = statement.order_by(
            product_events.c.created_at.desc()
        ).limit(min(max(limit, 1), 500))
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def record_audit_event(
        self,
        *,
        request_id: str,
        actor_user_id: str | None,
        actor_username: str | None,
        actor_role: str | None,
        action: str,
        resource_type: str,
        resource_id: str | None,
        outcome: str,
        method: str,
        path: str,
        status_code: int,
        duration_ms: int,
        detail: dict[str, object] | None = None,
    ) -> None:
        self.initialize()
        safe_detail = _sanitize_observability_detail(detail or {})
        with self.engine.begin() as connection:
            connection.execute(
                insert(audit_events).values(
                    event_id=str(uuid4()),
                    request_id=request_id[:128],
                    actor_user_id=actor_user_id,
                    actor_username=actor_username,
                    actor_role=actor_role,
                    action=action[:160],
                    resource_type=resource_type[:80],
                    resource_id=resource_id[:256] if resource_id else None,
                    outcome=outcome,
                    method=method[:10],
                    path=path[:300],
                    status_code=int(status_code),
                    duration_ms=max(0, int(duration_ms)),
                    detail_json=json.dumps(
                        safe_detail,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        default=str,
                    )[:4000],
                    created_at=datetime.now(UTC).isoformat(),
                )
            )

    def list_audit_events(
        self,
        *,
        user_id: str | None = None,
        action: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        self.initialize()
        statement = select(audit_events)
        if user_id:
            statement = statement.where(
                audit_events.c.actor_user_id == user_id
            )
        if action:
            statement = statement.where(audit_events.c.action == action)
        if outcome:
            statement = statement.where(audit_events.c.outcome == outcome)
        statement = statement.order_by(
            audit_events.c.created_at.desc()
        ).limit(min(max(limit, 1), 500))
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def record_execution_trace(
        self,
        *,
        request_id: str,
        user_id: str,
        interaction_type: str,
        interaction_id: str,
        stage: str,
        status: str,
        duration_ms: int | None = None,
        detail: dict[str, object] | None = None,
    ) -> None:
        self.initialize()
        with self.engine.begin() as connection:
            connection.execute(
                insert(execution_traces).values(
                    trace_id=str(uuid4()),
                    request_id=request_id[:128],
                    user_id=user_id[:128],
                    interaction_type=interaction_type[:30],
                    interaction_id=interaction_id[:256],
                    stage=stage[:80],
                    status=status[:30],
                    duration_ms=(
                        max(0, int(duration_ms))
                        if duration_ms is not None
                        else None
                    ),
                    detail_json=json.dumps(
                        _sanitize_observability_detail(detail or {}),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        default=str,
                    )[:4000],
                    created_at=datetime.now(UTC).isoformat(),
                )
            )

    def list_admin_interactions(
        self,
        *,
        interaction_type: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        self.initialize()
        bounded_limit = min(max(limit, 1), 200)
        result: list[dict[str, object]] = []
        with self.engine.connect() as connection:
            if interaction_type in {None, "chat"}:
                chat_statement = (
                    select(
                        chat_turns,
                        users.c.username,
                        conversations.c.title.label("container_title"),
                    )
                    .select_from(
                        chat_turns.join(
                            users,
                            users.c.user_id == chat_turns.c.user_id,
                        ).join(
                            conversations,
                            and_(
                                conversations.c.user_id
                                == chat_turns.c.user_id,
                                conversations.c.session_id
                                == chat_turns.c.session_id,
                            ),
                        )
                    )
                    .order_by(chat_turns.c.created_at.desc())
                    .limit(bounded_limit)
                )
                if user_id:
                    chat_statement = chat_statement.where(
                        chat_turns.c.user_id == user_id
                    )
                for row in connection.execute(
                    chat_statement
                ).mappings():
                    result.append(
                        {
                            "interaction_type": "chat",
                            "interaction_id": str(row["turn_id"]),
                            "user_id": str(row["user_id"]),
                            "username": str(row["username"]),
                            "container_id": str(row["session_id"]),
                            "container_title": str(row["container_title"]),
                            "prompt_text": "",
                            "input_text": str(row["request_content"]),
                            "output_text": str(
                                row["assistant_content"] or ""
                            ),
                            "status": str(row["status"]),
                            "error": str(row["error"] or ""),
                            "metadata_json": str(
                                row["metadata_json"] or "{}"
                            ),
                            "created_at": str(row["created_at"]),
                            "updated_at": str(row["updated_at"]),
                        }
                    )
            if interaction_type in {None, "interview"}:
                interview_statement = (
                    select(
                        interview_turns,
                        users.c.username,
                        interviews.c.topic.label("container_title"),
                    )
                    .select_from(
                        interview_turns.join(
                            users,
                            users.c.user_id == interview_turns.c.user_id,
                        ).join(
                            interviews,
                            and_(
                                interviews.c.user_id
                                == interview_turns.c.user_id,
                                interviews.c.interview_id
                                == interview_turns.c.interview_id,
                            ),
                        )
                    )
                    .where(interview_turns.c.answer.is_not(None))
                    .order_by(interview_turns.c.created_at.desc())
                    .limit(bounded_limit)
                )
                if user_id:
                    interview_statement = interview_statement.where(
                        interview_turns.c.user_id == user_id
                    )
                for row in connection.execute(
                    interview_statement
                ).mappings():
                    interaction_id = (
                        f"{row['interview_id']}:{row['turn_index']}"
                    )
                    result.append(
                        {
                            "interaction_type": "interview",
                            "interaction_id": interaction_id,
                            "user_id": str(row["user_id"]),
                            "username": str(row["username"]),
                            "container_id": str(row["interview_id"]),
                            "container_title": str(row["container_title"]),
                            "prompt_text": str(row["question"]),
                            "input_text": str(row["answer"] or ""),
                            "output_text": str(
                                row["result_json"]
                                or row["feedback"]
                                or ""
                            ),
                            "status": str(row["submission_status"]),
                            "error": str(
                                row["submission_error"] or ""
                            ),
                            "metadata_json": "{}",
                            "created_at": str(row["created_at"]),
                            "updated_at": str(row["updated_at"]),
                        }
                    )
        result.sort(key=lambda row: str(row["created_at"]), reverse=True)
        return result[:bounded_limit]

    def list_execution_trace(
        self,
        *,
        interaction_type: str,
        interaction_id: str,
    ) -> list[dict[str, object]]:
        self.initialize()
        statement = (
            select(execution_traces)
            .where(
                execution_traces.c.interaction_type == interaction_type,
                execution_traces.c.interaction_id == interaction_id,
            )
            .order_by(execution_traces.c.created_at)
        )
        tool_statement = (
            select(tool_audit_logs)
            .where(
                tool_audit_logs.c.interaction_type == interaction_type,
                tool_audit_logs.c.interaction_id == interaction_id,
            )
            .order_by(tool_audit_logs.c.created_at)
        )
        with self.engine.connect() as connection:
            traces = [
                dict(row)
                for row in connection.execute(statement).mappings()
            ]
            tools = connection.execute(tool_statement).mappings().all()
        for tool in tools:
            traces.append(
                {
                    "trace_id": str(tool["audit_id"]),
                    "request_id": str(tool["request_id"] or ""),
                    "user_id": str(tool["user_id"]),
                    "interaction_type": interaction_type,
                    "interaction_id": interaction_id,
                    "stage": f"tool:{tool['tool_name']}",
                    "status": str(tool["status"]),
                    "duration_ms": int(tool["duration_ms"]),
                    "detail_json": json.dumps(
                        {
                            "input_summary": tool["input_summary"],
                            "result_summary": tool["result_summary"],
                        },
                        ensure_ascii=False,
                    ),
                    "created_at": str(tool["created_at"]),
                }
            )
        traces.sort(key=lambda row: str(row["created_at"]))
        return traces

    def get_capability_rows(
        self,
        *,
        user_id: str,
    ) -> list[dict[str, object]]:
        self.initialize()
        statement = (
            select(
                interviews.c.interview_id,
                interviews.c.topic,
                interviews.c.level,
                interviews.c.status,
                interview_turns.c.turn_index,
                interview_turns.c.question,
                interview_turns.c.score,
                interview_turns.c.dimensions_json,
                interview_turns.c.weaknesses_json,
                interview_turns.c.updated_at,
            )
            .select_from(
                interviews.join(
                    interview_turns,
                    (interviews.c.user_id == interview_turns.c.user_id)
                    & (
                        interviews.c.interview_id
                        == interview_turns.c.interview_id
                    ),
                )
            )
            .where(
                interviews.c.user_id == user_id,
                interview_turns.c.answer.is_not(None),
                interview_turns.c.score.is_not(None),
            )
            .order_by(
                interview_turns.c.updated_at,
                interview_turns.c.turn_index,
            )
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def create_learning_tasks(
        self,
        *,
        user_id: str,
        candidates: list[dict[str, str]],
        source_interview_id: str | None = None,
    ) -> list[dict[str, object]]:
        self.initialize()
        now = datetime.now(UTC)
        now_iso = now.isoformat()
        with self.engine.begin() as connection:
            for candidate in candidates:
                existing = connection.execute(
                    select(learning_tasks.c.task_id).where(
                        learning_tasks.c.user_id == user_id,
                        learning_tasks.c.dimension
                        == candidate["dimension"],
                        learning_tasks.c.weakness
                        == candidate["weakness"],
                        learning_tasks.c.status != "completed",
                    )
                ).first()
                if existing:
                    continue
                connection.execute(
                    insert(learning_tasks).values(
                        task_id=str(uuid4()),
                        user_id=user_id,
                        source_interview_id=source_interview_id,
                        dimension=candidate["dimension"],
                        weakness=candidate["weakness"],
                        action=candidate["action"],
                        status="todo",
                        due_at=(now + timedelta(days=7)).isoformat(),
                        review_count=0,
                        next_review_at=(now + timedelta(days=1)).isoformat(),
                        created_at=now_iso,
                        updated_at=now_iso,
                    )
                )
        return self.list_learning_tasks(user_id=user_id)

    def list_learning_tasks(
        self,
        *,
        user_id: str,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        self.initialize()
        statement = select(learning_tasks).where(
            learning_tasks.c.user_id == user_id
        )
        if status:
            statement = statement.where(learning_tasks.c.status == status)
        statement = statement.order_by(
            learning_tasks.c.status,
            learning_tasks.c.due_at,
            learning_tasks.c.created_at.desc(),
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def update_learning_task(
        self,
        *,
        user_id: str,
        task_id: str,
        status: str | None = None,
        due_at: str | None = None,
    ) -> dict[str, object] | None:
        self.initialize()
        values: dict[str, object] = {
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if status is not None:
            values["status"] = status
        if due_at is not None:
            values["due_at"] = due_at
        with self.engine.begin() as connection:
            result = connection.execute(
                update(learning_tasks)
                .where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.task_id == task_id,
                )
                .values(**values)
            )
            if not result.rowcount:
                return None
            row = connection.execute(
                select(learning_tasks).where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.task_id == task_id,
                )
            ).mappings().one()
        return dict(row)

    def review_learning_task(
        self,
        *,
        user_id: str,
        task_id: str,
    ) -> dict[str, object] | None:
        from app.learning import next_review_time

        self.initialize()
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            current = connection.execute(
                select(
                    learning_tasks.c.review_count,
                    learning_tasks.c.status,
                ).where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.task_id == task_id,
                )
            ).mappings().first()
            if not current:
                return None
            review_count = int(current["review_count"]) + 1
            connection.execute(
                update(learning_tasks)
                .where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.task_id == task_id,
                )
                .values(
                    review_count=review_count,
                    last_reviewed_at=now.isoformat(),
                    next_review_at=next_review_time(
                        review_count,
                        now=now,
                    ).isoformat(),
                    status=(
                        current["status"]
                        if current["status"] == "completed"
                        else "in_progress"
                    ),
                    updated_at=now.isoformat(),
                )
            )
            row = connection.execute(
                select(learning_tasks).where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.task_id == task_id,
                )
            ).mappings().one()
        return dict(row)

    def delete_learning_task(
        self,
        *,
        user_id: str,
        task_id: str,
    ) -> bool:
        self.initialize()
        with self.engine.begin() as connection:
            result = connection.execute(
                delete(learning_tasks).where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.task_id == task_id,
                )
            )
        return bool(result.rowcount)

    def record_tool_audit(
        self,
        *,
        user_id: str,
        role: str,
        tool_name: str,
        input_summary: str,
        status: str,
        duration_ms: int,
        result_summary: str | None,
        request_id: str | None = None,
        interaction_type: str | None = None,
        interaction_id: str | None = None,
    ) -> None:
        self.initialize()
        with self.engine.begin() as connection:
            connection.execute(
                insert(tool_audit_logs).values(
                    audit_id=str(uuid4()),
                    user_id=user_id,
                    role=role,
                    tool_name=tool_name,
                    input_summary=input_summary[:500],
                    status=status,
                    duration_ms=max(0, duration_ms),
                    result_summary=(
                        result_summary[:500] if result_summary else None
                    ),
                    request_id=request_id,
                    interaction_type=interaction_type,
                    interaction_id=interaction_id,
                    created_at=datetime.now(UTC).isoformat(),
                )
            )

    def list_tool_audits(
        self,
        *,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        self.initialize()
        statement = select(tool_audit_logs)
        if user_id:
            statement = statement.where(tool_audit_logs.c.user_id == user_id)
        statement = statement.order_by(
            tool_audit_logs.c.created_at.desc()
        ).limit(min(max(limit, 1), 500))
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def record_deployment_release(
        self,
        *,
        release_id: str,
        version: str,
        title: str,
        summary: str,
        environment: str,
        status: str,
        commit_sha: str | None,
        changes: list[str],
        verification: dict[str, str],
        app_image: str | None,
        worker_image: str | None,
        migration_revision: str | None,
        recovery_point: str | None,
        triggered_by: str,
        started_at: str,
        completed_at: str | None,
    ) -> dict[str, object]:
        if environment not in {"canary", "production"}:
            raise ValueError("不支持的部署环境")
        if status not in {"deploying", "succeeded", "failed", "rolled_back"}:
            raise ValueError("不支持的发布状态")
        if not release_id.strip() or not version.strip() or not title.strip():
            raise ValueError("发布 ID、版本和标题不能为空")
        self.initialize()
        now = datetime.now(UTC).isoformat()
        values = {
            "version": version.strip()[:100],
            "title": title.strip()[:200],
            "summary": summary.strip(),
            "environment": environment,
            "status": status,
            "commit_sha": commit_sha.strip()[:64] if commit_sha else None,
            "changes_json": json.dumps(
                [item.strip()[:500] for item in changes if item.strip()],
                ensure_ascii=False,
            ),
            "verification_json": json.dumps(
                {
                    key.strip()[:100]: value.strip()[:300]
                    for key, value in verification.items()
                    if key.strip()
                },
                ensure_ascii=False,
            ),
            "app_image": app_image.strip()[:200] if app_image else None,
            "worker_image": worker_image.strip()[:200] if worker_image else None,
            "migration_revision": (
                migration_revision.strip()[:64] if migration_revision else None
            ),
            "recovery_point": (
                recovery_point.strip()[:200] if recovery_point else None
            ),
            "triggered_by": triggered_by.strip()[:100] or "deployment",
            "started_at": started_at,
            "completed_at": completed_at,
            "updated_at": now,
        }
        normalized_id = release_id.strip()[:128]
        with self.engine.begin() as connection:
            existing = connection.execute(
                select(deployment_releases.c.release_id).where(
                    deployment_releases.c.release_id == normalized_id
                )
            ).first()
            if existing:
                connection.execute(
                    update(deployment_releases)
                    .where(deployment_releases.c.release_id == normalized_id)
                    .values(**values)
                )
            else:
                connection.execute(
                    insert(deployment_releases).values(
                        release_id=normalized_id,
                        created_at=now,
                        **values,
                    )
                )
        return self.get_deployment_release(normalized_id)

    def get_deployment_release(self, release_id: str) -> dict[str, object]:
        self.initialize()
        with self.engine.connect() as connection:
            row = connection.execute(
                select(deployment_releases).where(
                    deployment_releases.c.release_id == release_id
                )
            ).mappings().first()
        if not row:
            raise KeyError("release not found")
        return self._serialize_deployment_release(dict(row))

    def list_deployment_releases(
        self,
        *,
        environment: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        self.initialize()
        statement = select(deployment_releases)
        if environment:
            statement = statement.where(
                deployment_releases.c.environment == environment
            )
        if status:
            statement = statement.where(deployment_releases.c.status == status)
        statement = statement.order_by(
            deployment_releases.c.started_at.desc()
        ).limit(min(max(limit, 1), 200))
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            self._serialize_deployment_release(dict(row))
            for row in rows
        ]

    @staticmethod
    def _serialize_deployment_release(
        row: dict[str, object],
    ) -> dict[str, object]:
        try:
            changes = json.loads(str(row.pop("changes_json")))
        except (TypeError, ValueError):
            changes = []
        try:
            verification = json.loads(str(row.pop("verification_json")))
        except (TypeError, ValueError):
            verification = {}
        row["changes"] = changes if isinstance(changes, list) else []
        row["verification"] = (
            verification if isinstance(verification, dict) else {}
        )
        return row

    def save_interview_answer(
        self,
        *,
        user_id: str,
        interview_id: str,
        turn_index: int,
        answer: str,
        score: float,
        feedback: str,
        dimensions_json: str,
        strengths_json: str,
        weaknesses_json: str,
        reference_answer: str | None = None,
        next_question: str | None = None,
    ) -> str:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            interview = connection.execute(
                select(interviews.c.total_questions).where(
                    interviews.c.user_id == user_id,
                    interviews.c.interview_id == interview_id,
                )
            ).mappings().first()
            if not interview:
                raise KeyError("interview not found")

            connection.execute(
                update(interview_turns)
                .where(
                    interview_turns.c.user_id == user_id,
                    interview_turns.c.interview_id == interview_id,
                    interview_turns.c.turn_index == turn_index,
                )
                .values(
                    answer=answer,
                    score=score,
                    feedback=feedback,
                    dimensions_json=dimensions_json,
                    strengths_json=strengths_json,
                    weaknesses_json=weaknesses_json,
                    reference_answer=reference_answer,
                    submission_status="completed",
                    updated_at=now,
                )
            )
            self._insert_interview_answer_attempt(
                connection,
                user_id=user_id,
                interview_id=interview_id,
                turn_index=turn_index,
                answer=answer,
                score=score,
                feedback=feedback,
                dimensions_json=dimensions_json,
                strengths_json=strengths_json,
                weaknesses_json=weaknesses_json,
                reference_answer=reference_answer,
                created_at=now,
            )

            status = "completed"
            if next_question and turn_index < int(interview["total_questions"]):
                connection.execute(
                    insert(interview_turns).values(
                        user_id=user_id,
                        interview_id=interview_id,
                        turn_index=turn_index + 1,
                        question=next_question,
                        created_at=now,
                        updated_at=now,
                    )
                )
                status = "active"
            connection.execute(
                update(interviews)
                .where(
                    interviews.c.user_id == user_id,
                    interviews.c.interview_id == interview_id,
                )
                .values(status=status, updated_at=now)
            )
        return status

    def claim_interview_answer(
        self,
        *,
        user_id: str,
        interview_id: str,
        idempotency_key: str,
        answer_digest: str,
        claim_token: str,
    ) -> dict[str, object]:
        """Atomically claim the one pending turn before any model call."""
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            interview = connection.execute(
                select(interviews).where(
                    interviews.c.user_id == user_id,
                    interviews.c.interview_id == interview_id,
                )
            ).mappings().first()
            if not interview:
                return {"outcome": "not_found"}
            if interview["archived_at"]:
                return {"outcome": "archived"}

            existing = connection.execute(
                select(interview_turns).where(
                    interview_turns.c.user_id == user_id,
                    interview_turns.c.interview_id == interview_id,
                    interview_turns.c.idempotency_key == idempotency_key,
                )
            ).mappings().first()
            if existing:
                if existing["answer_digest"] != answer_digest:
                    return {"outcome": "key_reused"}
                if existing["submission_status"] == "completed":
                    return {
                        "outcome": "completed",
                        "result": json.loads(str(existing["result_json"])),
                    }
                if existing["submission_status"] == "generating":
                    return {"outcome": "in_progress"}
                if existing["submission_status"] != "failed":
                    return {"outcome": "conflict"}
                candidate_id = int(existing["id"])
                claim_result = connection.execute(
                    update(interview_turns)
                    .where(
                        interview_turns.c.id == candidate_id,
                        interview_turns.c.submission_status == "failed",
                        interview_turns.c.idempotency_key == idempotency_key,
                        interview_turns.c.answer_digest == answer_digest,
                    )
                    .values(
                        submission_status="generating",
                        claim_token=claim_token,
                        submission_error=None,
                        processing_started_at=now,
                        updated_at=now,
                    )
                )
            else:
                candidate = connection.execute(
                    select(interview_turns)
                    .where(
                        interview_turns.c.user_id == user_id,
                        interview_turns.c.interview_id == interview_id,
                        interview_turns.c.answer.is_(None),
                        interview_turns.c.submission_status == "pending",
                    )
                    .order_by(interview_turns.c.turn_index)
                    .limit(1)
                ).mappings().first()
                if not candidate:
                    busy = connection.execute(
                        select(interview_turns.c.id).where(
                            interview_turns.c.user_id == user_id,
                            interview_turns.c.interview_id == interview_id,
                            interview_turns.c.answer.is_(None),
                            interview_turns.c.submission_status.in_(
                                ("generating", "failed")
                            ),
                        )
                    ).first()
                    return {
                        "outcome": "conflict" if busy else "no_pending"
                    }
                candidate_id = int(candidate["id"])
                claim_result = connection.execute(
                    update(interview_turns)
                    .where(
                        interview_turns.c.id == candidate_id,
                        interview_turns.c.answer.is_(None),
                        interview_turns.c.submission_status == "pending",
                        interview_turns.c.idempotency_key.is_(None),
                    )
                    .values(
                        submission_status="generating",
                        idempotency_key=idempotency_key,
                        answer_digest=answer_digest,
                        claim_token=claim_token,
                        submission_error=None,
                        processing_started_at=now,
                        updated_at=now,
                    )
                )

            if not claim_result.rowcount:
                replay = connection.execute(
                    select(
                        interview_turns.c.submission_status,
                        interview_turns.c.answer_digest,
                        interview_turns.c.result_json,
                    ).where(
                        interview_turns.c.user_id == user_id,
                        interview_turns.c.interview_id == interview_id,
                        interview_turns.c.idempotency_key == idempotency_key,
                    )
                ).mappings().first()
                if replay and replay["answer_digest"] != answer_digest:
                    return {"outcome": "key_reused"}
                if replay and replay["submission_status"] == "completed":
                    return {
                        "outcome": "completed",
                        "result": json.loads(str(replay["result_json"])),
                    }
                return {"outcome": "in_progress" if replay else "conflict"}

            turn = connection.execute(
                select(interview_turns).where(
                    interview_turns.c.id == candidate_id
                )
            ).mappings().one()
            turns = connection.execute(
                select(interview_turns)
                .where(
                    interview_turns.c.user_id == user_id,
                    interview_turns.c.interview_id == interview_id,
                )
                .order_by(interview_turns.c.turn_index)
            ).mappings().all()
            return {
                "outcome": "claimed",
                "interview": dict(interview),
                "turn": dict(turn),
                "turns": [dict(row) for row in turns],
            }

    def fail_interview_answer(
        self,
        *,
        turn_id: int,
        claim_token: str,
        error: str,
    ) -> bool:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            result = connection.execute(
                update(interview_turns)
                .where(
                    interview_turns.c.id == turn_id,
                    interview_turns.c.submission_status == "generating",
                    interview_turns.c.claim_token == claim_token,
                )
                .values(
                    submission_status="failed",
                    claim_token=None,
                    submission_error=error[:1000],
                    updated_at=now,
                )
            )
        return bool(result.rowcount)

    def complete_interview_answer(
        self,
        *,
        turn_id: int,
        claim_token: str,
        user_id: str,
        interview_id: str,
        turn_index: int,
        answer: str,
        score: float,
        feedback: str,
        dimensions_json: str,
        strengths_json: str,
        weaknesses_json: str,
        reference_answer: str | None,
        next_question: str | None,
        response: dict[str, object],
    ) -> str:
        """Commit the answer and successor only when the caller owns the claim."""
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            interview = connection.execute(
                select(interviews.c.total_questions).where(
                    interviews.c.user_id == user_id,
                    interviews.c.interview_id == interview_id,
                )
            ).mappings().first()
            if not interview:
                raise KeyError("interview not found")

            result = connection.execute(
                update(interview_turns)
                .where(
                    interview_turns.c.id == turn_id,
                    interview_turns.c.user_id == user_id,
                    interview_turns.c.interview_id == interview_id,
                    interview_turns.c.turn_index == turn_index,
                    interview_turns.c.submission_status == "generating",
                    interview_turns.c.claim_token == claim_token,
                )
                .values(
                    answer=answer,
                    score=score,
                    feedback=feedback,
                    dimensions_json=dimensions_json,
                    strengths_json=strengths_json,
                    weaknesses_json=weaknesses_json,
                    reference_answer=reference_answer,
                    submission_status="completed",
                    claim_token=None,
                    result_json=json.dumps(
                        response,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    submission_error=None,
                    updated_at=now,
                )
            )
            if result.rowcount != 1:
                raise ValueError("interview answer claim lost")

            self._insert_interview_answer_attempt(
                connection,
                user_id=user_id,
                interview_id=interview_id,
                turn_index=turn_index,
                answer=answer,
                score=score,
                feedback=feedback,
                dimensions_json=dimensions_json,
                strengths_json=strengths_json,
                weaknesses_json=weaknesses_json,
                reference_answer=reference_answer,
                created_at=now,
            )

            status = "completed"
            if next_question and turn_index < int(interview["total_questions"]):
                connection.execute(
                    insert(interview_turns).values(
                        user_id=user_id,
                        interview_id=interview_id,
                        turn_index=turn_index + 1,
                        question=next_question,
                        submission_status="pending",
                        created_at=now,
                        updated_at=now,
                    )
                )
                status = "active"
            connection.execute(
                update(interviews)
                .where(
                    interviews.c.user_id == user_id,
                    interviews.c.interview_id == interview_id,
                )
                .values(status=status, updated_at=now)
            )
        return status

    def retry_interview_answer(
        self,
        *,
        user_id: str,
        interview_id: str,
        turn_index: int,
        answer: str,
        score: float,
        feedback: str,
        dimensions_json: str,
        strengths_json: str,
        weaknesses_json: str,
        reference_answer: str | None,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            previous = connection.execute(
                select(
                    interview_turns.c.answer,
                    interview_turns.c.score,
                ).where(
                    interview_turns.c.user_id == user_id,
                    interview_turns.c.interview_id == interview_id,
                    interview_turns.c.turn_index == turn_index,
                )
            ).mappings().first()
            if not previous:
                raise KeyError("interview turn not found")
            if previous["answer"] is None:
                raise ValueError("interview turn has not been answered")

            attempt_index = self._insert_interview_answer_attempt(
                connection,
                user_id=user_id,
                interview_id=interview_id,
                turn_index=turn_index,
                answer=answer,
                score=score,
                feedback=feedback,
                dimensions_json=dimensions_json,
                strengths_json=strengths_json,
                weaknesses_json=weaknesses_json,
                reference_answer=reference_answer,
                created_at=now,
            )
            connection.execute(
                update(interview_turns)
                .where(
                    interview_turns.c.user_id == user_id,
                    interview_turns.c.interview_id == interview_id,
                    interview_turns.c.turn_index == turn_index,
                )
                .values(
                    answer=answer,
                    score=score,
                    feedback=feedback,
                    dimensions_json=dimensions_json,
                    strengths_json=strengths_json,
                    weaknesses_json=weaknesses_json,
                    reference_answer=reference_answer,
                    updated_at=now,
                )
            )
            connection.execute(
                update(interviews)
                .where(
                    interviews.c.user_id == user_id,
                    interviews.c.interview_id == interview_id,
                )
                .values(updated_at=now)
            )

        previous_score = float(previous["score"] or 0)
        return {
            "attempt_index": attempt_index,
            "previous_answer": str(previous["answer"]),
            "previous_score": previous_score,
            "score_delta": round(score - previous_score, 2),
        }

    def get_interview_answer_attempts(
        self,
        *,
        user_id: str,
        interview_id: str,
        turn_index: int | None = None,
    ) -> list[dict[str, object]]:
        self.initialize()
        statement = select(interview_answer_attempts).where(
            interview_answer_attempts.c.user_id == user_id,
            interview_answer_attempts.c.interview_id == interview_id,
        )
        if turn_index is not None:
            statement = statement.where(
                interview_answer_attempts.c.turn_index == turn_index
            )
        statement = statement.order_by(
            interview_answer_attempts.c.turn_index,
            interview_answer_attempts.c.attempt_index,
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    @staticmethod
    def _insert_interview_answer_attempt(
        connection,
        *,
        user_id: str,
        interview_id: str,
        turn_index: int,
        answer: str,
        score: float,
        feedback: str,
        dimensions_json: str,
        strengths_json: str,
        weaknesses_json: str,
        reference_answer: str | None,
        created_at: str,
    ) -> int:
        last_attempt = connection.execute(
            select(func.max(interview_answer_attempts.c.attempt_index)).where(
                interview_answer_attempts.c.user_id == user_id,
                interview_answer_attempts.c.interview_id == interview_id,
                interview_answer_attempts.c.turn_index == turn_index,
            )
        ).scalar_one()
        attempt_index = int(last_attempt or 0) + 1
        connection.execute(
            insert(interview_answer_attempts).values(
                attempt_id=str(uuid4()),
                user_id=user_id,
                interview_id=interview_id,
                turn_index=turn_index,
                attempt_index=attempt_index,
                answer=answer,
                score=score,
                feedback=feedback,
                dimensions_json=dimensions_json,
                strengths_json=strengths_json,
                weaknesses_json=weaknesses_json,
                reference_answer=reference_answer,
                created_at=created_at,
            )
        )
        return attempt_index
