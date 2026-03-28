"""DB-backed job queue with status transitions and retry logic.

No Redis, no Celery — uses the agent_job table as the queue.
Simple enough to run locally and on Railway.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text, update

from backend.app.db.database import async_session
from backend.app.db.models import AgentJob
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

# Status constants
PENDING = "pending"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
DEAD = "dead"  # max retries exceeded

# Retry backoff: attempt 1 → 30s, attempt 2 → 2min, attempt 3 → 10min
RETRY_DELAYS = [30, 120, 600]


async def enqueue_job(
    product_key: str,
    source: str = "crawl",
    task_type: str = "crawl",
    priority: int = 5,
    scheduled_for: datetime | None = None,
    max_attempts: int = 3,
) -> str:
    """Create a new job in pending state. Returns job ID."""
    job_id = str(uuid.uuid4())
    try:
        async with async_session() as session:
            job = AgentJob(
                id=job_id,
                product_key=product_key,
                source=source,
                task_type=task_type,
                status=PENDING,
                priority=priority,
                scheduled_for=scheduled_for,
                max_attempts=max_attempts,
                attempts=0,
            )
            session.add(job)
            await session.commit()
            logger.info("job.enqueued", extra={"job_id": job_id, "product_key": product_key, "priority": priority})
            return job_id
    except Exception as exc:
        logger.error("job.enqueue_failed", extra={"product_key": product_key, "error": str(exc)})
        raise


async def claim_next_job() -> dict | None:
    """Atomically claim the next pending job. Returns job dict or None.

    Uses SELECT ... FOR UPDATE SKIP LOCKED for safe concurrent access.
    """
    now = datetime.now(timezone.utc)
    try:
        async with async_session() as session:
            # Find next job: pending, not scheduled for future, or retry-ready
            result = await session.execute(
                text("""
                    UPDATE agent_job
                    SET status = 'running', started_at = :now, attempts = attempts + 1
                    WHERE id = (
                        SELECT id FROM agent_job
                        WHERE status = 'pending'
                          AND (scheduled_for IS NULL OR scheduled_for <= :now)
                          AND (next_retry_at IS NULL OR next_retry_at <= :now)
                        ORDER BY priority ASC, created_at ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING id, product_key, source, task_type, priority, attempts, max_attempts
                """),
                {"now": now},
            )
            row = result.fetchone()
            if not row:
                return None

            await session.commit()
            job = {
                "id": row[0],
                "product_key": row[1],
                "source": row[2],
                "task_type": row[3],
                "priority": row[4],
                "attempts": row[5],
                "max_attempts": row[6],
            }
            logger.info("job.claimed", extra={"job_id": job["id"], "product_key": job["product_key"], "attempt": job["attempts"]})
            return job
    except Exception as exc:
        logger.error("job.claim_failed", extra={"error": str(exc)})
        return None


async def complete_job(job_id: str, observations_added: int = 0, observations_rejected: int = 0, summary: str | None = None) -> None:
    """Mark a job as completed."""
    now = datetime.now(timezone.utc)
    try:
        async with async_session() as session:
            await session.execute(
                update(AgentJob)
                .where(AgentJob.id == job_id)
                .values(
                    status=COMPLETED,
                    finished_at=now,
                    observations_added=observations_added,
                    observations_rejected=observations_rejected,
                    summary=summary,
                )
            )
            await session.commit()
            logger.info("job.completed", extra={"job_id": job_id, "added": observations_added, "rejected": observations_rejected})
    except Exception as exc:
        logger.error("job.complete_failed", extra={"job_id": job_id, "error": str(exc)})


async def fail_job(job_id: str, error_message: str, attempts: int = 1, max_attempts: int = 3) -> None:
    """Mark a job as failed. Schedules retry if under max_attempts, otherwise marks as dead."""
    now = datetime.now(timezone.utc)
    try:
        async with async_session() as session:
            if attempts < max_attempts:
                # Schedule retry with exponential backoff
                delay_idx = min(attempts - 1, len(RETRY_DELAYS) - 1)
                retry_at = now + timedelta(seconds=RETRY_DELAYS[delay_idx])
                await session.execute(
                    update(AgentJob)
                    .where(AgentJob.id == job_id)
                    .values(
                        status=PENDING,  # Back to pending for retry
                        last_error=error_message,
                        next_retry_at=retry_at,
                        error_message=error_message,
                    )
                )
                logger.info("job.retry_scheduled", extra={
                    "job_id": job_id, "attempt": attempts, "retry_at": retry_at.isoformat(),
                })
            else:
                # Dead letter — no more retries
                await session.execute(
                    update(AgentJob)
                    .where(AgentJob.id == job_id)
                    .values(
                        status=DEAD,
                        finished_at=now,
                        last_error=error_message,
                        error_message=error_message,
                    )
                )
                logger.warning("job.dead", extra={"job_id": job_id, "error": error_message})
            await session.commit()
    except Exception as exc:
        logger.error("job.fail_update_failed", extra={"job_id": job_id, "error": str(exc)})


async def get_queue_stats() -> dict:
    """Return queue depth by status."""
    try:
        async with async_session() as session:
            result = await session.execute(
                text("""
                    SELECT status, count(*) as cnt
                    FROM agent_job
                    GROUP BY status
                    ORDER BY status
                """)
            )
            stats = {row[0]: row[1] for row in result}
            return {
                "pending": stats.get(PENDING, 0),
                "running": stats.get(RUNNING, 0),
                "completed": stats.get(COMPLETED, 0),
                "failed": stats.get(FAILED, 0),
                "dead": stats.get(DEAD, 0),
                "total": sum(stats.values()),
            }
    except Exception as exc:
        logger.error("job.stats_failed", extra={"error": str(exc)})
        return {"pending": 0, "running": 0, "completed": 0, "failed": 0, "dead": 0, "total": 0}
