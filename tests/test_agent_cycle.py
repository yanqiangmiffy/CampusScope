"""A named break whose own notice is out must not be answered from an earlier cycle (T3), even when that notice
names the service point differently; when it is not out yet, the earlier cycle is still given as history (T4)."""
from datetime import date

from campusscope.agent import CampusScope
from campusscope.graph import EvidenceGraph, Fact, Options

TARGET = (date(2026, 7, 8), date(2026, 8, 31))
CYCLE = ("暑假", 2026)
PLAN = {"entity": "拳道馆", "attr": "开放时间"}


def fact(fid, published, entity, value, start, end, cycle):
    return Fact(id=fid, doc_id=fid.split("#")[0], title="t", published=published, entity=entity, ekey=entity,
                type="体育场馆", attr="开放时间", group="availability", value=value, quote=value, span_ok=True,
                campus="zgc", start=start, end=end, ptype="暑假", cycle=cycle)


LAST_YEAR = fact("a#0", "2025-07-04", "拳道馆", "8:00—22:00", date(2025, 7, 7), date(2025, 9, 4), 2025)
THIS_YEAR = fact("b#0", "2026-06-26", "拳道馆健身房", "9:00—22:00", date(2026, 6, 26), None, 2026)


def agent(facts, passages=()):
    a = CampusScope.__new__(CampusScope)        # no index or model: only the graph reasoning is exercised
    a.opt, a.g = Options(), EvidenceGraph(facts, Options())
    a.scoped_passages = lambda *args, **kw: list(passages)
    a.history_passages = lambda *args, **kw: []
    return a


def run(a, today):
    cands = [LAST_YEAR]                          # retrieval and key expansion reach last year's key only
    st = a.g.status(cands, {}, today, TARGET, CYCLE)
    return a.cycle_status(PLAN, [], today, "zgc", cands, st, TARGET, CYCLE, None)


def test_this_cycles_notice_is_found_under_another_name():
    a = agent([LAST_YEAR, THIS_YEAR])
    assert [f.id for f in a.cycle_facts(PLAN, CYCLE, "2026-07-01", "availability")] == ["b#0"]
    cands, st, branches, hist_p, cur_p = run(a, "2026-07-01")
    assert [f.id for fs in branches.values() for f in fs] == ["b#0"]       # answered from 2026, not as history


def test_before_this_cycles_notice_the_last_cycle_is_history():
    a = agent([LAST_YEAR, THIS_YEAR])
    assert a.cycle_facts(PLAN, CYCLE, "2026-06-20", "availability") == []  # published after today
    cands, st, branches, hist_p, cur_p = run(a, "2026-06-20")
    assert branches == {} and [f.id for f in st["history"]] == ["a#0"]


def test_a_passage_of_this_cycle_also_blocks_history():
    p = dict(id="b~3", ptype="暑假", cycle=2026, start=date(2026, 6, 26), end=None)
    a = agent([LAST_YEAR], passages=[p])
    cands, st, branches, hist_p, cur_p = run(a, "2026-07-01")
    assert [x["id"] for x in cur_p] == ["b~3"] and hist_p == []


def test_without_a_cycle_only_dated_passages_in_force_count():
    dated = dict(id="c~1", ptype="国庆", cycle=2025, start=date(2025, 10, 1), end=date(2025, 10, 7))
    undated = dict(id="d~1", ptype=None, cycle=2025, start=None, end=None)
    a = agent([], passages=[dated, undated])
    day = (date(2025, 10, 4),) * 2
    assert [p["id"] for p in a.current_passages({}, [], "2025-10-04", "zgc", day, None)] == ["c~1"]
