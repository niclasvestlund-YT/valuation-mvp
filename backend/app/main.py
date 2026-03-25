import logging
from pathlib import Path

from fastapi import FastAPI

# Silence noisy libraries before anything else
logging.getLogger("httpx").setLevel(logging.WARNING)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from backend.app.api.value import router as value_router
from backend.app.core.config import settings
from backend.app.core.version import VERSION
from backend.app.db.database import init_db
from backend.app.middleware.request_id import RequestIdMiddleware
from backend.app.routers.admin import admin_router
from backend.app.utils.logger import get_logger, _configure_root

# Initialise structured logging as early as possible
_configure_root()
logger = get_logger(__name__)

app = FastAPI(title="valuation-mvp")
app.state.settings = settings
app.state.is_mock_mode = settings.is_mock_mode

# Request-ID middleware — must be first so all downstream code sees request_id
app.add_middleware(RequestIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_INDEX = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
FRONTEND_ADMIN = Path(__file__).resolve().parents[2] / "frontend" / "admin.html"


@app.on_event("startup")
async def startup():
    logger.info("starting up valuation-mvp", extra={
        "mock_mode": settings.is_mock_mode,
        "has_openai": bool(settings.openai_api_key),
        "has_tradera": settings.has_tradera_credentials,
        "has_serper": settings.has_serper_credentials,
        "has_serpapi": settings.has_serpapi_credentials,
    })
    await init_db()


@app.get("/", response_class=FileResponse)
def read_root():
    return FileResponse(FRONTEND_INDEX)


@app.get("/health")
def health_check():
    return {"status": "ok", "version": VERSION}


@app.get("/admin", response_class=FileResponse)
def admin_ui():
    return FileResponse(FRONTEND_ADMIN)


app.include_router(value_router)
app.include_router(admin_router)
