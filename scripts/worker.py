"""Redis 后台 Worker：以租约领取任务，续租期间执行，并按所有者令牌确认结果。"""

import logging
import time

from app.config import get_settings
from app.application.interview_review_service import InterviewReviewService
from app.application.resume_service import ResumeService
from app.logging_config import configure_logging
from app.operations import RedisRuntime
from app.storage import ConversationStore
from app.transcription import HttpTranscriptionProvider
from app.user_files import LocalUserFileStore
from app.worker_runtime import process_one_job, start_worker_heartbeat

logger = logging.getLogger(__name__)


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
