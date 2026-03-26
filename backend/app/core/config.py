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
    google_cse_api_key: str | None
    google_cse_cx: str | None
    serpapi_api_key: str | None
    serpapi_base_url: str
    serpapi_timeout_seconds: int
    serpapi_engine: str
    serpapi_location: str | None
    serpapi_gl: str | None
    serpapi_hl: str | None
    database_url: str
    allowed_origins: str | None
    admin_secret_key: str | None
    # Embeddings
    embedding_model: str
    use_mock_embedding: bool
    embedding_similarity_threshold: float
    # Crawler
    crawler_enabled: bool
    crawler_sleep_seconds: int
    crawler_tradera_sleep: int
    crawler_use_serper: bool
    crawler_max_products_per_run: int

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
    def has_google_cse_credentials(self) -> bool:
        return bool(self.google_cse_api_key and self.google_cse_cx)

    @property
    def has_serpapi_credentials(self) -> bool:
        return bool(self.serpapi_api_key)


settings = Settings(
    openai_api_key=_read_env("OPENAI_API_KEY"),
    serper_api_key=_read_env("SERPER_DEV_API_KEY"),
    google_cse_api_key=_read_env("GOOGLE_CSE_API_KEY"),
    google_cse_cx=_read_env("GOOGLE_CSE_CX"),
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
    allowed_origins=_read_env("ALLOWED_ORIGINS"),
    admin_secret_key=_read_env("ADMIN_SECRET_KEY"),
    embedding_model=_read_env("EMBEDDING_MODEL") or "google/siglip-base-patch16-224",
    use_mock_embedding=_read_bool_env("USE_MOCK_EMBEDDING", default=False),
    embedding_similarity_threshold=float(_read_env("EMBEDDING_SIMILARITY_THRESHOLD") or "0.92"),
    crawler_enabled=_read_bool_env("CRAWLER_ENABLED", default=False),
    crawler_sleep_seconds=_read_int_env("CRAWLER_SLEEP_SECONDS", default=5),
    crawler_tradera_sleep=_read_int_env("CRAWLER_TRADERA_SLEEP", default=3),
    crawler_use_serper=_read_bool_env("CRAWLER_USE_SERPER", default=False),
    crawler_max_products_per_run=_read_int_env("CRAWLER_MAX_PRODUCTS_PER_RUN", default=20),
)
