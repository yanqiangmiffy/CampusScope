"""Contract of POST /api/chat (docs/event-protocol.md), with fake agents:
one `data:` frame per event, `open` first, exactly one terminal event (complete | error) and it is
the last one before `data: [DONE]`; the baseline runs alongside; errors carry only a generic message."""
import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.deps import get_qa_service
from app.main import app
from app.services.qa_service import ERRORS, GENERIC_ERROR, QAService
from app.services.runtime import STATE


class FakeAgent:
    def __init__(self, fail=False):
        self.fail = fail

    def stream(self, conv, today):
        yield dict(type="stage", id="plan", status="running", data={})
        if self.fail:
            raise RuntimeError("model gateway exploded with a secret URL http://10.0.0.1")
        yield dict(type="stage", id="plan", status="done", ms=3, data={"plan": {"entity": "田径场"}})
        yield dict(type="graph", graph={"facts": [], "edges": [], "notices": []})
        yield dict(type="used", ids=["x#1"], mode="enumerate", passages=[])
        yield dict(type="delta", text="通州")
        yield dict(type="delta", text="校区")
        yield dict(type="answer", text="通州校区：8:00—22:00", action="enumerate", rewritten=False)
        yield dict(type="summary", calls=2, latency=1.2, cached=True)


class FakeRAG:
    def respond(self, conv, today):
        return dict(text="资料中没有找到。", action="answer", trace={"retrieved": ["chunk.a.0"]})


def frames(text):
    out = []
    for block in text.split("\n\n"):
        block = block.strip()
        if block.startswith("data:"):
            body = block[5:].strip()
            out.append(body if body == "[DONE]" else json.loads(body))
    return out


@pytest.fixture(autouse=True)
def fake_gloss(monkeypatch):
    from app.services import qa_service
    monkeypatch.setattr(qa_service, "gloss", lambda text, model: f"EN: {text}")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setitem(STATE, "ready", True)
    monkeypatch.setitem(STATE, "error", None)

    def use(fail=False):
        qa = QAService(lambda model: (FakeAgent(fail), FakeRAG()), get_settings())
        app.dependency_overrides[get_qa_service] = lambda: qa
        return TestClient(app)

    yield use
    app.dependency_overrides.clear()


BODY = {"conversation": [{"role": "user", "text": "今天田径场几点开放？"}], "today": "2026-01-20"}


def test_stream_contract(client):
    r = client().post("/api/chat", json=BODY)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    fs = frames(r.text)
    assert fs[-1] == "[DONE]"
    events = fs[:-1]
    assert events[0]["type"] == "open"
    terminal = [e for e in events if e["type"] in ("complete", "error")]
    assert len(terminal) == 1 and events[-1] is terminal[0]
    done = terminal[0]
    assert done["type"] == "complete" and done["answer"] == "通州校区：8:00—22:00" and done["calls"] == 2
    types = [e["type"] for e in events]
    assert types.index("graph") < types.index("delta") < types.index("answer")
    assert any(e["type"] == "baseline" and e["status"] == "done" for e in events)
    assert "summary" not in types


def test_campus_from_top_bar_becomes_a_user_turn():
    from app.schemas.chat import ChatRequest
    conv = QAService.conversation(ChatRequest(**BODY, campus="tz"))
    assert conv[0] == {"role": "user", "text": "（我在通州校区）"}
    said = ChatRequest(conversation=[{"role": "user", "text": "中关村校区田径场几点开？"}], today="2026-01-20", campus="tz")
    assert len(QAService.conversation(said)) == 1


def test_error_is_terminal_and_generic(client):
    fs = frames(client(fail=True).post("/api/chat", json={**BODY, "compare": False}).text)
    events = fs[:-1]
    assert events[-1] == {"type": "error", "message": GENERIC_ERROR}
    assert "10.0.0.1" not in json.dumps(events)


def test_error_follows_the_page_language(client):
    fs = frames(client(fail=True).post("/api/chat", json={**BODY, "compare": False, "lang": "zh"}).text)
    assert fs[:-1][-1] == {"type": "error", "message": ERRORS["zh"]["generic"]}


def test_english_glosses_by_default(client):
    events = frames(client().post("/api/chat", json=BODY).text)[:-1]
    glosses = {e["target"]: e["text"] for e in events if e["type"] == "gloss"}
    assert glosses == {"main": "EN: 通州校区：8:00—22:00", "baseline": "EN: 资料中没有找到。"}
    zh = frames(client().post("/api/chat", json={**BODY, "lang": "zh"}).text)[:-1]
    assert not any(e["type"] == "gloss" for e in zh)


def test_a_failing_gloss_does_not_lose_the_answer(client, monkeypatch):
    from app.services import qa_service

    def boom(text, model):
        raise RuntimeError("model endpoint down")
    monkeypatch.setattr(qa_service, "gloss", boom)
    events = frames(client().post("/api/chat", json=BODY).text)[:-1]
    assert events[-1]["type"] == "complete" and not any(e["type"] == "gloss" for e in events)


def test_english_is_the_default_language():
    from app.schemas.chat import ChatRequest
    assert ChatRequest(**BODY).lang == "en" and ChatRequest(**BODY).model == "deepseek"


def test_rejects_bad_requests(client):
    c = client()
    assert c.post("/api/chat", json={**BODY, "today": "20260120"}).status_code == 422
    assert c.post("/api/chat", json={**BODY, "campus": "mars"}).status_code == 422
    assert c.post("/api/chat", json={"conversation": [], "today": "2026-01-20"}).status_code == 422
