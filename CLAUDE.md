# Rules

## Commands
make setup          — create venv, install deps, copy .env.example
make dev            — uvicorn with --reload
make db             — start Postgres in Docker on :5432
make db-stop        — stop and remove the Docker container
pytest              — run all tests (405+)
pytest tests/test_golden_cases.py — run canonical pipeline tests only
alembic upgrade head              — apply all migrations
alembic revision --autogenerate -m "description" — generate migration after schema change
make context        — check CONTEXT.md line count and diff

## Code Style
- Async-first: all routers and DB calls use async/await
- Logging: `from backend.app.utils.logger import get_logger; logger = get_logger(__name__)`
- Caching: `from backend.app.utils.cache import get_cached, set_cached` (1h TTL)
- Thresholds: all numeric constants live in `backend/app/core/thresholds.py` — never inline magic numbers
- Config: all env vars defined in `backend/app/core/config.py`

## Workflow
- Plan before any change touching 3+ files
- Run pytest after every backend change
- Update CONTEXT.md endpoints section after adding routes
- Create Alembic migration after any schema change

## After every task
Update CONTEXT.md:
- File Map: sync with actual files (add/remove/rename)
- Recent Changes: prepend `YYYY-MM-DD — what changed` (keep max 15 entries, delete oldest)
- Known Issues: add/remove as needed
- Next Up: remove done items
- Skip sections where nothing changed
- Total file must stay under 200 lines; one line per entry, no paragraphs, no duplicates

Include CONTEXT.md in the commit if it changed.

## Security
CONTEXT.md must NEVER contain:
- API keys, tokens, passwords, or secrets
- Production URLs or internal endpoints
- User data or database connection strings
- .env values or references to actual key values

## Skills
- `skills/ui/SKILL.md` — UI design system (tokens, components, screen specs, copy rules, pre-ship checklist)

## Commits
Conventional: feat: fix: refactor: docs: chore:
Never commit .env
