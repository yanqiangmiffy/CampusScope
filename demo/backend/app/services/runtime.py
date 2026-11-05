"""Readiness of the demo (shown by /api/health and the top bar). Written by the warm-up thread only."""
import time

STATE: dict = dict(
    ready=False,
    stage="starting",            # starting -> loading graph -> waiting for Milvus -> indexing -> loading agents -> ready
    error=None,
    t0=time.time(),
    stats=None,                  # graph statistics (campusscope.graph.load_graph)
    index=dict(state="pending", collections={}, progress=None, zero_vectors=0),
)


def set_stage(stage: str) -> None:
    STATE["stage"] = stage


def fail(err: str) -> None:
    STATE.update(error=err, stage="error")
