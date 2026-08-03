"""Audit, observability, feedback, and release administration persistence."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, delete, insert, select, update

from app.database import (
    assistant_feedback,
    audit_events,
    chat_turns,
    conversations,
    deployment_releases,
    evaluation_candidates,
    execution_traces,
    interview_review_turns,
    interview_reviews,
    interview_turns,
    interviews,
    product_events,
    tool_audit_logs,
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


class AdministrationRepositoryMixin:
    engine: Any

    def initialize(self) -> None: ...

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
