# CampusScope demo

React · FastAPI · server-sent events · Milvus · Docker Compose

A visitor asks a campus-service question and watches every step of the agent stream in (plan → retrieve and
expand → target period → applicability → cost-sensitive decision → write → verify), reads the answer next to
the deployed RAG assistant's, and explores the condition-scoped evidence graph behind it. The interface is in
English by default (`?lang=zh` for Chinese). Questions are asked in Chinese, like the notices; every answer
gets an English gloss.

## Run (laptop or venue)

Needs `../data/` and `../cache/` (see [`../data/README.md`](../data/README.md)) and `../.env` with the model
endpoints (see [`../.env.example`](../.env.example)).

```bash
cd demo
docker compose up -d --build
```

Open <http://localhost:8795>. The first start waits for Milvus and builds the index (about two minutes; the top
bar shows the progress); later starts take a few seconds.

| Entry | Address |
| --- | --- |
| Demo | <http://localhost:8795> |
| API docs (Swagger, bound to 127.0.0.1) | <http://localhost:8796/docs> |
| Milvus (bound to 127.0.0.1; `scripts/` can use it) | `http://localhost:19531` |
| Milvus UI (optional) | `docker compose --profile tools up -d attu` → <http://localhost:8011> |
| Smoke test (five scenarios + protocol checks) | `python smoke/smoke.py` |

## Run on a server with a shared Milvus

`docker-compose.server.yml` starts only the backend and the frontend. The backend joins the Docker network of
the existing Milvus and keeps its collections in a database of its own (`campusscope`), so it never touches
another application's collections.

```bash
cd demo
cp .env.example .env      # FRONTEND_PORT, MILVUS_NETWORK, MILVUS_HOST, MILVUS_DB
docker compose -f docker-compose.server.yml up -d --build
```

Behind a reverse proxy, turn buffering off for `/api/` (`proxy_buffering off;`), or the agent trace arrives
all at once instead of step by step.

## URL parameters

| Parameter | Effect |
| --- | --- |
| `?lang=zh` | Chinese interface |
| `?d=2026-01-20` | "today" (the knowledge cutoff) |
| `?campus=zgc` / `?campus=tz` | the visitor's campus |
| `?compare=0` | hide the RAG baseline |
| `?q=今天田径场几点开放？&d=2026-01-20` | ask on load |

## When something is down

| What fails | What happens |
| --- | --- |
| Embedding endpoint slow or 502 | 8 s timeout, then a 60 s breaker: BM25-only retrieval, marked in the trace; switches back by itself. Cached queries keep hybrid retrieval |
| Chat model unreachable | The top bar says "model offline"; cached questions (all five scenarios) are still answered; new ones fail within seconds |
| Chat endpoint busy (503) | Up to four retries; the interface says "retrying" |
| RAG baseline fails | Only its card shows an error |

## The evidence graph

- Horizontal axis: publication time of the notices of the candidate facts (one column per notice). Lanes: the
  inherited campus. Bars: validity; ◆: publication date.
- Fact states: used in the answer (green ✓), currently applicable, revised (struck through), earlier cycle
  (purple), outside the target period, not yet published. Two extraction errors found by checking the source
  notice by hand are marked ⚠, with the source text in the fact drawer.
- Edges: *rev* (red, newer notice → the fact it revises; only the active one by default) and *rec* (purple,
  earlier cycle); hover or select a fact to see all of its edges.
- Drag "today": applicability is recomputed in the browser by the rules of `EvidenceGraph.status`; one click asks
  again on the new date.
- Click a fact: its inheritance chain (notice → headings → quote), each condition attached to the level that
  supplied it.
- "Graph walkthrough" in the top bar opens a step-by-step explanation page.

## Development

```bash
make test        # backend tests, no external service (cd backend && python -m pytest)
make lint        # ruff + tsc + oxlint
docker compose up -d milvus && make dev-backend   # backend on the host (8796), using the compose Milvus
make dev-frontend                                 # Vite (5173), /api proxied to 8796
make reindex     # rebuild the collections after the data or the embedder changed
```

Architecture and the event protocol: [docs/architecture.md](docs/architecture.md) ·
[docs/event-protocol.md](docs/event-protocol.md).

The decisions, costs and revision/history counts of S1–S4 are the ones recorded by
`scripts/run_scenarios.py` (`outputs/demo_scenarios.json`).
