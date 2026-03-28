"""
admin_errors.py — Strukturerade fel för admin-panelen.

Varje fel inkluderar:
- error_code: maskinläsbar kod
- message: mänsklig beskrivning
- copy_paste_context: klar text att klistra in i Claude Code för analys
- suggested_action: vad man ska göra härnäst

Används av frontend för att visa kopierbara felmeddelanden.
"""

import json
import traceback
from datetime import datetime, timezone
from typing import Any


class AdminError:
    def __init__(
        self,
        error_code: str,
        message: str,
        endpoint: str,
        raw_error: Exception | None = None,
        context: dict[str, Any] | None = None,
    ):
        self.error_code = error_code
        self.message = message
        self.endpoint = endpoint
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.traceback = traceback.format_exc() if raw_error else None
        self.context = context or {}

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "endpoint": self.endpoint,
            "timestamp": self.timestamp,
            "context": self.context,
        }

    def to_copy_paste(self) -> str:
        """Returnerar text redo att klistras in i Claude Code."""
        lines = [
            f"## Admin-fel: {self.error_code}",
            f"Tidsstämpel: {self.timestamp}",
            f"Endpoint: {self.endpoint}",
            f"Meddelande: {self.message}",
        ]
        if self.context:
            lines.append(f"Kontext: {json.dumps(self.context, ensure_ascii=False, indent=2)}")
        if self.traceback:
            lines.append(f"Traceback:\n```\n{self.traceback}\n```")
        lines.append("\nFråga: Vad orsakar detta fel och hur fixar jag det?")
        return "\n".join(lines)


def raise_admin_error(
    error_code: str,
    endpoint: str,
    raw_error: Exception | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """Build AdminError and raise as HTTPException with structured detail."""
    from fastapi import HTTPException
    from backend.app.utils.logger import get_logger

    logger = get_logger(__name__)

    message = KNOWN_ERRORS.get(error_code, "Okänt admin-fel")
    err = AdminError(
        error_code=error_code,
        message=message,
        endpoint=endpoint,
        raw_error=raw_error,
        context=context,
    )
    logger.error(
        f"admin error: {error_code}",
        extra={"admin_error": err.to_dict()},
        exc_info=raw_error is not None,
    )
    raise HTTPException(
        status_code=500,
        detail={
            "error_code": err.error_code,
            "message": err.message,
            "copy_paste_context": err.to_copy_paste(),
        },
    )


# Fördefinierade felkoder
KNOWN_ERRORS = {
    "DB_CONNECTION_FAILED": "Kunde inte ansluta till databasen",
    "METRICS_FETCH_FAILED": "Kunde inte hämta metrics-data",
    "ASSISTANT_STATS_FAILED": "Kunde inte hämta Prisassistent-statistik",
    "VALOR_STATS_FAILED": "Kunde inte hämta Valor ML-statistik",
    "HEALTH_CHECK_FAILED": "Hälsokontroll misslyckades",
    "CRAWLER_STATS_FAILED": "Kunde inte hämta crawler-data",
    "AUTH_FAILED": "Autentisering misslyckades",
    "OVERVIEW_FETCH_FAILED": "Kunde inte hämta DB-översikt",
    "VALUATIONS_FETCH_FAILED": "Kunde inte hämta värderingsdata",
    "OCR_STATS_FAILED": "Kunde inte hämta OCR-statistik",
    "AGENT_STATS_FAILED": "Kunde inte hämta agent-statistik",
    "MARKET_DATA_FAILED": "Kunde inte hämta marknadsdata",
}
