# Deployment Guide

## Railway (recommended)

### One-time setup

1. Install Railway CLI: `npm install -g @railway/cli`
2. Login: `railway login`
3. Link project: `railway link` (or create new: `railway init`)
4. Add a PostgreSQL service in the Railway dashboard — Railway sets `DATABASE_URL` automatically.

### Environment variables

Set these in the Railway dashboard (Variables tab):

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI Vision API key (platform.openai.com) |
| `OPENAI_VISION_MODEL` | No | Default: `gpt-4.1-mini` |
| `OPENAI_TIMEOUT_SECONDS` | No | Default: `30` |
| `OPENAI_MAX_RETRIES` | No | Default: `3` |
| `TRADERA_APP_ID` | No | Tradera marketplace API (developer.tradera.com) |
| `TRADERA_APP_KEY` | No | Tradera API key |
| `SERPER_DEV_API_KEY` | Recommended | Serper.dev for new prices (primary source) |
| `SERPAPI_API_KEY` | Optional | SerpAPI fallback for new prices + used market supplement |
| `DATABASE_URL` | Auto | Set by Railway when PostgreSQL service is linked |

> **Note:** `DATABASE_URL` is injected automatically by Railway when you attach a Postgres database. It should be in asyncpg format: `postgresql+asyncpg://...`
>
> If Railway injects a standard `postgres://` URL, prefix it: `DATABASE_URL=postgresql+asyncpg://...`

### Deploy

```bash
git push                # Railway auto-deploys on push to main
# or
railway up              # Deploy current branch manually
```

### Run database migrations

```bash
railway run alembic upgrade head
```

### Health check

```
GET /health
```
Returns `{"status": "ok", "version": "...", "dependencies": {...}}`.
Railway uses this as the liveness probe (configured in `railway.toml`).

---

## Local development

```bash
make setup      # Create venv and install dependencies
make dev        # Start uvicorn with --reload on localhost:8000
make db         # Start PostgreSQL via Docker on port 5432
make db-stop    # Stop and remove the Docker container
```

Copy `.env.example` to `.env` and fill in API keys before running `make dev`.
