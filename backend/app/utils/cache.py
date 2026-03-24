import time
from typing import Any

_cache: dict[str, dict] = {}
CACHE_TTL = 3600  # 1 hour


def get_cached(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < CACHE_TTL:
        return entry["data"]
    return None


def set_cached(key: str, data: Any) -> None:
    _cache[key] = {"data": data, "ts": time.time()}
