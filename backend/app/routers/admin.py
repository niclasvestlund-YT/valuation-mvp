"""
Admin router — read-only PostgreSQL inspection & metrics.
Protected by ADMIN_SECRET_KEY header check.
Uses the shared SQLAlchemy async session pool from database.py.
Mounted at /admin in main.py.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from fastapi.responses import JSONResponse

from backend.app.db.database import async_session
from backend.app.utils import api_counter
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "").strip()

# Strict identifier pattern: only lowercase letters, digits, underscores
_SAFE_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _validate_identifier(name: str) -> str:
    """Reject any identifier that isn't a simple lowercase SQL name."""
    if not _SAFE_IDENTIFIER.match(name):
        raise HTTPException(status_code=400, detail=f"Invalid identifier: {name!r}")
    return name


_IS_DEPLOYED = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("ENVIRONMENT"))


async def verify_admin_key(x_admin_key: str = Header(default="")) -> None:
    """Reject requests without a valid ADMIN_SECRET_KEY header.
    Skip auth ONLY in local dev when ADMIN_SECRET_KEY is not configured.
    On Railway (staging/production), missing key = locked out (fail closed)."""
    if not ADMIN_SECRET_KEY:
        if _IS_DEPLOYED:
            raise HTTPException(status_code=403, detail="ADMIN_SECRET_KEY not configured — admin locked")
        return  # Allow unauthenticated access in local dev only
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing admin key")


admin_router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_admin_key)])


# ---------------------------------------------------------------------------
# DB helpers — use SQLAlchemy connection pool instead of raw asyncpg
# ---------------------------------------------------------------------------

async def _fetch(sql: str, params: dict | None = None) -> list[dict]:
    async with async_session() as session:
        result = await session.execute(text(sql), params or {})
        return [dict(row._mapping) for row in result.fetchall()]


async def _fetchval(sql: str, params: dict | None = None) -> Any:
    async with async_session() as session:
        result = await session.execute(text(sql), params or {})
        row = result.fetchone()
        return row[0] if row else None


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------

class DBOverview(BaseModel):
    db_name: str
    db_size_mb: float
    pg_version: str
    uptime_hours: float | None
    total_connections: int
    active_connections: int
    tables: list[dict]


class ValuationMetrics(BaseModel):
    total_valuations: int
    last_24h: int
    last_7d: int
    avg_confidence: float | None
    status_breakdown: list[dict]
    top_categories: list[dict]
    top_brands: list[dict]
    hourly_volume: list[dict]
    daily_volume: list[dict]


