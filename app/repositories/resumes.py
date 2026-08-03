"""Resume document and analysis persistence slice."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, insert, select, update

from app.database import resume_analyses, resume_documents


class ResumeRepositoryMixin:
    engine: Any

    def initialize(self) -> None: ...

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
