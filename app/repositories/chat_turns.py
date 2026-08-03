"""Durable, owner-fenced chat-turn transaction scripts."""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from app.chat_context import ContextMessage, plan_chat_context
from app.database import chat_turns, conversations, messages


class ChatTurnRepositoryMixin:
    engine: Any

    def initialize(self) -> None: ...

    def begin_chat_turn(
        self, *, user_id: str, session_id: str, content: str,
        idempotency_key: str, request_digest: str, turn_id: str,
        claim_token: str, context_token_budget: int,
        summary_token_budget: int,
    ) -> dict[str, object]:
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
                    connection.execute(insert(conversations).values(
                        user_id=user_id, session_id=session_id, title=title,
                        mode="chat", next_chat_turn_index=1,
                        created_at=now, updated_at=now,
                    ))
        except IntegrityError:
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
                            if existing["metadata_json"] else {}
                        ),
                    }
                if status in {"pending", "generating"}:
                    return {"outcome": "in_progress"}
                if status not in {"failed", "cancelled"}:
                    return {"outcome": "conflict"}
                active = connection.execute(
                    update(conversations).where(
                        conversations.c.user_id == user_id,
                        conversations.c.session_id == session_id,
                        conversations.c.active_chat_turn_id.is_(None),
                    ).values(active_chat_turn_id=existing["turn_id"], updated_at=now)
                )
                if active.rowcount != 1:
                    return {"outcome": "conflict"}
                claimed = connection.execute(
                    update(chat_turns).where(
                        chat_turns.c.turn_id == existing["turn_id"],
                        chat_turns.c.status.in_(("failed", "cancelled")),
                        chat_turns.c.request_digest == request_digest,
                    ).values(
                        status="generating", claim_token=claim_token,
                        assistant_content=None, metadata_json=None, error=None,
                        updated_at=now,
                    )
                )
                if claimed.rowcount != 1:
                    raise ValueError("chat turn claim lost")
                claimed_turn_id = str(existing["turn_id"])
                turn_index = int(existing["turn_index"])
            else:
                activated = connection.execute(
                    update(conversations).where(
                        conversations.c.user_id == user_id,
                        conversations.c.session_id == session_id,
                        conversations.c.active_chat_turn_id.is_(None),
                    ).values(
                        active_chat_turn_id=turn_id,
                        next_chat_turn_index=conversations.c.next_chat_turn_index + 1,
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
                connection.execute(insert(chat_turns).values(
                    turn_id=turn_id, user_id=user_id, session_id=session_id,
                    turn_index=turn_index, idempotency_key=idempotency_key,
                    request_digest=request_digest, request_content=content,
                    status="pending", created_at=now, updated_at=now,
                ))
                claimed = connection.execute(
                    update(chat_turns).where(
                        chat_turns.c.turn_id == turn_id,
                        chat_turns.c.status == "pending",
                    ).values(status="generating", claim_token=claim_token, updated_at=now)
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
                select(messages.c.id, messages.c.role, messages.c.content).where(
                    messages.c.user_id == user_id,
                    messages.c.session_id == session_id,
                    *((messages.c.id > conversation["chat_summary_through_message_id"],)
                      if conversation["chat_summary_through_message_id"] is not None
                      else ()),
                ).order_by(messages.c.id)
            ).mappings().all()
            context = plan_chat_context(
                (ContextMessage(id=int(row["id"]), role=str(row["role"]),
                                content=str(row["content"])) for row in history),
                current_content=content,
                existing_summary=str(conversation["chat_summary"] or ""),
                summary_through_message_id=(
                    int(conversation["chat_summary_through_message_id"])
                    if conversation["chat_summary_through_message_id"] is not None
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
                connection.execute(update(conversations).where(
                    conversations.c.user_id == user_id,
                    conversations.c.session_id == session_id,
                ).values(
                    chat_summary=context.summary,
                    chat_summary_through_message_id=context.summary_through_message_id,
                    updated_at=now,
                ))
            return {
                "outcome": "claimed", "turn_id": claimed_turn_id,
                "turn_index": turn_index, "claim_token": claim_token,
                "history": list(context.history),
                "context_estimated_tokens": context.estimated_tokens,
                "context_truncated_messages": context.truncated_messages,
            }

    def complete_chat_turn(
        self, *, user_id: str, session_id: str, turn_id: str,
        claim_token: str, answer: str, metadata: dict[str, object],
    ) -> None:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        with self.engine.begin() as connection:
            turn = connection.execute(
                select(chat_turns.c.request_content, chat_turns.c.turn_index).where(
                    chat_turns.c.turn_id == turn_id,
                    chat_turns.c.user_id == user_id,
                    chat_turns.c.session_id == session_id,
                    chat_turns.c.status == "generating",
                    chat_turns.c.claim_token == claim_token,
                )
            ).mappings().first()
            if not turn:
                raise ValueError("chat turn claim lost")
            completed = connection.execute(update(chat_turns).where(
                chat_turns.c.turn_id == turn_id,
                chat_turns.c.status == "generating",
                chat_turns.c.claim_token == claim_token,
            ).values(
                status="completed", claim_token=None, assistant_content=answer,
                metadata_json=metadata_json, error=None, updated_at=now,
            ))
            if completed.rowcount != 1:
                raise ValueError("chat turn claim lost")
            connection.execute(insert(messages), [
                {"user_id": user_id, "session_id": session_id, "role": "user",
                 "content": str(turn["request_content"]), "metadata_json": None,
                 "created_at": now},
                {"user_id": user_id, "session_id": session_id, "role": "assistant",
                 "content": answer, "metadata_json": metadata_json, "created_at": now},
            ])
            released = connection.execute(update(conversations).where(
                conversations.c.user_id == user_id,
                conversations.c.session_id == session_id,
                conversations.c.active_chat_turn_id == turn_id,
            ).values(active_chat_turn_id=None, updated_at=now))
            if released.rowcount != 1:
                raise ValueError("chat session ownership lost")

    def terminate_chat_turn(
        self, *, turn_id: str, claim_token: str, status: str,
        partial_answer: str, error: str,
    ) -> bool:
        if status not in {"failed", "cancelled"}:
            raise ValueError("invalid terminal chat status")
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as connection:
            turn = connection.execute(select(
                chat_turns.c.user_id, chat_turns.c.session_id,
            ).where(
                chat_turns.c.turn_id == turn_id,
                chat_turns.c.status == "generating",
                chat_turns.c.claim_token == claim_token,
            )).mappings().first()
            if not turn:
                return False
            changed = connection.execute(update(chat_turns).where(
                chat_turns.c.turn_id == turn_id,
                chat_turns.c.status == "generating",
                chat_turns.c.claim_token == claim_token,
            ).values(
                status=status, claim_token=None, assistant_content=partial_answer,
                error=error[:1000], updated_at=now,
            ))
            if changed.rowcount != 1:
                return False
            released = connection.execute(update(conversations).where(
                conversations.c.user_id == turn["user_id"],
                conversations.c.session_id == turn["session_id"],
                conversations.c.active_chat_turn_id == turn_id,
            ).values(active_chat_turn_id=None, updated_at=now))
            if released.rowcount != 1:
                raise ValueError("chat session ownership lost")
        return True

    def recover_stale_chat_turns(
        self,
        *,
        stale_before: datetime,
        limit: int = 100,
    ) -> list[str]:
        """回收进程崩溃后超龄的 generating 回合，并封闭旧 owner 写入。

        先按 ``updated_at`` 选择有限数量候选，再以状态、claim token 和原时间戳
        做条件更新。成功回收后清空会话活动回合；迟到的旧模型调用因状态/token
        已改变，无法通过 ``complete_chat_turn`` 的 fencing 条件。
        """
        if stale_before.tzinfo is None:
            raise ValueError("stale_before must be timezone-aware")
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        self.initialize()
        cutoff = stale_before.astimezone(UTC).isoformat()
        now = datetime.now(UTC).isoformat()
        recovered: list[str] = []
        with self.engine.begin() as connection:
            candidates = connection.execute(
                select(
                    chat_turns.c.turn_id,
                    chat_turns.c.user_id,
                    chat_turns.c.session_id,
                    chat_turns.c.claim_token,
                    chat_turns.c.updated_at,
                ).where(
                    chat_turns.c.status == "generating",
                    chat_turns.c.updated_at < cutoff,
                ).order_by(chat_turns.c.updated_at).limit(limit)
            ).mappings().all()
            for candidate in candidates:
                changed = connection.execute(
                    update(chat_turns).where(
                        chat_turns.c.turn_id == candidate["turn_id"],
                        chat_turns.c.status == "generating",
                        chat_turns.c.claim_token == candidate["claim_token"],
                        chat_turns.c.updated_at == candidate["updated_at"],
                    ).values(
                        status="failed",
                        claim_token=None,
                        error="StaleClaimRecovered: operator recovery",
                        updated_at=now,
                    )
                )
                if changed.rowcount != 1:
                    continue
                connection.execute(
                    update(conversations).where(
                        conversations.c.user_id == candidate["user_id"],
                        conversations.c.session_id == candidate["session_id"],
                        conversations.c.active_chat_turn_id == candidate["turn_id"],
                    ).values(active_chat_turn_id=None, updated_at=now)
                )
                recovered.append(str(candidate["turn_id"]))
        return recovered

    def get_chat_turn(
        self, *, user_id: str, session_id: str, turn_id: str,
    ) -> dict[str, object] | None:
        self.initialize()
        with self.engine.connect() as connection:
            row = connection.execute(select(chat_turns).where(
                chat_turns.c.user_id == user_id,
                chat_turns.c.session_id == session_id,
                chat_turns.c.turn_id == turn_id,
            )).mappings().first()
        return dict(row) if row else None
