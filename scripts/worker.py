"""Redis 后台 Worker：以租约领取任务，续租期间执行，并按所有者令牌确认结果。"""

import logging
import threading
import time
from collections.abc import Callable
from uuid import uuid4

from app.config import get_settings
from app.application.interview_review_service import InterviewReviewService
from app.application.resume_service import ResumeService
from app.logging_config import configure_logging
from app.operations import JobClaim, RedisRuntime
from app.storage import ConversationStore
from app.transcription import HttpTranscriptionProvider
from app.user_files import LocalUserFileStore
from scripts.ingest import ingest_knowledge

logger = logging.getLogger(__name__)


def start_worker_heartbeat(
    runtime: RedisRuntime,
    *,
    interval_seconds: float,
    ttl_seconds: int,
) -> tuple[threading.Event, threading.Thread]:
    stopped = threading.Event()
    instance_id = str(uuid4())
    ttl = max(3, int(ttl_seconds))
    interval = min(
        max(0.1, float(interval_seconds)),
        max(0.1, ttl / 3),
    )

    def publish() -> None:
        try:
            runtime.publish_worker_heartbeat(
                instance_id,
                ttl_seconds=ttl,
            )
        except Exception:
            logger.exception("worker_process_heartbeat_failed")

    def refresh() -> None:
        while not stopped.wait(interval):
            publish()

    publish()
    thread = threading.Thread(
        target=refresh,
        name="worker-process-heartbeat",
        daemon=True,
    )
    thread.start()
    return stopped, thread


def _run_with_heartbeat(
    runtime: RedisRuntime,
    claim: JobClaim,
    handler: Callable[..., object],
    *,
    lease_seconds: int,
) -> object:
    stopped = threading.Event()
    ownership_lost = threading.Event()

    # 任务处理可能长于初始租约；独立心跳线程防止健康处理被误判为失联。
    def renew_lease() -> None:
        interval = max(1.0, lease_seconds / 3)
        while not stopped.wait(interval):
            try:
                if not runtime.heartbeat_job(
                    claim,
                    lease_seconds=lease_seconds,
                ):
                    ownership_lost.set()
                    return
            except Exception:
                logger.exception(
                    "job_heartbeat_failed job_id=%s",
                    claim.job_id,
                )

    heartbeat = threading.Thread(
        target=renew_lease,
        name=f"job-heartbeat-{claim.job_id}",
        daemon=True,
    )
    heartbeat.start()
    try:
        result = handler(job_id=claim.job_id)
        if ownership_lost.is_set():
            raise RuntimeError("job lease ownership lost")
        return result
    finally:
        stopped.set()
        heartbeat.join(timeout=1)


def process_one_job(
    runtime: RedisRuntime,
    *,
    lease_seconds: int,
    retry_base_seconds: int,
    ingest: Callable[..., object] = ingest_knowledge,
    resume_handler: Callable[..., object] | None = None,
    review_transcription_handler: Callable[..., object] | None = None,
    review_analysis_handler: Callable[..., object] | None = None,
) -> bool:
    claim = runtime.claim_job(lease_seconds=lease_seconds)
    if not claim:
        return False
    try:
        if claim.job_type == "knowledge_import":
            handler = ingest
        elif claim.job_type == "resume_analysis" and resume_handler:
            analysis_id = str(claim.payload.get("analysis_id") or "")
            if not analysis_id:
                raise ValueError("resume_analysis payload missing analysis_id")
            handler = lambda **_: resume_handler(analysis_id=analysis_id)
        elif (
            claim.job_type == "interview_transcription"
            and review_transcription_handler
        ):
            review_id = str(claim.payload.get("review_id") or "")
            if not review_id:
                raise ValueError(
                    "interview_transcription payload missing review_id"
                )
            handler = lambda **_: review_transcription_handler(
                review_id=review_id
            )
        elif (
            claim.job_type == "interview_review_analysis"
            and review_analysis_handler
        ):
            review_id = str(claim.payload.get("review_id") or "")
            if not review_id:
                raise ValueError(
                    "interview_review_analysis payload missing review_id"
                )
            handler = lambda **_: review_analysis_handler(
                review_id=review_id
            )
        else:
            raise ValueError(f"unsupported job type: {claim.job_type}")
        result = _run_with_heartbeat(
            runtime,
            claim,
            handler,
            lease_seconds=lease_seconds,
        )
        # ACK 同样校验 owner token；租约丢失的旧 Worker 不得提交迟到结果。
        if not runtime.acknowledge_job(claim, result=result):
            raise RuntimeError("job acknowledgement rejected")
        logger.info(
            "job_completed job_id=%s attempt=%s result=%s",
            claim.job_id,
            claim.attempt,
            result,
        )
    except Exception as exc:
        delay = retry_base_seconds * (2 ** max(0, claim.attempt - 1))
        outcome = runtime.fail_job(
            claim,
            error=f"{type(exc).__name__}: {exc}",
            retry_delay_seconds=delay,
        )
        logger.exception(
            "job_failed job_id=%s attempt=%s outcome=%s",
            claim.job_id,
            claim.attempt,
            outcome,
        )
    return True


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.json_logs)
    runtime = RedisRuntime(settings.redis_url, settings.redis_queue_name)
    if not runtime.client:
        raise RuntimeError("后台 Worker 需要配置 REDIS_URL")
    conversation_store = ConversationStore(
        settings.database_url or settings.conversation_db_path,
        auto_create_schema=settings.auto_create_schema,
    )
    files = LocalUserFileStore(
        settings.user_files_dir,
        max_upload_bytes=settings.resume_max_upload_bytes,
    )
    resume_service = ResumeService(
        conversation_store,
        files,
        settings,
        enqueue=runtime.enqueue,
    )
    review_service = InterviewReviewService(
        conversation_store,
        files,
        settings,
        enqueue=runtime.enqueue,
        transcription_provider=HttpTranscriptionProvider(settings),
    )
    logger.info(
        (
            "worker_started queue=%s lease_seconds=%s max_attempts=%s "
            "heartbeat_ttl_seconds=%s"
        ),
        settings.redis_queue_name,
        settings.job_lease_seconds,
        settings.job_max_attempts,
        settings.worker_heartbeat_ttl_seconds,
    )
    heartbeat_stopped, heartbeat_thread = start_worker_heartbeat(
        runtime,
        interval_seconds=settings.worker_heartbeat_interval_seconds,
        ttl_seconds=settings.worker_heartbeat_ttl_seconds,
    )
    try:
        while True:
            processed = process_one_job(
                runtime,
                lease_seconds=settings.job_lease_seconds,
                retry_base_seconds=settings.job_retry_base_seconds,
                resume_handler=resume_service.process_analysis,
                review_transcription_handler=(
                    review_service.process_transcription
                ),
                review_analysis_handler=review_service.process_analysis,
            )
            if not processed:
                time.sleep(max(0.05, settings.job_poll_seconds))
    finally:
        heartbeat_stopped.set()
        heartbeat_thread.join(timeout=1)


if __name__ == "__main__":
    main()
