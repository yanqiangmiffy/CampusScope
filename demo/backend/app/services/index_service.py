"""Builds the demo's Milvus collections from data/ if they are missing or incomplete.

Same units and schema as scripts/build_index.py (campusscope.index): the full graph's facts and passages,
and the deployed chunker's notice chunks for the RAG baseline. Vectors come from the embedding cache
(cache/llm_cache.sqlite holds every unit), then the endpoint, then zeros (those rows are found by
BM25 only; counted in STATE["index"]["zero_vectors"]). A restart finds the collections complete and
skips the build (Milvus keeps them in its named volumes).
"""
import time

from loguru import logger

from app import system  # noqa: F401
from app.services import retrieval
from app.services.runtime import STATE

from campusscope import search
from campusscope.config import CHUNK_COLLECTION
from campusscope.index import chunk_units, graph_units, insert
from campusscope.search import service


def wait_for_milvus(timeout: float = 300.0) -> None:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            if service(CHUNK_COLLECTION).healthy():
                return
        except Exception as e:  # noqa: BLE001  (the client cannot even connect yet)
            last = e
            search._services.pop(CHUNK_COLLECTION, None)
        time.sleep(3)
    raise RuntimeError(f"Milvus not reachable: {last}")


def plan() -> list[tuple[str, list[dict]]]:
    parts, _ = graph_units(None)
    return [(CHUNK_COLLECTION, chunk_units())] + parts


def ensure(recreate: bool = False) -> dict:
    idx = STATE["index"]
    idx["state"] = "checking"
    todo = plan()
    for coll, units in todo:
        stats = service(coll).get_stats()
        idx["collections"][coll] = dict(rows=stats["rows"], expected=len(units))
        if not recreate and stats["ready"] and stats["rows"] == len(units):
            service(coll).settle()            # a restart during a build: compact + index before serving
            continue
        idx["state"] = "building"
        logger.info("building {} ({} units)", coll, len(units))

        def progress(c, done, total):
            idx["progress"] = dict(collection=c, done=done, total=total)

        before = retrieval.COUNTS["zero"]
        stats = insert(coll, units, vectors=retrieval.cached_vectors, progress=progress)
        idx["collections"][coll] = dict(rows=stats["rows"], expected=len(units))
        idx["zero_vectors"] += retrieval.COUNTS["zero"] - before
    idx.update(state="ready", progress=None)
    if idx["zero_vectors"]:
        logger.warning("{} rows have no embedding (BM25 only)", idx["zero_vectors"])
    return idx
