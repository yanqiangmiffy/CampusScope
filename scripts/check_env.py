"""Checks that every service the pipeline needs is reachable: Milvus (and the collections built by
scripts/build_index.py), the bge embedder and the backbone chat model.

    python scripts/check_env.py

Writes outputs/env_check.json (no keys: model ids and reachability only).
"""
import json
import time

from campusscope.config import CHUNK_COLLECTION, FACT_COLLECTION, MILVUS_URI, MODEL_LABEL, MODELS, OUT, PASSAGE_COLLECTION, SYSTEM_MODEL
from campusscope.llm import chat, embed
from campusscope.search import service


def main():
    report = {}
    report["milvus"] = dict(uri=MILVUS_URI, healthy=service(FACT_COLLECTION).healthy(),
                            collections={c: service(c).get_stats() for c in (FACT_COLLECTION, PASSAGE_COLLECTION, CHUNK_COLLECTION)})
    t = time.time()
    v = embed(["宿舍报修找谁"])[0]
    report["embedding"] = dict(dim=len(v), seconds=round(time.time() - t, 2))
    for name in (SYSTEM_MODEL,):
        t = time.time()
        r = chat([dict(role="user", content="只回答一个数字：1+1=?")], model=name, max_tokens=8, tag="env")
        report[name] = dict(model=MODELS[name][2], label=MODEL_LABEL[name], reply=r["content"][:20],
                            seconds=round(time.time() - t, 2))
    (OUT / "env_check.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
