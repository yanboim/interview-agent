"""真实面试复盘服务：管理上传、转写确认、后台分析及所有权隔离的状态转换。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, BinaryIO, Callable
from uuid import uuid4

from app.config import Settings
from app.interview_review_engine import (
    InterviewReviewResult,
    TranscriptSegment,
    analyze_interview_review,
    pair_confirmed_turns,
    parse_text_transcript,
)
from app.resume_engine import deserialize_json
from app.transcription import TranscriptionProvider
from app.user_files import LocalUserFileStore


class InterviewReviewError(RuntimeError):
    pass


class InterviewReviewNotFound(InterviewReviewError):
    pass


class InterviewReviewConflict(InterviewReviewError):
    pass


class InterviewReviewUnavailable(InterviewReviewError):
    pass


class InterviewReviewService:
    def __init__(
        self,
        repository: Any,
        files: LocalUserFileStore,
        settings: Settings,
        *,
        enqueue: Callable[..., str],
        transcription_provider: TranscriptionProvider,
        analyzer: Callable[..., InterviewReviewResult] = analyze_interview_review,
    ) -> None:
        self.repository = repository
        self.files = files
        self.settings = settings
        self.enqueue = enqueue
        self.transcription_provider = transcription_provider
        self.analyzer = analyzer

    def create_text(
        self,
        *,
        user_id: str,
        transcript: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        segments = parse_text_transcript(transcript)
        digest = hashlib.sha256(
            transcript.strip().encode("utf-8")
        ).hexdigest()
        review_id = str(uuid4())
        result = self.repository.create_interview_review(
            user_id=user_id,
            review_id=review_id,
            input_type="text",
            transcript_json=self._segments_json(segments),
            create_idempotency_key=idempotency_key,
            create_request_digest=digest,
            external_processing_consent=False,
        )
        return self._resolve_create_result(
            user_id=user_id,
            review_id=review_id,
            result=result,
        )

    def create_audio(
        self,
        *,
        user_id: str,
        original_filename: str,
        source: BinaryIO,
        external_processing_consent: bool,
        idempotency_key: str,
    ) -> dict[str, object]:
        if not external_processing_consent:
            raise InterviewReviewConflict("上传音频前必须确认外部转写数据流")
        if (
            not self.settings.transcription_enabled
            or not self.settings.transcription_api_url
            or not self.settings.transcription_api_key
        ):
            raise InterviewReviewUnavailable(
                "音频转写服务未启用；仍可使用文本逐字稿入口"
            )
        review_id = str(uuid4())
        stored = self.files.save_audio(
            user_id=user_id,
            asset_id=review_id,
            original_filename=original_filename,
            source=source,
            max_upload_bytes=self.settings.review_max_audio_bytes,
        )
        digest = hashlib.sha256(
            (
                stored.sha256
                + "\x1f"
                + self.settings.transcription_provider_name
            ).encode("utf-8")
        ).hexdigest()
        result = self.repository.create_interview_review(
            user_id=user_id,
            review_id=review_id,
            input_type="audio",
            transcript_json=None,
            create_idempotency_key=idempotency_key,
            create_request_digest=digest,
            external_processing_consent=True,
            original_filename=self._display_filename(original_filename),
            content_type=stored.content_type,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            storage_key=stored.storage_key,
        )
        outcome = str(result["outcome"])
        if outcome != "created":
            self.files.delete(stored.storage_key)
            return self._resolve_create_result(
                user_id=user_id,
                review_id=review_id,
                result=result,
            )
        try:
            self._enqueue(
                "interview_transcription",
                review_id,
                idempotency_key,
            )
        except Exception as exc:
            token = str(uuid4())
            if self.repository.claim_interview_transcription(
                review_id=review_id,
                claim_token=token,
            ):
                self.repository.fail_interview_review_job(
                    review_id=review_id,
                    claim_token=token,
                    error_category="queue_unavailable",
                    error=str(exc),
                )
            raise InterviewReviewUnavailable(
                "转写队列暂不可用，请稍后重试"
            ) from exc
        return self.get(user_id=user_id, review_id=review_id)

    def list(self, *, user_id: str) -> list[dict[str, object]]:
        return [
            self._public_review(item, include_transcript=False)
            for item in self.repository.list_interview_reviews(user_id=user_id)
        ]

    def get(
        self,
        *,
        user_id: str,
        review_id: str,
    ) -> dict[str, object]:
        review = self.repository.get_interview_review(
            user_id=user_id,
            review_id=review_id,
        )
        if not review:
            raise InterviewReviewNotFound("面试复盘不存在")
        return self._public_review(review, include_transcript=True)

    def update_transcript(
        self,
        *,
        user_id: str,
        review_id: str,
        expected_revision: int,
        segments_payload: list[dict[str, object]],
    ) -> dict[str, object]:
        segments = [
            TranscriptSegment.model_validate(item)
            for item in segments_payload
        ]
        if not segments:
            raise InterviewReviewConflict("逐字稿不能为空")
        updated = self.repository.update_interview_review_transcript(
            user_id=user_id,
            review_id=review_id,
            expected_revision=expected_revision,
            transcript_json=self._segments_json(segments),
        )
        if not updated:
            raise InterviewReviewConflict("逐字稿已有新版本，请刷新后重试")
        return self._public_review(updated, include_transcript=True)

    def confirm_and_analyze(
        self,
        *,
        user_id: str,
        review_id: str,
        expected_revision: int,
        idempotency_key: str,
    ) -> dict[str, object]:
        review = self.repository.get_interview_review(
            user_id=user_id,
            review_id=review_id,
        )
        if not review:
            raise InterviewReviewNotFound("面试复盘不存在")
        segments = self._segments(review.get("transcript_json"))
        pair_confirmed_turns(segments)
        request_digest = hashlib.sha256(
            (
                str(expected_revision)
                + "\x1f"
                + str(review.get("transcript_json") or "")
            ).encode("utf-8")
        ).hexdigest()
        if (
            review.get("analysis_idempotency_key") == idempotency_key
            and review.get("analysis_request_digest") == request_digest
            and review.get("status") in {"analyzing", "ready"}
        ):
            return self._public_review(review, include_transcript=True)
        result = self.repository.schedule_interview_review_analysis(
            user_id=user_id,
            review_id=review_id,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            prompt_version=self.settings.review_prompt_version,
        )
        outcome = str(result["outcome"])
        if outcome == "not_found":
            raise InterviewReviewNotFound("面试复盘不存在")
        if outcome == "key_reused":
            raise InterviewReviewConflict("同一幂等键不能用于不同逐字稿版本")
        if outcome == "stale_revision":
            raise InterviewReviewConflict("确认版本已过期，请刷新后重试")
        if outcome == "invalid_status":
            current = self.get(user_id=user_id, review_id=review_id)
            if current["status"] == "ready":
                return current
            raise InterviewReviewConflict("当前状态不能开始复盘分析")
        if outcome == "completed":
            return self.get(user_id=user_id, review_id=review_id)
        if outcome not in {"scheduled"}:
            raise InterviewReviewConflict("复盘分析提交冲突")
        try:
            self._enqueue(
                "interview_review_analysis",
                review_id,
                idempotency_key,
            )
        except Exception as exc:
            self.repository.fail_scheduled_interview_review_analysis(
                user_id=user_id,
                review_id=review_id,
                error=str(exc),
            )
            raise InterviewReviewUnavailable(
                "复盘分析队列暂不可用，请稍后重试"
            ) from exc
        return self.get(user_id=user_id, review_id=review_id)

    def retry(self, *, user_id: str, review_id: str) -> dict[str, object]:
        review = self.repository.get_interview_review(
            user_id=user_id,
            review_id=review_id,
        )
        if not review:
            raise InterviewReviewNotFound("面试复盘不存在")
        if not self.repository.retry_interview_transcription(
            user_id=user_id,
            review_id=review_id,
        ):
            raise InterviewReviewConflict("当前失败不能直接重试，请先检查逐字稿")
        try:
            self._enqueue(
                "interview_transcription",
                review_id,
                str(uuid4()),
            )
        except Exception as exc:
            token = str(uuid4())
            if self.repository.claim_interview_transcription(
                review_id=review_id,
                claim_token=token,
            ):
                self.repository.fail_interview_review_job(
                    review_id=review_id,
                    claim_token=token,
                    error_category="queue_unavailable",
                    error=str(exc),
                )
            raise InterviewReviewUnavailable("转写队列暂不可用") from exc
        return self.get(user_id=user_id, review_id=review_id)

    def delete(self, *, user_id: str, review_id: str) -> bool:
        storage_key = self.repository.delete_interview_review(
            user_id=user_id,
            review_id=review_id,
        )
        if storage_key is None:
            return False
        if storage_key:
            self.files.delete(storage_key)
        return True

    def process_transcription(self, *, review_id: str) -> dict[str, object]:
        token = str(uuid4())
        review = self.repository.claim_interview_transcription(
            review_id=review_id,
            claim_token=token,
        )
        if not review:
            return {"review_id": review_id, "outcome": "not_claimed"}
        try:
            segments = self.transcription_provider.transcribe(
                path=self.files.path(str(review["storage_key"])),
                content_type=str(review["content_type"]),
                filename=str(review.get("original_filename") or "audio"),
            )
            validated = [
                TranscriptSegment.model_validate(item)
                for item in segments
            ]
            storage_key = self.repository.complete_interview_transcription(
                review_id=review_id,
                claim_token=token,
                transcript_json=self._segments_json(validated),
            )
            if storage_key is None:
                raise InterviewReviewConflict("转写完成提交被拒绝")
            if storage_key:
                self.files.delete(storage_key)
            return {"review_id": review_id, "outcome": "completed"}
        except Exception as exc:
            self.repository.fail_interview_review_job(
                review_id=review_id,
                claim_token=token,
                error_category=type(exc).__name__,
                error=str(exc),
            )
            raise

    def process_analysis(self, *, review_id: str) -> dict[str, object]:
        token = str(uuid4())
        review = self.repository.claim_interview_review_analysis(
            review_id=review_id,
            claim_token=token,
        )
        if not review:
            return {"review_id": review_id, "outcome": "not_claimed"}
        try:
            paired = pair_confirmed_turns(
                self._segments(review.get("transcript_json"))
            )
            result = self.analyzer(turns=paired, settings=self.settings)
            assessments = {turn.turn_index: turn for turn in result.turns}
            stored_turns = []
            for index, turn in enumerate(paired, start=1):
                assessment = assessments[index]
                stored_turns.append(
                    {
                        "question": turn["question"],
                        "answer": turn["answer"],
                        "score": assessment.score,
                        "dimensions_json": json.dumps(
                            assessment.dimensions,
                            ensure_ascii=False,
                        ),
                        "strengths_json": json.dumps(
                            assessment.strengths,
                            ensure_ascii=False,
                        ),
                        "weaknesses_json": json.dumps(
                            assessment.weaknesses,
                            ensure_ascii=False,
                        ),
                        "feedback": assessment.feedback,
                        "improved_answer": assessment.improved_answer,
                    }
                )
            report = result.model_dump(exclude={"turns"})
            if not self.repository.complete_interview_review_analysis(
                review_id=review_id,
                claim_token=token,
                report_json=json.dumps(report, ensure_ascii=False),
                turns=stored_turns,
                model_version=self.settings.zhipu_model,
                schema_version="interview-review-v1",
            ):
                raise InterviewReviewConflict("复盘分析完成提交被拒绝")
            return {"review_id": review_id, "outcome": "completed"}
        except Exception as exc:
            self.repository.fail_interview_review_job(
                review_id=review_id,
                claim_token=token,
                error_category=type(exc).__name__,
                error=str(exc),
            )
            raise

    def _resolve_create_result(
        self,
        *,
        user_id: str,
        review_id: str,
        result: dict[str, object],
    ) -> dict[str, object]:
        if result["outcome"] == "key_reused":
            raise InterviewReviewConflict("同一幂等键不能用于不同内容")
        if result["outcome"] == "existing":
            review_id = str(result["review"]["review_id"])  # type: ignore[index]
        return self.get(user_id=user_id, review_id=review_id)

    def _enqueue(
        self,
        job_type: str,
        review_id: str,
        idempotency_key: str,
    ) -> None:
        self.enqueue(
            job_type,
            {"review_id": review_id},
            idempotency_key=f"{job_type}:{review_id}:{idempotency_key}",
            max_attempts=self.settings.job_max_attempts,
        )

    @staticmethod
    def _segments_json(segments: list[TranscriptSegment]) -> str:
        return json.dumps(
            [segment.model_dump() for segment in segments],
            ensure_ascii=False,
        )

    @staticmethod
    def _segments(value: object) -> list[TranscriptSegment]:
        payload = deserialize_json(value, [])
        if not isinstance(payload, list):
            raise InterviewReviewConflict("逐字稿数据损坏")
        return [TranscriptSegment.model_validate(item) for item in payload]

    @staticmethod
    def _display_filename(value: str) -> str:
        return (value.replace("\\", "/").rsplit("/", 1)[-1] or "audio")[:255]

    @classmethod
    def _public_review(
        cls,
        item: dict[str, object],
        *,
        include_transcript: bool,
    ) -> dict[str, object]:
        result = {
            "review_id": item["review_id"],
            "input_type": item["input_type"],
            "original_filename": item.get("original_filename"),
            "status": item["status"],
            "transcript_revision": int(item.get("transcript_revision") or 1),
            "confirmed_revision": item.get("confirmed_revision"),
            "report": deserialize_json(item.get("report_json"), None),
            "error_category": item.get("error_category"),
            "error": item.get("error"),
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
        }
        if include_transcript:
            result["segments"] = [
                segment.model_dump()
                for segment in cls._segments(item.get("transcript_json"))
            ]
            result["turns"] = [
                {
                    "turn_index": turn["turn_index"],
                    "question": turn["question"],
                    "answer": turn["answer"],
                    "score": turn.get("score"),
                    "dimensions": deserialize_json(
                        turn.get("dimensions_json"), {}
                    ),
                    "strengths": deserialize_json(
                        turn.get("strengths_json"), []
                    ),
                    "weaknesses": deserialize_json(
                        turn.get("weaknesses_json"), []
                    ),
                    "feedback": turn.get("feedback"),
                    "improved_answer": turn.get("improved_answer"),
                }
                for turn in item.get("turns", [])  # type: ignore[union-attr]
            ]
        return result
