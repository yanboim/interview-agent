"""面试复盘应用服务（转写/确认/分析）的测试。"""

import io
from pathlib import Path

import pytest

from app.application.interview_review_service import (
    InterviewReviewConflict,
    InterviewReviewService,
)
from app.config import Settings
from app.interview_review_engine import (
    InterviewReviewResult,
    ReviewTurnAssessment,
)
from app.storage import ConversationStore
from app.user_files import LocalUserFileStore


class FakeTranscriptionProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def transcribe(self, **_):
        if self.fail:
            raise TimeoutError("provider timeout")
        return [
            {
                "segment_id": "s1",
                "speaker": "unknown",
                "text": "请介绍缓存一致性方案",
            },
            {
                "segment_id": "s2",
                "speaker": "unknown",
                "text": "我会使用延迟双删",
            },
        ]


def analyzer(*, turns, settings):
    del settings
    return InterviewReviewResult(
        overall_summary="候选人具备基础方案意识。",
        dimension_scores={
            "accuracy": 7,
            "depth": 6,
            "communication": 8,
            "practicality": 7,
        },
        strengths=["表达清晰"],
        weaknesses=["异常场景不足"],
        action_plan=["补充并发写入场景"],
        turns=[
            ReviewTurnAssessment(
                turn_index=index,
                score=7,
                dimensions={
                    "accuracy": 7,
                    "depth": 6,
                    "communication": 8,
                    "practicality": 7,
                },
                strengths=["结构清晰"],
                weaknesses=["缺少权衡"],
                feedback="补充失败处理。",
                improved_answer="先说明一致性目标，再比较方案。",
            )
            for index, _ in enumerate(turns, start=1)
        ],
    )


def make_service(tmp_path: Path, *, provider_fail: bool = False):
    store = ConversationStore(tmp_path / "reviews.db")
    files = LocalUserFileStore(tmp_path / "files", max_upload_bytes=2_000_000)
    jobs = []

    def enqueue(job_type, payload, **kwargs):
        jobs.append({"type": job_type, "payload": payload, **kwargs})
        return "job-1"

    settings = Settings(
        _env_file=None,
        review_feature_enabled=True,
        transcription_enabled=True,
        transcription_api_url="https://transcription.invalid",
        transcription_api_key="test-key",
        user_files_dir=tmp_path / "files",
        review_max_audio_bytes=2_000_000,
        zhipu_model="test-model",
    )
    service = InterviewReviewService(
        store,
        files,
        settings,
        enqueue=enqueue,
        transcription_provider=FakeTranscriptionProvider(
            fail=provider_fail
        ),
        analyzer=analyzer,
    )
    return service, store, files, jobs


def test_text_review_edit_confirm_and_analysis_lifecycle(
    tmp_path: Path,
) -> None:
    service, _, _, jobs = make_service(tmp_path)
    created = service.create_text(
        user_id="user-1",
        transcript=(
            "面试官：请介绍缓存一致性方案\n\n"
            "候选人：我会先明确一致性目标，再选择延迟双删。"
        ),
        idempotency_key="review-text-key",
    )
    assert created["status"] == "awaiting_confirmation"
    assert created["segments"][0]["speaker"] == "interviewer"

    segments = created["segments"]
    segments[1]["text"] += "并监控失败重试。"
    edited = service.update_transcript(
        user_id="user-1",
        review_id=created["review_id"],
        expected_revision=1,
        segments_payload=segments,
    )
    assert edited["transcript_revision"] == 2
    assert edited["confirmed_revision"] is None

    scheduled = service.confirm_and_analyze(
        user_id="user-1",
        review_id=created["review_id"],
        expected_revision=2,
        idempotency_key="review-analysis-key",
    )
    assert scheduled["status"] == "analyzing"
    assert jobs[-1]["type"] == "interview_review_analysis"
    assert jobs[-1]["payload"] == {"review_id": created["review_id"]}

    result = service.process_analysis(review_id=created["review_id"])
    assert result["outcome"] == "completed"
    ready = service.get(
        user_id="user-1",
        review_id=created["review_id"],
    )
    assert ready["status"] == "ready"
    assert ready["turns"][0]["answer"].startswith("我会先明确")
    assert ready["turns"][0]["score"] == 7
    assert ready["report"]["overall_summary"]
    capability_rows = service.repository.get_capability_rows(user_id="user-1")
    assert capability_rows[-1]["source_type"] == "real"
    assert capability_rows[-1]["topic"] == "面试复盘"


