"""Table 1 metrics: denominators of SCE and TE, missing records, bootstrap."""
from campusscope.evaluation.metrics import bootstrap_ci, paired_p, summarize


def item(i, kind, notice):
    return dict(id=f"{kind}-{i}", kind=kind, source=dict(gid=f"{notice}#{i}"))


ITEMS = [item(i, k, f"n{i % 3}") for i, k in enumerate(["T1", "T2", "T3", "T4", "T5", "T6"] * 2)]


def run(correct=(), sce=(), te=()):
    return {it["id"]: dict(id=it["id"], latency=1.0 + n,
                           verdict=dict(correct=it["id"] in correct, sce=it["id"] in sce, te=it["id"] in te))
            for n, it in enumerate(ITEMS)}


def test_rates_and_denominators():
    ids = [it["id"] for it in ITEMS]
    r = summarize(run(correct=ids[:6], sce=["T2-1"], te=["T3-2", "T4-3"]), ITEMS)
    assert r["acc"] == 50.0 and r["per_kind"]["T1"] == 50.0
    assert r["sce"] == 100 / 6            # over the six T1/T2/T6 items
    assert r["te"] == 200 / 6             # over the six T3/T4/T5 items
    assert r["sec"] == 6.5


def test_missing_records_count_as_wrong():
    records = run(correct=[it["id"] for it in ITEMS])
    records.pop(ITEMS[0]["id"])
    r = summarize(records, ITEMS)
    assert r["missing"] == 1 and r["acc"] == 100 * 11 / 12


def test_bootstrap():
    a, b = run(correct=[it["id"] for it in ITEMS]), run()
    lo, hi = bootstrap_ci(a, ITEMS, n_boot=200)
    assert lo == hi == 100.0
    assert paired_p(a, b, ITEMS, n_boot=200) < 0.01
    assert paired_p(b, b, ITEMS, n_boot=200) == 1.0
