"""Persistent API usage and free-tier quota tracking for the admin dashboard.

Thread-safe. Persists to <project_root>/logs/api_counter.json on every
mutation so counters survive server restarts and crashes.
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from backend.app.core.config import settings

_lock = threading.Lock()

# parents: [0]=utils [1]=app [2]=backend [3]=project_root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PERSIST_FILE = _PROJECT_ROOT / "logs" / "api_counter.json"

_success_total: dict[str, int] = defaultdict(int)
_success_daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
_quota_total: dict[str, int] = defaultdict(int)
_quota_daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
_quota_monthly: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
_errors: dict[str, int] = defaultdict(int)
_blocked_total: dict[str, int] = defaultdict(int)
_blocked_daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
_blocked_monthly: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
_last_called: dict[str, str] = {}
_last_blocked: dict[str, str] = {}
_started_at: str = datetime.utcnow().isoformat()

_ALL_SOURCES = [
    "tradera",
    "blocket",
    "vinted",
    "google_cse",
    "google_vision_ocr",
    "serper_new_price",
    "serpapi_used",
    "serpapi_new_price",
    "vision_openai",
]


def _today_key() -> str:
    return str(date.today())


def _month_key() -> str:
    return _today_key()[:7]


def _quota_meta(source: str) -> dict[str, Any]:
    if source == "google_cse":
        return {
            "period": "day",
            "limit": max(settings.google_cse_free_daily_queries, 0),
            "unit_label": "queries",
        }
    if source == "google_vision_ocr":
        return {
            "period": "month",
            "limit": max(settings.google_vision_free_monthly_units, 0),
            "unit_label": "units",
        }
    if source == "tradera":
        return {
            "period": "day",
            "limit": max(settings.tradera_free_daily_calls, 0),
            "unit_label": "calls",
        }
    return {"period": None, "limit": 0, "unit_label": "calls"}


def _quota_managed_sources() -> set[str]:
    return {source for source in _ALL_SOURCES if _quota_meta(source)["period"] is not None}


def _load_nested_int_map(
    target: dict[str, dict[str, int]],
    payload: dict[str, dict[str, int]] | None,
) -> None:
    if not payload:
        return
    for outer_key, inner in payload.items():
        target[outer_key].update({key: int(value) for key, value in inner.items()})


def _build_monthly_from_daily(
    daily_map: dict[str, dict[str, int]],
) -> dict[str, dict[str, int]]:
    monthly: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for day_key, sources in daily_map.items():
        month = day_key[:7]
        for source, value in sources.items():
            monthly[month][source] += int(value)
    return monthly


def _load_from_disk() -> None:
    """Load persisted counters on module import."""
    global _started_at
    try:
        if not _PERSIST_FILE.exists():
            return

        data = json.loads(_PERSIST_FILE.read_text())

        # Backward compatibility with the old persisted shape.
        success_total = data.get("success_total") or data.get("total") or {}
        success_daily = data.get("success_daily") or data.get("daily") or {}
        quota_managed_sources = _quota_managed_sources()
        quota_total = data.get("quota_total") or {
            source: value for source, value in success_total.items() if source in quota_managed_sources
        }
        quota_daily = data.get("quota_daily") or {
            day_key: {
                source: value for source, value in sources.items() if source in quota_managed_sources
            }
            for day_key, sources in success_daily.items()
        }
        quota_monthly = data.get("quota_monthly")
        blocked_total = data.get("blocked_total") or {}
        blocked_daily = data.get("blocked_daily") or {}
        blocked_monthly = data.get("blocked_monthly")

        _success_total.update({key: int(value) for key, value in success_total.items()})
        _load_nested_int_map(_success_daily, success_daily)
        _quota_total.update({key: int(value) for key, value in quota_total.items()})
        _load_nested_int_map(_quota_daily, quota_daily)

        if quota_monthly:
            _load_nested_int_map(_quota_monthly, quota_monthly)
        else:
            _load_nested_int_map(_quota_monthly, _build_monthly_from_daily(_quota_daily))

        _errors.update({key: int(value) for key, value in (data.get("errors") or {}).items()})
        _blocked_total.update({key: int(value) for key, value in blocked_total.items()})
        _load_nested_int_map(_blocked_daily, blocked_daily)

        if blocked_monthly:
            _load_nested_int_map(_blocked_monthly, blocked_monthly)
        else:
            _load_nested_int_map(_blocked_monthly, _build_monthly_from_daily(_blocked_daily))

        _last_called.update(data.get("last_called", {}))
        _last_blocked.update(data.get("last_blocked", {}))
        _started_at = data.get("started_at", _started_at)
    except Exception:
        pass  # Corrupt file — start fresh


def _save_to_disk() -> None:
    """Persist current state to JSON file. Called on every mutation."""
    try:
        _PERSIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": 2,
            "success_total": dict(_success_total),
            "success_daily": {key: dict(value) for key, value in _success_daily.items()},
            "quota_total": dict(_quota_total),
            "quota_daily": {key: dict(value) for key, value in _quota_daily.items()},
            "quota_monthly": {key: dict(value) for key, value in _quota_monthly.items()},
            "errors": dict(_errors),
            "blocked_total": dict(_blocked_total),
            "blocked_daily": {key: dict(value) for key, value in _blocked_daily.items()},
            "blocked_monthly": {key: dict(value) for key, value in _blocked_monthly.items()},
            "last_called": dict(_last_called),
            "last_blocked": dict(_last_blocked),
            "started_at": _started_at,
        }
        _PERSIST_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def _quota_used_for_period(source: str, period: str | None) -> int:
    if period == "day":
        return int(_quota_daily.get(_today_key(), {}).get(source, 0))
    if period == "month":
        return int(_quota_monthly.get(_month_key(), {}).get(source, 0))
    return 0


def get_persist_path() -> Path:
    """Return the persist file path (for testing)."""
    return _PERSIST_FILE


def reserve_quota(source: str, *, amount: int = 1) -> dict[str, Any]:
    """Reserve usage against the source free-tier budget before an API call.

    This is intentionally conservative: once a request is about to hit a paid
    provider, we count it against the free-tier budget immediately so
    concurrent calls cannot overspend the quota.
    """
    with _lock:
        meta = _quota_meta(source)
        limit = meta["limit"]
        period = meta["period"]
        now = datetime.utcnow().isoformat()

        if not period or limit <= 0:
            return {
                "allowed": True,
                "quota_limit": None,
                "quota_period": None,
                "quota_used": None,
                "quota_remaining": None,
                "quota_unit_label": meta["unit_label"],
            }

        current_used = _quota_used_for_period(source, period)
        if current_used + amount > limit:
            _blocked_total[source] += 1
            _blocked_daily[_today_key()][source] += 1
            _blocked_monthly[_month_key()][source] += 1
            _last_blocked[source] = now
            _save_to_disk()
            return {
                "allowed": False,
                "quota_limit": limit,
                "quota_period": period,
                "quota_used": current_used,
                "quota_remaining": max(limit - current_used, 0),
                "quota_unit_label": meta["unit_label"],
            }

        _quota_total[source] += amount
        _quota_daily[_today_key()][source] += amount
        _quota_monthly[_month_key()][source] += amount
        _last_called[source] = now
        _save_to_disk()
        return {
            "allowed": True,
            "quota_limit": limit,
            "quota_period": period,
            "quota_used": current_used + amount,
            "quota_remaining": max(limit - current_used - amount, 0),
            "quota_unit_label": meta["unit_label"],
        }


# Load on import
_load_from_disk()


def increment(source: str, *, amount: int = 1) -> None:
    with _lock:
        _success_total[source] += amount
        _success_daily[_today_key()][source] += amount
        _last_called[source] = datetime.utcnow().isoformat()
        _save_to_disk()


def increment_error(source: str, *, amount: int = 1) -> None:
    with _lock:
        _errors[source] += amount
        _save_to_disk()


def get_stats() -> dict[str, Any]:
    with _lock:
        today_key = _today_key()
        month_key = _month_key()
        sources: dict[str, dict[str, Any]] = {}
        total_all = 0
        quota_total_all = 0

        for source in _ALL_SOURCES:
            success_total = int(_success_total.get(source, 0))
            error_total = int(_errors.get(source, 0))
            total_all += success_total

            quota_total = int(_quota_total.get(source, 0))
            quota_today = int(_quota_daily.get(today_key, {}).get(source, 0))
            quota_this_month = int(_quota_monthly.get(month_key, {}).get(source, 0))
            quota_total_all += quota_total

            meta = _quota_meta(source)
            quota_period = meta["period"]
            quota_limit = meta["limit"] if meta["limit"] > 0 and quota_period else None
            quota_used = _quota_used_for_period(source, quota_period)
            quota_remaining = max(quota_limit - quota_used, 0) if quota_limit is not None else None

            if success_total + error_total > 0:
                success_rate = round(success_total / (success_total + error_total) * 100)
            else:
                success_rate = None

            sources[source] = {
                "total_calls": success_total,
                "error_calls": error_total,
                "success_rate_pct": success_rate,
                "last_called": _last_called.get(source),
                "last_blocked": _last_blocked.get(source),
                "today": int(_success_daily.get(today_key, {}).get(source, 0)),
                "quota_total": quota_total,
                "quota_today": quota_today,
                "quota_this_month": quota_this_month,
                "blocked_total": int(_blocked_total.get(source, 0)),
                "blocked_today": int(_blocked_daily.get(today_key, {}).get(source, 0)),
                "blocked_this_month": int(_blocked_monthly.get(month_key, {}).get(source, 0)),
                "quota_period": quota_period,
                "quota_limit": quota_limit,
                "quota_used": quota_used if quota_limit is not None else None,
                "quota_remaining": quota_remaining,
                "quota_exhausted": quota_limit is not None and quota_remaining == 0,
                "quota_unit_label": meta["unit_label"],
                "quota_window": today_key if quota_period == "day" else month_key if quota_period == "month" else None,
            }

        return {
            "sources": sources,
            "total_all_sources": total_all,
            "total_quota_units_all_sources": quota_total_all,
            "since": _started_at,
            "today": today_key,
            "current_month": month_key,
        }


def reset(scope: str = "all") -> None:
    """Reset counters.

    scope="period" clears the currently active day/month budget windows only.
    scope="all" clears everything, including lifetime success/error totals.
    """
    global _started_at
    with _lock:
        if scope == "period":
            current_day = _today_key()
            current_month = _month_key()
            _quota_daily.pop(current_day, None)
            _quota_monthly.pop(current_month, None)
            _blocked_daily.pop(current_day, None)
            _blocked_monthly.pop(current_month, None)
            _last_blocked.clear()
            _save_to_disk()
            return

        _success_total.clear()
        _success_daily.clear()
        _quota_total.clear()
        _quota_daily.clear()
        _quota_monthly.clear()
        _last_called.clear()
        _last_blocked.clear()
        _errors.clear()
        _blocked_total.clear()
        _blocked_daily.clear()
        _blocked_monthly.clear()
        _started_at = datetime.utcnow().isoformat()
        _save_to_disk()
