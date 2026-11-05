"""Service wiring: lazy singletons, injected with Depends (tests replace them via app.dependency_overrides)."""
import threading
from functools import lru_cache

from app import system  # noqa: F401
from app.config import get_settings
from app.services.qa_service import QAService

_lock = threading.Lock()
_agents: dict[str, tuple] = {}


def get_agents(model: str = "deepseek") -> tuple:
    """(StreamingCampusScope, RAG) for a model; built once (loads the graph and the collection clients)."""
    with _lock:
        if model not in _agents:
            from app.services.agent_service import StreamingCampusScope

            from campusscope.baselines import RAG
            _agents[model] = (StreamingCampusScope(model), RAG(model))
        return _agents[model]


@lru_cache
def get_qa_service() -> QAService:
    return QAService(get_agents, get_settings())
