import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)


def _read_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None

    value = value.strip()
    return value or None


def _read_bool_env(name: str, default: bool = False) -> bool:
    value = _read_env(name)
    if value is None:
        return default

    return value.lower() in {"1", "true", "yes", "on"}


def _read_int_env(name: str, default: int) -> int:
    value = _read_env(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def _read_optional_int_env(name: str) -> int | None:
    value = _read_env(name)
    if value is None:
        return None

    try:
        return int(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    use_mock_vision: bool
    openai_vision_model: str
    openai_timeout_seconds: int
    openai_max_retries: int
    tradera_app_id: int | None
    tradera_app_key: str | None
    tradera_base_url: str
    tradera_timeout_seconds: int
    serper_api_key: str | None
    serpapi_api_key: str | None
    serpapi_base_url: str
    serpapi_timeout_seconds: int
    serpapi_engine: str
    serpapi_location: str | None
    serpapi_gl: str | None
    serpapi_hl: str | None
    database_url: str

    @property
    def is_mock_mode(self) -> bool:
        return self.use_mock_vision

    @property
    def has_database(self) -> bool:
        return bool(self.database_url)

    @property
    def has_tradera_credentials(self) -> bool:
        return self.tradera_app_id is not None and bool(self.tradera_app_key)

    @property
    def has_serper_credentials(self) -> bool:
        return bool(self.serper_api_key)

    @property
    def has_serpapi_credentials(self) -> bool:
        return bool(self.serpapi_api_key)


settings = Settings(
    openai_api_key=_read_env("OPENAI_API_KEY"),
    serper_api_key=_read_env("SERPER_DEV_API_KEY"),
    use_mock_vision=_read_bool_env("USE_MOCK_VISION", default=False),
    openai_vision_model=_read_env("OPENAI_VISION_MODEL") or "gpt-4.1-mini",
    openai_timeout_seconds=_read_int_env("OPENAI_TIMEOUT_SECONDS", default=30),
    openai_max_retries=_read_int_env("OPENAI_MAX_RETRIES", default=3),
    tradera_app_id=_read_optional_int_env("TRADERA_APP_ID"),
    tradera_app_key=_read_env("TRADERA_APP_KEY"),
    tradera_base_url=_read_env("TRADERA_BASE_URL") or "https://api.tradera.com/v3/searchservice.asmx",
    tradera_timeout_seconds=_read_int_env("TRADERA_TIMEOUT_SECONDS", default=20),
    serpapi_api_key=_read_env("SERPAPI_API_KEY"),
    serpapi_base_url=_read_env("SERPAPI_BASE_URL") or "https://serpapi.com/search.json",
    serpapi_timeout_seconds=_read_int_env("SERPAPI_TIMEOUT_SECONDS", default=20),
    serpapi_engine=_read_env("SERPAPI_ENGINE") or "google_shopping",
    serpapi_location=_read_env("SERPAPI_LOCATION") or "Sweden",
    serpapi_gl=_read_env("SERPAPI_GL") or "se",
    serpapi_hl=_read_env("SERPAPI_HL") or "sv",
    database_url=_read_env("DATABASE_URL") or "postgresql+asyncpg://postgres:dev@localhost:5432/valuation",
)
