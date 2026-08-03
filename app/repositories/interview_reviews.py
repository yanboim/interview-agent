"""Interview review and transcription persistence slice."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, insert, select, update

from app.database import interview_review_turns, interview_reviews


class InterviewReviewRepositoryMixin:
    engine: Any

    def initialize(self) -> None: ...

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
