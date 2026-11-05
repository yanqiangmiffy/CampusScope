"""Evidence-graph compiler, offline (Section 2.2): every service notice -> a positioned scope tree (LLM).

    python scripts/compile_graph.py --workers 2      # each notice sends up to four windows at once

For every service notice (scripts/prepare_corpus.py), the model extracts (i) the section outline with
the scope each heading introduces and (ii) atomic facts with verbatim quotes. The raw model output is
stored in data/compiled_<model>.jsonl; placement, scope inheritance, temporal anchoring and cross-notice
edges are deterministic (campusscope/graph.py) and run at load time, so every graph component can be
ablated without recompiling. Resumable: notices already compiled are skipped.
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from campusscope.compiler import compile_notice
from campusscope.config import DATA, SYSTEM_MODEL, compiled_path
from campusscope.llm import stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=SYSTEM_MODEL)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--only-benchmark", action="store_true", help="compile only notices used by the benchmark")
    args = ap.parse_args()
    docs = [json.loads(l) for l in open(DATA / "notices.jsonl", encoding="utf8")]
    docs = [d for d in docs if d["service"] and len(d["text"]) >= 60]
    if args.only_benchmark:
        bench = {json.loads(l)["doc_id"] for l in open(DATA / "benchmark_sources.jsonl", encoding="utf8")}
        docs = [d for d in docs if d["doc_id"] in bench]
    out_path = compiled_path(args.model)
    done = {}
    if out_path.exists():
        for line in open(out_path, encoding="utf8"):
            r = json.loads(line)
            done[r["doc_id"]] = r
    todo = [d for d in docs if d["doc_id"] not in done]
    print(f"{len(docs)} service notices; {len(done)} already compiled; compiling {len(todo)} with {args.model}", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex, open(out_path, "a", encoding="utf8") as f:
        futs = {ex.submit(compile_notice, d, args.model): d for d in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            d = futs[fut]
            try:
                comp, calls = fut.result()
            except Exception as e:  # noqa: BLE001
                print("FAILED", d["published"], d["title"][:30], e, flush=True)
                continue
            rec = dict(doc_id=d["doc_id"], published=d["published"], title=d["title"], model=args.model,
                       calls=len(calls), out_tokens=sum(c["usage"]["completion"] for c in calls),
                       seconds=round(sum(c["latency"] for c in calls), 1), **comp)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            if i % 10 == 0 or i == len(todo):
                print(f"{i}/{len(todo)} {time.time() - t0:.0f}s {stats()}", flush=True)


if __name__ == "__main__":
    main()
