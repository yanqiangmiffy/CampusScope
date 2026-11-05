"""Indexes the same notices in Milvus: as chunks (baselines) and as facts and passages (CampusScope),
the latter once per option set that changes what the index holds (Section 3.1).

    python scripts/build_index.py                       # chunks + every variant
    python scripts/build_index.py --only chunks,full    # what the main comparison and the demo need

All collections use the deployed prototype's schema (campusscope/search.py: bge dense + built-in BM25 with
the Chinese analyzer, RRF fusion) and the same text cleaning, and all cover exactly the compiled service
notices, so a comparison isolates the representation, not the corpus or the retriever. The units are built
by campusscope/index.py (also used by the demo on first start):
  * campusscope_chunks: the deployed chunker (600 characters, overlap 100) on cleaned text (baselines);
  * campusscope_facts<suffix>: one node per grounded fact, rendered with its scope and validity;
  * campusscope_passages<suffix>: section-aligned passages with their scope and heading path.
The ablated variants are rendered from the ablated graph (suffixes _noinh, _nogaz, _notime, _noinh_nogaz;
config.index_suffix). Also writes data/graph_stats.json (full graph). Embeddings are cached
(cache/llm_cache.sqlite), so with the released cache no embedding endpoint is needed.
"""
import argparse
import json

from campusscope.config import CHUNK_COLLECTION, DATA, MILVUS_DB, MILVUS_URI
from campusscope.graph import Options
from campusscope.index import chunk_units, graph_units, insert

VARIANTS = {
    "full": Options(),
    "no_inherit": Options(inherit_scope=False),
    "no_gazetteer": Options(gazetteer=False),
    "no_time": Options(anchor_time=False),
    "no_scope": Options(inherit_scope=False, gazetteer=False),
}


def build_chunks():
    print(CHUNK_COLLECTION, insert(CHUNK_COLLECTION, chunk_units()), flush=True)


def build_variant(name):
    parts, stats = graph_units(VARIANTS[name])
    for coll, units in parts:
        print(coll, insert(coll, units), flush=True)
    if name == "full":
        (DATA / "graph_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf8")
        print(json.dumps(stats, ensure_ascii=False, indent=1))
    else:
        print(name, dict(facts=stats["facts_grounded"], campus_scoped=stats["campus_scoped"],
                         with_validity=stats["with_validity"], passages_scoped=stats["passages_scoped"]), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="comma-separated: chunks," + ",".join(VARIANTS))
    args = ap.parse_args()
    print("Milvus:", MILVUS_URI, "database:", MILVUS_DB or "default", flush=True)
    todo = args.only.split(",") if args.only else ["chunks"] + list(VARIANTS)
    for name in todo:
        build_chunks() if name == "chunks" else build_variant(name)


if __name__ == "__main__":
    main()
