"""Paths, model endpoints and index names.

Everything lives under the repository root (or ``CAMPUSSCOPE_HOME``):

    data/      notices, compiled notices, the benchmark and its gold facts (see data/README.md)
    outputs/   run records and summaries
    cache/     SQLite cache of every LLM reply and embedding (git-ignored)

Endpoints and keys are read from ``.env`` at the root, overridden by the process environment, and are
never written to any artifact.
"""
import os
from pathlib import Path

HOME = Path(os.getenv("CAMPUSSCOPE_HOME") or Path(__file__).resolve().parents[1])
DATA = HOME / "data"
OUT = HOME / "outputs"
CACHE = HOME / "cache"
for p in (DATA, OUT, CACHE):
    p.mkdir(parents=True, exist_ok=True)

# raw notice PDFs: input of scripts/prepare_corpus.py only (not distributed)
NOTICE_DIR = Path(os.getenv("CAMPUSSCOPE_NOTICE_DIR") or HOME / "notices_pdf")

CHUNK_COLLECTION = "campusscope_chunks"        # baselines: the deployed prototype's 600-character chunks
FACT_COLLECTION = "campusscope_facts"          # fact nodes of the evidence graph
PASSAGE_COLLECTION = "campusscope_passages"    # section passages with their inherited scope


def index_suffix(opt):
    """Collections are built once per option set that changes what the index holds, so an ablation never
    searches text or filters that still carry the component it removes. Options that act only at query
    time share the full index."""
    if opt is None:
        return ""
    s = ""
    if not opt.inherit_scope:
        s += "_noinh"
    if not opt.gazetteer:
        s += "_nogaz"
    if not opt.anchor_time:
        s += "_notime"
    return s


def collections_for(opt=None):
    s = index_suffix(opt)
    return FACT_COLLECTION + s, PASSAGE_COLLECTION + s


CORPUS_SINCE = "2023-01-01"             # notices compiled into the evidence graph
CAMPUS = {"zgc": "中关村校区", "tz": "通州校区"}
CAMPUS_WORDS = {"zgc": ("中关村",), "tz": ("通州", "潞城")}


def load_env():
    """``.env`` at the repository root, overridden by the process environment (Docker passes settings that way)."""
    cfg = {}
    f = HOME / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    cfg.update({k: v for k, v in os.environ.items() if v != ""})
    return cfg


ENV = load_env()


def _endpoint(base, key, model):
    return (ENV.get(base, ""), ENV.get(key) or "EMPTY", ENV.get(model, ""))


SYSTEM_MODEL = "deepseek"               # compiles the notices and answers for every system
MODELS = {
    # name -> (base_url, api_key, model id); all OpenAI-compatible, thinking disabled unless asked
    "deepseek": _endpoint("DEEPSEEK_BASE_URL", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"),
    # benchmark construction only (scripts/prepare_corpus.py, scripts/build_benchmark.py)
    "qwen": _endpoint("QWEN_BASE_URL", "QWEN_API_KEY", "QWEN_MODEL"),
    "bonsai": _endpoint("BONSAI_BASE_URL", "BONSAI_API_KEY", "BONSAI_MODEL"),
}
MODEL_LABEL = {"deepseek": "DeepSeek-V4.1-Flash", "qwen": "Qwen3-32B", "bonsai": "Bonsai-27B (ternary)"}
# how each endpoint turns thinking off / on
THINKING_OFF = {"deepseek": {"thinking": {"type": "disabled"}},
                "qwen": {"chat_template_kwargs": {"enable_thinking": False}},
                "bonsai": {"chat_template_kwargs": {"enable_thinking": False}}}
THINKING_ON = {"deepseek": {"thinking": {"type": "enabled"}},
               "qwen": {"chat_template_kwargs": {"enable_thinking": True}},
               "bonsai": {"chat_template_kwargs": {"enable_thinking": True}}}


def compiled_path(model=SYSTEM_MODEL):
    """Raw compiler output for every service notice (scripts/compile_graph.py)."""
    return DATA / f"compiled_{model}.jsonl"


EMBED = _endpoint("EMBEDDING_BASE_URL", "EMBEDDING_API_KEY", "EMBEDDING_MODEL")     # bge-large-zh-v1.5
EMBEDDING_DIM = int(ENV.get("EMBEDDING_DIM") or 1024)

MILVUS_URI = ENV.get("MILVUS_URI") or "http://localhost:19530"
MILVUS_TOKEN = ENV.get("MILVUS_TOKEN") or None
MILVUS_DB = ENV.get("MILVUS_DB") or None          # a database of its own when the Milvus instance is shared
