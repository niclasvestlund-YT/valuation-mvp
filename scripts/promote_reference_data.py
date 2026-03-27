#!/usr/bin/env python3
"""
Reference data promotion: local → staging / production.

Idempotent, transactional, auditable.
Promotes ONLY: product, market_comparable, new_price_snapshot.
Never touches: valuations, feedback, embeddings, agent, valor, training.

Usage:
  # Step 1: Export curated snapshot from local DB
  python scripts/promote_reference_data.py export

  # Step 2: Import into staging (requires STAGING_DATABASE_URL, never falls back)
  STAGING_DATABASE_URL="postgresql://..." python scripts/promote_reference_data.py import --target staging

  # Step 3: Verify
  STAGING_DATABASE_URL="postgresql://..." python scripts/promote_reference_data.py verify --target staging

  # Dry run (shows what would happen, no writes)
  python scripts/promote_reference_data.py export --dry-run

Flags:
  --min-comparables N   Minimum unflagged comparables per product (default: 3)
  --max-age-days N      Max product age in days (default: 30)
  --comparable-max-age N  Max comparable age in days (default: 60)
  --snapshot-dir DIR    Where to write/read snapshot (default: data/snapshots/)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

SNAPSHOT_DIR = PROJECT_ROOT / "data" / "snapshots"

# ─── Quality filters ───
MIN_PRICE_SEK = 200
MAX_PRICE_SEK = 150_000
DEFAULT_MIN_COMPARABLES = 3
DEFAULT_MAX_AGE_DAYS = 30
DEFAULT_COMPARABLE_MAX_AGE_DAYS = 60
NEW_PRICE_MAX_AGE_DAYS = 14


# ─── URL helpers ───

def to_sync_url(url: str) -> str:
    """Normalize any PostgreSQL URL to psycopg2 sync format for scripts."""
    u = url.strip()
    u = u.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    if u.startswith("postgres://"):
        u = u.replace("postgres://", "postgresql+psycopg2://", 1)
    elif u.startswith("postgresql://") and "+psycopg2" not in u:
        u = u.replace("postgresql://", "postgresql+psycopg2://", 1)
    return u


def get_engine(url: str):
    from sqlalchemy import create_engine
    return create_engine(to_sync_url(url))


# ─── Target URL resolution (strict — never falls back to DATABASE_URL) ───

_TARGET_ENV_VARS = {
    "staging": "STAGING_DATABASE_URL",
    "production": "PRODUCTION_DATABASE_URL",
}


def resolve_target_url(target: str) -> str:
    """Get the DB URL for a target environment. Fails hard if not set.

    CRITICAL: staging requires STAGING_DATABASE_URL.
              production requires PRODUCTION_DATABASE_URL.
              We NEVER fall back to DATABASE_URL to prevent accidental local writes.
    """
    env_var = _TARGET_ENV_VARS.get(target)
    if not env_var:
        print(f"ERROR: Unknown target '{target}'. Use 'staging' or 'production'.")
        sys.exit(1)

    url = os.getenv(env_var, "").strip()
    if not url:
        print(f"ERROR: {env_var} is not set.")
        print(f"  Set it to the {target} PostgreSQL connection string.")
        print(f"  Example: {env_var}=\"postgresql://user:pass@host:port/dbname\"")
        sys.exit(1)

    # Guard: reject obviously-local URLs for remote targets
    for local_marker in ("localhost", "127.0.0.1", "::1"):
        if local_marker in url:
            print(f"ERROR: {env_var} points to {local_marker}.")
            print(f"  This looks like a local database, not {target}.")
            print(f"  Set {env_var} to the actual {target} connection string.")
            sys.exit(1)

    return url


# ═══════════════════════════════════════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════════════════════════════════════

def cmd_export(args):
    """Export curated reference snapshot from local DB."""
    from sqlalchemy import text

    local_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:dev@localhost:5432/valuation")
    engine = get_engine(local_url)

    print("═══ EXPORT REFERENCE SNAPSHOT ═══")
    print(f"Source: local DB")
    print(f"Min comparables: {args.min_comparables}")
    print(f"Max product age: {args.max_age_days} days")
    print(f"Max comparable age: {args.comparable_max_age} days")
    print()

    with engine.connect() as conn:
        # Find qualifying products: recent products with enough recent, unflagged comparables
        keys = conn.execute(text("""
            SELECT p.product_key
            FROM product p
            JOIN market_comparable mc ON mc.product_key = p.product_key
            WHERE mc.is_active = true
              AND mc.flagged = false
              AND mc.price_sek BETWEEN :min_price AND :max_price
              AND mc.last_seen >= NOW() - MAKE_INTERVAL(days => :comp_max_age)
              AND p.last_seen >= NOW() - MAKE_INTERVAL(days => :max_age)
            GROUP BY p.product_key
            HAVING COUNT(*) >= :min_comps
        """), {
            "min_price": MIN_PRICE_SEK,
            "max_price": MAX_PRICE_SEK,
            "max_age": args.max_age_days,
            "comp_max_age": args.comparable_max_age,
            "min_comps": args.min_comparables,
        }).fetchall()
        product_keys = [r[0] for r in keys]

        if not product_keys:
            print("No qualifying products found. Nothing to export.")
            return

        print(f"Qualifying products: {len(product_keys)}")

        # Extract products (WITHOUT valuation_count — that's env-specific runtime data)
        products = conn.execute(text("""
            SELECT product_key, brand, model, category, first_seen, last_seen
            FROM product
            WHERE product_key = ANY(:keys)
            ORDER BY product_key
        """), {"keys": product_keys}).fetchall()
        product_cols = ["product_key", "brand", "model", "category", "first_seen", "last_seen"]

        # Extract comparables (WITHOUT id, with recency filter)
        comparables = conn.execute(text("""
            SELECT product_key, source, listing_url, title, price_sek, condition,
                   relevance_score, is_active, flagged, flag_reason,
                   first_seen, last_seen, disappeared_at
            FROM market_comparable
            WHERE product_key = ANY(:keys)
              AND is_active = true
              AND flagged = false
              AND price_sek BETWEEN :min_price AND :max_price
              AND last_seen >= NOW() - MAKE_INTERVAL(days => :comp_max_age)
            ORDER BY product_key, last_seen DESC
        """), {
            "keys": product_keys,
            "min_price": MIN_PRICE_SEK,
            "max_price": MAX_PRICE_SEK,
            "comp_max_age": args.comparable_max_age,
        }).fetchall()
        comparable_cols = [
            "product_key", "source", "listing_url", "title", "price_sek", "condition",
            "relevance_score", "is_active", "flagged", "flag_reason",
            "first_seen", "last_seen", "disappeared_at",
        ]

        # Extract new prices (WITHOUT id)
        new_prices = conn.execute(text("""
            SELECT product_key, source, price_sek, currency, url, title, fetched_at
            FROM new_price_snapshot
            WHERE product_key = ANY(:keys)
              AND fetched_at >= NOW() - MAKE_INTERVAL(days => :age)
            ORDER BY product_key, fetched_at DESC
        """), {"keys": product_keys, "age": NEW_PRICE_MAX_AGE_DAYS}).fetchall()
        new_price_cols = ["product_key", "source", "price_sek", "currency", "url", "title", "fetched_at"]

    print(f"Products:    {len(products)}")
    print(f"Comparables: {len(comparables)}")
    print(f"New prices:  {len(new_prices)}")

    if args.dry_run:
        print("\n[DRY RUN] No files written.")
        return

    # Write snapshot
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snap_dir = Path(args.snapshot_dir) / timestamp
    snap_dir.mkdir(parents=True, exist_ok=True)

    def write_jsonl(path: Path, cols: list[str], rows: list):
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(
                    {col: (val.isoformat() if hasattr(val, "isoformat") else val) for col, val in zip(cols, row)},
                    ensure_ascii=False, default=str,
                ) + "\n")

    write_jsonl(snap_dir / "products.jsonl", product_cols, products)
    write_jsonl(snap_dir / "comparables.jsonl", comparable_cols, comparables)
    write_jsonl(snap_dir / "new_prices.jsonl", new_price_cols, new_prices)

    # Write manifest
    manifest = {
        "schema_version": 2,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source": "local",
        "filters": {
            "min_comparables": args.min_comparables,
            "max_age_days": args.max_age_days,
            "comparable_max_age_days": args.comparable_max_age,
            "price_range": [MIN_PRICE_SEK, MAX_PRICE_SEK],
            "new_price_max_age_days": NEW_PRICE_MAX_AGE_DAYS,
        },
        "counts": {
            "products": len(products),
            "comparables": len(comparables),
            "new_prices": len(new_prices),
        },
        "product_keys": sorted(product_keys),
    }
    (snap_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    # Symlink latest
    latest = Path(args.snapshot_dir) / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(timestamp)

    print(f"\nSnapshot: {snap_dir}")
    print(f"Symlink:  {latest} → {timestamp}")
    print("Next: STAGING_DATABASE_URL=\"...\" python scripts/promote_reference_data.py import --target staging")


# ═══════════════════════════════════════════════════════════════════════
# IMPORT
# ═══════════════════════════════════════════════════════════════════════

def cmd_import(args):
    """Import reference snapshot into target environment (idempotent)."""
    from sqlalchemy import text

    db_url = resolve_target_url(args.target)

    # Load snapshot
    snap_dir = Path(args.snapshot_dir) / "latest"
    if not snap_dir.exists():
        print("ERROR: No snapshot found. Run 'export' first.")
        sys.exit(1)

    snap_dir = snap_dir.resolve()  # Follow symlink
    manifest = json.loads((snap_dir / "manifest.json").read_text())

    print(f"═══ IMPORT REFERENCE DATA → {args.target.upper()} ═══")
    print(f"Snapshot: {snap_dir.name} ({manifest['exported_at']})")
    print(f"Products: {manifest['counts']['products']}")
    print(f"Comparables: {manifest['counts']['comparables']}")
    print(f"New prices: {manifest['counts']['new_prices']}")
    print()

    def read_jsonl(path: Path) -> list[dict]:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    products = read_jsonl(snap_dir / "products.jsonl")
    comparables = read_jsonl(snap_dir / "comparables.jsonl")
    new_prices = read_jsonl(snap_dir / "new_prices.jsonl")

    if args.dry_run:
        print("[DRY RUN] Would import:")
        print(f"  {len(products)} products")
        print(f"  {len(comparables)} comparables")
        print(f"  {len(new_prices)} new prices")
        return

    engine = get_engine(db_url)

    # Pre-flight: verify target has migrations and is not accidentally local
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar()
        except Exception:
            print("ERROR: Target database has no alembic_version table.")
            print("  Run migrations first: cd backend && alembic upgrade head")
            sys.exit(1)

        # Deterministic guard: check the actual server address from the live connection
        server_addr = conn.execute(text("SELECT inet_server_addr()")).scalar()
        if server_addr and str(server_addr) in ("127.0.0.1", "::1"):
            print(f"ERROR: Target database server is at {server_addr} (local loopback).")
            print(f"  This is a local database, not {args.target}.")
            print(f"  Set {_TARGET_ENV_VARS[args.target]} to the actual remote connection string.")
            sys.exit(1)

    stats = {"products_upserted": 0, "comparables_upserted": 0, "new_prices_inserted": 0, "comparables_skipped": 0}

    with engine.begin() as conn:
        # ── Products: UPSERT on product_key (no valuation_count — reset to 0 for target) ──
        for p in products:
            conn.execute(text("""
                INSERT INTO product (product_key, brand, model, category, valuation_count, first_seen, last_seen)
                VALUES (:product_key, :brand, :model, :category, 0, :first_seen, :last_seen)
                ON CONFLICT (product_key) DO UPDATE SET
                    brand = EXCLUDED.brand,
                    model = EXCLUDED.model,
                    category = COALESCE(EXCLUDED.category, product.category),
                    last_seen = GREATEST(product.last_seen, EXCLUDED.last_seen)
            """), p)
            stats["products_upserted"] += 1

        # ── Comparables: UPSERT on listing_url ──
        for c in comparables:
            result = conn.execute(text("""
                INSERT INTO market_comparable
                    (product_key, source, listing_url, title, price_sek, condition,
                     relevance_score, is_active, flagged, flag_reason,
                     first_seen, last_seen, disappeared_at)
                VALUES
                    (:product_key, :source, :listing_url, :title, :price_sek, :condition,
                     :relevance_score, :is_active, :flagged, :flag_reason,
                     :first_seen, :last_seen, :disappeared_at)
                ON CONFLICT (listing_url) DO UPDATE SET
                    title = EXCLUDED.title,
                    price_sek = EXCLUDED.price_sek,
                    condition = COALESCE(EXCLUDED.condition, market_comparable.condition),
                    is_active = EXCLUDED.is_active,
                    last_seen = GREATEST(market_comparable.last_seen, EXCLUDED.last_seen)
                    -- NOTE: flagged and flag_reason are NOT overwritten.
                    -- If staging flags a comparable, re-import does not clear the flag.
            """), c)
            if result.rowcount > 0:
                stats["comparables_upserted"] += 1
            else:
                stats["comparables_skipped"] += 1

        # ── New prices: INSERT only if not duplicate (product_key + source + fetched_at) ──
        for np in new_prices:
            result = conn.execute(text("""
                INSERT INTO new_price_snapshot
                    (product_key, source, price_sek, currency, url, title, fetched_at)
                SELECT :product_key, :source, :price_sek, :currency, :url, :title, :fetched_at
                WHERE NOT EXISTS (
                    SELECT 1 FROM new_price_snapshot
                    WHERE product_key = :product_key
                      AND source = :source
                      AND fetched_at = :fetched_at
                )
            """), np)
            if result.rowcount > 0:
                stats["new_prices_inserted"] += 1

    # Write import log
    import_log = {
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "target": args.target,
        "snapshot": snap_dir.name,
        "stats": stats,
    }
    log_path = snap_dir / f"import_{args.target}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    log_path.write_text(json.dumps(import_log, indent=2))

    print(f"Products upserted:     {stats['products_upserted']}")
    print(f"Comparables upserted:  {stats['comparables_upserted']}")
    print(f"Comparables skipped:   {stats['comparables_skipped']}")
    print(f"New prices inserted:   {stats['new_prices_inserted']}")
    print(f"\nImport log: {log_path}")
    print(f"Next: {_TARGET_ENV_VARS[args.target]}=\"...\" python scripts/promote_reference_data.py verify --target {args.target}")


# ═══════════════════════════════════════════════════════════════════════
# VERIFY
# ═══════════════════════════════════════════════════════════════════════

def cmd_verify(args):
    """Verify reference data in target environment."""
    from sqlalchemy import text

    db_url = resolve_target_url(args.target)
    engine = get_engine(db_url)

    print(f"═══ VERIFY REFERENCE DATA — {args.target.upper()} ═══\n")

    with engine.connect() as conn:
        # Migration status
        ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        print(f"Alembic version: {ver}")

        # pgvector
        ext = conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")).scalar()
        print(f"pgvector:        {ext or 'NOT INSTALLED'}")

        # DB name (for operator confirmation)
        db_name = conn.execute(text("SELECT current_database()")).scalar()
        print(f"Database name:   {db_name}")

        # Row counts — reference data
        print("\n── Reference data ──")
        for tbl in ["product", "market_comparable", "new_price_snapshot"]:
            count = conn.execute(text(f'SELECT COUNT(*) FROM "{tbl}"')).scalar()
            print(f"  {tbl}: {count}")

        # Env-local tables should be empty or near-empty
        print("\n── Environment-local (should be empty or minimal) ──")
        for tbl in ["valuations", "price_snapshots", "product_embedding", "agent_job",
                     "price_observation", "training_sample", "valor_model", "valor_estimate", "price_statistic"]:
            try:
                count = conn.execute(text(f'SELECT COUNT(*) FROM "{tbl}"')).scalar()
                status = "OK" if count == 0 else f"⚠ {count} rows"
                print(f"  {tbl}: {status}")
            except Exception:
                print(f"  {tbl}: (table not found)")

        # Quality
        print("\n── Quality checks ──")
        flagged = conn.execute(text("SELECT COUNT(*) FROM market_comparable WHERE flagged = true")).scalar()
        print(f"  Flagged comparables: {flagged}")
        outside = conn.execute(text(f"SELECT COUNT(*) FROM market_comparable WHERE price_sek < {MIN_PRICE_SEK} OR price_sek > {MAX_PRICE_SEK}")).scalar()
        print(f"  Price outside {MIN_PRICE_SEK}-{MAX_PRICE_SEK}: {outside}")
        coverage = conn.execute(text("SELECT COUNT(DISTINCT product_key) FROM market_comparable WHERE is_active = true")).scalar()
        print(f"  Products with active comparables: {coverage}")

        # Sample
        print("\n── Top 5 products ──")
        rows = conn.execute(text("""
            SELECT p.product_key, p.brand, p.model, COUNT(mc.id) AS comps
            FROM product p
            LEFT JOIN market_comparable mc ON mc.product_key = p.product_key AND mc.is_active = true
            GROUP BY p.product_key, p.brand, p.model
            ORDER BY comps DESC LIMIT 5
        """)).fetchall()
        for r in rows:
            print(f"  {r[1]} {r[2]}: {r[3]} comparables")

    print(f"\n═══ Verification complete ═══")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Reference data promotion: local → staging/production")
    sub = parser.add_subparsers(dest="command")

    # Export
    exp = sub.add_parser("export", help="Export curated snapshot from local DB")
    exp.add_argument("--min-comparables", type=int, default=DEFAULT_MIN_COMPARABLES)
    exp.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    exp.add_argument("--comparable-max-age", type=int, default=DEFAULT_COMPARABLE_MAX_AGE_DAYS)
    exp.add_argument("--snapshot-dir", default=str(SNAPSHOT_DIR))
    exp.add_argument("--dry-run", action="store_true")

    # Import
    imp = sub.add_parser("import", help="Import snapshot into target environment")
    imp.add_argument("--target", required=True, choices=["staging", "production"])
    imp.add_argument("--snapshot-dir", default=str(SNAPSHOT_DIR))
    imp.add_argument("--dry-run", action="store_true")

    # Verify
    ver = sub.add_parser("verify", help="Verify reference data in target environment")
    ver.add_argument("--target", required=True, choices=["staging", "production"])

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    {"export": cmd_export, "import": cmd_import, "verify": cmd_verify}[args.command](args)


if __name__ == "__main__":
    main()
