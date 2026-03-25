"""Tests for structured logging foundation."""
from __future__ import annotations

import json
import logging
from io import StringIO

import pytest

from backend.app.utils.logger import _JsonFormatter, get_logger, request_id_var


def _capture_json_log(level: str, message: str, extra: dict | None = None) -> dict:
    """Emit a single log record and return the parsed JSON entry."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_JsonFormatter())

    log = logging.getLogger(f"test.{level}.{message[:10]}")
    log.handlers.clear()
    log.propagate = False
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)

    getattr(log, level)(message, extra=extra or {})
    output = stream.getvalue().strip()
    return json.loads(output)


def test_json_log_has_required_fields():
    """Every log entry must include timestamp, level, module, request_id, message."""
    entry = _capture_json_log("info", "hello world")
    assert "timestamp" in entry
    assert "level" in entry
    assert "module" in entry
    assert "request_id" in entry
    assert entry["message"] == "hello world"
    assert entry["level"] == "INFO"


def test_json_log_includes_extra_context():
    """Extra key-value context must appear at the top level of the JSON entry."""
    entry = _capture_json_log("info", "test", extra={"source": "tradera", "count": 7})
    assert entry.get("source") == "tradera"
    assert entry.get("count") == 7


def test_request_id_propagation():
    """When request_id_var is set, it must appear in log entries."""
    token = request_id_var.set("req-abc123")
    try:
        entry = _capture_json_log("info", "propagation check")
        assert entry["request_id"] == "req-abc123"
    finally:
        request_id_var.reset(token)


def test_request_id_absent_without_context():
    """Without a request context, request_id should be None."""
    # Ensure no context leaks from other tests
    token = request_id_var.set(None)
    try:
        entry = _capture_json_log("info", "no context")
        assert entry["request_id"] is None
    finally:
        request_id_var.reset(token)


def test_get_logger_returns_named_logger():
    """get_logger must return a Logger with the given name."""
    log = get_logger("backend.app.test.module")
    assert isinstance(log, logging.Logger)
    assert log.name == "backend.app.test.module"


def test_debug_level_entry():
    """DEBUG level must serialise correctly."""
    entry = _capture_json_log("debug", "cache hit")
    assert entry["level"] == "DEBUG"


def test_error_level_entry():
    """ERROR level must serialise correctly."""
    entry = _capture_json_log("error", "external API failure")
    assert entry["level"] == "ERROR"


def test_warning_level_entry():
    """WARNING level must serialise correctly."""
    entry = _capture_json_log("warning", "low confidence result")
    assert entry["level"] == "WARNING"


def test_json_log_timestamp_is_iso8601():
    """Timestamp must be a valid ISO 8601 string."""
    from datetime import datetime
    entry = _capture_json_log("info", "ts check")
    # datetime.fromisoformat raises ValueError for invalid strings
    datetime.fromisoformat(entry["timestamp"])


def test_exc_info_captured():
    """Exception info must appear in the log entry."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_JsonFormatter())

    log = logging.getLogger("test.exc_info")
    log.handlers.clear()
    log.propagate = False
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)

    try:
        raise ValueError("test error")
    except ValueError:
        log.error("caught error", exc_info=True)

    entry = json.loads(stream.getvalue().strip())
    assert "exc_info" in entry
    assert "ValueError" in entry["exc_info"]
