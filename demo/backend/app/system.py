"""Loads the system (the `campusscope` package at the repository root) for the demo. Import this module
before anything from campusscope.

The demo does not copy the system: the image contains campusscope/ and data/ (docker-compose.yml,
additional build contexts), so the answers are the paper's. Before campusscope reads its configuration
this module:
  * points it at CAMPUSSCOPE_HOME (the repository root) and at the demo's Milvus;
  * rewrites endpoints written for the host (localhost / 127.0.0.1) to HOST_ALIAS inside Docker.
"""
import os
import re
import sys

from app.config import get_settings

ENDPOINT_KEYS = ("DEEPSEEK_BASE_URL", "EMBEDDING_BASE_URL", "QWEN_BASE_URL", "BONSAI_BASE_URL")


def rewrite_host(url: str, alias: str) -> str:
    if not alias or not url:
        return url
    return re.sub(r"//(localhost|127\.0\.0\.1|0\.0\.0\.0)(?=[:/]|$)", f"//{alias}", url)


def _env_file_values(path) -> dict[str, str]:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def prepare_environment() -> None:
    s = get_settings()
    os.environ["CAMPUSSCOPE_HOME"] = str(s.home)
    os.environ["MILVUS_URI"] = s.MILVUS_URI
    if s.HOST_ALIAS:
        file_env = _env_file_values(s.home / ".env")
        for k in ENDPOINT_KEYS:
            v = os.environ.get(k) or file_env.get(k)
            if v:
                os.environ[k] = rewrite_host(v, s.HOST_ALIAS)
    root = str(s.home)
    if root not in sys.path:
        sys.path.insert(0, root)


prepare_environment()

import campusscope.config  # noqa: E402,F401  (reads the environment prepared above)
