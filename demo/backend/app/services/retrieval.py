"""Keeps retrieval responsive when the embedding endpoint is down.

The system's `embed` retries six times with exponential back-off (the endpoint answered 502 after ~17 s
per try when the demo was written), so one question could hang for minutes. The demo:
  * reads the same embedding cache (cache/llm_cache.sqlite, keyed by the text);
  * otherwise calls the endpoint once with a short timeout;
  * on failure opens a breaker: for EMBED_BREAK_S seconds no call is made and the query embedder
    returns None, so campusscope.search searches BM25 only (and says so, search.bm25_only()).
Index building uses `cached_vectors`: cache, then the endpoint, then zero vectors (BM25-only rows).
"""
import hashlib
import json
import threading
import time

from loguru import logger
from openai import OpenAI

from app import system  # noqa: F401
from app.config import get_settings

from campusscope import config, llm, search

STATUS = dict(state="unknown", error=None, until=0.0, last_ok=None)
COUNTS = dict(zero=0)          # index rows that got a zero vector
_client = None
_lock = threading.Lock()


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def _endpoint():
    global _client
    with _lock:
        if _client is None and config.EMBED[0]:
            s = get_settings()
            _client = OpenAI(base_url=config.EMBED[0], api_key=config.EMBED[1] or "EMPTY",
                             timeout=s.EMBED_TIMEOUT, max_retries=0)
        return _client


def _call(texts: list[str]) -> list[list[float]] | None:
    """One request for `texts`, or None (breaker open, endpoint not configured, or the call failed)."""
    if time.time() < STATUS["until"]:
        return None
    client = _endpoint()
    if client is None:
        STATUS.update(state="off", error="EMBEDDING_BASE_URL not set")
        return None
    try:
        r = client.embeddings.create(model=config.EMBED[2], input=texts)
    except Exception as e:  # noqa: BLE001
        s = get_settings()
        STATUS.update(state="down", error=f"{type(e).__name__}: {str(e)[:120]}", until=time.time() + s.EMBED_BREAK_S)
        logger.warning("embedding endpoint failed ({}); BM25 only for {}s", STATUS["error"], s.EMBED_BREAK_S)
        return None
    STATUS.update(state="ok", error=None, until=0.0, last_ok=time.time())
    vecs = [d.embedding for d in sorted(r.data, key=lambda d: d.index)]
    for t, v in zip(texts, vecs, strict=False):
        llm._put("emb", _key(t), json.dumps(v))
    return vecs


def query_vector(text: str) -> list[float] | None:
    hit = llm._get("emb", _key(text))
    if hit is not None:
        return json.loads(hit)
    out = _call([text])
    return out[0] if out else None


def cached_vectors(texts: list[str]) -> list[list[float]]:
    """Vectors for index rows: cache, then the endpoint, then zeros (counted in COUNTS["zero"])."""
    out: list = [None] * len(texts)
    miss = []
    for i, t in enumerate(texts):
        hit = llm._get("emb", _key(t))
        if hit is not None:
            out[i] = json.loads(hit)
        else:
            miss.append(i)
    if miss:
        got = _call([texts[i] for i in miss])
        for j, i in enumerate(miss):
            out[i] = got[j] if got else None
    zero = [0.0] * config.EMBEDDING_DIM
    for i, v in enumerate(out):
        if v is None:
            out[i] = zero
            COUNTS["zero"] += 1
    return out


def install() -> None:
    """Make the system's retrieval use the breaker (the paper's runs keep the default embedder)."""
    search.EMBEDDER = query_vector
