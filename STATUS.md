# STATUS — 2026-03-25

## Done
- Full DB + Git review written to DB_GIT_REVIEW.md
- Found critical bug: admin.py queries `confidence_score` but column is `confidence`
- Found 4 missing indexes, connection pool bypass, dual-path create_all issue
- Git: 3 branches pushed to GitHub, commits clean, currently on main (should be develop)

## Key Findings
- admin.py metrics tab is broken (wrong column name, lines 160 + 212)
- _persist_valuation has no try/except — silent data loss
- admin.py bypasses SQLAlchemy pool — opens raw connections per query
- No indexes on status/brand/category — admin will timeout at scale

## Next
1. Fix confidence_score → confidence in admin.py (live bug)
2. Wrap _persist_valuation in try/except
3. Add missing indexes via Alembic migration
4. Switch admin.py to use SQLAlchemy session pool
