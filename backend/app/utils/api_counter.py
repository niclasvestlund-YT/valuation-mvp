"""API call counter for admin dashboard.

Thread-safe. Persists to logs/api_counter.json so data survives server restarts.
"""

import json
import threading
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

_lock = threading.Lock()
_PERSIST_FILE = Path(__file__).resolve().parents[4] / "logs" / "api_counter.json"

_total: dict[str, int] = defaultdict(int)
_daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
_last_called: dict[str, str] = {}
_errors: dict[str, int] = defaultdict(int)
_started_at: str = datetime.utcnow().isoformat()

_ALL_SOURCES = [
    "tradera",
    "blocket",
    "vinted",
    "serper_new_price",
    "serpapi_used",
    "serpapi_new_price",
    "vision_openai",
]

# How often to persist (every N increments)
_PERSIST_INTERVAL = 5
_increment_count = 0


def _load_from_disk() -> None:
    """Load persisted counters on module import."""
    global _started_at
    try:
        if _PERSIST_FILE.exists():
            data = json.loads(_PERSIST_FILE.read_text())
            _total.update(data.get("total", {}))
            for day, sources in data.get("daily", {}).items():
                _daily[day].update(sources)
            _last_called.update(data.get("last_called", {}))
            _errors.update(data.get("errors", {}))
            _started_at = data.get("started_at", _started_at)
    except Exception:
        pass  # Corrupt file — start fresh


def _save_to_disk() -> None:
    """Persist current state to JSON file."""
    try:
        _PERSIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "total": dict(_total),
            "daily": {k: dict(v) for k, v in _daily.items()},
            "last_called": dict(_last_called),
            "errors": dict(_errors),
            "started_at": _started_at,
        }
        _PERSIST_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


# Load on import
_load_from_disk()


def increment(source: str) -> None:
    global _increment_count
    with _lock:
        _total[source] += 1
        _daily[str(date.today())][source] += 1
        _last_called[source] = datetime.utcnow().isoformat()
        _increment_count += 1
        if _increment_count % _PERSIST_INTERVAL == 0:
            _save_to_disk()


def increment_error(source: str) -> None:
    with _lock:
        _errors[source] += 1
        _save_to_disk()


def get_stats() -> dict:
    with _lock:
        today_key = str(date.today())
        sources = {}
        total_all = 0
        for src in _ALL_SOURCES:
            total = _total.get(src, 0)
            errors = _errors.get(src, 0)
            total_all += total
            if total + errors > 0:
                success_rate = round(total / (total + errors) * 100)
            else:
                success_rate = None
            sources[src] = {
                "total_calls": total,
                "error_calls": errors,
                "success_rate_pct": success_rate,
                "last_called": _last_called.get(src),
                "today": _daily.get(today_key, {}).get(src, 0),
            }
        return {
            "sources": sources,
            "total_all_sources": total_all,
            "since": _started_at,
        }


def reset() -> None:
    with _lock:
        _total.clear()
        _daily.clear()
        _last_called.clear()
        _errors.clear()
        _save_to_disk()
