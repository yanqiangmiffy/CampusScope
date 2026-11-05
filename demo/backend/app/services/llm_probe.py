"""Is the chat model's endpoint reachable? A TCP connect, cached for a few seconds.

Used to fail fast when the endpoint is not running (the system's own client retries with back-off,
which makes sense for a busy gateway, not for one that refuses connections) and by /api/health.
Cached replies never need the endpoint, so the demo keeps answering the questions it has seen.
"""
import socket
import threading
import time
from urllib.parse import urlparse

from app import system  # noqa: F401

from campusscope import config

TTL_S = 15.0
_cache: dict[str, tuple[float, bool | None]] = {}
_lock = threading.Lock()


def reachable(model: str = config.SYSTEM_MODEL) -> bool | None:
    """True / False, or None when the model has no endpoint configured."""
    now = time.time()
    with _lock:
        hit = _cache.get(model)
        if hit and now - hit[0] < TTL_S:
            return hit[1]
    base = config.MODELS.get(model, ("", "", ""))[0]
    if not base:
        ok = None
    else:
        u = urlparse(base)
        port = u.port or (443 if u.scheme == "https" else 80)
        try:
            with socket.create_connection((u.hostname, port), timeout=1.5):
                ok = True
        except OSError:
            ok = False
    with _lock:
        _cache[model] = (now, ok)
    return ok


def retries(model: str = config.SYSTEM_MODEL, normal: int = 4) -> int:
    """How many times the system's client may try: one when the endpoint is known to be down."""
    return 1 if reachable(model) is False else normal
