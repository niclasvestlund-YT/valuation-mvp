import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

# Silence noisy libraries before anything else
logging.getLogger("httpx").setLevel(logging.WARNING)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.app.api.agent import router as agent_router
from backend.app.api.value import router as value_router
from backend.app.routers.ingest import ingest_router
from backend.app.core.config import settings
from backend.app.core.version import VERSION
from backend.app.db.database import dispose_engine, init_db
from backend.app.middleware.request_id import RequestIdMiddleware
from backend.app.routers.admin import admin_router
from backend.app.services.valor_service import ValorService
from backend.app.utils.logger import get_logger, _configure_root

_MAX_REQUEST_BODY_BYTES = 20 * 1024 * 1024  # 20 MB


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_REQUEST_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Request body too large (max {_MAX_REQUEST_BODY_BYTES // (1024*1024)} MB)"},
            )
        return await call_next(request)

# Initialise structured logging as early as possible
_configure_root()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic.

    - Startup: verify DB connectivity
    - Shutdown: dispose connection pool to avoid leaked connections
    """
    logger.info("starting up valuation-mvp", extra={
        "mock_mode": settings.is_mock_mode,
        "has_openai": bool(settings.openai_api_key),
        "has_tradera": settings.has_tradera_credentials,
        "has_serper": settings.has_serper_credentials,
        "has_serpapi": settings.has_serpapi_credentials,
    })
    # Ensure model directory exists for VALOR (Railway volume or local)
    import os as _startup_os
    model_dir = Path(_startup_os.getenv("VALOR_MODEL_DIR", "models"))
    model_dir.mkdir(exist_ok=True, parents=True)
    logger.info("valor.model_dir", extra={"path": str(model_dir.resolve())})
    await init_db()
    yield
    await dispose_engine()


limiter = Limiter(key_func=get_remote_address, default_limits=[])

import os as _os
_environment = _os.getenv("RAILWAY_ENVIRONMENT") or _os.getenv("ENVIRONMENT") or "local"
_is_production = _environment == "production"
_is_staging = _environment == "staging"
_is_deployed = _environment != "local"

app = FastAPI(
    title="valuation-mvp",
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
)
app.state.limiter = limiter
app.state.settings = settings
app.state.is_mock_mode = settings.is_mock_mode
app.state.valor_service = ValorService()
app.add_exception_handler(RateLimitExceeded, lambda req, exc: JSONResponse(
    status_code=429,
    content={"detail": "Rate limit exceeded. Max 10 requests per minute."},
))

# Request-ID middleware — must be first so all downstream code sees request_id
app.add_middleware(RequestIdMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)

_allowed_origins_raw = settings.allowed_origins
_allowed_origins = [o.strip() for o in _allowed_origins_raw.split(",") if o.strip()] if _allowed_origins_raw else ["http://localhost:8000", "http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_INDEX = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
FRONTEND_ADMIN = Path(__file__).resolve().parents[2] / "frontend" / "admin.html"


@app.get("/", response_class=FileResponse)
def read_root():
    return FileResponse(FRONTEND_INDEX)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "version": VERSION,
        "environment": _environment,
        "dependencies": {
            "vision": "mock" if settings.is_mock_mode else ("configured" if settings.openai_api_key else "missing_key"),
            "tradera": "configured" if settings.has_tradera_credentials else "unconfigured",
            "serper": "configured" if settings.has_serper_credentials else "unconfigured",
            "serpapi": "configured" if settings.has_serpapi_credentials else "unconfigured",
            "database": "configured" if settings.has_database else "unconfigured",
            "google_vision_ocr": "mock" if settings.use_mock_google_vision else ("enabled" if settings.google_vision_enabled else "disabled"),
            "easyocr": "mock" if settings.use_mock_easyocr else ("enabled" if settings.easyocr_enabled else "disabled"),
            "embeddings": "mock" if settings.use_mock_embedding else "configured",
            "crawler": "enabled" if settings.crawler_enabled else "disabled",
            "valor": "available" if app.state.valor_service.is_available() else "no_model",
        },
    }


@app.get("/admin", response_class=FileResponse)
def admin_ui():
    return FileResponse(FRONTEND_ADMIN)


app.include_router(value_router)
app.include_router(agent_router)
app.include_router(ingest_router)
app.include_router(admin_router)
