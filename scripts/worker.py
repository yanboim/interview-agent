import json
import logging

from redis.exceptions import TimeoutError as RedisTimeoutError

from app.config import get_settings
from app.logging_config import configure_logging
from app.operations import RedisRuntime
from scripts.ingest import ingest_knowledge


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.json_logs)
    logger = logging.getLogger(__name__)
    runtime = RedisRuntime(settings.redis_url, settings.redis_queue_name)
    if not runtime.client:
        raise RuntimeError("后台 Worker 需要配置 REDIS_URL")
    logger.info("worker_started queue=%s", settings.redis_queue_name)
    while True:
        try:
            item = runtime.client.blpop(
                settings.redis_queue_name,
                timeout=5,
            )
        except RedisTimeoutError:
            continue
        if not item:
            continue
        _, raw_job = item
        job = json.loads(raw_job)
        try:
            runtime.update_job(job["job_id"], status="running")
            if job["type"] == "knowledge_import":
                result = ingest_knowledge()
                runtime.update_job(
                    job["job_id"],
                    status="completed",
                    result=result,
                )
                logger.info(
                    "job_completed job_id=%s result=%s",
                    job["job_id"],
                    result,
                )
            else:
                runtime.update_job(
                    job["job_id"],
                    status="ignored",
                    error=f"unsupported job type: {job.get('type')}",
                )
                logger.warning(
                    "job_ignored job_id=%s type=%s",
                    job.get("job_id"),
                    job.get("type"),
                )
        except Exception as exc:
            runtime.update_job(
                job.get("job_id", "unknown"),
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
            )
            logger.exception("job_failed job_id=%s", job.get("job_id"))


if __name__ == "__main__":
    main()
