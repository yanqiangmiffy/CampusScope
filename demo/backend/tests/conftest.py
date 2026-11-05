"""Test fixtures: no external service (no Milvus, LLM or embedding endpoint).

The system is imported from the repository root (app.system); the evidence graph is built from data/ on
the local disk, which needs no service (tests that need it are skipped without data/). The QA flow is
tested with fake agents.
"""
import os

# the API must never try to start its warm-up (Milvus) in tests; TestClient is used without `with`
os.environ.setdefault("INGEST_ON_START", "false")
os.environ.setdefault("MILVUS_URI", "http://127.0.0.1:1")

import pytest

from app import system  # noqa: F401


@pytest.fixture(scope="session")
def graph():
    from campusscope.config import DATA, compiled_path
    if not (DATA / "notices.jsonl").exists() or not compiled_path().exists():
        pytest.skip("needs data/notices.jsonl and data/compiled_deepseek.jsonl")
    from campusscope.graph import load_graph
    g, _ = load_graph()
    return g
