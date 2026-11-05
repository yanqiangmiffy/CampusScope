"""Runs every system on CondQA-RUC with simulated users (Section 4.1; DeepSeek-V4.1-Flash as the backbone).

    python scripts/run_benchmark.py --suite main       # the seven baselines + CampusScope (Table 1)
    python scripts/run_benchmark.py --suite ablation   # components of CampusScope
    python scripts/run_benchmark.py --suite sweep      # lambda sweep (T2 items only)
    python scripts/run_benchmark.py --suite extra      # ReAct with thinking on
    python scripts/run_benchmark.py --suite all        # main + ablation + sweep

Every configuration writes one JSONL to outputs/runs/<config>.jsonl (final reply, transcript, verdict,
calls, latency); scripts/make_table.py turns them into Table 1. All model calls are cached
(cache/llm_cache.sqlite), so with the released cache a rerun replays the paper's calls, costs nothing and
needs no chat endpoint. Runs are resumable: items already recorded without an error are skipped.
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from campusscope.agent import CampusScope
from campusscope.baselines import RAG, ClarifyRAG, LongContext, PassageRAG, ReAct
from campusscope.config import DATA, OUT, SYSTEM_MODEL
from campusscope.evaluation.simulate import run_dialogue
from campusscope.graph import Options
from campusscope.llm import stats

RUNS = OUT / "runs"
RUNS.mkdir(parents=True, exist_ok=True)
SWEEP_KINDS = {"T2"}          # the trade-off figure and its numbers use silent-campus items only


def suite(name):
    cfg = {}
    m = SYSTEM_MODEL
    if name in ("main", "all"):
        cfg[f"{m}__rag"] = lambda: RAG(m)
        cfg[f"{m}__rag_rules"] = lambda: RAG(m, rules=True)
        cfg[f"{m}__clarify"] = lambda: ClarifyRAG(m)
        cfg[f"{m}__react"] = lambda: ReAct(m)
        cfg[f"{m}__passage_rag"] = lambda: PassageRAG(m)
        cfg[f"{m}__passage_rag_valid"] = lambda: PassageRAG(m, valid_only=True)
        cfg[f"{m}__long_context"] = lambda: LongContext(m)
        cfg[f"{m}__campusscope"] = lambda: CampusScope(m)
    if name in ("ablation", "all"):
        cfg["abl__no_inherit"] = lambda: CampusScope(m, Options(inherit_scope=False), name="- scope inheritance")
        cfg["abl__no_gazetteer"] = lambda: CampusScope(m, Options(gazetteer=False), name="- place gazetteer")
        cfg["abl__no_scope"] = lambda: CampusScope(m, Options(inherit_scope=False, gazetteer=False), name="- all scope")
        cfg["abl__no_time"] = lambda: CampusScope(m, Options(anchor_time=False), name="- temporal validity")
        cfg["abl__no_revision"] = lambda: CampusScope(m, Options(revisions=False), name="- revision edges")
        cfg["abl__no_recurrence"] = lambda: CampusScope(m, Options(recurrence=False), name="- recurrence (history)")
        cfg["abl__no_expand"] = lambda: CampusScope(m, Options(expand_keys=False), name="- key expansion")
        cfg["abl__no_passages"] = lambda: CampusScope(m, Options(passages=False), name="- scoped passages")
        cfg["abl__no_planner"] = lambda: CampusScope(m, planner=False, name="- LLM planner")
        cfg["abl__guess"] = lambda: CampusScope(m, lam=0.0, beta=1e9, name="policy: always guess")
        cfg["abl__ask_only"] = lambda: CampusScope(m, lam=1e9, beta=1e9, name="policy: ask, never enumerate")
    if name in ("sweep", "all"):
        for lam in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0, 1e9):
            cfg[f"sweep__lam{lam:g}"] = lambda lam=lam: CampusScope(m, lam=lam, beta=1e9, name=f"lambda={lam:g}")
    if name == "extra":
        cfg[f"{m}__react_thinking"] = lambda: ReAct(m, thinking=True)
    return cfg


def run(config, factory, items, workers):
    path = RUNS / f"{config}.jsonl"
    done = set()
    if path.exists():       # an item whose last record is an error (e.g. an endpoint was down) is run again
        last = {}
        for l in open(path, encoding="utf8"):
            r = json.loads(l)
            last[r["id"]] = r
        done = {i for i, r in last.items() if not r.get("error")}
    todo = [it for it in items if it["id"] not in done]
    if config.startswith("sweep__"):
        todo = [it for it in todo if it["kind"] in SWEEP_KINDS]
    if not todo:
        return
    system = factory()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex, open(path, "a", encoding="utf8") as f:
        futs = {ex.submit(run_dialogue, system, it): it for it in todo}
        for fut in as_completed(futs):
            it = futs[fut]
            try:
                r = fut.result()
            except Exception as e:  # noqa: BLE001
                r = dict(id=it["id"], kind=it["kind"], error=str(e)[:300], final=dict(action="error", text=""),
                         verdict=dict(correct=False, sce=False, te=False, over_ask=False, abstain=False, asked=0),
                         calls=0, latency=0.0, asked=[])
            r["config"] = config
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
            f.flush()
    print(f"{config}: {len(todo)} items in {time.time() - t0:.0f}s {stats()}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="main")
    ap.add_argument("--only", default=None, help="comma-separated config names")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--shard", default=None, help="i/n: run every n-th item starting at i (parallel resumable shards)")
    args = ap.parse_args()
    items = [json.loads(l) for l in open(DATA / "benchmark.jsonl", encoding="utf8")]
    if args.limit:
        items = items[:args.limit]
    if args.shard:
        i, n = map(int, args.shard.split("/"))
        items = items[i::n]
    cfg = suite(args.suite)
    if args.only:
        keep = set(args.only.split(","))
        cfg = {k: v for k, v in cfg.items() if k in keep}
    for name, factory in cfg.items():
        run(name, factory, items, args.workers)


if __name__ == "__main__":
    main()
