"""SQLAlchemy Core 持久化适配器；每个写方法拥有完整业务事务和并发条件。"""

import json
import hashlib
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
    agent_action_confirmations,
    agent_runs,
    agent_steps,
    assistant_feedback,
    audit_events,
    auth_tokens,
    chat_turns,
    coaching_memories,
    conversations,
    deployment_releases,
    execution_traces,
    evaluation_candidates,
    interview_answer_attempts,
    interview_review_turns,
    interview_reviews,
    interview_turns,
    interviews,
    learning_tasks,
    messages,
    metadata,
    normalize_database_url,
    product_events,
    resume_analyses,
    resume_documents,
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
        # 此锁只避免单进程重复执行 create_all；业务并发完全依赖事务、条件更新和约束。
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
            "agent_runs": agent_runs,
            "agent_steps": agent_steps,
            "assistant_feedback": assistant_feedback,
            "evaluation_candidates": evaluation_candidates,
            "tool_audit_logs": tool_audit_logs,
            "audit_events": audit_events,
            "execution_traces": execution_traces,
            "user_profiles": user_profiles,
            "interview_answer_attempts": interview_answer_attempts,
            "product_events": product_events,
            "deployment_releases": deployment_releases,
            "resume_documents": resume_documents,
            "resume_analyses": resume_analyses,
            "interview_reviews": interview_reviews,
            "interview_review_turns": interview_review_turns,
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
        """在模型调用前以数据库条件更新独占会话，并返回可重放的领取结果。"""
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
            # 另一副本可能刚创建同一会话；后续事务会读取这个权威记录。
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
            # 摘要游标和回合领取在同一事务推进，失败重试不会重复折叠历史。
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
            # 用户消息和助手消息必须一起落库，历史中不暴露半完成回合。
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
        source_type: str = "general",
        source_resume_id: str | None = None,
        source_analysis_id: str | None = None,
        source_display_name: str | None = None,
        resume_context_json: str | None = None,
        question_prompt_version: str | None = None,
        question_schema_version: str | None = None,
        question_model_version: str | None = None,
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
                    source_type=source_type,
                    source_resume_id=source_resume_id,
                    source_analysis_id=source_analysis_id,
                    source_display_name=source_display_name,
                    resume_context_json=resume_context_json,
                    question_prompt_version=question_prompt_version,
                    question_schema_version=question_schema_version,
                    question_model_version=question_model_version,
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
            if not row:
                return None
            item = dict(row)
            available = bool(
                item.get("source_resume_id")
                and connection.execute(
                    select(resume_documents.c.resume_id).where(
                        resume_documents.c.user_id == user_id,
                        resume_documents.c.resume_id
                        == item["source_resume_id"],
                    )
                ).first()
            )
        item.pop("resume_context_json", None)
        item.pop("question_prompt_version", None)
        self._add_interview_source(item, available=available)
        return item

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
                interviews.c.source_type,
                interviews.c.source_resume_id,
                interviews.c.source_analysis_id,
                interviews.c.source_display_name,
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
                interviews.c.source_type,
                interviews.c.source_resume_id,
                interviews.c.source_analysis_id,
                interviews.c.source_display_name,
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
            available = False
            if item.get("source_resume_id"):
                with self.engine.connect() as connection:
                    available = bool(
                        connection.execute(
                            select(resume_documents.c.resume_id).where(
                                resume_documents.c.user_id == user_id,
                                resume_documents.c.resume_id
                                == item["source_resume_id"],
                            )
                        ).first()
                    )
            self._add_interview_source(item, available=available)
            result.append(item)
        return result

    @staticmethod
    def _add_interview_source(
        item: dict[str, object],
        *,
        available: bool,
    ) -> None:
        source_type = str(item.get("source_type") or "general")
        item["source_type"] = source_type
        resume_id = item.pop("source_resume_id", None)
        analysis_id = item.pop("source_analysis_id", None)
        display_name = item.pop("source_display_name", None)
        if source_type == "resume":
            item["source_resume"] = {
                "resume_id": resume_id,
                "analysis_id": analysis_id,
                "display_name": display_name or "来源简历",
                "available": available,
            }
        else:
            item["source_resume"] = None

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
        prompt_version: str | None = None,
        schema_version: str | None = None,
        model_version: str | None = None,
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
                    prompt_version=prompt_version,
                    schema_version=schema_version,
                    model_version=model_version,
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
                interviews.c.source_type,
                interview_turns.c.turn_index,
                interview_turns.c.question,
                interview_turns.c.score,
                interview_turns.c.dimensions_json,
                interview_turns.c.weaknesses_json,
                interview_turns.c.assessment_model_version,
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
            rows = [
                dict(row)
                for row in connection.execute(statement).mappings().all()
            ]
            real_rows = connection.execute(
                select(
                    interview_reviews.c.review_id.label("interview_id"),
                    interview_review_turns.c.turn_index,
                    interview_review_turns.c.question,
                    interview_review_turns.c.score,
                    interview_review_turns.c.dimensions_json,
                    interview_review_turns.c.weaknesses_json,
                    interview_reviews.c.model_version.label(
                        "assessment_model_version"
                    ),
                    interview_review_turns.c.created_at.label("updated_at"),
                )
                .select_from(
                    interview_reviews.join(
                        interview_review_turns,
                        (
                            interview_reviews.c.user_id
                            == interview_review_turns.c.user_id
                        )
                        & (
                            interview_reviews.c.review_id
                            == interview_review_turns.c.review_id
                        ),
                    )
                )
                .where(
                    interview_reviews.c.user_id == user_id,
                    interview_reviews.c.status == "ready",
                    interview_review_turns.c.score.is_not(None),
                )
                .order_by(
                    interview_review_turns.c.created_at,
                    interview_review_turns.c.turn_index,
                )
            ).mappings().all()
        rows.extend(
            {
                **dict(row),
                "topic": "面试复盘",
                "level": "真实",
                "status": "completed",
                "source_type": "real",
            }
            for row in real_rows
        )
        return rows

    def upsert_assistant_feedback(
        self,
        *,
        user_id: str,
        turn_id: str,
        rating: str,
        reason_code: str | None = None,
        comment: str | None = None,
    ) -> dict[str, object] | None:
        self.initialize()
        if rating not in {"up", "down"}:
            raise ValueError("反馈评分不合法")
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            turn = connection.execute(select(
                chat_turns.c.turn_id,
                chat_turns.c.metadata_json,
            ).where(
                chat_turns.c.user_id == user_id,
                chat_turns.c.turn_id == turn_id,
                chat_turns.c.status == "completed",
            )).mappings().first()
            if not turn:
                return None
            metadata_payload = json.loads(str(turn["metadata_json"])) if turn["metadata_json"] else {}
            source_ids = sorted({
                str(item.get("evidence_id"))
                for item in metadata_payload.get("sources", [])
                if isinstance(item, dict) and item.get("evidence_id")
            })
            existing = connection.execute(select(assistant_feedback).where(
                assistant_feedback.c.user_id == user_id,
                assistant_feedback.c.turn_id == turn_id,
            )).mappings().first()
            values = {
                "rating": rating,
                "reason_code": reason_code,
                "comment": comment,
                "prompt_version": metadata_payload.get("prompt_version"),
                "schema_version": metadata_payload.get("schema_version"),
                "model_version": metadata_payload.get("model_version"),
                "source_ids_json": json.dumps(source_ids, separators=(",", ":")),
                "updated_at": now,
            }
            if existing:
                feedback_id = str(existing["feedback_id"])
                connection.execute(update(assistant_feedback).where(
                    assistant_feedback.c.feedback_id == feedback_id
                ).values(**values))
            else:
                feedback_id = str(uuid4())
                connection.execute(insert(assistant_feedback).values(
                    feedback_id=feedback_id, user_id=user_id, turn_id=turn_id,
                    created_at=now, **values,
                ))
            if rating == "down":
                candidate = connection.execute(select(evaluation_candidates.c.candidate_id).where(
                    evaluation_candidates.c.feedback_id == feedback_id
                )).first()
                if not candidate:
                    connection.execute(insert(evaluation_candidates).values(
                        candidate_id=str(uuid4()), feedback_id=feedback_id,
                        user_id=user_id, status="pending_privacy_review",
                        created_at=now,
                    ))
            else:
                connection.execute(delete(evaluation_candidates).where(
                    evaluation_candidates.c.feedback_id == feedback_id,
                    evaluation_candidates.c.status == "pending_privacy_review",
                ))
            row = connection.execute(select(assistant_feedback).where(
                assistant_feedback.c.feedback_id == feedback_id
            )).mappings().one()
        payload = dict(row)
        payload["source_ids"] = json.loads(str(payload.pop("source_ids_json")))
        return payload

    def delete_assistant_feedback(
        self, *, user_id: str, turn_id: str
    ) -> bool:
        self.initialize()
        with self.engine.begin() as connection:
            feedback_id = connection.execute(select(assistant_feedback.c.feedback_id).where(
                assistant_feedback.c.user_id == user_id,
                assistant_feedback.c.turn_id == turn_id,
            )).scalar_one_or_none()
            if not feedback_id:
                return False
            immutable_candidate = connection.execute(
                select(evaluation_candidates.c.candidate_id).where(
                    evaluation_candidates.c.feedback_id == feedback_id,
                    evaluation_candidates.c.status.in_(("approved", "rejected")),
                )
            ).first()
            if immutable_candidate:
                return False
            connection.execute(delete(evaluation_candidates).where(
                evaluation_candidates.c.feedback_id == feedback_id,
                evaluation_candidates.c.status == "pending_privacy_review",
            ))
            result = connection.execute(delete(assistant_feedback).where(
                assistant_feedback.c.feedback_id == feedback_id
            ))
        return bool(result.rowcount)

    def list_evaluation_candidates(
        self, *, status: str = "pending_privacy_review"
    ) -> list[dict[str, object]]:
        self.initialize()
        with self.engine.connect() as connection:
            rows = connection.execute(select(
                evaluation_candidates.c.candidate_id,
                evaluation_candidates.c.feedback_id,
                evaluation_candidates.c.user_id,
                evaluation_candidates.c.status,
                evaluation_candidates.c.reviewed_by,
                evaluation_candidates.c.reviewed_at,
                evaluation_candidates.c.created_at,
                assistant_feedback.c.turn_id,
                assistant_feedback.c.rating,
                assistant_feedback.c.reason_code,
                assistant_feedback.c.prompt_version,
                assistant_feedback.c.schema_version,
                assistant_feedback.c.model_version,
                assistant_feedback.c.source_ids_json,
            ).select_from(evaluation_candidates.join(
                assistant_feedback,
                evaluation_candidates.c.feedback_id == assistant_feedback.c.feedback_id,
            )).where(
                evaluation_candidates.c.status == status
            ).order_by(evaluation_candidates.c.created_at)).mappings().all()
        return [dict(row) for row in rows]

    def review_evaluation_candidate(
        self,
        *,
        candidate_id: str,
        reviewer_id: str,
        decision: str,
        approved_payload: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        self.initialize()
        if decision not in {"approved", "rejected"}:
            raise ValueError("评测候选审核决定不合法")
        if decision == "approved" and not approved_payload:
            raise ValueError("通过隐私审核需要提供已审阅的评测载荷")
        now = datetime.now(UTC).isoformat()
        payload_json = (
            json.dumps(approved_payload, ensure_ascii=False, sort_keys=True)
            if decision == "approved"
            else None
        )
        with self.engine.begin() as connection:
            changed = connection.execute(update(evaluation_candidates).where(
                evaluation_candidates.c.candidate_id == candidate_id,
                evaluation_candidates.c.status == "pending_privacy_review",
            ).values(
                status=decision, reviewed_by=reviewer_id,
                reviewed_at=now, approved_payload_json=payload_json,
            ))
            if changed.rowcount != 1:
                return None
            row = connection.execute(select(evaluation_candidates).where(
                evaluation_candidates.c.candidate_id == candidate_id
            )).mappings().one()
        return dict(row)

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

    @staticmethod
    def _agent_run_payload(row: dict[str, object], steps: list[dict[str, object]]) -> dict[str, object]:
        payload = dict(row)
        for key in ("input_json", "proposal_json", "result_json"):
            raw = payload.pop(key, None)
            payload[key.removesuffix("_json")] = json.loads(str(raw)) if raw else None
        decoded_steps = []
        for item in steps:
            step = dict(item)
            raw_result = step.pop("result_json", None)
            step["result"] = json.loads(str(raw_result)) if raw_result else None
            decoded_steps.append(step)
        payload["steps"] = decoded_steps
        return payload

    def create_agent_run(
        self,
        *,
        user_id: str,
        run_type: str,
        idempotency_key: str,
        input_payload: dict[str, object],
        proposal: dict[str, object],
    ) -> dict[str, object]:
        """Persist a proposed workflow and its stable steps in one transaction."""
        self.initialize()
        now = datetime.now(UTC).isoformat()
        input_json = json.dumps(input_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        input_digest = hashlib.sha256(input_json.encode("utf-8")).hexdigest()
        proposal_json = json.dumps(proposal, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        run_id = str(uuid4())
        try:
            with self.engine.begin() as connection:
                connection.execute(insert(agent_runs).values(
                    run_id=run_id, user_id=user_id, run_type=run_type,
                    status="awaiting_confirmation", idempotency_key=idempotency_key,
                    input_digest=input_digest, input_json=input_json,
                    proposal_json=proposal_json, created_at=now, updated_at=now,
                ))
                read_result = json.dumps(
                    {"candidate_count": len(proposal.get("candidates", []))},
                    ensure_ascii=False, separators=(",", ":"),
                )
                for step_key, step_type, status, result in (
                    ("plan", "read", "completed", read_result),
                    ("create_tasks", "command", "pending", None),
                ):
                    connection.execute(insert(agent_steps).values(
                        step_id=str(uuid4()), run_id=run_id, user_id=user_id,
                        step_key=step_key, step_type=step_type, status=status,
                        idempotency_key=f"{run_id}:{step_key}", input_digest=input_digest,
                        attempt_count=1 if status == "completed" else 0,
                        result_json=result, created_at=now, updated_at=now,
                    ))
        except IntegrityError:
            existing = self.get_agent_run_by_idempotency(
                user_id=user_id, run_type=run_type, idempotency_key=idempotency_key
            )
            if not existing or existing["input_digest"] != input_digest:
                raise ValueError("Idempotency-Key 已用于不同的 Agent 工作流输入")
            return existing
        return self.get_agent_run(user_id=user_id, run_id=run_id)  # type: ignore[return-value]

    def get_agent_run_by_idempotency(
        self, *, user_id: str, run_type: str, idempotency_key: str
    ) -> dict[str, object] | None:
        self.initialize()
        with self.engine.connect() as connection:
            row = connection.execute(select(agent_runs).where(
                agent_runs.c.user_id == user_id,
                agent_runs.c.run_type == run_type,
                agent_runs.c.idempotency_key == idempotency_key,
            )).mappings().first()
            if not row:
                return None
            steps = connection.execute(select(agent_steps).where(
                agent_steps.c.run_id == row["run_id"]
            ).order_by(agent_steps.c.created_at)).mappings().all()
        return self._agent_run_payload(dict(row), [dict(item) for item in steps])

    def get_agent_run(self, *, user_id: str, run_id: str) -> dict[str, object] | None:
        self.initialize()
        with self.engine.connect() as connection:
            row = connection.execute(select(agent_runs).where(
                agent_runs.c.user_id == user_id, agent_runs.c.run_id == run_id
            )).mappings().first()
            if not row:
                return None
            steps = connection.execute(select(agent_steps).where(
                agent_steps.c.run_id == run_id,
                agent_steps.c.user_id == user_id,
            ).order_by(agent_steps.c.created_at)).mappings().all()
        return self._agent_run_payload(dict(row), [dict(item) for item in steps])

    def get_agent_run_for_admin(self, *, run_id: str) -> dict[str, object] | None:
        self.initialize()
        with self.engine.connect() as connection:
            row = connection.execute(select(agent_runs).where(
                agent_runs.c.run_id == run_id
            )).mappings().first()
        if not row:
            return None
        return self.get_agent_run(
            user_id=str(row["user_id"]), run_id=str(row["run_id"])
        )

    def list_agent_runs(self, *, user_id: str) -> list[dict[str, object]]:
        self.initialize()
        with self.engine.connect() as connection:
            ids = connection.execute(select(agent_runs.c.run_id).where(
                agent_runs.c.user_id == user_id
            ).order_by(agent_runs.c.created_at.desc())).scalars().all()
        return [run for run_id in ids if (run := self.get_agent_run(user_id=user_id, run_id=str(run_id)))]

    def claim_agent_run_command(
        self, *, user_id: str, run_id: str, claim_owner: str
    ) -> dict[str, object] | None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            row = connection.execute(select(agent_runs).where(
                agent_runs.c.user_id == user_id, agent_runs.c.run_id == run_id
            ).with_for_update()).mappings().first()
            if not row:
                return None
            if row["status"] in {"completed", "cancelled"}:
                return {"state": "replay", "status": str(row["status"])}
            if row["status"] not in {"awaiting_confirmation", "running", "failed"}:
                return {"state": "busy", "status": str(row["status"])}
            claimed = connection.execute(update(agent_steps).where(
                agent_steps.c.run_id == run_id,
                agent_steps.c.user_id == user_id,
                agent_steps.c.step_key == "create_tasks",
                agent_steps.c.status.in_(["pending", "failed"]),
            ).values(
                status="claimed", claim_owner=claim_owner, claimed_at=now,
                attempt_count=agent_steps.c.attempt_count + 1,
                error_code=None, updated_at=now,
            ))
            if claimed.rowcount != 1:
                return {"state": "busy", "status": str(row["status"])}
            connection.execute(update(agent_runs).where(
                agent_runs.c.run_id == run_id
            ).values(status="running", error_code=None, updated_at=now))
        return {"state": "claimed", "status": "running"}

    def complete_training_program_command(
        self, *, user_id: str, run_id: str, claim_owner: str
    ) -> dict[str, object] | None:
        """Apply the command and store its replay result atomically."""
        self.initialize()
        now = datetime.now(UTC)
        now_iso = now.isoformat()
        with self.engine.begin() as connection:
            run = connection.execute(select(agent_runs).where(
                agent_runs.c.user_id == user_id, agent_runs.c.run_id == run_id
            ).with_for_update()).mappings().first()
            if not run:
                return None
            if run["status"] == "completed":
                return json.loads(str(run["result_json"]))
            step = connection.execute(select(agent_steps).where(
                agent_steps.c.run_id == run_id,
                agent_steps.c.step_key == "create_tasks",
                agent_steps.c.status == "claimed",
                agent_steps.c.claim_owner == claim_owner,
            ).with_for_update()).mappings().first()
            if not step:
                return None
            proposal = json.loads(str(run["proposal_json"]))
            created_ids: list[str] = []
            for candidate in proposal["candidates"]:
                existing = connection.execute(select(learning_tasks.c.task_id).where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.dimension == candidate["dimension"],
                    learning_tasks.c.weakness == candidate["weakness"],
                    learning_tasks.c.status != "completed",
                )).scalar_one_or_none()
                if existing:
                    created_ids.append(str(existing))
                    continue
                task_id = str(uuid4())
                connection.execute(insert(learning_tasks).values(
                    task_id=task_id, user_id=user_id,
                    dimension=candidate["dimension"], weakness=candidate["weakness"],
                    action=candidate["action"], status="todo",
                    due_at=(now + timedelta(days=7)).isoformat(), review_count=0,
                    next_review_at=(now + timedelta(days=1)).isoformat(),
                    created_at=now_iso, updated_at=now_iso,
                ))
                created_ids.append(task_id)
            result = {
                "task_ids": created_ids,
                "task_count": len(created_ids),
                "interview_create_url": "/interviews",
            }
            result_json = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            completed = connection.execute(update(agent_steps).where(
                agent_steps.c.step_id == step["step_id"],
                agent_steps.c.status == "claimed",
                agent_steps.c.claim_owner == claim_owner,
            ).values(status="completed", result_json=result_json, updated_at=now_iso))
            if completed.rowcount != 1:
                raise RuntimeError("Agent 命令步骤领取已失效")
            connection.execute(update(agent_runs).where(
                agent_runs.c.run_id == run_id, agent_runs.c.status == "running"
            ).values(status="completed", result_json=result_json, updated_at=now_iso))
        return result

    def cancel_agent_run(self, *, user_id: str, run_id: str) -> dict[str, object] | None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            changed = connection.execute(update(agent_runs).where(
                agent_runs.c.user_id == user_id, agent_runs.c.run_id == run_id,
                agent_runs.c.status.in_(["proposed", "awaiting_confirmation"]),
            ).values(status="cancelled", updated_at=now))
            if changed.rowcount:
                connection.execute(update(agent_steps).where(
                    agent_steps.c.run_id == run_id, agent_steps.c.status == "pending"
                ).values(status="skipped", updated_at=now))
        return self.get_agent_run(user_id=user_id, run_id=run_id)

    def fail_agent_run_command(
        self,
        *,
        user_id: str,
        run_id: str,
        claim_owner: str,
        error_code: str,
    ) -> None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            connection.execute(update(agent_steps).where(
                agent_steps.c.user_id == user_id,
                agent_steps.c.run_id == run_id,
                agent_steps.c.step_key == "create_tasks",
                agent_steps.c.status == "claimed",
                agent_steps.c.claim_owner == claim_owner,
            ).values(status="failed", error_code=error_code[:80], updated_at=now))
            connection.execute(update(agent_runs).where(
                agent_runs.c.user_id == user_id,
                agent_runs.c.run_id == run_id,
                agent_runs.c.status == "running",
            ).values(status="failed", error_code=error_code[:80], updated_at=now))

    def recover_stale_agent_steps(
        self, *, stale_before: str
    ) -> int:
        """Release abandoned claims; command effects are atomic and replay-safe."""
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            stale = connection.execute(select(agent_steps.c.run_id).where(
                agent_steps.c.status == "claimed",
                agent_steps.c.claimed_at < stale_before,
            )).scalars().all()
            if not stale:
                return 0
            released = connection.execute(update(agent_steps).where(
                agent_steps.c.status == "claimed",
                agent_steps.c.claimed_at < stale_before,
            ).values(
                status="pending", claim_owner=None, claimed_at=None,
                error_code="stale_claim_recovered", updated_at=now,
            ))
            connection.execute(update(agent_runs).where(
                agent_runs.c.run_id.in_(list(stale)), agent_runs.c.status == "running"
            ).values(status="failed", error_code="stale_claim_recovered", updated_at=now))
            return int(released.rowcount)

    def create_learning_plan_preview(
        self,
        *,
        user_id: str,
        topic: str,
        candidates: list[dict[str, str]],
        ttl_seconds: int = 600,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC)
        payload = {
            "topic": topic.strip(),
            "candidates": candidates,
        }
        payload_json = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        confirmation_id = str(uuid4())
        expires_at = now + timedelta(seconds=max(60, min(ttl_seconds, 3600)))
        with self.engine.begin() as connection:
            connection.execute(
                insert(agent_action_confirmations).values(
                    confirmation_id=confirmation_id,
                    user_id=user_id,
                    action_type="create_learning_plan",
                    payload_json=payload_json,
                    payload_digest=hashlib.sha256(
                        payload_json.encode("utf-8")
                    ).hexdigest(),
                    status="pending",
                    expires_at=expires_at.isoformat(),
                    created_at=now.isoformat(),
                )
            )
        return {
            "confirmation_id": confirmation_id,
            "status": "awaiting_confirmation",
            "expires_at": expires_at.isoformat(),
            **payload,
        }

    def confirm_learning_plan(
        self,
        *,
        user_id: str,
        confirmation_id: str,
    ) -> dict[str, object] | None:
        self.initialize()
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            row = connection.execute(
                select(agent_action_confirmations)
                .where(
                    agent_action_confirmations.c.user_id == user_id,
                    agent_action_confirmations.c.confirmation_id
                    == confirmation_id,
                    agent_action_confirmations.c.action_type
                    == "create_learning_plan",
                )
                .with_for_update()
            ).mappings().first()
            if not row:
                return None
            if row["status"] == "applied":
                return json.loads(str(row["result_json"]))
            if row["status"] != "pending":
                return {
                    "confirmation_id": confirmation_id,
                    "status": str(row["status"]),
                }
            if datetime.fromisoformat(str(row["expires_at"])) <= now:
                connection.execute(
                    update(agent_action_confirmations)
                    .where(
                        agent_action_confirmations.c.confirmation_id
                        == confirmation_id,
                        agent_action_confirmations.c.status == "pending",
                    )
                    .values(status="expired")
                )
                return {
                    "confirmation_id": confirmation_id,
                    "status": "expired",
                }
            payload_json = str(row["payload_json"])
            digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            if digest != row["payload_digest"]:
                raise ValueError("学习计划确认内容摘要不匹配")
            payload = json.loads(payload_json)
            candidates = payload["candidates"]
            for candidate in candidates:
                existing = connection.execute(
                    select(learning_tasks.c.task_id).where(
                        learning_tasks.c.user_id == user_id,
                        learning_tasks.c.dimension == candidate["dimension"],
                        learning_tasks.c.weakness == candidate["weakness"],
                        learning_tasks.c.status != "completed",
                    )
                ).first()
                if existing:
                    continue
                connection.execute(
                    insert(learning_tasks).values(
                        task_id=str(uuid4()),
                        user_id=user_id,
                        dimension=candidate["dimension"],
                        weakness=candidate["weakness"],
                        action=candidate["action"],
                        status="todo",
                        due_at=(now + timedelta(days=7)).isoformat(),
                        review_count=0,
                        next_review_at=(now + timedelta(days=1)).isoformat(),
                        created_at=now.isoformat(),
                        updated_at=now.isoformat(),
                    )
                )
            tasks = [
                dict(item)
                for item in connection.execute(
                    select(learning_tasks)
                    .where(learning_tasks.c.user_id == user_id)
                    .order_by(
                        learning_tasks.c.status,
                        learning_tasks.c.due_at,
                        learning_tasks.c.created_at.desc(),
                    )
                ).mappings()
            ]
            result = {
                "confirmation_id": confirmation_id,
                "status": "applied",
                "tasks": tasks,
            }
            result_json = json.dumps(
                result,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            claimed = connection.execute(
                update(agent_action_confirmations)
                .where(
                    agent_action_confirmations.c.confirmation_id
                    == confirmation_id,
                    agent_action_confirmations.c.status == "pending",
                )
                .values(
                    status="applied",
                    result_json=result_json,
                    consumed_at=now.isoformat(),
                )
            )
            if claimed.rowcount != 1:
                raise RuntimeError("学习计划确认发生并发冲突")
            return result

    def create_public_search_preview(
        self,
        *,
        user_id: str,
        query: str,
        ttl_seconds: int = 600,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC)
        payload_json = json.dumps(
            {"query": query},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        confirmation_id = str(uuid4())
        expires_at = now + timedelta(seconds=max(60, min(ttl_seconds, 3600)))
        with self.engine.begin() as connection:
            connection.execute(
                insert(agent_action_confirmations).values(
                    confirmation_id=confirmation_id,
                    user_id=user_id,
                    action_type="public_web_search",
                    payload_json=payload_json,
                    payload_digest=hashlib.sha256(
                        payload_json.encode("utf-8")
                    ).hexdigest(),
                    status="pending",
                    expires_at=expires_at.isoformat(),
                    created_at=now.isoformat(),
                )
            )
        return {
            "confirmation_id": confirmation_id,
            "status": "awaiting_confirmation",
            "expires_at": expires_at.isoformat(),
            "query": query,
        }

    def claim_public_search_confirmation(
        self,
        *,
        user_id: str,
        confirmation_id: str,
    ) -> dict[str, object] | None:
        """Atomically consume a pending search preview before network I/O."""
        self.initialize()
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            row = connection.execute(
                select(agent_action_confirmations).where(
                    agent_action_confirmations.c.user_id == user_id,
                    agent_action_confirmations.c.confirmation_id
                    == confirmation_id,
                    agent_action_confirmations.c.action_type
                    == "public_web_search",
                )
            ).mappings().first()
            if not row:
                return None
            if row["status"] == "applied":
                if row["result_json"]:
                    return {
                        "status": "replay",
                        "result": json.loads(str(row["result_json"]))["result"],
                    }
                return {"status": "in_progress"}
            if row["status"] != "pending":
                return {"status": str(row["status"])}
            if datetime.fromisoformat(str(row["expires_at"])) <= now:
                connection.execute(
                    update(agent_action_confirmations)
                    .where(
                        agent_action_confirmations.c.confirmation_id
                        == confirmation_id,
                        agent_action_confirmations.c.status == "pending",
                    )
                    .values(status="expired")
                )
                return {"status": "expired"}
            payload_json = str(row["payload_json"])
            digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            if digest != row["payload_digest"]:
                raise ValueError("联网查询确认内容摘要不匹配")
            claimed = connection.execute(
                update(agent_action_confirmations)
                .where(
                    agent_action_confirmations.c.confirmation_id
                    == confirmation_id,
                    agent_action_confirmations.c.status == "pending",
                )
                .values(status="applied", consumed_at=now.isoformat())
            )
            if claimed.rowcount != 1:
                return {"status": "in_progress"}
            return {
                "status": "claimed",
                "query": json.loads(payload_json)["query"],
            }

    def complete_public_search_confirmation(
        self,
        *,
        user_id: str,
        confirmation_id: str,
        result: str,
    ) -> None:
        self.initialize()
        result_json = json.dumps(
            {"result": result},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self.engine.begin() as connection:
            completed = connection.execute(
                update(agent_action_confirmations)
                .where(
                    agent_action_confirmations.c.user_id == user_id,
                    agent_action_confirmations.c.confirmation_id
                    == confirmation_id,
                    agent_action_confirmations.c.action_type
                    == "public_web_search",
                    agent_action_confirmations.c.status == "applied",
                    agent_action_confirmations.c.result_json.is_(None),
                )
                .values(result_json=result_json)
            )
            if completed.rowcount != 1:
                raise RuntimeError("联网查询确认结果保存发生并发冲突")

    def cancel_public_search_confirmation(
        self,
        *,
        user_id: str,
        confirmation_id: str,
    ) -> None:
        self.initialize()
        with self.engine.begin() as connection:
            connection.execute(
                update(agent_action_confirmations)
                .where(
                    agent_action_confirmations.c.user_id == user_id,
                    agent_action_confirmations.c.confirmation_id
                    == confirmation_id,
                    agent_action_confirmations.c.action_type
                    == "public_web_search",
                    agent_action_confirmations.c.status == "applied",
                    agent_action_confirmations.c.result_json.is_(None),
                )
                .values(status="cancelled")
            )

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

    def create_coaching_memory(
        self,
        *,
        user_id: str,
        kind: str,
        content: str,
        source_type: str = "user",
        source_id: str | None = None,
        source_revision: int | None = None,
        expires_at: str | None = None,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        memory_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                insert(coaching_memories).values(
                    memory_id=memory_id,
                    user_id=user_id,
                    kind=kind,
                    content=content.strip(),
                    status="proposed",
                    source_type=source_type,
                    source_id=source_id,
                    source_revision=source_revision,
                    expires_at=expires_at,
                    created_at=now,
                    updated_at=now,
                )
            )
            row = connection.execute(
                select(coaching_memories).where(
                    coaching_memories.c.memory_id == memory_id
                )
            ).mappings().one()
        return dict(row)

    def list_coaching_memories(
        self,
        *,
        user_id: str,
        status: str | None = None,
        context_ready_only: bool = False,
    ) -> list[dict[str, object]]:
        self.initialize()
        statement = select(coaching_memories).where(
            coaching_memories.c.user_id == user_id
        )
        if status:
            statement = statement.where(coaching_memories.c.status == status)
        statement = statement.order_by(coaching_memories.c.updated_at.desc())
        now = datetime.now(UTC)
        with self.engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(statement).mappings()]
            if not context_ready_only:
                return rows
            ready = []
            for row in rows:
                if row["status"] != "confirmed":
                    continue
                expires_at = row.get("expires_at")
                if expires_at and datetime.fromisoformat(str(expires_at)) <= now:
                    continue
                if row["kind"] == "observation" and not self._memory_source_current(
                    connection, row
                ):
                    continue
                ready.append(row)
            return ready

    @staticmethod
    def _memory_source_current(connection, row: dict[str, object]) -> bool:
        source_type = str(row.get("source_type") or "")
        source_id = row.get("source_id")
        revision = row.get("source_revision")
        if source_type == "resume_analysis" and source_id:
            current = connection.execute(
                select(resume_analyses.c.revision, resume_analyses.c.status).where(
                    resume_analyses.c.analysis_id == source_id
                )
            ).first()
            return bool(current and current[1] == "ready" and current[0] == revision)
        if source_type == "interview_review" and source_id:
            current = connection.execute(
                select(
                    interview_reviews.c.confirmed_revision,
                    interview_reviews.c.status,
                ).where(interview_reviews.c.review_id == source_id)
            ).first()
            return bool(current and current[1] == "ready" and current[0] == revision)
        return source_type == "user"

    def update_coaching_memory(
        self,
        *,
        user_id: str,
        memory_id: str,
        action: str,
        content: str | None = None,
    ) -> dict[str, object] | None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        values: dict[str, object | None] = {"updated_at": now}
        if action == "confirm":
            values.update(status="confirmed", confirmed_at=now)
        elif action == "reject":
            values.update(status="rejected", confirmed_at=None)
        elif action == "correct":
            if not content or not content.strip():
                raise ValueError("记忆内容不能为空")
            values.update(
                content=content.strip(),
                status="proposed",
                confirmed_at=None,
                source_type="user",
                source_id=None,
                source_revision=None,
            )
        else:
            raise ValueError("未知记忆操作")
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(coaching_memories)
                .where(
                    coaching_memories.c.user_id == user_id,
                    coaching_memories.c.memory_id == memory_id,
                )
                .values(**values)
            )
            if not changed.rowcount:
                return None
            row = connection.execute(
                select(coaching_memories).where(
                    coaching_memories.c.user_id == user_id,
                    coaching_memories.c.memory_id == memory_id,
                )
            ).mappings().one()
        return dict(row)

    def delete_coaching_memory(self, *, user_id: str, memory_id: str) -> bool:
        self.initialize()
        with self.engine.begin() as connection:
            deleted = connection.execute(
                delete(coaching_memories).where(
                    coaching_memories.c.user_id == user_id,
                    coaching_memories.c.memory_id == memory_id,
                )
            )
        return bool(deleted.rowcount)

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
        outcome: str = "remembered",
        difficulty: int = 3,
    ) -> dict[str, object] | None:
        from app.learning import next_review_time

        self.initialize()
        if outcome not in {"remembered", "partial", "forgotten"}:
            raise ValueError("复习结果不合法")
        if not 1 <= difficulty <= 5:
            raise ValueError("难度必须在 1 到 5 之间")
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            current = connection.execute(
                select(
                    learning_tasks.c.review_count,
                    learning_tasks.c.status,
                    learning_tasks.c.lapse_count,
                    learning_tasks.c.review_confidence,
                ).where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.task_id == task_id,
                )
            ).mappings().first()
            if not current:
                return None
            review_count = int(current["review_count"]) + 1
            lapse_count = int(current["lapse_count"] or 0) + (
                1 if outcome == "forgotten" else 0
            )
            previous_confidence = float(current["review_confidence"] or 0.5)
            confidence_delta = {
                "remembered": 0.15,
                "partial": -0.05,
                "forgotten": -0.2,
            }[outcome]
            confidence = min(1.0, max(0.1, previous_confidence + confidence_delta))
            connection.execute(
                update(learning_tasks)
                .where(
                    learning_tasks.c.user_id == user_id,
                    learning_tasks.c.task_id == task_id,
                )
                .values(
                    review_count=review_count,
                    recall_outcome=outcome,
                    difficulty_rating=difficulty,
                    lapse_count=lapse_count,
                    review_confidence=confidence,
                    last_reviewed_at=now.isoformat(),
                    next_review_at=next_review_time(
                        review_count,
                        now=now,
                        outcome=outcome,
                        difficulty=difficulty,
                        lapse_count=lapse_count,
                        confidence=confidence,
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
                prompt_version=None,
                schema_version=None,
                model_version=None,
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
        """在模型调用前原子领取唯一待答题目，并支持同一请求安全重放。"""
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
        prompt_version: str | None = None,
        schema_version: str | None = None,
        model_version: str | None = None,
    ) -> str:
        """仅当调用方仍持有领取令牌时，原子提交回答、评分和下一题。"""
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
                    assessment_prompt_version=prompt_version,
                    assessment_schema_version=schema_version,
                    assessment_model_version=model_version,
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
                prompt_version=prompt_version,
                schema_version=schema_version,
                model_version=model_version,
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
        prompt_version: str | None = None,
        schema_version: str | None = None,
        model_version: str | None = None,
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
                prompt_version=prompt_version,
                schema_version=schema_version,
                model_version=model_version,
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
        prompt_version: str | None,
        schema_version: str | None,
        model_version: str | None,
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
                prompt_version=prompt_version,
                schema_version=schema_version,
                model_version=model_version,
                created_at=created_at,
            )
        )
        return attempt_index

    def create_resume_with_analysis(
        self,
        *,
        user_id: str,
        resume_id: str,
        analysis_id: str,
        original_filename: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
        storage_key: str,
        idempotency_key: str,
        request_digest: str,
        job_description: str,
        target_role: str,
        experience_level: str,
        prompt_version: str,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            existing = connection.execute(
                select(resume_documents).where(
                    resume_documents.c.user_id == user_id,
                    resume_documents.c.idempotency_key == idempotency_key,
                )
            ).mappings().first()
            if existing:
                if existing["request_digest"] != request_digest:
                    return {"outcome": "key_reused"}
                analysis = connection.execute(
                    select(resume_analyses)
                    .where(
                        resume_analyses.c.user_id == user_id,
                        resume_analyses.c.resume_id == existing["resume_id"],
                    )
                    .order_by(resume_analyses.c.created_at.desc())
                ).mappings().first()
                return {
                    "outcome": "existing",
                    "resume": dict(existing),
                    "analysis": dict(analysis) if analysis else None,
                }
            connection.execute(
                insert(resume_documents).values(
                    resume_id=resume_id,
                    user_id=user_id,
                    original_filename=original_filename,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    sha256=sha256,
                    storage_key=storage_key,
                    idempotency_key=idempotency_key,
                    request_digest=request_digest,
                    status="uploaded",
                    created_at=now,
                    updated_at=now,
                )
            )
            connection.execute(
                insert(resume_analyses).values(
                    analysis_id=analysis_id,
                    user_id=user_id,
                    resume_id=resume_id,
                    idempotency_key=idempotency_key,
                    request_digest=request_digest,
                    status="pending",
                    job_description=job_description,
                    target_role=target_role,
                    experience_level=experience_level,
                    prompt_version=prompt_version,
                    created_at=now,
                    updated_at=now,
                )
            )
        return {
            "outcome": "created",
            "resume_id": resume_id,
            "analysis_id": analysis_id,
        }

    def create_resume_analysis(
        self,
        *,
        user_id: str,
        resume_id: str,
        analysis_id: str,
        idempotency_key: str,
        request_digest: str,
        job_description: str,
        target_role: str,
        experience_level: str,
        prompt_version: str,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            document = connection.execute(
                select(resume_documents.c.resume_id).where(
                    resume_documents.c.user_id == user_id,
                    resume_documents.c.resume_id == resume_id,
                )
            ).first()
            if not document:
                return {"outcome": "not_found"}
            existing = connection.execute(
                select(resume_analyses).where(
                    resume_analyses.c.user_id == user_id,
                    resume_analyses.c.resume_id == resume_id,
                    resume_analyses.c.idempotency_key == idempotency_key,
                )
            ).mappings().first()
            if existing:
                if existing["request_digest"] != request_digest:
                    return {"outcome": "key_reused"}
                return {"outcome": "existing", "analysis": dict(existing)}
            connection.execute(
                insert(resume_analyses).values(
                    analysis_id=analysis_id,
                    user_id=user_id,
                    resume_id=resume_id,
                    idempotency_key=idempotency_key,
                    request_digest=request_digest,
                    status="pending",
                    job_description=job_description,
                    target_role=target_role,
                    experience_level=experience_level,
                    prompt_version=prompt_version,
                    created_at=now,
                    updated_at=now,
                )
            )
            connection.execute(
                update(resume_documents)
                .where(
                    resume_documents.c.user_id == user_id,
                    resume_documents.c.resume_id == resume_id,
                )
                .values(status="uploaded", error=None, updated_at=now)
            )
        return {
            "outcome": "created",
            "resume_id": resume_id,
            "analysis_id": analysis_id,
        }

    def list_resumes(self, *, user_id: str) -> list[dict[str, object]]:
        self.initialize()
        with self.engine.connect() as connection:
            documents = connection.execute(
                select(resume_documents)
                .where(resume_documents.c.user_id == user_id)
                .order_by(resume_documents.c.updated_at.desc())
            ).mappings().all()
            result: list[dict[str, object]] = []
            for document in documents:
                analysis = connection.execute(
                    select(resume_analyses)
                    .where(
                        resume_analyses.c.user_id == user_id,
                        resume_analyses.c.resume_id == document["resume_id"],
                    )
                    .order_by(resume_analyses.c.created_at.desc())
                ).mappings().first()
                result.append(
                    {
                        **dict(document),
                        "latest_analysis": (
                            dict(analysis) if analysis else None
                        ),
                    }
                )
        return result

    def get_resume(
        self,
        *,
        user_id: str,
        resume_id: str,
    ) -> dict[str, object] | None:
        self.initialize()
        with self.engine.connect() as connection:
            document = connection.execute(
                select(resume_documents).where(
                    resume_documents.c.user_id == user_id,
                    resume_documents.c.resume_id == resume_id,
                )
            ).mappings().first()
            if not document:
                return None
            analyses = connection.execute(
                select(resume_analyses)
                .where(
                    resume_analyses.c.user_id == user_id,
                    resume_analyses.c.resume_id == resume_id,
                )
                .order_by(resume_analyses.c.created_at.desc())
            ).mappings().all()
        return {
            **dict(document),
            "analyses": [dict(item) for item in analyses],
        }

    def get_resume_analysis(
        self,
        *,
        user_id: str,
        analysis_id: str,
    ) -> dict[str, object] | None:
        self.initialize()
        with self.engine.connect() as connection:
            row = connection.execute(
                select(
                    resume_analyses,
                    resume_documents.c.storage_key,
                    resume_documents.c.content_type,
                    resume_documents.c.original_filename,
                )
                .select_from(
                    resume_analyses.join(
                        resume_documents,
                        (
                            resume_analyses.c.user_id
                            == resume_documents.c.user_id
                        )
                        & (
                            resume_analyses.c.resume_id
                            == resume_documents.c.resume_id
                        ),
                    )
                )
                .where(
                    resume_analyses.c.user_id == user_id,
                    resume_analyses.c.analysis_id == analysis_id,
                )
            ).mappings().first()
        return dict(row) if row else None

    def claim_resume_analysis(
        self,
        *,
        analysis_id: str,
        claim_token: str,
    ) -> dict[str, object] | None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            result = connection.execute(
                update(resume_analyses)
                .where(
                    resume_analyses.c.analysis_id == analysis_id,
                    resume_analyses.c.status.in_(["pending", "failed"]),
                    resume_analyses.c.claim_token.is_(None),
                )
                .values(
                    status="processing",
                    claim_token=claim_token,
                    error=None,
                    updated_at=now,
                )
            )
            if not result.rowcount:
                return None
            row = connection.execute(
                select(
                    resume_analyses,
                    resume_documents.c.storage_key,
                    resume_documents.c.content_type,
                    resume_documents.c.original_filename,
                )
                .select_from(
                    resume_analyses.join(
                        resume_documents,
                        (
                            resume_analyses.c.user_id
                            == resume_documents.c.user_id
                        )
                        & (
                            resume_analyses.c.resume_id
                            == resume_documents.c.resume_id
                        ),
                    )
                )
                .where(resume_analyses.c.analysis_id == analysis_id)
            ).mappings().one()
            connection.execute(
                update(resume_documents)
                .where(
                    resume_documents.c.user_id == row["user_id"],
                    resume_documents.c.resume_id == row["resume_id"],
                )
                .values(status="processing", error=None, updated_at=now)
            )
        return dict(row)

    def complete_resume_analysis(
        self,
        *,
        analysis_id: str,
        claim_token: str,
        parsed_text: str,
        report_json: str,
        draft_json: str,
        warnings_json: str,
        model_version: str,
        schema_version: str = "resume-analysis-v1",
    ) -> bool:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            row = connection.execute(
                select(
                    resume_analyses.c.user_id,
                    resume_analyses.c.resume_id,
                ).where(
                    resume_analyses.c.analysis_id == analysis_id,
                    resume_analyses.c.status == "processing",
                    resume_analyses.c.claim_token == claim_token,
                )
            ).mappings().first()
            if not row:
                return False
            connection.execute(
                update(resume_analyses)
                .where(
                    resume_analyses.c.analysis_id == analysis_id,
                    resume_analyses.c.claim_token == claim_token,
                )
                .values(
                    status="ready",
                    claim_token=None,
                    parsed_text=parsed_text,
                    report_json=report_json,
                    draft_json=draft_json,
                    warnings_json=warnings_json,
                    model_version=model_version,
                    schema_version=schema_version,
                    error=None,
                    updated_at=now,
                )
            )
            connection.execute(
                update(resume_documents)
                .where(
                    resume_documents.c.user_id == row["user_id"],
                    resume_documents.c.resume_id == row["resume_id"],
                )
                .values(status="ready", error=None, updated_at=now)
            )
        return True

    def fail_resume_analysis(
        self,
        *,
        analysis_id: str,
        claim_token: str,
        error: str,
    ) -> bool:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            row = connection.execute(
                select(
                    resume_analyses.c.user_id,
                    resume_analyses.c.resume_id,
                ).where(
                    resume_analyses.c.analysis_id == analysis_id,
                    resume_analyses.c.status == "processing",
                    resume_analyses.c.claim_token == claim_token,
                )
            ).mappings().first()
            if not row:
                return False
            safe_error = error[:2000]
            connection.execute(
                update(resume_analyses)
                .where(
                    resume_analyses.c.analysis_id == analysis_id,
                    resume_analyses.c.claim_token == claim_token,
                )
                .values(
                    status="failed",
                    claim_token=None,
                    error=safe_error,
                    updated_at=now,
                )
            )
            connection.execute(
                update(resume_documents)
                .where(
                    resume_documents.c.user_id == row["user_id"],
                    resume_documents.c.resume_id == row["resume_id"],
                )
                .values(status="failed", error=safe_error, updated_at=now)
            )
        return True

    def update_resume_draft(
        self,
        *,
        user_id: str,
        analysis_id: str,
        expected_revision: int,
        draft_json: str,
        warnings_json: str,
    ) -> dict[str, object] | None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            result = connection.execute(
                update(resume_analyses)
                .where(
                    resume_analyses.c.user_id == user_id,
                    resume_analyses.c.analysis_id == analysis_id,
                    resume_analyses.c.status == "ready",
                    resume_analyses.c.revision == expected_revision,
                )
                .values(
                    draft_json=draft_json,
                    warnings_json=warnings_json,
                    revision=expected_revision + 1,
                    updated_at=now,
                )
            )
            if not result.rowcount:
                return None
            row = connection.execute(
                select(resume_analyses).where(
                    resume_analyses.c.user_id == user_id,
                    resume_analyses.c.analysis_id == analysis_id,
                )
            ).mappings().one()
        return dict(row)

    def delete_resume(
        self,
        *,
        user_id: str,
        resume_id: str,
    ) -> str | None:
        self.initialize()
        with self.engine.begin() as connection:
            storage_key = connection.execute(
                select(resume_documents.c.storage_key).where(
                    resume_documents.c.user_id == user_id,
                    resume_documents.c.resume_id == resume_id,
                )
            ).scalar_one_or_none()
            if storage_key is None:
                return None
            connection.execute(
                delete(resume_documents).where(
                    resume_documents.c.user_id == user_id,
                    resume_documents.c.resume_id == resume_id,
                )
            )
        return str(storage_key)

    def create_interview_review(
        self,
        *,
        user_id: str,
        review_id: str,
        input_type: str,
        transcript_json: str | None,
        create_idempotency_key: str,
        create_request_digest: str,
        external_processing_consent: bool,
        original_filename: str | None = None,
        content_type: str | None = None,
        size_bytes: int | None = None,
        sha256: str | None = None,
        storage_key: str | None = None,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            existing = connection.execute(
                select(interview_reviews).where(
                    interview_reviews.c.user_id == user_id,
                    interview_reviews.c.create_idempotency_key
                    == create_idempotency_key,
                )
            ).mappings().first()
            if existing:
                return {
                    "outcome": (
                        "existing"
                        if existing["create_request_digest"]
                        == create_request_digest
                        else "key_reused"
                    ),
                    "review": dict(existing),
                }
            connection.execute(
                insert(interview_reviews).values(
                    review_id=review_id,
                    user_id=user_id,
                    input_type=input_type,
                    original_filename=original_filename,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    sha256=sha256,
                    storage_key=storage_key,
                    external_processing_consent=external_processing_consent,
                    consent_at=now if external_processing_consent else None,
                    status=(
                        "transcribing"
                        if input_type == "audio"
                        else "awaiting_confirmation"
                    ),
                    transcript_json=transcript_json,
                    transcript_revision=1,
                    create_idempotency_key=create_idempotency_key,
                    create_request_digest=create_request_digest,
                    created_at=now,
                    updated_at=now,
                )
            )
        return {"outcome": "created"}

    def list_interview_reviews(
        self,
        *,
        user_id: str,
    ) -> list[dict[str, object]]:
        self.initialize()
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(interview_reviews)
                .where(interview_reviews.c.user_id == user_id)
                .order_by(interview_reviews.c.updated_at.desc())
            ).mappings().all()
        return [dict(row) for row in rows]

    def get_interview_review(
        self,
        *,
        user_id: str,
        review_id: str,
    ) -> dict[str, object] | None:
        self.initialize()
        with self.engine.connect() as connection:
            row = connection.execute(
                select(interview_reviews).where(
                    interview_reviews.c.user_id == user_id,
                    interview_reviews.c.review_id == review_id,
                )
            ).mappings().first()
            if not row:
                return None
            turns = connection.execute(
                select(interview_review_turns)
                .where(
                    interview_review_turns.c.user_id == user_id,
                    interview_review_turns.c.review_id == review_id,
                )
                .order_by(interview_review_turns.c.turn_index)
            ).mappings().all()
        result = dict(row)
        result["turns"] = [dict(turn) for turn in turns]
        return result

    def update_interview_review_transcript(
        self,
        *,
        user_id: str,
        review_id: str,
        expected_revision: int,
        transcript_json: str,
    ) -> dict[str, object] | None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(interview_reviews)
                .where(
                    interview_reviews.c.user_id == user_id,
                    interview_reviews.c.review_id == review_id,
                    interview_reviews.c.transcript_revision
                    == expected_revision,
                    interview_reviews.c.status.in_(
                        ["awaiting_confirmation", "ready", "failed"]
                    ),
                )
                .values(
                    transcript_json=transcript_json,
                    transcript_revision=expected_revision + 1,
                    confirmed_revision=None,
                    status="awaiting_confirmation",
                    analysis_idempotency_key=None,
                    analysis_request_digest=None,
                    claim_token=None,
                    report_json=None,
                    model_version=None,
                    error_category=None,
                    error=None,
                    updated_at=now,
                )
            )
            if not changed.rowcount:
                return None
            connection.execute(
                delete(interview_review_turns).where(
                    interview_review_turns.c.user_id == user_id,
                    interview_review_turns.c.review_id == review_id,
                )
            )
        return self.get_interview_review(
            user_id=user_id,
            review_id=review_id,
        )

    def claim_interview_transcription(
        self,
        *,
        review_id: str,
        claim_token: str,
    ) -> dict[str, object] | None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(interview_reviews)
                .where(
                    interview_reviews.c.review_id == review_id,
                    interview_reviews.c.status.in_(
                        ["transcribing", "failed"]
                    ),
                    interview_reviews.c.claim_token.is_(None),
                    interview_reviews.c.input_type == "audio",
                    interview_reviews.c.storage_key.is_not(None),
                )
                .values(
                    status="transcribing",
                    claim_token=claim_token,
                    processing_started_at=now,
                    updated_at=now,
                )
            )
            if not changed.rowcount:
                return None
            row = connection.execute(
                select(interview_reviews).where(
                    interview_reviews.c.review_id == review_id,
                    interview_reviews.c.claim_token == claim_token,
                )
            ).mappings().first()
        return dict(row) if row else None

    def complete_interview_transcription(
        self,
        *,
        review_id: str,
        claim_token: str,
        transcript_json: str,
    ) -> str | None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            row = connection.execute(
                select(interview_reviews.c.storage_key).where(
                    interview_reviews.c.review_id == review_id,
                    interview_reviews.c.status == "transcribing",
                    interview_reviews.c.claim_token == claim_token,
                )
            ).first()
            if not row:
                return None
            connection.execute(
                update(interview_reviews)
                .where(
                    interview_reviews.c.review_id == review_id,
                    interview_reviews.c.status == "transcribing",
                    interview_reviews.c.claim_token == claim_token,
                )
                .values(
                    transcript_json=transcript_json,
                    transcript_revision=1,
                    status="awaiting_confirmation",
                    storage_key=None,
                    claim_token=None,
                    processing_started_at=None,
                    error_category=None,
                    error=None,
                    updated_at=now,
                )
            )
        return str(row[0]) if row[0] else None

    def schedule_interview_review_analysis(
        self,
        *,
        user_id: str,
        review_id: str,
        expected_revision: int,
        idempotency_key: str,
        request_digest: str,
        prompt_version: str,
    ) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            row = connection.execute(
                select(interview_reviews).where(
                    interview_reviews.c.user_id == user_id,
                    interview_reviews.c.review_id == review_id,
                )
            ).mappings().first()
            if not row:
                return {"outcome": "not_found"}
            if (
                row["analysis_idempotency_key"] == idempotency_key
                and row["analysis_request_digest"] == request_digest
                and row["status"] == "ready"
            ):
                return {"outcome": "completed"}
            if (
                row["analysis_idempotency_key"] == idempotency_key
                and row["analysis_request_digest"] != request_digest
            ):
                return {"outcome": "key_reused"}
            if int(row["transcript_revision"]) != expected_revision:
                return {"outcome": "stale_revision"}
            if row["status"] != "awaiting_confirmation":
                return {"outcome": "invalid_status"}
            changed = connection.execute(
                update(interview_reviews)
                .where(
                    interview_reviews.c.user_id == user_id,
                    interview_reviews.c.review_id == review_id,
                    interview_reviews.c.status == "awaiting_confirmation",
                    interview_reviews.c.transcript_revision
                    == expected_revision,
                )
                .values(
                    status="analyzing",
                    confirmed_revision=expected_revision,
                    analysis_idempotency_key=idempotency_key,
                    analysis_request_digest=request_digest,
                    claim_token=None,
                    prompt_version=prompt_version,
                    processing_started_at=now,
                    updated_at=now,
                )
            )
            if not changed.rowcount:
                return {"outcome": "conflict"}
        return {"outcome": "scheduled"}

    def claim_interview_review_analysis(
        self,
        *,
        review_id: str,
        claim_token: str,
    ) -> dict[str, object] | None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(interview_reviews)
                .where(
                    interview_reviews.c.review_id == review_id,
                    interview_reviews.c.status.in_(["analyzing", "failed"]),
                    interview_reviews.c.claim_token.is_(None),
                    interview_reviews.c.confirmed_revision
                    == interview_reviews.c.transcript_revision,
                    interview_reviews.c.analysis_idempotency_key.is_not(None),
                )
                .values(
                    status="analyzing",
                    claim_token=claim_token,
                    processing_started_at=now,
                    updated_at=now,
                )
            )
            if not changed.rowcount:
                return None
            row = connection.execute(
                select(interview_reviews).where(
                    interview_reviews.c.review_id == review_id,
                    interview_reviews.c.claim_token == claim_token,
                )
            ).mappings().first()
        return dict(row) if row else None

    def fail_scheduled_interview_review_analysis(
        self,
        *,
        user_id: str,
        review_id: str,
        error: str,
    ) -> bool:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(interview_reviews)
                .where(
                    interview_reviews.c.user_id == user_id,
                    interview_reviews.c.review_id == review_id,
                    interview_reviews.c.status == "analyzing",
                    interview_reviews.c.claim_token.is_(None),
                )
                .values(
                    status="failed",
                    error_category="queue_unavailable",
                    error=error[:2000],
                    updated_at=now,
                )
            )
        return bool(changed.rowcount)

    def complete_interview_review_analysis(
        self,
        *,
        review_id: str,
        claim_token: str,
        report_json: str,
        turns: list[dict[str, object]],
        model_version: str,
        schema_version: str = "interview-review-v1",
    ) -> bool:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            row = connection.execute(
                select(
                    interview_reviews.c.user_id,
                    interview_reviews.c.confirmed_revision,
                    interview_reviews.c.transcript_revision,
                ).where(
                    interview_reviews.c.review_id == review_id,
                    interview_reviews.c.status == "analyzing",
                    interview_reviews.c.claim_token == claim_token,
                )
            ).mappings().first()
            if (
                not row
                or row["confirmed_revision"] != row["transcript_revision"]
            ):
                return False
            connection.execute(
                delete(interview_review_turns).where(
                    interview_review_turns.c.user_id == row["user_id"],
                    interview_review_turns.c.review_id == review_id,
                )
            )
            for index, turn in enumerate(turns, start=1):
                connection.execute(
                    insert(interview_review_turns).values(
                        user_id=row["user_id"],
                        review_id=review_id,
                        turn_index=index,
                        created_at=now,
                        **turn,
                    )
                )
            changed = connection.execute(
                update(interview_reviews)
                .where(
                    interview_reviews.c.review_id == review_id,
                    interview_reviews.c.status == "analyzing",
                    interview_reviews.c.claim_token == claim_token,
                )
                .values(
                    status="ready",
                    report_json=report_json,
                    model_version=model_version,
                    schema_version=schema_version,
                    claim_token=None,
                    processing_started_at=None,
                    error_category=None,
                    error=None,
                    updated_at=now,
                )
            )
        return bool(changed.rowcount)

    def fail_interview_review_job(
        self,
        *,
        review_id: str,
        claim_token: str,
        error_category: str,
        error: str,
    ) -> bool:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(interview_reviews)
                .where(
                    interview_reviews.c.review_id == review_id,
                    interview_reviews.c.claim_token == claim_token,
                    interview_reviews.c.status.in_(
                        ["transcribing", "analyzing"]
                    ),
                )
                .values(
                    status="failed",
                    claim_token=None,
                    processing_started_at=None,
                    error_category=error_category[:80],
                    error=error[:2000],
                    updated_at=now,
                )
            )
        return bool(changed.rowcount)

    def retry_interview_transcription(
        self,
        *,
        user_id: str,
        review_id: str,
    ) -> bool:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(interview_reviews)
                .where(
                    interview_reviews.c.user_id == user_id,
                    interview_reviews.c.review_id == review_id,
                    interview_reviews.c.input_type == "audio",
                    interview_reviews.c.status == "failed",
                    interview_reviews.c.storage_key.is_not(None),
                )
                .values(
                    status="transcribing",
                    error_category=None,
                    error=None,
                    updated_at=now,
                )
            )
        return bool(changed.rowcount)

    def delete_interview_review(
        self,
        *,
        user_id: str,
        review_id: str,
    ) -> str | None:
        self.initialize()
        with self.engine.begin() as connection:
            row = connection.execute(
                select(interview_reviews.c.storage_key).where(
                    interview_reviews.c.user_id == user_id,
                    interview_reviews.c.review_id == review_id,
                )
            ).first()
            if not row:
                return None
            connection.execute(
                delete(interview_reviews).where(
                    interview_reviews.c.user_id == user_id,
                    interview_reviews.c.review_id == review_id,
                )
            )
        return str(row[0] or "")
