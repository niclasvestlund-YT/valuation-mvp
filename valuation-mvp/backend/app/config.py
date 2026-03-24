import sys
import logging
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Required
    openai_api_key: str
    # api_key is kept for possible future programmatic access but no longer
    # enforced via middleware — a shared secret in the browser bundle is not auth.
    api_key: str = ""

    # Optional — degrade gracefully if missing
    tradera_app_id: str = ""
    tradera_app_key: str = ""
    serpapi_api_key: str = ""
    serper_dev_api_key: str = ""

    # Behaviour
    search_provider: str = "serpapi"  # "serpapi" or "serper"
    tradera_timeout_seconds: int = 20
    debug: bool = False

    # CORS — comma-separated list of allowed origins
    # Leave empty in production (same-origin serving); set for dev cross-origin
    cors_origins: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def cors_origins_list(self) -> list[str]:
        base = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if self.debug:
            base += ["http://localhost:5173", "http://localhost:8000"]
        return list(dict.fromkeys(base))  # deduplicate, preserve order


def _validate_startup(s: Settings) -> None:
    """Fail fast if required config is missing."""
    missing = []
    if not s.openai_api_key:
        missing.append("OPENAI_API_KEY")

    if missing:
        logger.critical(f"Missing required env vars: {', '.join(missing)} — cannot start.")
        sys.exit(1)

    if s.search_provider == "serper" and not s.serper_dev_api_key:
        logger.warning("SEARCH_PROVIDER=serper but SERPER_DEV_API_KEY is not set — new-price search will fail.")
    if s.search_provider == "serpapi" and not s.serpapi_api_key:
        logger.warning("SEARCH_PROVIDER=serpapi but SERPAPI_API_KEY is not set — new-price search will fail.")
    if not s.tradera_app_id or not s.tradera_app_key:
        logger.warning("TRADERA_APP_ID / TRADERA_APP_KEY not set — Tradera search disabled.")


settings = Settings()
_validate_startup(settings)
