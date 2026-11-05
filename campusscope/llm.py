"""Cached clients for the OpenAI-compatible chat models and the bge embedder.

Every request is cached in SQLite (cache/llm_cache.sqlite) by the hash of (model id, messages, max_tokens,
temperature), so every reported number can be traced to a stored response and a rerun costs nothing.
"""
import hashlib
import json
import random
import re
import sqlite3
import threading
import time

from openai import OpenAI

from .config import CACHE, EMBED, MODELS, SYSTEM_MODEL, THINKING_OFF, THINKING_ON

_DB = CACHE / "llm_cache.sqlite"
_lock = threading.Lock()
_conn = sqlite3.connect(_DB, check_same_thread=False)
_conn.execute("create table if not exists chat (key text primary key, model text, tag text, response text)")
_conn.execute("create table if not exists emb (key text primary key, vec text)")
_conn.commit()
_clients = {}
STATS = {"calls": 0, "cached": 0, "prompt_tokens": 0, "completion_tokens": 0, "errors": 0}


def _client(model):
    if model not in _clients:
        base, key, _ = MODELS[model]
        _clients[model] = OpenAI(base_url=base, api_key=key or "EMPTY", timeout=900 if model == "bonsai" else 300)
    return _clients[model]


def _get(table, key):
    with _lock:
        row = _conn.execute(f"select {'response' if table == 'chat' else 'vec'} from {table} where key=?", (key,)).fetchone()
    return row[0] if row else None


def _put(table, key, value, model="", tag=""):
    with _lock:
        if table == "chat":
            _conn.execute("insert or replace into chat values (?,?,?,?)", (key, model, tag, value))
        else:
            _conn.execute("insert or replace into emb values (?,?)", (key, value))
        _conn.commit()


def chat(messages, model=SYSTEM_MODEL, max_tokens=1024, temperature=0.0, tag="chat", retries=8, thinking=False):
    """Returns dict(content, latency, cached, usage). Temperature 0, thinking disabled unless asked
    (a thinking request gets its own cache key)."""
    _, _, model_id = MODELS[model]
    req = dict(model=model_id, messages=messages, max_tokens=max_tokens, temperature=temperature)
    key_req = dict(req, thinking=True) if thinking else req
    key = hashlib.sha256(json.dumps(key_req, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    hit = _get("chat", key)
    if hit is not None:
        with _lock:
            STATS["cached"] += 1
        rec = json.loads(hit)
        rec["cached"] = True
        return rec
    t0 = time.perf_counter()
    for attempt in range(retries):
        try:
            r = _client(model).chat.completions.create(**req, top_p=1,
                                                   extra_body=(THINKING_ON if thinking else THINKING_OFF)[model])
            break
        except Exception:  # noqa: BLE001  (busy endpoints answer 503: retry with back-off)
            if attempt == retries - 1:
                with _lock:
                    STATS["errors"] += 1
                raise
            time.sleep(min(60, 3 * 2 ** attempt) + random.random() * 2)
    content = r.choices[0].message.content or ""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    usage = dict(prompt=getattr(r.usage, "prompt_tokens", 0), completion=getattr(r.usage, "completion_tokens", 0))
    rec = dict(content=content, latency=time.perf_counter() - t0, usage=usage, model=model)
    if thinking:
        rec["thinking"] = True
    _put("chat", key, json.dumps(rec, ensure_ascii=False), model, tag)
    with _lock:
        STATS["calls"] += 1
        STATS["prompt_tokens"] += usage["prompt"]
        STATS["completion_tokens"] += usage["completion"]
    rec["cached"] = False
    return rec


def parse_json(text):
    """Lenient JSON extraction from a model reply (code fences, leading prose, trailing text)."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        v = json.loads(t)
        return v
    except ValueError:
        pass
    for opener in ("{", "["):
        start = t.find(opener)
        if start >= 0:
            try:
                obj, _ = json.JSONDecoder().raw_decode(t[start:])
                return obj
            except ValueError:
                continue
    return {}


_emb_client = None


def embed(texts, batch=32):
    """bge-large-zh-v1.5 vectors, cached by text hash."""
    global _emb_client
    if _emb_client is None:
        _emb_client = OpenAI(base_url=EMBED[0], api_key=EMBED[1] or "EMPTY", timeout=120)
    keys = [hashlib.sha256(t.encode("utf8")).hexdigest() for t in texts]
    out = [None] * len(texts)
    todo = []
    for i, k in enumerate(keys):
        hit = _get("emb", k)
        if hit is not None:
            out[i] = json.loads(hit)
        else:
            todo.append(i)
    for s in range(0, len(todo), batch):
        idx = todo[s:s + batch]
        for attempt in range(6):
            try:
                r = _emb_client.embeddings.create(model=EMBED[2], input=[texts[i] for i in idx])
                break
            except Exception:  # noqa: BLE001  (a restarting embedding endpoint answers 502: retry)
                if attempt == 5:
                    raise
                time.sleep(min(30, 2 ** attempt) + random.random())
        for i, d in zip(idx, sorted(r.data, key=lambda d: d.index)):
            out[i] = d.embedding
            _put("emb", keys[i], json.dumps(d.embedding))
    return out


def stats():
    return dict(STATS)
