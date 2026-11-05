"""Pure helpers: the incremental answer decoder, SSE frames, host rewriting, the embedding breaker."""
import json

from app.services import retrieval
from app.services.llm_stream import AnswerStream
from app.system import rewrite_host
from app.utils.sse import SSE_DONE, sse


def feed_all(parts):
    d = AnswerStream()
    return "".join(d.feed(p) for p in parts)


def test_answer_stream_decodes_across_chunks():
    reply = json.dumps({"answer": "通州校区：8:00—22:00\n\"正常\"开放"}, ensure_ascii=False)
    for size in (1, 2, 3, 7, len(reply)):
        parts = [reply[i:i + size] for i in range(0, len(reply), size)]
        assert feed_all(parts) == "通州校区：8:00—22:00\n\"正常\"开放"


def test_answer_stream_unicode_escapes_split():
    reply = json.dumps({"answer": "田径场"})          # ascii escapes: 田径场
    parts = [reply[i:i + 4] for i in range(0, len(reply), 4)]
    assert feed_all(parts) == "田径场"


def test_answer_stream_ignores_text_after_the_string():
    assert feed_all(['```json\n{"answer": "好"', ', "x": "不要"}```']) == "好"


def test_sse_frames():
    assert sse({"type": "delta", "text": "你好"}) == 'data: {"type": "delta", "text": "你好"}\n\n'
    assert sse({"type": "ping"}).startswith(":")
    assert SSE_DONE == "data: [DONE]\n\n"


def test_rewrite_host():
    alias = "host.docker.internal"
    assert rewrite_host("http://127.0.0.1:7864/v1", alias) == "http://host.docker.internal:7864/v1"
    assert rewrite_host("http://localhost/v1", alias) == "http://host.docker.internal/v1"
    assert rewrite_host("https://api.example.com/v1", alias) == "https://api.example.com/v1"
    assert rewrite_host("http://127.0.0.1:7864/v1", "") == "http://127.0.0.1:7864/v1"


def test_breaker_opens_and_falls_back(monkeypatch):
    calls = []

    class Broken:
        class embeddings:  # noqa: N801
            @staticmethod
            def create(**_):
                calls.append(1)
                raise RuntimeError("502")

    monkeypatch.setattr(retrieval.llm, "_get", lambda table, key: None)
    monkeypatch.setattr(retrieval, "_endpoint", lambda: Broken)
    monkeypatch.setitem(retrieval.STATUS, "until", 0.0)
    assert retrieval.query_vector("一个没缓存的问题") is None
    assert retrieval.STATUS["state"] == "down"
    assert retrieval.query_vector("又一个") is None      # breaker open: no second call
    assert len(calls) == 1
    vecs = retrieval.cached_vectors(["a", "b"])
    assert len(vecs) == 2 and not any(vecs[0])          # zero vectors for index rows


def test_llm_probe_fails_fast_when_nothing_listens(monkeypatch):
    from app.services import llm_probe

    monkeypatch.setitem(llm_probe.config.MODELS, "probe", ("http://127.0.0.1:9/v1", "EMPTY", "m"))
    llm_probe._cache.pop("probe", None)
    assert llm_probe.reachable("probe") is False
    assert llm_probe.retries("probe") == 1
    monkeypatch.setitem(llm_probe.config.MODELS, "none", ("", "EMPTY", ""))
    assert llm_probe.reachable("none") is None and llm_probe.retries("none") == 4
