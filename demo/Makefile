# Common commands of the demo. Without make (Windows), copy the command lines.
.PHONY: help up up-server down logs ps restart dev-backend dev-frontend test lint build ingest reindex smoke

help:          ## list the commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

up:            ## start everything (Milvus, backend, frontend)
	docker compose up -d --build

up-server:     ## start backend + frontend on a server with a shared Milvus
	docker compose -f docker-compose.server.yml up -d --build

down:          ## stop (the Milvus volumes are kept)
	docker compose down

logs:          ## follow the backend log
	docker compose logs -f backend

ps:            ## container status
	docker compose ps

restart:       ## after editing ../.env (model endpoints)
	docker compose up -d backend

dev-backend:   ## backend on the host (needs `docker compose up -d milvus`)
	cd backend && uvicorn app.main:app --reload --port 8796

dev-frontend:  ## frontend dev server (Vite proxies /api to localhost:8796)
	cd frontend && npm run dev

test:          ## backend tests (no external service)
	cd backend && python -m pytest

lint:          ## ruff + type check + oxlint
	cd backend && ruff check .
	cd frontend && npm run typecheck && npm run lint

build:         ## frontend production build
	cd frontend && npm run build

ingest:        ## build the Milvus collections that are missing
	docker compose exec backend python -m app.scripts.ingest

reindex:       ## rebuild every collection (after the data or the embedder changed)
	docker compose exec backend python -m app.scripts.ingest --recreate

smoke:         ## wait until ready, ask the five scenarios, check the protocol
	python smoke/smoke.py
