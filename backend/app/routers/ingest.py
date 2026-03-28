"""
Ingest router — accepts price observations from external agents/crawlers.
Protected by ADMIN_SECRET_KEY via X-Admin-Key header.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.db.database import async_session
from backend.app.db.models import AgentJob, PriceObservation
from backend.app.routers.admin import verify_admin_key
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

ingest_router = APIRouter(prefix="/api", tags=["ingest"], dependencies=[Depends(verify_admin_key)])

# ─── Validation constants ───
MIN_PRICE_SEK = 100
MAX_PRICE_SEK = 200_000
RAW_TEXT_MAX_LEN = 500
MEDIAN_LOW_RATIO = 0.20
MEDIAN_HIGH_RATIO = 3.0
MEDIAN_MIN_OBSERVATIONS = 5

ACCESSORY_KEYWORDS = frozenset({
    "del ", "kabel", "fodral", "case", "skal", "laddare",
    "adapter", "öronkudde", "dyna", "cover", "strap", "band",
    "lins", "filter", "batteri", "hållare",
})


# ─── Request/Response models ───

class ObservationIn(BaseModel):
    product_key: str
    price_sek: int
    condition: str = "unknown"
    source: str
    source_url: str | None = None
    title: str | None = None
    raw_text: str | None = None
    agent_run_id: str | None = None
    is_sold: bool = False
    listing_type: str = "unknown"
    final_price: bool = False
    new_price_at_observation: int | None = None
    currency: str = "SEK"


class IngestRequest(BaseModel):
    observations: list[ObservationIn]
    agent_name: str | None = None
    search_terms: list[str] | None = None


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    suspicious: int
    rejection_reasons: list[str]
    agent_job_id: str | None = None


class JobStartRequest(BaseModel):
    product_key: str
    search_terms: list[str] | None = None
    source: str


class JobStartResponse(BaseModel):
    job_id: str


class JobCompleteRequest(BaseModel):
    job_id: str
    observations_added: int = 0
    observations_rejected: int = 0
    summary: str | None = None
    status: str = "done"
    error_message: str | None = None


# ─── Helpers ───

async def _get_median_price(session, product_key: str) -> int | None:
    """Get median price for non-suspicious observations if we have enough data."""
    result = await session.execute(
        select(PriceObservation.price_sek)
        .where(
            PriceObservation.product_key == product_key,
            PriceObservation.suspicious.is_(False),
        )
        .order_by(PriceObservation.price_sek)
    )
    prices = [row[0] for row in result]
    if len(prices) < MEDIAN_MIN_OBSERVATIONS:
        return None
    mid = len(prices) // 2
    if len(prices) % 2 == 0:
        return (prices[mid - 1] + prices[mid]) // 2
    return prices[mid]


def _check_accessory(title: str | None) -> bool:
    if not title:
        return False
    title_lower = title.lower()
    return any(kw in title_lower for kw in ACCESSORY_KEYWORDS)


# ─── Endpoints ───

@ingest_router.post("/ingest", response_model=IngestResponse)
async def ingest_observations(req: IngestRequest):
    """Accept price observations from external agents."""
    accepted = 0
    rejected = 0
    suspicious_count = 0
    rejection_reasons: list[str] = []

    job_id = str(uuid.uuid4())

    async with async_session() as session:
        async with session.begin():
            first_obs = req.observations[0] if req.observations else None
            job = AgentJob(
                id=job_id,
                started_at=datetime.now(timezone.utc),
                product_key=first_obs.product_key if first_obs else "unknown",
                search_terms=req.search_terms,
                source=first_obs.source if first_obs else "unknown",
                status="running",
            )
            session.add(job)

        median_cache: dict[str, int | None] = {}
        to_insert: list[PriceObservation] = []

        for obs in req.observations:
            # ── Hard rejects ──
            if not obs.product_key or not obs.product_key.strip():
                rejected += 1
                rejection_reasons.append("missing_product_key")
                continue

            if not obs.source or not obs.source.strip():
                rejected += 1
                rejection_reasons.append("missing_source")
                continue

            if obs.price_sek < MIN_PRICE_SEK:
                rejected += 1
                rejection_reasons.append(f"price_too_low:{obs.price_sek}")
                continue

            if obs.price_sek > MAX_PRICE_SEK:
                rejected += 1
                rejection_reasons.append(f"price_too_high:{obs.price_sek}")
                continue

            # ── Truncate raw_text ──
            raw_text = obs.raw_text[:RAW_TEXT_MAX_LEN] if obs.raw_text else None

            # ── Suspicious flags ──
            suspicious = False
            suspicious_reason_parts: list[str] = []

            pk = obs.product_key.strip()
            if pk not in median_cache:
                median_cache[pk] = await _get_median_price(session, pk)
            median = median_cache[pk]

            if median:
                if obs.price_sek < median * MEDIAN_LOW_RATIO:
                    suspicious = True
                    suspicious_reason_parts.append(f"price_below_20pct_median(median={median})")
                if obs.price_sek > median * MEDIAN_HIGH_RATIO:
                    suspicious = True
                    suspicious_reason_parts.append(f"price_above_300pct_median(median={median})")

            if obs.source == "tradera" and obs.listing_type == "auction" and not obs.is_sold:
                suspicious = True
                suspicious_reason_parts.append("possible_auction")

            if _check_accessory(obs.title):
                suspicious = True
                suspicious_reason_parts.append("possible_accessory")

            if suspicious:
                suspicious_count += 1

            # Compute price_to_new_ratio if new price provided
            price_to_new = None
            if obs.new_price_at_observation and obs.new_price_at_observation > 0:
                price_to_new = round(obs.price_sek / obs.new_price_at_observation, 3)

            row = PriceObservation(
                id=str(uuid.uuid4()),
                product_key=pk,
                price_sek=obs.price_sek,
                condition=obs.condition,
                source=obs.source.strip(),
                source_url=obs.source_url,
                title=obs.title,
                raw_text=raw_text,
                agent_run_id=obs.agent_run_id or job_id,
                is_sold=obs.is_sold,
                listing_type=obs.listing_type,
                final_price=obs.final_price,
                new_price_at_observation=obs.new_price_at_observation,
                price_to_new_ratio=price_to_new,
                suspicious=suspicious,
                suspicious_reason="; ".join(suspicious_reason_parts) if suspicious_reason_parts else None,
                currency=obs.currency,
            )
            to_insert.append(row)
            accepted += 1

        async with session.begin():
            for row in to_insert:
                session.add(row)

        async with session.begin():
            job_row = await session.get(AgentJob, job_id)
            if job_row:
                job_row.finished_at = datetime.now(timezone.utc)
                job_row.observations_added = accepted
                job_row.observations_rejected = rejected
                job_row.status = "done"
                job_row.summary = f"accepted={accepted} rejected={rejected} suspicious={suspicious_count}"

    logger.info("ingest.complete", extra={
        "agent_job_id": job_id, "accepted": accepted,
        "rejected": rejected, "suspicious": suspicious_count,
    })

    return IngestResponse(
        accepted=accepted, rejected=rejected, suspicious=suspicious_count,
        rejection_reasons=rejection_reasons, agent_job_id=job_id,
    )


@ingest_router.post("/agent/job/start", response_model=JobStartResponse)
async def agent_job_start(req: JobStartRequest):
    """Create a new agent job record. Returns job_id."""
    job_id = str(uuid.uuid4())
    async with async_session() as session:
        async with session.begin():
            job = AgentJob(
                id=job_id,
                product_key=req.product_key,
                search_terms=req.search_terms,
                source=req.source,
                status="running",
            )
            session.add(job)
    logger.info("agent.job.started", extra={"job_id": job_id, "product_key": req.product_key})
    return JobStartResponse(job_id=job_id)


@ingest_router.post("/agent/job/complete")
async def agent_job_complete(req: JobCompleteRequest):
    """Update an existing agent job with results."""
    async with async_session() as session:
        async with session.begin():
            job = await session.get(AgentJob, req.job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            job.finished_at = datetime.now(timezone.utc)
            job.observations_added = req.observations_added
            job.observations_rejected = req.observations_rejected
            job.summary = req.summary
            job.status = req.status
            job.error_message = req.error_message
    logger.info("agent.job.completed", extra={"job_id": req.job_id, "status": req.status})
    return {"ok": True, "job_id": req.job_id}


class RollbackRequest(BaseModel):
    version: str


# ─── VALOR training state (module-level, survives across requests) ───
_training_state: dict = {
    "running": False,
    "last_result": None,    # "success" | "failed" | None
    "last_error": None,
    "last_run_at": None,
}


def _find_project_root():
    """Walk up from this file to find the directory containing scripts/train_valor.py."""
    candidate = Path(__file__).resolve()
    for _ in range(6):
        candidate = candidate.parent
        if (candidate / "scripts" / "train_valor.py").exists():
            return candidate
    return None


@ingest_router.post("/valor/train")
async def valor_train(background_tasks: BackgroundTasks):
    """Trigger VALOR training as a background subprocess."""
    import subprocess
    import sys

    if _training_state["running"]:
        return {"status": "already_running", "note": "Träning pågår redan."}

    root = _find_project_root()
    if not root:
        return {"status": "error", "note": f"train_valor.py not found. Searched from {Path(__file__).resolve()}"}

    script_path = root / "scripts" / "train_valor.py"

    def run_training():
        _training_state["running"] = True
        _training_state["last_error"] = None
        try:
            result = subprocess.run(
                [sys.executable, str(script_path), "--force", "--min-samples", "10"],
                capture_output=True, text=True, timeout=300,
            )
            _training_state["last_run_at"] = datetime.now(timezone.utc).isoformat()

            if result.returncode == 0:
                _training_state["last_result"] = "success"
                logger.info("valor.train.completed", extra={"stdout": result.stdout[-500:]})
                try:
                    from backend.app.main import app
                    if hasattr(app.state, "valor_service"):
                        app.state.valor_service.reload_model()
                        logger.info("valor.model.reloaded")
                except Exception as e:
                    logger.warning(f"valor.reload.failed: {e}")
            else:
                _training_state["last_result"] = "failed"
                _training_state["last_error"] = (result.stderr or "")[-300:].strip() or "Okänt fel"
                logger.error("valor.train.failed", extra={"stderr": result.stderr[-500:]})
        except subprocess.TimeoutExpired:
            _training_state["last_result"] = "failed"
            _training_state["last_error"] = "Träning tog för lång tid (>5 min)"
            logger.error("valor.train.timeout")
        except Exception as e:
            _training_state["last_result"] = "failed"
            _training_state["last_error"] = str(e)
            logger.error(f"valor.train.exception: {e}")
        finally:
            _training_state["running"] = False

    background_tasks.add_task(run_training)
    logger.info("valor.train.triggered")
    return {
        "status": "started",
        "note": "Träning startad i bakgrunden. Klar om ~60 sekunder.",
        "min_samples": 10,
        "force": True,
    }


@ingest_router.get("/valor/train/status")
async def valor_train_status():
    """Training state + model availability."""
    try:
        from backend.app.main import app
        svc = getattr(app.state, "valor_service", None)
        return {
            "model_available": svc.is_available() if svc else False,
            "model_version": getattr(svc, "model_version", None) if svc else None,
            "last_reload": getattr(svc, "_loaded_at", None) if svc else None,
            "training_running": _training_state["running"],
            "last_result": _training_state["last_result"],
            "last_error": _training_state["last_error"],
            "last_run_at": _training_state["last_run_at"],
        }
    except Exception:
        return {"model_available": False, "model_version": None, "training_running": False,
                "last_result": None, "last_error": None, "last_run_at": None}


@ingest_router.post("/valor/rollback")
async def valor_rollback(req: RollbackRequest):
    """Roll back VALOR model to a specific version."""
    import shutil
    from pathlib import Path
    from sqlalchemy import text

    models_dir = Path(__file__).resolve().parents[3] / "models"
    target_path = models_dir / f"{req.version}.pkl"

    if not target_path.exists():
        raise HTTPException(status_code=404, detail=f"Model file {req.version}.pkl not found")

    latest_path = models_dir / "valor_latest.pkl"
    shutil.copy2(target_path, latest_path)

    # Update DB
    try:
        async with async_session() as session:
            async with session.begin():
                await session.execute(text(
                    "UPDATE valor_model SET is_active = false WHERE is_active = true"
                ))
                await session.execute(text(
                    "UPDATE valor_model SET is_active = true WHERE model_version = :v"
                ), {"v": req.version})
    except Exception as exc:
        logger.error(f"valor.rollback.db_error: {exc}")

    logger.info("valor.rollback.complete", extra={"version": req.version})
    return {"status": "rolled_back", "version": req.version}
