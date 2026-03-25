"""Centralised structured logging factory.

Every log entry includes: timestamp (ISO 8601), level, module, request_id
(when available via context var), message, and arbitrary key-value context.

Two sinks:
  - stdout  — JSON, one line per entry (for Railway / log aggregators)
  - logs/app.jsonl — rotating file, max 10 MB, keep 5 files
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Request-ID context var — set by RequestIdMiddleware for each request
# ---------------------------------------------------------------------------
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[4]
LOG_DIR = REPO_ROOT / "logs"


class _JsonFormatter(logging.Formatter):
    """Format each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "request_id": request_id_var.get(),
            "message": record.getMessage(),
        }

        # Attach extra key-value context attached via logger.info("msg", extra={...})
        skip = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "funcName", "lineno", "created",
            "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "taskName",
            "exc_info", "exc_text", "stack_info",
        }
        for key, value in record.__dict__.items():
            if key not in skip:
                entry[key] = value

        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(entry, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Module-level singleton — initialised once
# ---------------------------------------------------------------------------
_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    formatter = _JsonFormatter()

    # Stdout sink
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(logging.DEBUG)
    root.addHandler(stdout_handler)

    # Rotating file sink
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "app.jsonl",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------
def get_logger(name: str) -> logging.Logger:
    """Return a named logger with structured JSON output.

    Usage::

        from backend.app.utils.logger import get_logger
        logger = get_logger(__name__)
        logger.info("market fetch complete", extra={"source": "tradera", "count": 12})
    """
    _configure_root()
    return logging.getLogger(name)
