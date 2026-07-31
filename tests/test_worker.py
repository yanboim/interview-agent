from unittest.mock import MagicMock

from app.operations import JobClaim
from scripts.worker import process_one_job, start_worker_heartbeat


def claim(attempt: int = 1) -> JobClaim:
    return JobClaim(
        job_id="job-1",
        job_type="knowledge_import",
        payload={"requested_by": "admin"},
        claim_token=f"owner-{attempt}",
        attempt=attempt,
        max_attempts=3,
    )


def test_worker_publishes_process_heartbeat_at_startup() -> None:
    runtime = MagicMock()

    stopped, thread = start_worker_heartbeat(
        runtime,
        interval_seconds=5,
        ttl_seconds=20,
    )
    try:
        runtime.publish_worker_heartbeat.assert_called_once()
        assert (
            runtime.publish_worker_heartbeat.call_args.kwargs["ttl_seconds"]
            == 20
        )
        assert thread.is_alive()
    finally:
        stopped.set()
        thread.join(timeout=1)

    assert not thread.is_alive()


def test_worker_acknowledges_successful_job() -> None:
    runtime = MagicMock()
    runtime.claim_job.return_value = claim()
    runtime.acknowledge_job.return_value = True
    ingest = MagicMock(return_value={"chunks": 10})

    assert process_one_job(
        runtime,
        lease_seconds=60,
        retry_base_seconds=5,
        ingest=ingest,
    )

    ingest.assert_called_once_with(job_id="job-1")
    runtime.acknowledge_job.assert_called_once()
    runtime.fail_job.assert_not_called()


def test_worker_schedules_retry_then_can_ack_recovered_claim() -> None:
    runtime = MagicMock()
    runtime.claim_job.side_effect = [claim(1), claim(2)]
    runtime.acknowledge_job.return_value = True
    ingest = MagicMock(
        side_effect=[RuntimeError("worker crashed"), {"chunks": 10}]
    )

    assert process_one_job(
        runtime,
        lease_seconds=60,
        retry_base_seconds=5,
        ingest=ingest,
    )
    assert process_one_job(
        runtime,
        lease_seconds=60,
        retry_base_seconds=5,
        ingest=ingest,
    )

    runtime.fail_job.assert_called_once()
    assert runtime.fail_job.call_args.kwargs["retry_delay_seconds"] == 5
    runtime.acknowledge_job.assert_called_once()


def test_worker_uses_exponential_retry_delay() -> None:
    runtime = MagicMock()
    runtime.claim_job.return_value = claim(3)
    ingest = MagicMock(side_effect=RuntimeError("still unavailable"))

    process_one_job(
        runtime,
        lease_seconds=60,
        retry_base_seconds=5,
        ingest=ingest,
    )

    assert runtime.fail_job.call_args.kwargs["retry_delay_seconds"] == 20


def test_worker_dispatches_resume_analysis_without_content_payload() -> None:
    runtime = MagicMock()
    runtime.claim_job.return_value = JobClaim(
        job_id="job-resume",
        job_type="resume_analysis",
        payload={"analysis_id": "analysis-1"},
        claim_token="owner-1",
        attempt=1,
        max_attempts=3,
    )
    runtime.acknowledge_job.return_value = True
    handler = MagicMock(return_value={"outcome": "completed"})

    assert process_one_job(
        runtime,
        lease_seconds=60,
        retry_base_seconds=5,
        resume_handler=handler,
    )

    handler.assert_called_once_with(analysis_id="analysis-1")
    runtime.acknowledge_job.assert_called_once()


def test_worker_dispatches_review_jobs_with_resource_id_only() -> None:
    for job_type, argument, handler_name in (
        (
            "interview_transcription",
            "review_transcription_handler",
            "transcription",
        ),
        (
            "interview_review_analysis",
            "review_analysis_handler",
            "analysis",
        ),
    ):
        runtime = MagicMock()
        runtime.claim_job.return_value = JobClaim(
            job_id=f"job-{handler_name}",
            job_type=job_type,
            payload={"review_id": "review-1"},
            claim_token="owner-1",
            attempt=1,
            max_attempts=3,
        )
        runtime.acknowledge_job.return_value = True
        handler = MagicMock(return_value={"outcome": "completed"})

        assert process_one_job(
            runtime,
            lease_seconds=60,
            retry_base_seconds=5,
            **{argument: handler},
        )

        handler.assert_called_once_with(review_id="review-1")
        runtime.acknowledge_job.assert_called_once()
