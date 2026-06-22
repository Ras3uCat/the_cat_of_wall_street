import json
import time
from pathlib import Path
from config import CACHE_DIR, CACHE_TTL


def _path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def get(key: str, source: str) -> dict | None:
    """Return cached data if it exists and is within TTL, else None."""
    ttl = CACHE_TTL.get(source, 3600)
    p = _path(key)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text())
        age = time.time() - payload.get("_cached_at", 0)
        if age > ttl:
            return None
        return payload.get("data")
    except (json.JSONDecodeError, KeyError):
        return None


def set(key: str, data: dict) -> None:
    """Write data to cache with current timestamp."""
    payload = {"_cached_at": time.time(), "data": data}
    _path(key).write_text(json.dumps(payload, indent=2, default=str))


def cache_key(source: str, identifier: str = "") -> str:
    """Generate a cache key. identifier is ticker or date or empty for market-wide."""
    from datetime import date
    today = date.today().isoformat()
    parts = [source, identifier, today] if identifier else [source, today]
    return "_".join(p for p in parts if p)
