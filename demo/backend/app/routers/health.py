"""GET /api/health (container HEALTHCHECK and the top bar) and GET /api/meta (scenarios, graph statistics).
Health answers 200 while warming up or degraded; the state is in the body."""
import time

from fastapi import APIRouter

from app.prompts.texts import SCENARIOS
from app.services import llm_probe, retrieval
from app.services.runtime import STATE

from campusscope.config import MODEL_LABEL, MODELS, SYSTEM_MODEL

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", summary="Readiness and degradations")
def health() -> dict:
    return dict(
        ready=STATE["ready"], stage=STATE["stage"], error=STATE["error"], uptime=round(time.time() - STATE["t0"], 1),
        index=STATE["index"],
        embedding=retrieval.status(),
        llm=dict(configured=bool(MODELS[SYSTEM_MODEL][0] and MODELS[SYSTEM_MODEL][2]),
                 reachable=llm_probe.reachable(SYSTEM_MODEL), model=MODEL_LABEL[SYSTEM_MODEL]),
    )


@router.get("/meta", summary="Scenarios, model and graph statistics")
def meta() -> dict:
    return dict(scenarios=SCENARIOS, models=[dict(id=SYSTEM_MODEL, label=MODEL_LABEL[SYSTEM_MODEL])], stats=STATE["stats"])