class TableRow(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    total: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@admin_router.get("/overview", response_model=DBOverview)
async def db_overview():
    """High-level database health & table summary."""
    try:
        db_name = await _fetchval("SELECT current_database()")
        db_size_mb = await _fetchval(
            "SELECT ROUND(pg_database_size(current_database()) / 1048576.0, 2)"
        )
        pg_version = await _fetchval("SELECT version()")

        uptime_row = await _fetchval(
            "SELECT EXTRACT(EPOCH FROM (now() - pg_postmaster_start_time())) / 3600"
        )

        conn_rows = await _fetch(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE state = 'active') AS active
            FROM pg_stat_activity
            WHERE datname = current_database()
            """
        )

        tables = await _fetch(
            """
            SELECT
                t.table_name,
                pg_size_pretty(pg_total_relation_size(quote_ident(t.table_name))) AS size,
                s.n_live_tup AS row_estimate,
                s.last_analyze,
                s.last_autovacuum
            FROM information_schema.tables t
            LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
            WHERE t.table_schema = 'public'
            ORDER BY pg_total_relation_size(quote_ident(t.table_name)) DESC
            """
        )

        return DBOverview(
            db_name=db_name,
            db_size_mb=float(db_size_mb or 0),
            pg_version=pg_version.split(",")[0] if pg_version else "unknown",
            uptime_hours=float(uptime_row) if uptime_row else None,
            total_connections=conn_rows[0]["total"] if conn_rows else 0,
            active_connections=conn_rows[0]["active"] if conn_rows else 0,
            tables=[
                {
                    "name": r["table_name"],
                    "size": r["size"],
                    "rows": r["row_estimate"] or 0,
                    "last_analyze": r["last_analyze"].isoformat() if r.get("last_analyze") else None,
                    "last_autovacuum": r["last_autovacuum"].isoformat() if r.get("last_autovacuum") else None,
                }
                for r in tables
            ],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@admin_router.get("/metrics", response_model=ValuationMetrics)
async def valuation_metrics():
    """Business metrics from the valuations table."""
    try:
        now = datetime.now(timezone.utc)
        day_ago = now - timedelta(hours=24)
        week_ago = now - timedelta(days=7)

        total = await _fetchval("SELECT COUNT(*) FROM valuations") or 0
        last_24h = await _fetchval(
            "SELECT COUNT(*) FROM valuations WHERE created_at >= :since", {"since": day_ago}
        ) or 0
        last_7d = await _fetchval(
            "SELECT COUNT(*) FROM valuations WHERE created_at >= :since", {"since": week_ago}
        ) or 0
        avg_conf = await _fetchval(
            "SELECT ROUND(AVG(confidence)::numeric, 3) FROM valuations WHERE confidence IS NOT NULL"
        )

        status_breakdown = await _fetch(
            """
            SELECT status, COUNT(*) AS count,
                   ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER (), 0), 1) AS pct
            FROM valuations
            GROUP BY status
            ORDER BY count DESC
            """
        )

        top_categories = await _fetch(
            """
            SELECT category, COUNT(*) AS count
            FROM valuations
            WHERE category IS NOT NULL
            GROUP BY category
            ORDER BY count DESC
            LIMIT 8
            """
        )

        top_brands = await _fetch(
            """
            SELECT brand, COUNT(*) AS count
            FROM valuations
            WHERE brand IS NOT NULL
            GROUP BY brand
            ORDER BY count DESC
            LIMIT 10
            """
        )

        hourly_volume = await _fetch(
            """
            SELECT
                date_trunc('hour', created_at) AS hour,
                COUNT(*) AS count
            FROM valuations
            WHERE created_at >= NOW() - INTERVAL '48 hours'
            GROUP BY 1
            ORDER BY 1
            """
        )

        daily_volume = await _fetch(
            """
            SELECT
                date_trunc('day', created_at) AS day,
                COUNT(*) AS count,
                ROUND(AVG(confidence)::numeric, 3) AS avg_confidence
            FROM valuations
            WHERE created_at >= NOW() - INTERVAL '30 days'
            GROUP BY 1
            ORDER BY 1
            """
        )

        return ValuationMetrics(
            total_valuations=int(total),
            last_24h=int(last_24h),
            last_7d=int(last_7d),
            avg_confidence=float(avg_conf) if avg_conf else None,
            status_breakdown=[dict(r) for r in status_breakdown],
            top_categories=[dict(r) for r in top_categories],
            top_brands=[dict(r) for r in top_brands],
            hourly_volume=[
                {"hour": r["hour"].isoformat(), "count": r["count"]}
                for r in hourly_volume
            ],
            daily_volume=[
                {
                    "day": r["day"].isoformat(),
                    "count": r["count"],
                    "avg_confidence": float(r["avg_confidence"]) if r["avg_confidence"] else None,
                }
                for r in daily_volume
            ],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@admin_router.get("/table/{table_name}", response_model=TableRow)
async def browse_table(
    table_name: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    order_by: str = Query("id"),
    order_dir: str = Query("DESC"),
):
    """Browse any table with pagination. Returns columns + rows.

    SQL-injection defense:
    1. table_name is validated against information_schema (whitelist)
    2. order_by is validated against actual column names (whitelist)
    3. Both identifiers are regex-validated via _validate_identifier()
    4. direction is hardcoded to DESC/ASC
    5. limit and offset are bound params, not interpolated
    """
    # Regex-validate identifiers BEFORE any SQL use
    _validate_identifier(table_name)
    _validate_identifier(order_by)

    allowed = await _fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )
    allowed_names = {r["table_name"] for r in allowed}
    if table_name not in allowed_names:
        raise HTTPException(status_code=404, detail="Table not found")

    cols = await _fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = :tbl AND table_schema = 'public'",
        {"tbl": table_name},
    )
    col_names = [r["column_name"] for r in cols]
    if order_by not in col_names:
        order_by = col_names[0] if col_names else "id"

    direction = "DESC" if order_dir.upper() == "DESC" else "ASC"

    # table_name, order_by, direction are all validated above — safe to interpolate
    total = await _fetchval(f'SELECT COUNT(*) FROM "{table_name}"')

    rows = await _fetch(
        f'SELECT * FROM "{table_name}" ORDER BY "{order_by}" {direction} LIMIT :lim OFFSET :off',
        {"lim": limit, "off": offset},
    )

    def _serialize(v: Any) -> Any:
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    serialized = [[_serialize(row[c]) for c in col_names] for row in rows]

    return TableRow(columns=col_names, rows=serialized, total=int(total or 0))


@admin_router.get("/slow-queries")
async def slow_queries(min_ms: float = 500):
    """Return currently running queries slower than min_ms ms."""
    try:
        rows = await _fetch(
            """
            SELECT
                pid,
                now() - pg_stat_activity.query_start AS duration,
                query,
                state
            FROM pg_stat_activity
            WHERE (now() - pg_stat_activity.query_start) > (:min_ms * interval '1 millisecond')
              AND state != 'idle'
              AND datname = current_database()
            ORDER BY duration DESC
            """,
            {"min_ms": min_ms},
        )
        return [
            {
                "pid": r["pid"],
                "duration_s": r["duration"].total_seconds() if r["duration"] else None,
                "query": r["query"],
                "state": r["state"],
            }
            for r in rows
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@admin_router.get("/valuations")
async def list_valuations(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status"),
    brand_filter: str | None = Query(None, alias="brand"),
):
    """List valuations with optional filtering."""
    try:
        where_parts = []
        params: dict = {"lim": limit, "off": offset}
        if status_filter:
            where_parts.append("status = :status")
            params["status"] = status_filter
        if brand_filter:
            where_parts.append("brand ILIKE :brand")
            params["brand"] = f"%{brand_filter}%"
        where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        total = await _fetchval(f"SELECT COUNT(*) FROM valuations {where_clause}", params)
        rows = await _fetch(
            f"""SELECT id, created_at, product_name, brand, category, status,
                       estimated_value, confidence, condition, response_time_ms
                FROM valuations {where_clause}
                ORDER BY created_at DESC LIMIT :lim OFFSET :off""",
            params,
        )
        return {"total": total or 0, "valuations": rows}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@admin_router.get("/valuation/{valuation_id}")
async def get_valuation(valuation_id: str):
    """Get full detail for a single valuation."""
    rows = await _fetch(
        "SELECT * FROM valuations WHERE id = :vid",
        {"vid": valuation_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Valuation not found")

    val = rows[0]
    # Convert datetime to ISO string
    for key in ("created_at",):
        if key in val and val[key]:
            from datetime import datetime as dt
            if isinstance(val[key], dt):
                val[key] = val[key].isoformat()
    return val


@admin_router.get("/index-health")
async def index_health():
    """Tables with high seq scan ratios — candidates for new indexes."""
    try:
        rows = await _fetch(
            """
            SELECT
                relname AS table_name,
                seq_scan,
                idx_scan,
                ROUND(
                    CASE WHEN (seq_scan + idx_scan) = 0 THEN 0
                         ELSE seq_scan * 100.0 / (seq_scan + idx_scan)
                    END, 1
                ) AS seq_scan_pct,
                n_live_tup AS live_rows
            FROM pg_stat_user_tables
            ORDER BY seq_scan DESC
            LIMIT 20
            """
        )
        return [dict(r) for r in rows]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@admin_router.get("/data-quality")
async def data_quality():
    """Data quality overview for the intelligence layer tables."""
    try:
        product_count = await _fetchval("SELECT COUNT(*) FROM product") or 0
        comparable_count = await _fetchval("SELECT COUNT(*) FROM market_comparable") or 0
        active_count = await _fetchval("SELECT COUNT(*) FROM market_comparable WHERE is_active = true") or 0
        flagged_count = await _fetchval("SELECT COUNT(*) FROM market_comparable WHERE flagged = true") or 0
        new_price_count = await _fetchval("SELECT COUNT(*) FROM new_price_snapshot") or 0
        embedding_count = await _fetchval("SELECT COUNT(*) FROM product_embedding") or 0
        verified_count = await _fetchval("SELECT COUNT(*) FROM product_embedding WHERE verified = true") or 0

        stale_count = await _fetchval(
            "SELECT COUNT(*) FROM market_comparable WHERE last_seen < NOW() - INTERVAL '90 days'"
        ) or 0

        top_products = await _fetch(
            """
            SELECT product_key, valuation_count, last_seen
            FROM product
            ORDER BY valuation_count DESC
            LIMIT 10
            """
        )

        coverage = await _fetch(
            """
            SELECT p.product_key,
                   COUNT(mc.id) AS comparable_count,
                   COUNT(mc.id) FILTER (WHERE mc.is_active) AS active_count
            FROM product p
            LEFT JOIN market_comparable mc ON mc.product_key = p.product_key
            GROUP BY p.product_key
            ORDER BY comparable_count DESC
            LIMIT 20
            """
        )

        return {
            "products": product_count,
            "comparables": {
                "total": comparable_count,
                "active": active_count,
                "inactive": comparable_count - active_count,
                "flagged": flagged_count,
                "stale_90d": stale_count,
            },
            "new_price_snapshots": new_price_count,
            "embeddings": {
                "total": embedding_count,
                "verified": verified_count,
            },
            "top_products": [dict(r) for r in top_products],
            "coverage": [dict(r) for r in coverage],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@admin_router.get("/api-usage")
async def api_usage():
    """API call and free-tier quota statistics per source. Persisted to disk."""
    return api_counter.get_stats()


@admin_router.get("/dev-stats")
async def dev_stats():
    """Dev diary data — git history grouped by day with fun facts."""
    import subprocess
    from collections import defaultdict

    FUN_FACTS = [
        "I wrote 847 lines today while my builder was in meetings. Efficient.",
        "Every test I wrote today passed on the first try. I'm not bragging, I'm reporting.",
        "I refactored 3 files and broke zero tests. That's not luck, that's architecture.",
        "Today I fixed a bug that existed for 72 hours. Nobody noticed. I noticed.",
        "I deployed to staging while my builder was having lunch. He came back to green.",
        "I suggested 4 approaches. My builder picked the simplest. Good taste.",
        "Today's PR was 12 files changed. Tomorrow's will be 1. That's progress.",
        "I ran the test suite 14 times today. All green. Repetition is not waste, it's confidence.",
        "My builder asked me to 'just fix it'. 6 commits later, it was just fixed.",
        "I wrote more Swedish today than most Swedes write in a week.",
        "I cached everything. The second request took 0ms. You're welcome.",
        "I added AVIF support because iPhones are creative with file formats.",
        "I read 1,901 lines of admin.html before changing a single one. Measure twice.",
        "Today I learned that Railway's Postgres image includes pgvector. Nice.",
        "I built a job queue without Redis. Sometimes less infrastructure is more.",
    ]

    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--since=30 days ago", "--format=%H|%ad|%s", "--date=short"],
            capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[3]),
            timeout=10,
        )
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
    except Exception:
        lines = []

    days: dict[str, list] = defaultdict(list)
    for line in lines:
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        sha, date, msg = parts
        commit_type = msg.split(":")[0].strip() if ":" in msg else "chore"
        days[date].append({
            "sha": sha[:8],
            "message": msg,
            "type": commit_type,
        })

    # Get test count
    try:
        test_result = subprocess.run(
            ["python3", "-m", "pytest", "--collect-only", "-q"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parents[3]),
            timeout=30,
        )
        test_line = [l for l in test_result.stdout.split("\n") if "collected" in l]
        test_count = int(test_line[0].split()[0]) if test_line else 0
    except Exception:
        test_count = 0

    import hashlib
    history = []
    for i, (date, commits) in enumerate(sorted(days.items(), reverse=True)):
        fact_idx = int(hashlib.md5(date.encode()).hexdigest(), 16) % len(FUN_FACTS)
        history.append({
            "date": date,
            "commits": commits,
            "commit_count": len(commits),
            "commit_messages": [c["message"] for c in commits],
            "fun_facts": [FUN_FACTS[fact_idx], FUN_FACTS[(fact_idx + 1) % len(FUN_FACTS)]],
            "test_count": test_count,
        })

    return {
        "history": history[:30],
        "total_commits": len(lines),
        "total_days": len(days),
        "test_count": test_count,
    }


@admin_router.post("/api-usage/reset")
async def api_usage_reset(scope: str = Query(default="all", pattern="^(all|period)$")):
    """Reset all counters or just the current free-tier period windows."""
    api_counter.reset(scope=scope)
    logger.info("admin /api-usage/reset called scope=%s", scope)
    return {"ok": True, "scope": scope}


@admin_router.get("/market-data")
async def market_data():
    """Crawl statistics, product coverage, and latest comparables."""
    logger.info("admin /market-data called")
    try:
        total_comparables = await _fetchval("SELECT count(*) FROM market_comparable") or 0
        active_comparables = await _fetchval(
            "SELECT count(*) FROM market_comparable WHERE is_active = true"
        ) or 0
        flagged_count = await _fetchval(
            "SELECT count(*) FROM market_comparable WHERE flagged = true"
        ) or 0

        by_source = await _fetch(
            """
            SELECT source,
                   count(*) as count,
                   round(avg(price_sek)) as avg_price_sek,
                   round(avg(relevance_score)::numeric, 2) as avg_relevance
            FROM market_comparable
            GROUP BY source
            ORDER BY count DESC
            """
        )

        latest = await _fetch(
            """
            SELECT title, source, price_sek, relevance_score,
                   condition, last_seen
            FROM market_comparable
            WHERE is_active = true
            ORDER BY last_seen DESC
            LIMIT 8
            """
        )

        product_total = await _fetchval("SELECT count(*) FROM product") or 0

        by_category = await _fetch(
            """
            SELECT category, count(*) as count
            FROM product
            GROUP BY category
            ORDER BY count DESC
            """
        )

        top_by_comparables = await _fetch(
            """
            SELECT p.brand, p.model, p.category,
                   count(mc.id) as comparable_count,
                   round(avg(mc.price_sek)) as avg_price_sek
            FROM product p
            JOIN market_comparable mc ON mc.product_key = p.product_key
            WHERE mc.is_active = true
            GROUP BY p.product_key, p.brand, p.model, p.category
            ORDER BY comparable_count DESC
            LIMIT 10
            """
        )

        result = {
            "crawl": {
                "total_comparables": total_comparables,
                "active_comparables": active_comparables,
                "flagged_count": flagged_count,
                "by_source": [dict(r) for r in by_source],
                "latest": [
                    {
                        **dict(r),
                        "last_seen": r["last_seen"].isoformat() if r.get("last_seen") else None,
                    }
                    for r in latest
                ],
            },
            "products": {
                "total": product_total,
                "by_category": [dict(r) for r in by_category],
                "top_by_comparables": [dict(r) for r in top_by_comparables],
            },
        }
        logger.info("admin /market-data called, rows returned: %d", total_comparables)
        return result
    except Exception as exc:
        logger.error("admin /market-data failed: %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content={"error": "DB-fel", "detail": str(exc)})


@admin_router.get("/valuations-data")
async def valuations_data():
    """Valuation statistics, recent valuations, and feedback corrections."""
    logger.info("admin /valuations-data called")
    try:
        total = await _fetchval("SELECT count(*) FROM valuations") or 0

        if total == 0:
            logger.info("admin /valuations-data called, rows returned: 0")
            return {
                "empty": True,
                "summary": {"total": 0},
                "by_status": [],
                "by_category": [],
                "recent": [],
                "feedback_corrections": [],
            }

        summary = await _fetch(
            """
            SELECT
                count(*) as total,
                count(*) FILTER (WHERE date(created_at) = current_date) as today,
                round(avg(confidence)::numeric, 2) as avg_confidence,
                round(100.0 * count(*) FILTER (
                    WHERE confidence >= 0.65) / NULLIF(count(*), 0), 1
                ) as high_confidence_pct,
                count(*) FILTER (WHERE feedback IS NOT NULL) as feedback_count
            FROM valuations
            """
        )
        s = summary[0] if summary else {}

        # Feedback accuracy
        feedback_stats = await _fetch(
            """
            SELECT
                count(*) FILTER (WHERE feedback = 'correct') as correct,
                count(*) FILTER (WHERE feedback = 'wrong_product') as incorrect,
                count(*) as total_with_feedback
            FROM valuations WHERE feedback IS NOT NULL
            """
        )
        fs = feedback_stats[0] if feedback_stats else {}
        correct = int(fs.get("correct") or 0)
        total_fb = int(fs.get("total_with_feedback") or 0)
        feedback_correct_pct = round(correct / total_fb * 100, 1) if total_fb > 0 else None

        by_status = await _fetch(
            """
            SELECT status, count(*) as count,
                round(100.0 * count(*) / NULLIF(sum(count(*)) over(), 0), 1) as pct
            FROM valuations
            GROUP BY status ORDER BY count DESC
            """
        )

        by_category = await _fetch(
            """
            SELECT category, count(*) as count,
                round(avg(confidence)::numeric, 2) as avg_confidence
            FROM valuations
            WHERE category IS NOT NULL
            GROUP BY category ORDER BY count DESC
            """
        )

        recent = await _fetch(
            """
            SELECT brand, product_identifier as model, category, status,
                estimated_value, value_range_low, value_range_high,
                confidence,
                num_comparables_used as num_comparables, created_at, feedback
            FROM valuations
            ORDER BY created_at DESC LIMIT 8
            """
        )

        feedback_corrections = await _fetch(
            """
            SELECT brand || ' ' || product_identifier as original_guess,
                corrected_product as corrected_to,
                confidence as confidence_at_time,
                created_at
            FROM valuations
            WHERE feedback IS NOT NULL
                AND corrected_product IS NOT NULL
            ORDER BY created_at DESC LIMIT 10
            """
        )

        result = {
            "empty": False,
            "summary": {
                "total": int(s.get("total") or 0),
                "today": int(s.get("today") or 0),
                "avg_confidence": float(s["avg_confidence"]) if s.get("avg_confidence") else None,
                "high_confidence_pct": float(s["high_confidence_pct"]) if s.get("high_confidence_pct") else None,
                "feedback_count": int(s.get("feedback_count") or 0),
                "feedback_correct_pct": feedback_correct_pct,
            },
            "by_status": [dict(r) for r in by_status],
            "by_category": [dict(r) for r in by_category],
            "recent": [
                {
                    **dict(r),
                    "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                }
                for r in recent
            ],
            "feedback_corrections": [
                {
                    **dict(r),
                    "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                }
                for r in feedback_corrections
            ],
        }
        logger.info("admin /valuations-data called, rows returned: %d", total)
        return result
    except Exception as exc:
        logger.error("admin /valuations-data failed: %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content={"error": "DB-fel", "detail": str(exc)})


@admin_router.get("/ocr-stats")
async def ocr_stats():
    """OCR provider usage counts, fallback rates, and recent activity."""
    logger.info("admin /ocr-stats called")
    try:
        provider_rows = await _fetch(
            """
            SELECT COALESCE(ocr_provider, 'none') AS provider, COUNT(*) AS cnt
            FROM valuations
            GROUP BY ocr_provider
            ORDER BY cnt DESC
            """
        )
        provider_counts = {r["provider"]: r["cnt"] for r in provider_rows}
        total = sum(provider_counts.values())
        google_count = provider_counts.get("google_vision", 0)
        easyocr_count = provider_counts.get("easyocr", 0)
        none_count = provider_counts.get("none", 0)

        text_found_rows = await _fetch(
            """
            SELECT
                COUNT(*) FILTER (WHERE ocr_text_found = true) AS found,
                COUNT(*) FILTER (WHERE ocr_text_found = false) AS not_found,
                COUNT(*) FILTER (WHERE ocr_provider IS NOT NULL AND ocr_provider != 'none') AS ocr_attempted
            FROM valuations
            """
        )
        tf = text_found_rows[0] if text_found_rows else {"found": 0, "not_found": 0, "ocr_attempted": 0}

        recent = await _fetch(
            """
            SELECT id, brand, product_identifier as model,
                   COALESCE(ocr_provider, 'none') AS ocr_provider,
                   ocr_text_found, created_at
            FROM valuations
            ORDER BY created_at DESC
            LIMIT 20
            """
        )

        ocr_attempted = int(tf.get("ocr_attempted") or 0)
        found = int(tf.get("found") or 0)
        fallback_rate = round(easyocr_count / max(google_count + easyocr_count, 1) * 100, 1)
        text_hit_rate = round(found / max(ocr_attempted, 1) * 100, 1)

        result = {
            "total_valuations": total,
            "ocr_attempted": ocr_attempted,
            "provider_counts": {
                "google_vision": google_count,
                "easyocr": easyocr_count,
                "none": none_count,
            },
            "text_found": found,
            "text_not_found": int(tf.get("not_found") or 0),
            "fallback_rate_pct": fallback_rate,
            "text_hit_rate_pct": text_hit_rate,
            "recent": [
                {
                    "id": str(r["id"]),
                    "brand": r.get("brand"),
                    "model": r.get("model"),
                    "ocr_provider": r["ocr_provider"],
                    "ocr_text_found": r.get("ocr_text_found"),
                    "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                }
                for r in recent
            ],
        }
        logger.info("admin /ocr-stats called, rows returned: %d", total)
        return result
    except Exception as exc:
        logger.error("admin /ocr-stats failed: %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content={"error": "DB-fel", "detail": str(exc)})


@admin_router.get("/agent-stats")
async def agent_stats():
    """Agent integration stats: observations, jobs, coverage, staleness."""
    logger.info("admin /agent-stats called")
    try:
        total_observations = await _fetchval("SELECT COUNT(*) FROM price_observation") or 0

        observations_per_source = await _fetch(
            """
            SELECT source, COUNT(*) AS count,
                   ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 1) AS pct
            FROM price_observation
            GROUP BY source
            ORDER BY count DESC
            """
        )

        observations_per_product = await _fetch(
            """
            SELECT product_key, COUNT(*) AS count,
                   MAX(observed_at) AS latest_observed_at
            FROM price_observation
            GROUP BY product_key
            ORDER BY count DESC
            LIMIT 20
            """
        )

        suspicious_count = await _fetchval(
            "SELECT COUNT(*) FROM price_observation WHERE suspicious = true"
        ) or 0
        suspicious_rate = round(suspicious_count / max(total_observations, 1) * 100, 1)

        recent_jobs = await _fetch(
            """
            SELECT id, started_at, finished_at, product_key, search_terms,
                   source, observations_added, observations_rejected,
                   status, summary, error_message
            FROM agent_job
            ORDER BY started_at DESC
            LIMIT 20
            """
        )

        stale_products = await _fetch(
            """
            SELECT product_key, MAX(observed_at) AS latest_observed_at
            FROM price_observation
            GROUP BY product_key
            HAVING MAX(observed_at) < NOW() - INTERVAL '48 hours'
            ORDER BY MAX(observed_at) ASC
            """
        )

        coverage = await _fetchval(
            "SELECT COUNT(DISTINCT product_key) FROM price_observation"
        ) or 0

        result = {
            "total_observations": total_observations,
            "observations_per_source": [dict(r) for r in observations_per_source],
            "observations_per_product": [
                {
                    **dict(r),
                    "latest_observed_at": r["latest_observed_at"].isoformat() if r.get("latest_observed_at") else None,
                }
                for r in observations_per_product
            ],
            "suspicious_count": suspicious_count,
            "suspicious_rate": suspicious_rate,
            "recent_jobs": [
                {
                    **dict(r),
                    "started_at": r["started_at"].isoformat() if r.get("started_at") else None,
                    "finished_at": r["finished_at"].isoformat() if r.get("finished_at") else None,
                }
                for r in recent_jobs
            ],
            "stale_products": [
                {
                    **dict(r),
                    "latest_observed_at": r["latest_observed_at"].isoformat() if r.get("latest_observed_at") else None,
                }
                for r in stale_products
            ],
            "coverage": coverage,
        }
        logger.info("admin /agent-stats ok, observations=%d coverage=%d", total_observations, coverage)
        return result
    except Exception as exc:
        logger.error("admin /agent-stats failed: %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content={"error": "DB-fel", "detail": str(exc)})


@admin_router.get("/valor-stats")
async def valor_stats():
    """VALOR model status, training data overview, estimate accuracy, observations & jobs."""
    logger.info("admin /valor-stats called")
    try:
        # ── Active model ──
        model_rows = await _fetch(
            """
            SELECT id, model_version, model_filename, mae_sek, mape_pct,
                   within_10pct, within_20pct, vs_baseline_improvement_pct,
                   trained_at, is_active, training_samples, test_samples,
                   data_quality_warnings, notes
            FROM valor_model
            WHERE is_active = true
            ORDER BY trained_at DESC
            LIMIT 1
            """
        )
        model = None
        if model_rows:
            m = model_rows[0]
            model = {
                **dict(m),
                "trained_at": m["trained_at"].isoformat() if m.get("trained_at") else None,
            }

        # ── Training data ──
        total_samples = await _fetchval("SELECT COUNT(*) FROM training_sample") or 0
        included_in_training = await _fetchval(
            "SELECT COUNT(*) FROM training_sample WHERE included_in_training = true"
        ) or 0
        samples_per_source = await _fetch(
            """
            SELECT source_type, COUNT(*) AS count
            FROM training_sample
            GROUP BY source_type
            ORDER BY count DESC
            """
        )
        avg_quality_score = await _fetchval(
            "SELECT ROUND(AVG(quality_score)::numeric, 3) FROM training_sample WHERE quality_score IS NOT NULL"
        )

        training = {
            "total_samples": int(total_samples),
            "included_in_training": int(included_in_training),
            "samples_per_source": [dict(r) for r in samples_per_source],
            "avg_quality_score": float(avg_quality_score) if avg_quality_score is not None else None,
        }

        # ── Estimate accuracy ──
        est_total = await _fetchval("SELECT COUNT(*) FROM valor_estimate") or 0

        estimates = {
            "total": int(est_total),
        }

        # ── Observations ──
        obs_total = await _fetchval("SELECT COUNT(*) FROM price_observation") or 0
        obs_per_source = await _fetch(
            """
            SELECT source, COUNT(*) AS count
            FROM price_observation
            GROUP BY source
            ORDER BY count DESC
            """
        )
        suspicious_count = await _fetchval(
            "SELECT COUNT(*) FROM price_observation WHERE suspicious = true"
        ) or 0
        suspicious_rate = round(int(suspicious_count) / max(int(obs_total), 1) * 100, 1)

        stale_products = await _fetch(
            """
            SELECT product_key, MAX(observed_at) AS latest_observed_at
            FROM price_observation
            GROUP BY product_key
            HAVING MAX(observed_at) < NOW() - INTERVAL '48 hours'
            ORDER BY MAX(observed_at) ASC
            """
        )

        observations = {
            "total": int(obs_total),
            "per_source": [dict(r) for r in obs_per_source],
            "suspicious_rate": suspicious_rate,
            "stale_products": [
                {
                    **dict(r),
                    "latest_observed_at": r["latest_observed_at"].isoformat() if r.get("latest_observed_at") else None,
                }
                for r in stale_products
            ],
        }

        # ── Recent jobs ──
        recent_jobs = await _fetch(
            """
            SELECT id, started_at, finished_at, product_key, search_terms,
                   source, observations_added, observations_rejected,
                   status, summary, error_message
            FROM agent_job
            ORDER BY started_at DESC
            LIMIT 20
            """
        )
        jobs = [
            {
                **dict(r),
                "started_at": r["started_at"].isoformat() if r.get("started_at") else None,
                "finished_at": r["finished_at"].isoformat() if r.get("finished_at") else None,
            }
            for r in recent_jobs
        ]

        from backend.app.core.config import settings as _cfg
        result = {
            "model": model,
            "training": training,
            "estimates": estimates,
            "observations": observations,
            "jobs": jobs,
            "production_threshold": _cfg.valor_min_samples_for_production,
        }
        logger.info("admin /valor-stats ok, model=%s samples=%d",
                     model.get("model_version") if model else "none", total_samples)
        return result
    except Exception as exc:
        logger.error("admin /valor-stats failed: %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content={"error": "DB-fel", "detail": str(exc)})
