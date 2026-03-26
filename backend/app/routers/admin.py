"""
Admin router — read-only PostgreSQL inspection & metrics.
Protected by ADMIN_SECRET_KEY header check.
Uses the shared SQLAlchemy async session pool from database.py.
Mounted at /admin in main.py.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from backend.app.db.database import async_session

ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "").strip()

# Strict identifier pattern: only lowercase letters, digits, underscores
_SAFE_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _validate_identifier(name: str) -> str:
    """Reject any identifier that isn't a simple lowercase SQL name."""
    if not _SAFE_IDENTIFIER.match(name):
        raise HTTPException(status_code=400, detail=f"Invalid identifier: {name!r}")
    return name


async def verify_admin_key(x_admin_key: str = Header(default="")) -> None:
    """Reject requests without a valid ADMIN_SECRET_KEY header."""
    if not ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Admin access disabled — ADMIN_SECRET_KEY not configured")
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
