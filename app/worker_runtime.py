"""可复用 Worker 处理循环：租约领取、续租、分派、确认和失败重试。"""

import logging
import threading
from collections.abc import Callable
from uuid import uuid4

from app.knowledge_ingestion import ingest_knowledge
from app.operations import JobClaim, RedisRuntime

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
    interval = min(max(0.1, float(interval_seconds)), max(0.1, ttl / 3))

    def publish() -> None:
        try:
            runtime.publish_worker_heartbeat(instance_id, ttl_seconds=ttl)
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

    def renew_lease() -> None:
        interval = max(1.0, lease_seconds / 3)
        while not stopped.wait(interval):
            try:
                if not runtime.heartbeat_job(claim, lease_seconds=lease_seconds):
                    ownership_lost.set()
                    return
            except Exception:
                logger.exception("job_heartbeat_failed job_id=%s", claim.job_id)

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
        elif claim.job_type == "interview_transcription" and review_transcription_handler:
            review_id = str(claim.payload.get("review_id") or "")
            if not review_id:
                raise ValueError("interview_transcription payload missing review_id")
            handler = lambda **_: review_transcription_handler(review_id=review_id)
        elif claim.job_type == "interview_review_analysis" and review_analysis_handler:
            review_id = str(claim.payload.get("review_id") or "")
            if not review_id:
                raise ValueError("interview_review_analysis payload missing review_id")
            handler = lambda **_: review_analysis_handler(review_id=review_id)
        else:
            raise ValueError(f"unsupported job type: {claim.job_type}")

        result = _run_with_heartbeat(
            runtime,
            claim,
            handler,
            lease_seconds=lease_seconds,
        )
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
