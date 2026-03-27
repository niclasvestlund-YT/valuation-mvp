"""In-memory API call counter for admin dashboard.

Thread-safe. Counters reset on server restart.
"""

from collections import defaultdict
from datetime import date, datetime
import threading

_lock = threading.Lock()
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


def increment(source: str) -> None:
    with _lock:
        _total[source] += 1
        _daily[str(date.today())][source] += 1
        _last_called[source] = datetime.utcnow().isoformat()


def increment_error(source: str) -> None:
    with _lock:
        _errors[source] += 1


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
