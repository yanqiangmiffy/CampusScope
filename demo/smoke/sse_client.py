"""A tiny SSE client for POST /api/chat (standard library only)."""
import json
import time
import urllib.request


def get_json(url: str, timeout: float = 5) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf8"))


def ask(base: str, question: str, today: str, campus=None, compare=True, lang="zh", timeout: float = 300):
    """Returns (events, seconds to the first stage event, total seconds, saw [DONE])."""
    body = json.dumps(dict(conversation=[dict(role="user", text=question)], today=today, campus=campus,
                           compare=compare, lang=lang)).encode()
    req = urllib.request.Request(f"{base}/api/chat", data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    first, events, done, buf = None, [], False, b""
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for chunk in iter(lambda: r.read1(4096), b""):
            buf += chunk
            while b"\n\n" in buf:
                block, buf = buf.split(b"\n\n", 1)
                for line in block.decode("utf8").splitlines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        done = True
                        continue
                    ev = json.loads(data)
                    if first is None and ev["type"] == "stage":
                        first = time.time() - t0
                    events.append(ev)
    return events, first, time.time() - t0, done


def terminal(events: list[dict]) -> dict | None:
    ends = [e for e in events if e["type"] in ("complete", "error")]
    return ends[-1] if ends else None
