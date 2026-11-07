# Event protocol (POST /api/chat)

The one contract between backend and frontend. When it changes, change all four together:

- backend: `backend/app/services/agent_service.py` + `qa_service.py` produce the events, `routers/chat.py` frames them
- frontend: `frontend/src/types.ts` (`ChatEvent`) and `frontend/src/lib/events.ts` (`applyEvent`)
- contract test: `backend/tests/test_chat_stream.py`
- this document

## Request

```text
POST /api/chat
Content-Type: application/json

{"conversation": [{"role": "user", "text": "今天田径场几点开放？"}],
 "today": "2026-01-20", "campus": null, "model": "deepseek", "compare": true, "lang": "en"}
```

| field | meaning |
| --- | --- |
| `conversation` | the dialogue so far (1–20 turns, `user` / `assistant`); the last turn is the question |
| `today` | the visitor's "today" = the knowledge cutoff (notices published later are unknown) |
| `campus` | `zgc` / `tz` / `null`: the campus picked in the top bar, prepended as a user turn naming the campus |
| `compare` | also run the chunk-RAG baseline, in parallel |
| `lang` | `en` (default) adds English glosses (a separate call; never feeds back into the answer); `zh` does not. Error messages follow it |

## Frames

`text/event-stream`, one `data: {json}` line per event, ended by `data: [DONE]`. A quiet stream gets
`: keep-alive` comments every 5 s (clients ignore them).

```text
data: {"type": "open", "baseline": true}
data: {"type": "stage", "id": "plan", "status": "running", "data": {}}
data: {"type": "stage", "id": "plan", "status": "done", "ms": 12, "data": {"plan": {...}, "campus": null, ...}}
data: {"type": "baseline", "status": "running"}
...
data: {"type": "graph", "graph": {"notices": [...], "facts": [...], "edges": [...], ...}}
data: {"type": "used", "ids": ["b28eb1484c#44", ...], "mode": "enumerate", "passages": [...]}
data: {"type": "delta", "text": "B校区："}
...
data: {"type": "answer", "text": "B校区：…", "action": "enumerate", "rewritten": false}
data: {"type": "baseline", "status": "done", "text": "…", "ms": 2100}
data: {"type": "complete", "answer": "…", "action": "enumerate", "calls": 2, "latency": 1.3, "cached": true}
data: [DONE]
```

Try it: `curl -N -X POST http://localhost:8796/api/chat -H 'Content-Type: application/json' -d '{"conversation":[{"role":"user","text":"今天田径场几点开放？"}],"today":"2026-01-20"}'`

## Events

| type | when | payload | frontend |
| --- | --- | --- | --- |
| `open` | first | `baseline` | — |
| `status` | the backend is still warming up / indexing | `text: "warming"`, `stage` | "warming up" line |
| `stage` | a step starts / ends | `id` (plan, ground, target, apply, decide, write, verify), `status`, `ms`, `data` | trace panel |
| `graph` | after the applicability step | the evidence subgraph (below) | evidence graph |
| `used` | after the decision | facts licensed for the reply (`ids`), `mode`, `passages`, `revisedShown` | green ✓ on the graph |
| `delta` | while the writer streams | `text` (answer text increment) | appended to the bubble |
| `retry` | the model gateway is busy | `attempt` | "retrying" line |
| `answer` | the checked reply | `text`, `action` (answer / enumerate / assume / ask / history / abstain), `rewritten` | replaces the streamed text |
| `baseline` | the RAG baseline (parallel) | `status` running / done / error, `text`, `action`, `ms` | RAG card |
| `gloss` | `lang=en` | `target` main / baseline, `text` | italic English line |
| `complete` | **terminal** · success | `answer`, `action`, `rewritten`, `calls`, `latency`, `cached` | ends the turn |
| `error` | **terminal** · failure | `message` (generic; details only in the log) | error line |
| `[DONE]` | end of stream | — | closes the reader |

### `stage.data` per step

| id | data |
| --- | --- |
| `plan` | `plan` (entity, type, attr, target, query), `campus`, `campusHow` (stated / gazetteer), `cached` |
| `ground` | `hits` (retrieved facts), `candidates`, `entities`, `nEntities`, `specific`, `etype`, `degraded` (BM25 only) |
| `target` | `lo`, `hi`, `cycle` ([period, year] or null), `kind` (now / date / period) |
| `apply` | `branches` ({campus: n}), `revised`, `history`, `future`, `audience` |
| `decide` | `decision`, `costs` ({assume, enumerate, ask} or null), `best`, `prior`, `lam`, `beta`, `sizes`, `passages`, `degraded` |
| `write` | `nFacts`, `nPassages`, `nRevised`, `cached` |
| `verify` | `times` (clock times in the reply), `bad` (not in the evidence), `rewritten`, `fallback` |

### `graph`

`today`, `target` [lo, hi], `cycle`, `notices` [{id, title, pub, ptype, kind}], `facts` [{id, doc, entity, ekey,
attr, value, quote, campus, start, end, pub, ptype, cycle, path (heading path, root first), status (current /
revised / history / inactive / future), src (where campus / validity / audience came from), err (known extraction
error)}], `edges` [{kind rev|rec, src, dst, active, near}], `total`, `shown`, `keys`.

## Rules

1. One frame per event: `data: {json}\n\n`, `type` names the event, `ensure_ascii=False`.
2. **Exactly one terminal event** (`complete` or `error`), and it is the last one before `[DONE]`; a stream that
   closes without `[DONE]` is a dropped connection.
3. `graph` comes before the first `delta`; `answer` comes after the last `delta` and replaces the streamed text.
4. Errors are events, not status codes (HTTP 200 is out once the stream starts), with a generic message.
5. The visitor's "stop" closes the stream; the backend stops sending (the model call in flight finishes and is cached).
