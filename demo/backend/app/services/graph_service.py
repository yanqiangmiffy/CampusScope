"""The evidence subgraph of one question, as the frontend draws it.

Nodes are the candidate facts (every branch of the asked key(s), after graph expansion) with their
status at the visitor's "today"; edges are the graph's revision (rev) and recurrence (rec) edges
among them; notices are the columns of the time axis. Each fact also says where each of its
conditions came from (the fact's own quote, a heading of its section path, the notice as a whole,
or the gazetteer) — the scope inheritance the paper's Figure 2 illustrates.
"""
import json
import re
from functools import lru_cache

from app import system  # noqa: F401
from app.config import get_settings

from campusscope.config import compiled_path
from campusscope.text import iso

# extraction errors found by checking the source notice by hand: shown in the fact drawer, never corrected silently
KNOWN_ERRORS = {
    "b28eb1484c#45": ("原文表格里，「10:00—18:00」这一格属于北区足球场。PDF 转文字时表格错行，LLM 把它挂到了田径场上；"
                      "中关村田径场这一行只写了「正常开放」。",
                      "In the source table, 10:00-18:00 belongs to the north football field; the PDF text shifted a row and "
                      "the extractor attached it to the track field, whose row only says 'open as usual'."),
    "b28eb1484c#61": ("原文表格里，这一格属于健身房、乒乓球室（2月10日—2月24日暂停开放）。PDF 转文字时表格错行，LLM 把它挂到了田径场上；"
                      "通州田径场这一行是「正常开放，8:00—22:00」。",
                      "In the source table, this cell belongs to the gym and table-tennis room (closed Feb 10-24); the PDF "
                      "text shifted a row. The Tongzhou track field's row says 'open as usual, 8:00-22:00'."),
}
PRIORITY = {"used": 0, "current": 1, "revised": 2, "history": 3, "inactive": 4, "future": 5}
PERIOD_WORDS = ("寒假", "暑假", "暑期", "国庆", "五一", "春节", "元旦", "清明", "端午", "中秋", "开学", "考试周", "期末")


@lru_cache(maxsize=1)
def _compiled() -> dict:
    out = {}
    with open(compiled_path(), encoding="utf8") as fh:
        for line in fh:
            c = json.loads(line)
            out[c["doc_id"]] = c
    return out


def _heads(comp):
    heads = {}
    for o in comp.get("outline") or []:
        o = list(o) + [None] * (6 - len(o))
        heads.setdefault(o[1], []).append(o)
    return heads


def sources(f) -> dict:
    """Where the campus, validity and audience of a fact came from (the level of its section path
    that supplied each), mirroring the inheritance in graph.build_facts."""
    comp = _compiled().get(f.doc_id)
    if not comp:
        return {}
    try:
        raw = comp["facts"][int(f.id.split("#")[1].split(".")[0])]
    except (IndexError, ValueError, KeyError):
        raw = {}
    heads = _heads(comp)

    def first_head(i, allowed=None):
        for name in f.sec_path:
            for o in heads.get(name, []):
                if o[i] not in (None, "null") and (allowed is None or o[i] in allowed):
                    return name
        return None

    def src(kind, head=None):
        return dict(kind=kind, head=head)

    if f.campus_src == "section":
        h = first_head(2, ("zgc", "tz"))
        campus = src("section", h) if h else src("doc")
    else:
        campus = src(f.campus_src or "none")
    if raw.get("start") or raw.get("end"):
        valid = src("fact")
    elif f.start or f.end:
        h = first_head(4) or first_head(5)
        valid = src("section", h) if h else src("doc")
    else:
        valid = src("none")
    if raw.get("audience"):
        aud = src("fact")
    elif f.audience:
        h = first_head(3)
        aud = src("section", h) if h else src("doc")
    else:
        aud = src("none")
    return dict(campus=campus, valid=valid, audience=aud)


def notice_kind(title: str, ptype: str | None) -> str:
    """Short label of a notice for its column header."""
    if ptype:
        return ptype
    for w in PERIOD_WORDS:
        if w in title:
            return w
    t = re.sub(r"^(关于|【[^】]*】)", "", title)
    t = re.sub(r"(的)?(通知|公告|温馨提示|提示)$", "", t)
    return t[:8] + ("…" if len(t) > 8 else "")


def fact_node(f, status: str) -> dict:
    return dict(id=f.id, doc=f.doc_id, entity=f.entity, ekey=f.ekey, type=f.type, attr=f.attr, group=f.group,
                value=f.value, quote=f.quote, campus=f.campus, campusSrc=f.campus_src, audience=f.audience,
                start=iso(f.start), end=iso(f.end), pub=f.published, period=f.period, ptype=f.ptype, cycle=f.cycle,
                path=list(reversed(f.sec_path)), status=status, src=sources(f), err=KNOWN_ERRORS.get(f.id))


def statuses(cands, st, today: str, branches) -> dict[str, str]:
    cur = {f.id for fs in branches.values() for f in fs}
    rev = {f.id for f in st["revised"]}
    hist = {f.id for f in st["history"]}
    out = {}
    for f in cands:
        if f.published > today:
            out[f.id] = "future"
        elif f.id in rev:
            out[f.id] = "revised"
        elif f.id in cur:
            out[f.id] = "current"
        elif f.id in hist:
            out[f.id] = "history"
        else:
            out[f.id] = "inactive"
    return out


def build(g, cands, st, today, lo, hi, cycle, branches, max_nodes: int | None = None) -> dict:
    """Subgraph payload at the time of the answer (before the decision: `used` is sent separately)."""
    max_nodes = max_nodes or get_settings().MAX_GRAPH_NODES
    status = statuses(cands, st, today, branches)
    rev = {f.id for f in st["revised"]}
    keep = sorted(cands, key=lambda f: (PRIORITY[status[f.id]], f.published))[:max_nodes]
    # keep what the kept facts' edges point at, so a revision is never drawn to nowhere
    ids = {f.id for f in keep}
    for f in list(keep):
        for n in g.revises.get(f.id, []):
            if n not in ids and n in g.by_id and len(ids) < max_nodes + 20:
                ids.add(n)
                keep.append(g.by_id[n])
                status.setdefault(n, "future" if g.by_id[n].published > today else "inactive")
    edges = []
    for f in keep:
        for n in g.revises.get(f.id, []):
            if n in ids:
                edges.append(dict(kind="rev", src=n, dst=f.id, active=f.id in rev and g.by_id[n].published <= today))
        prev = [p for p in g.recurs.get(f.id, []) if p in ids]
        if prev:
            near = max((g.by_id[p].cycle or 0) for p in prev)
            for p in prev:
                edges.append(dict(kind="rec", src=f.id, dst=p, near=(g.by_id[p].cycle or 0) == near))
    docs = {}
    for f in keep:
        if f.doc_id not in docs:
            docs[f.doc_id] = dict(id=f.doc_id, title=f.title, pub=f.published, ptype=f.ptype,
                                  kind=notice_kind(f.title, f.ptype))
    return dict(today=today, target=[iso(lo), iso(hi)], cycle=list(cycle) if cycle else None,
                notices=sorted(docs.values(), key=lambda d: d["pub"]),
                facts=[fact_node(f, status[f.id]) for f in keep], edges=edges,
                total=len(cands), shown=len(keep), keys=len({(f.ekey, f.group) for f in cands}))
