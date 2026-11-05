"""The evidence subgraph of S1 (今天田径场几点开放？ on 2026-01-20), built offline from data/."""
from datetime import date

from app.services import graph_service


def s1(graph):
    spec = graph.lookup("田径场", "今天田径场几点开放？", "availability")
    keys = {(f.ekey, f.group) for f in spec}
    cands = [f for f in graph.candidates(spec, etype=None, group="availability") if (f.ekey, f.group) in keys]
    day = date(2026, 1, 20)
    st = graph.status(cands, dict(campus=None), "2026-01-20", (day, day), None)
    return cands, st, graph_service.build(graph, cands, st, "2026-01-20", day, day, None, st["branches"])


def test_s1_candidates_are_the_whole_key(graph):
    cands, _, payload = s1(graph)
    assert len(cands) == 14 and payload["total"] == 14 and payload["keys"] == 1


def test_s1_statuses(graph):
    _, _, payload = s1(graph)
    count = {}
    for f in payload["facts"]:
        count[f["status"]] = count.get(f["status"], 0) + 1
    assert count == {"current": 4, "future": 5, "history": 3, "inactive": 2}
    current = {f["id"]: f["campus"] for f in payload["facts"] if f["status"] == "current"}
    assert sorted(current.values()) == ["tz", "tz", "zgc", "zgc"]


def test_s1_edges_stay_inside_the_subgraph(graph):
    _, _, payload = s1(graph)
    ids = {f["id"] for f in payload["facts"]}
    assert payload["edges"]
    assert all(e["src"] in ids and e["dst"] in ids for e in payload["edges"])
    # every reviser of S1 is published after 2026-01-20, so no revision is active yet
    assert not any(e.get("active") for e in payload["edges"] if e["kind"] == "rev")


def test_known_error_and_inherited_campus(graph):
    _, _, payload = s1(graph)
    f = next(f for f in payload["facts"] if f["id"] == "b28eb1484c#45")
    assert f["err"] and "北区足球场" in f["err"][0]
    assert f["src"]["campus"] == {"kind": "section", "head": "中关村校区"}
    assert f["path"][0] == "中关村校区"


def test_node_limit_keeps_revision_targets(graph):
    cands, st, _ = s1(graph)
    day = date(2026, 1, 20)
    payload = graph_service.build(graph, cands, st, "2026-01-20", day, day, None, st["branches"], max_nodes=5)
    ids = {f["id"] for f in payload["facts"]}
    assert all(e["src"] in ids and e["dst"] in ids for e in payload["edges"])
