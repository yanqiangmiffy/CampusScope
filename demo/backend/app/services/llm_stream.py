"""Token streaming for the writer, sharing the system's SQLite cache.

The cache key is the one `campusscope.llm.chat` uses, so a reply the paper's runs already produced is
replayed (typed out at reading speed) and a new reply streamed from the endpoint is stored for them.
"""
import hashlib
import json
import random
import re
import time
from collections.abc import Iterator
from typing import Any

from openai import APIConnectionError

from app import system  # noqa: F401

from campusscope import config
from campusscope.llm import _client, _get, _put

TYPE_DELAY = 0.012          # seconds per chunk when replaying a cached reply
TYPE_CHUNK = 2              # characters per chunk


def cache_key(messages, model, max_tokens, temperature=0.0):
    _, _, model_id = config.MODELS[model]
    req = dict(model=model_id, messages=messages, max_tokens=max_tokens, temperature=temperature)
    return req, hashlib.sha256(json.dumps(req, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def stream_chat(messages, model=config.SYSTEM_MODEL, max_tokens=400, tag="demo", retries=4) -> Iterator[tuple[str, Any]]:
    """Yields ("delta", text) while the reply arrives, ("retry", attempt) when the endpoint is busy,
    and finally ("done", rec) with rec = dict(content, latency, cached, usage)."""
    req, key = cache_key(messages, model, max_tokens)
    hit = _get("chat", key)
    if hit is not None:
        rec = json.loads(hit)
        text = rec.get("content", "")
        for i in range(0, len(text), TYPE_CHUNK):
            yield "delta", text[i:i + TYPE_CHUNK]
            time.sleep(TYPE_DELAY)
        rec["cached"] = True
        yield "done", rec
        return
    t0 = time.perf_counter()
    parts, usage = [], dict(prompt=0, completion=0)
    for attempt in range(retries):
        try:
            stream = _client(model).chat.completions.create(
                **req, top_p=1, extra_body=config.THINKING_OFF[model], stream=True,
                stream_options={"include_usage": True})
            for chunk in stream:
                if getattr(chunk, "usage", None):
                    usage = dict(prompt=chunk.usage.prompt_tokens or 0, completion=chunk.usage.completion_tokens or 0)
                if not chunk.choices:
                    continue
                d = chunk.choices[0].delta.content or ""
                if d:
                    parts.append(d)
                    yield "delta", d
            break
        except APIConnectionError:  # refused / unreachable: one quick retry, then give up (do not wait ~20 s)
            if parts or attempt >= 1:
                raise
            yield "retry", attempt + 1
            time.sleep(1.0)
            continue
        except Exception:  # noqa: BLE001  (a busy endpoint answers 503: retry with back-off)
            if parts or attempt == retries - 1:
                raise
            yield "retry", attempt + 1
            time.sleep(min(20, 2 * 2 ** attempt) + random.random())
    content = re.sub(r"<think>.*?</think>", "", "".join(parts), flags=re.S).strip()
    rec = dict(content=content, latency=time.perf_counter() - t0, usage=usage, model=model)
    _put("chat", key, json.dumps(rec, ensure_ascii=False), model, tag)
    rec["cached"] = False
    yield "done", rec


class AnswerStream:
    """Incrementally decodes the "answer" string of a JSON reply ({"answer": "..."}) as it streams,
    so the visitor reads the answer while the model is still writing it."""
    OPEN = re.compile(r'"answer"\s*:\s*"')
    ESC = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}

    def __init__(self):
        self.buf, self.pos, self.closed = "", None, False

    def feed(self, delta: str) -> str:
        self.buf += delta
        if self.closed:
            return ""
        if self.pos is None:
            m = self.OPEN.search(self.buf)
            if not m:
                return ""
            self.pos = m.end()
        out, i, b = [], self.pos, self.buf
        while i < len(b):
            c = b[i]
            if c == '"':
                self.closed = True
                i += 1
                break
            if c == "\\":
                if i + 1 >= len(b):
                    break
                e = b[i + 1]
                if e == "u":
                    if i + 6 > len(b):
                        break
                    try:
                        out.append(chr(int(b[i + 2:i + 6], 16)))
                    except ValueError:
                        pass
                    i += 6
                    continue
                out.append(self.ESC.get(e, e))
                i += 2
                continue
            out.append(c)
            i += 1
        self.pos = i
        return "".join(out)