def test_text_review_idempotency_owner_and_confirmation_guards(
    tmp_path: Path,
) -> None:
    service, _, _, _ = make_service(tmp_path)
    transcript = "面试官：问题\n\n候选人：回答"
    first = service.create_text(
        user_id="user-1",
        transcript=transcript,
        idempotency_key="review-text-key",
    )
    replay = service.create_text(
        user_id="user-1",
        transcript=transcript,
        idempotency_key="review-text-key",
    )
    assert replay["review_id"] == first["review_id"]
    assert service.list(user_id="user-2") == []
    with pytest.raises(InterviewReviewConflict):
        service.create_text(
            user_id="user-1",
            transcript="面试官：不同问题\n\n候选人：不同回答",
            idempotency_key="review-text-key",
        )
    with pytest.raises(InterviewReviewConflict, match="版本"):
        service.confirm_and_analyze(
            user_id="user-1",
            review_id=first["review_id"],
            expected_revision=2,
            idempotency_key="analysis-key",
        )

    unknown = service.create_text(
        user_id="user-1",
        transcript="这是一段没有角色标记的逐字稿",
        idempotency_key="review-unknown-key",
    )
    with pytest.raises(ValueError, match="说话人"):
        service.confirm_and_analyze(
            user_id="user-1",
            review_id=unknown["review_id"],
            expected_revision=1,
            idempotency_key="unknown-analysis-key",
        )


def wav_bytes() -> bytes:
    return b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt " + b"\x00" * 40


def test_audio_transcription_deletes_source_only_after_commit(
    tmp_path: Path,
) -> None:
    service, store, files, jobs = make_service(tmp_path)
    created = service.create_audio(
        user_id="user-1",
        original_filename="synthetic.wav",
        source=io.BytesIO(wav_bytes()),
        external_processing_consent=True,
        idempotency_key="review-audio-key",
    )
    raw = store.get_interview_review(
        user_id="user-1",
        review_id=created["review_id"],
    )
    storage_key = str(raw["storage_key"])
    assert files.path(storage_key).is_file()
    assert jobs[0]["type"] == "interview_transcription"

    service.process_transcription(review_id=created["review_id"])
    completed = service.get(
        user_id="user-1",
        review_id=created["review_id"],
    )
    assert completed["status"] == "awaiting_confirmation"
    assert all(
        segment["speaker"] == "unknown"
        for segment in completed["segments"]
    )
    assert not (tmp_path / "files" / storage_key).exists()


def test_audio_failure_preserves_source_and_delete_cleans_it(
    tmp_path: Path,
) -> None:
    service, store, files, _ = make_service(tmp_path, provider_fail=True)
    created = service.create_audio(
        user_id="user-1",
        original_filename="synthetic.wav",
        source=io.BytesIO(wav_bytes()),
        external_processing_consent=True,
        idempotency_key="review-audio-key",
    )
    raw = store.get_interview_review(
        user_id="user-1",
        review_id=created["review_id"],
    )
    storage_key = str(raw["storage_key"])
    with pytest.raises(TimeoutError):
        service.process_transcription(review_id=created["review_id"])
    assert files.path(storage_key).is_file()
    assert service.delete(
        user_id="user-1",
        review_id=created["review_id"],
    )
    assert not (tmp_path / "files" / storage_key).exists()


def test_failed_audio_job_can_be_reclaimed_by_worker_retry(
    tmp_path: Path,
) -> None:
    service, _, _, _ = make_service(tmp_path, provider_fail=True)
    created = service.create_audio(
        user_id="user-1",
        original_filename="synthetic.wav",
        source=io.BytesIO(wav_bytes()),
        external_processing_consent=True,
        idempotency_key="review-audio-key",
    )
    with pytest.raises(TimeoutError):
        service.process_transcription(review_id=created["review_id"])
    service.transcription_provider.fail = False

    assert service.process_transcription(
        review_id=created["review_id"]
    )["outcome"] == "completed"


def test_audio_requires_explicit_external_processing_consent(
    tmp_path: Path,
) -> None:
    service, _, _, _ = make_service(tmp_path)
    with pytest.raises(InterviewReviewConflict, match="确认"):
        service.create_audio(
            user_id="user-1",
            original_filename="synthetic.wav",
            source=io.BytesIO(wav_bytes()),
            external_processing_consent=False,
            idempotency_key="review-audio-key",
        )
