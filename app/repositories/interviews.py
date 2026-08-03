"""Interview session and owner-fenced answer persistence slice."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, insert, select, update

from app.database import (
    interview_answer_attempts,
    interview_turns,
    interviews,
    resume_documents,
)


class InterviewRepositoryMixin:
    engine: Any

    def initialize(self) -> None: ...

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
