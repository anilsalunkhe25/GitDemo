"""Minimal in-memory sliding-window rate limiter for sensitive endpoints."""
import threading
import time
from functools import wraps

from flask import current_app, jsonify, request

_BUCKETS: dict[str, list[float]] = {}
_LOCK = threading.Lock()


def rate_limit(limit: int | None = None, window_seconds: int | None = None):
    """Limit requests per client IP within a rolling window."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            cfg = current_app.config
            max_calls = limit or cfg["LOGIN_RATE_LIMIT"]
            window = window_seconds or cfg["LOGIN_RATE_WINDOW_SECONDS"]
            key = f"{request.remote_addr}:{request.path}"
            now = time.time()
            with _LOCK:
                hits = [t for t in _BUCKETS.get(key, []) if now - t < window]
                if len(hits) >= max_calls:
                    resp = jsonify({
                        "success": False,
                        "message": "Too many attempts. Please try again later.",
                        "error": "rate_limited",
                    })
                    resp.status_code = 429
                    return resp
                hits.append(now)
                _BUCKETS[key] = hits
            return fn(*args, **kwargs)

        return wrapper

    return decorator
