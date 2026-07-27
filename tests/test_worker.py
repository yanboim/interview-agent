from unittest.mock import MagicMock

from app.operations import JobClaim
from scripts.worker import process_one_job


def claim(attempt: int = 1) -> JobClaim:
    return JobClaim(
        job_id="job-1",
        job_type="knowledge_import",
        payload={"requested_by": "admin"},
        claim_token=f"owner-{attempt}",
        attempt=attempt,
        max_attempts=3,
    )


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
