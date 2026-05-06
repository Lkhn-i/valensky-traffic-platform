from __future__ import annotations

from uuid import uuid4

from django.core.cache import caches
from django.db import connections
from django.db.utils import Error as DatabaseError


def check_database() -> tuple[bool, dict[str, str]]:
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError as exc:
        return False, {"status": "error", "detail": str(exc)}

    return True, {"status": "ok"}


def check_cache() -> tuple[bool, dict[str, str]]:
    cache = caches["default"]
    cache_key = f"healthcheck:{uuid4()}"

    try:
        cache.set(cache_key, "ok", timeout=5)
        value = cache.get(cache_key)
    except Exception as exc:  # pragma: no cover - backend specific
        return False, {"status": "error", "detail": str(exc)}

    if value != "ok":
        return False, {"status": "error", "detail": "Cache round-trip failed"}

    return True, {"status": "ok"}


def run_healthcheck() -> tuple[dict[str, object], bool]:
    db_ok, db_payload = check_database()
    cache_ok, cache_payload = check_cache()
    is_healthy = db_ok and cache_ok

    payload: dict[str, object] = {
        "status": "ok" if is_healthy else "error",
        "checks": {
            "database": db_payload,
            "cache": cache_payload,
        },
    }
    return payload, is_healthy
