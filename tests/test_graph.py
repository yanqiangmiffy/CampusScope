"""Section 2.2: scope inheritance along the section path; Eq. 1: applicability with revision and recurrence."""
from datetime import date

from campusscope.graph import EvidenceGraph, Fact, Gazetteer, Options, build_facts

NOTICE = dict(doc_id="d1", title="寒假期间各服务点营业时间", published="2026-01-07", cycle="2026寒假",
              text="中关村校区 体育场馆 田径场 10:00—18:00 正常开放 通州校区 体育场馆 田径场 8:00—22:00 正常开放")
COMPILED = dict(
    doc=dict(campus="both", period="2026寒假", start="2026-01-12", end="2026-02-28"),
    outline=[[1, "中关村校区", "zgc", None, None, None], [1, "通州校区", "tz", None, None, None]],
    facts=[dict(entity="田径场", type="田径球场", attr="开放时间", value="10:00—18:00", quote="田径场 10:00—18:00 正常开放"),
           dict(entity="田径场", type="田径球场", attr="开放时间", value="8:00—22:00", quote="田径场 8:00—22:00 正常开放")],
)


def test_campus_is_inherited_from_the_heading():
    fs = build_facts(NOTICE, COMPILED, Gazetteer({}))
    assert [(f.value, f.campus, f.campus_src) for f in fs] == [("10:00—18:00", "zgc", "section"),
                                                                ("8:00—22:00", "tz", "section")]
    assert all(f.sec_path for f in fs) and fs[0].start == date(2026, 1, 12)


def test_without_inheritance_the_campus_is_lost():
    fs = build_facts(NOTICE, COMPILED, Gazetteer({}), Options(inherit_scope=False))
    assert [f.campus for f in fs] == [None, None]          # what a 600-character chunk loses (C1)


def fact(fid, published, value, start=None, end=None, campus="zgc", ptype=None, cycle=None):
    return Fact(id=fid, doc_id=fid.split("#")[0], title="t", published=published, entity="东区浴室", ekey="东区浴室",
                type="浴室", attr="开放时间", group="availability", value=value, quote=value, span_ok=True,
                campus=campus, start=start, end=end, ptype=ptype, cycle=cycle)


def test_a_revision_applies_only_from_its_publication_date():
    old = fact("a#0", "2025-09-01", "7:00—9:00")
    new = fact("b#0", "2026-01-10", "暂停早场")
    g = EvidenceGraph([old, new])
    assert g.revises == {"a#0": ["b#0"]}
    before = g.status([old, new], {}, "2025-10-15", (date(2025, 10, 15),) * 2)
    after = g.status([old, new], {}, "2026-03-09", (date(2026, 3, 9),) * 2)
    assert [f.id for f in before["branches"]["zgc"]] == ["a#0"] and not before["revised"]
    assert [f.id for f in after["branches"]["zgc"]] == ["b#0"] and [f.id for f in after["revised"]] == ["a#0"]


def test_an_earlier_cycle_is_history_when_this_cycles_notice_is_not_out():
    last = fact("w#0", "2025-01-06", "8:00—20:00", date(2025, 1, 12), date(2025, 2, 28), ptype="寒假", cycle=2025)
    g = EvidenceGraph([last])
    st = g.status([last], {}, "2025-12-28", (date(2026, 1, 12), date(2026, 2, 28)), ("寒假", 2026))
    assert not st["branches"] and [f.id for f in st["history"]] == ["w#0"]
