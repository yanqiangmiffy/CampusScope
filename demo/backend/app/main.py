"""CampusScope demo API: FastAPI + server-sent events over the system in campusscope/.

Start-up runs in a background thread (the API answers /api/health at once): load the evidence graph,
wait for Milvus, build the collections if they are missing (from data/ and the embedding cache), load
the agents. A question asked meanwhile waits and says so ("status: warming").
"""
import sys
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app import system  # noqa: F401  (must run before campusscope is imported)
from app.config import get_settings
from app.deps import get_agents
from app.routers import chat, health
from app.services import index_service, retrieval
from app.services.runtime import STATE, fail, set_stage

from campusscope.graph import load_graph

settings = get_settings()
logger.remove()
logger.add(sys.stderr, level=settings.LOG_LEVEL)


def warmup() -> None:
    try:
        retrieval.install()
        # check the embedding endpoint now, not at the first question the cache cannot answer
        threading.Thread(target=retrieval.probe, daemon=True, name="embed-probe").start()
        set_stage("loading graph")
        _, STATE["stats"] = load_graph()
        set_stage("waiting for Milvus")
        index_service.wait_for_milvus()
        if settings.INGEST_ON_START:
            set_stage("indexing")
            index_service.ensure()
        set_stage("loading agents")
        get_agents(settings.MODEL)
        STATE.update(ready=True, stage="ready")
        logger.info("ready in {:.1f}s", time.time() - STATE["t0"])
    except Exception as e:  # noqa: BLE001
        logger.exception("warm-up failed")
        fail(f"{type(e).__name__}: {e}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=warmup, daemon=True, name="warmup").start()
    yield


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION,
              description="CampusScope demo: condition-aware campus service QA over the evidence graph (SSE)",
              lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(health.router)
app.include_router(chat.router)
