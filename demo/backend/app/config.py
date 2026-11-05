"""Demo settings: code defaults -> backend/.env -> environment (compose `environment` / `env_file`).

The model endpoints are not settings of the demo: they belong to the system (.env at the repository root,
read by campusscope.config; compose passes the same file to this container). The demo only decides how to
reach them from inside Docker, where Milvus is, and how patient to be.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]          # the repository root when run from the checkout


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore")

    APP_NAME: str = "CampusScope demo"
    APP_VERSION: str = "1.0"
    LOG_LEVEL: str = "INFO"

    # the system's package (campusscope/), its data (data/) and its cache (cache/)
    CAMPUSSCOPE_HOME: str = str(ROOT)
    # the demo's own Milvus (docker compose); 19531 on the host so it never clashes with another Milvus
    MILVUS_URI: str = "http://localhost:19531"
    # inside Docker, endpoints written for the host (localhost / 127.0.0.1) are rewritten to this name
    HOST_ALIAS: str = ""
    MODEL: str = "deepseek"

    # build the collections at start-up if they are missing (from data/ + the embedding cache)
    INGEST_ON_START: bool = True
    # embedding endpoint: one try with this timeout, then BM25 only for EMBED_BREAK_S seconds
    EMBED_TIMEOUT: float = 8.0
    EMBED_BREAK_S: int = 60
    # nodes of the evidence subgraph sent to the browser
    MAX_GRAPH_NODES: int = 90
    # seconds between keep-alive comments on a quiet stream
    KEEPALIVE_S: float = 5.0

    CORS_ORIGINS: str = "*"

    @property
    def home(self) -> Path:
        return Path(self.CAMPUSSCOPE_HOME)

    @property
    def cors_origin_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
