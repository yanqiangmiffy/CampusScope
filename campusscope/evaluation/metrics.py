"""The metrics of Table 1, computed from run records (outputs/runs/<config>.jsonl, one per system).

  Acc    share of the items answered correctly (judge.py), overall and per item type T1-T6;
  SCE    silent-condition errors (another campus's value) among the campus items T1, T2, T6;
  TE     temporal errors (a stale or revised value) among the temporal items T3, T4, T5;
  Sec.   median seconds per item (model latency summed over the dialogue, as recorded by the run).

An item without a record (or whose last record is an error) counts as wrong. The 95% confidence interval
and the p-values resample source notices with replacement (a cluster bootstrap: the items generated from
one notice are not independent); p is paired and one-sided, for "the system is more accurate than the
baseline".
"""
import json
import random
import statistics
from collections import defaultdict

KINDS = ("T1", "T2", "T3", "T4", "T5", "T6")
CAMPUS_KINDS = ("T1", "T2", "T6")
TEMPORAL_KINDS = ("T3", "T4", "T5")


def load_items(path):
    return [json.loads(line) for line in open(path, encoding="utf8")]


def load_runs(path):
    """{item id: record}; a resumed run appends, so the last record of an item wins."""
    out = {}
    for line in open(path, encoding="utf8"):
        r = json.loads(line)
        out[r["id"]] = r
    return out


def notice_of(item):
    """The source notice of an item (its gold fact id is "<doc_id>#<k>")."""
    return item["source"]["gid"].split("#")[0]


def _verdict(records, item_id):
    r = records.get(item_id)
    return (r or {}).get("verdict") or {}


def _rate(flags):
    return 100.0 * sum(flags) / len(flags) if flags else float("nan")


def summarize(records, items, time_field="latency"):
    """One row of Table 1."""
    by_kind = defaultdict(list)
    for it in items:
        by_kind[it["kind"]].append(_verdict(records, it["id"]))
    correct = [bool(_verdict(records, it["id"]).get("correct")) for it in items]
    times = [records[it["id"]].get(time_field, 0.0) for it in items if it["id"] in records]
    return dict(
        n=len(items),
        acc=_rate(correct),
        per_kind={k: _rate([bool(v.get("correct")) for v in by_kind[k]]) for k in KINDS},
        sce=_rate([bool(v.get("sce")) for k in CAMPUS_KINDS for v in by_kind[k]]),
        te=_rate([bool(v.get("te")) for k in TEMPORAL_KINDS for v in by_kind[k]]),
        sec=statistics.median(times) if times else float("nan"),
        missing=sum(it["id"] not in records for it in items),
    )


def _clusters(items):
    groups = defaultdict(list)
    for it in items:
        groups[notice_of(it)].append(it["id"])
    return list(groups.values())


def bootstrap_ci(records, items, n_boot=10000, seed=0, level=0.95):
    """Percentile interval of the accuracy (in %) under resampling of source notices."""
    clusters = _clusters(items)
    ok = {it["id"]: bool(_verdict(records, it["id"]).get("correct")) for it in items}
    rng = random.Random(seed)
    accs = []
    for _ in range(n_boot):
        ids = [i for c in rng.choices(clusters, k=len(clusters)) for i in c]
        accs.append(100.0 * sum(ok[i] for i in ids) / len(ids))
    accs.sort()
    lo = accs[int((1 - level) / 2 * n_boot)]
    hi = accs[min(n_boot - 1, int((1 + level) / 2 * n_boot))]
    return lo, hi


def paired_p(records_a, records_b, items, n_boot=10000, seed=0):
    """One-sided p-value that system a is more accurate than system b (paired cluster bootstrap)."""
    clusters = _clusters(items)
    diff = {it["id"]: int(bool(_verdict(records_a, it["id"]).get("correct")))
            - int(bool(_verdict(records_b, it["id"]).get("correct"))) for it in items}
    rng = random.Random(seed)
    not_better = 0
    for _ in range(n_boot):
        ids = [i for c in rng.choices(clusters, k=len(clusters)) for i in c]
        if sum(diff[i] for i in ids) <= 0:
            not_better += 1
    return (not_better + 1) / (n_boot + 1)
