import logging
from pathlib import Path

from fastapi import FastAPI

logging.getLogger("httpx").setLevel(logging.WARNING)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

from backend.app.api.value import router as value_router
from backend.app.core.config import settings
from backend.app.db.database import init_db

app = FastAPI(title="valuation-mvp")
app.state.settings = settings
app.state.is_mock_mode = settings.is_mock_mode


@app.on_event("startup")
async def startup():
    await init_db()
FRONTEND_INDEX = Path(__file__).resolve().parents[2] / "frontend" / "index.html"

# Keep local development simple when opening the HTML file directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=FileResponse)
def read_root():
    return FileResponse(FRONTEND_INDEX)


@app.get("/health", response_class=PlainTextResponse)
def health_check():
    return "API running"


app.include_router(value_router)
