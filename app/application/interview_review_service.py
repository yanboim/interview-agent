"""真实面试复盘服务：管理上传、转写确认、后台分析及所有权隔离的状态转换。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, BinaryIO, Callable, Protocol
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


class InterviewReviewRepository(Protocol):
    def create_interview_review(self, **kwargs: Any) -> Any: ...
    def list_interview_reviews(self, **kwargs: Any) -> Any: ...
    def get_interview_review(self, **kwargs: Any) -> Any: ...
    def update_interview_review_transcript(self, **kwargs: Any) -> Any: ...
    def claim_interview_transcription(self, **kwargs: Any) -> Any: ...
    def complete_interview_transcription(self, **kwargs: Any) -> Any: ...
    def schedule_interview_review_analysis(self, **kwargs: Any) -> Any: ...
    def claim_interview_review_analysis(self, **kwargs: Any) -> Any: ...
    def fail_scheduled_interview_review_analysis(self, **kwargs: Any) -> Any: ...
    def complete_interview_review_analysis(self, **kwargs: Any) -> Any: ...
    def fail_interview_review_job(self, **kwargs: Any) -> Any: ...
    def retry_interview_transcription(self, **kwargs: Any) -> Any: ...
    def delete_interview_review(self, **kwargs: Any) -> Any: ...


class InterviewReviewError(RuntimeError):
    """面试复盘服务应用层基类错误。"""


class InterviewReviewNotFound(InterviewReviewError):
    pass


class InterviewReviewConflict(InterviewReviewError):
    pass


class InterviewReviewUnavailable(InterviewReviewError):
    pass


class InterviewReviewService:
    """真实面试复盘服务：管理上传、转写确认、后台分析与所有权隔离。

    音频是用户敏感文件，仅在「转写开关 + 供应商配置 + 用户每次明确同意」
    三者同时满足时才接受；转写成功即删除音频。后台转写与分析都用
    claim_token 所有者封闭、有界模型调用，逐字稿草稿用乐观版本
    （transcript_revision）保护并发确认。
    """

    def __init__(
        self,
        repository: InterviewReviewRepository,
        files: LocalUserFileStore,
        settings: Settings,
        *,
        enqueue: Callable[..., str],
        transcription_provider: TranscriptionProvider,
        analyzer: Callable[..., InterviewReviewResult] = analyze_interview_review,
    ) -> None:
        """注入持久化仓库、文件存储、配置、入队回调与转写/分析回调。

        参数:
            repository: 持久化适配器（``ConversationStore`` 或替身）。
            files: 本地用户文件存储（音频暂存与清理）。
            settings: 应用配置（转写开关、音频上限、提示词版本等）。
            enqueue: 后台任务入队回调。
            transcription_provider: 外部转写提供方适配器。
            analyzer: 复盘分析回调，默认为引擎纯函数实现。
        """
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
        """创建基于文本逐字稿的复盘（幂等）。

        把文本逐字稿解析为段落后幂等创建复盘记录；同一幂等键换不同内容
        则报冲突。文本入口不要求外部转写服务，无需用户同意外发。

        返回:
            该复盘的公开视图。

        异常:
            InterviewReviewConflict: 同一幂等键不能用于不同内容。
        """
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
        """创建基于音频的复盘（需用户每次明确同意外发转写，幂等）。

        三重门禁：用户明确同意 + 转写开关 + 供应商配置齐全，缺一不可，
        否则拒绝上传。音频以服务端存储键暂存，幂等创建后入队转写；若入队
        失败则领取并标记失败，避免留下卡死任务。

        参数:
            external_processing_consent: 用户本次是否明确同意外部转写。

        返回:
            该复盘的公开视图（含上传后的初始状态）。

        异常:
            InterviewReviewConflict: 未确认外部转写数据流。
            InterviewReviewUnavailable: 转写服务未启用或队列暂不可用（可重试）。
        """
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
        """列出当前用户的所有复盘（不含逐字稿正文，所有者范围）。"""
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
        """获取单个复盘视图（含逐字稿与回合评分）。

        异常:
            InterviewReviewNotFound: 复盘不存在或不属于该用户。
        """
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
        """编辑/确认逐字稿草稿（乐观并发保护）。

        用 ``expected_revision`` 做条件更新，确保用户编辑不被并发转写或
        他方修改覆盖。确认后的版本才是复盘分析的输入。

        参数:
            expected_revision: 客户端持有的逐字稿版本号。
            segments_payload: 逐字稿段落数组。

        返回:
            更新后的复盘公开视图。

        异常:
            InterviewReviewConflict: 逐字稿为空，或已有新版本需刷新重试。
        """
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
        """确认逐字稿版本并排队后台复盘分析（幂等）。

        以 ``(expected_revision, transcript_json)`` 计算请求摘要，配合
        幂等键判定是否为重放：若已用相同键与版本排过队且状态在
        ``analyzing/ready``，则直接返回现状。否则条件调度分析任务并入队。

        参数:
            expected_revision: 客户端确认的逐字稿版本号。
            idempotency_key: 客户端幂等键。

        返回:
            该复盘的公开视图。

        异常:
            InterviewReviewNotFound: 复盘不存在。
            InterviewReviewConflict: 幂等键复用于不同版本 / 版本已过期 /
                当前状态不能开始分析。
            InterviewReviewUnavailable: 分析队列暂不可用（可重试）。
        """
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
        """重试失败的转写任务（仅转写失败可直接重试）。

        异常:
            InterviewReviewNotFound: 复盘不存在。
            InterviewReviewConflict: 当前失败不能直接重试（请先检查逐字稿）。
            InterviewReviewUnavailable: 转写队列暂不可用（可重试）。
        """
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
        """删除复盘记录及其暂存音频（幂等清理）。

        返回:
            是否删除了记录；删除后亦尝试清理底层音频文件，失败不报错（幂等）。
        """
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
        """后台执行音频转写（claim_token 所有者封闭）。

        先领取任务（仅所有者能完成），调用外部转写得到逐字稿段落，再条件
        提交并删除音频；任何异常都把任务标记失败再上抛。转写成功后音频
        立即删除，不再留存。

        返回:
            ``{"review_id", "outcome"}``，``outcome`` 为
            ``"completed"`` 或 ``"not_claimed"``。
        """
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
        """后台执行逐字稿复盘分析（claim_token 所有者封闭）。

        先领取任务，再在事务之外把已确认的问答回合送入引擎打分，最后把
        报告与各回合评分条件提交；任何异常都把任务标记失败再上抛。

        返回:
            ``{"review_id", "outcome"}``，``outcome`` 为
            ``"completed"`` 或 ``"not_claimed"``。
        """
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
        """统一解析幂等创建结果：重用既有记录或返回新记录的公开视图。"""
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
        """按任务类型入队后台作业，用幂等键保证可安全重放。"""
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
