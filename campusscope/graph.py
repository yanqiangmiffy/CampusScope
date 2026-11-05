"""The condition-scoped evidence graph (paper Section 2.2) and applicability on it (Section 2.3, Eq. 1).

Nodes: notices, sections, facts, entities, service types, scope values.
A fact f carries a key k(f) = (entity, attribute group), a value v(f), a quote, and
  * an inherited scope    sigma*(f) = sigma(f) (+) sigma(sec_k) (+) ... (+) sigma(doc)
    (child overrides parent, dimension by dimension; gazetteer as the last resort),
  * a validity interval   V(f) = [b(f), e(f)] anchored to the publication date tau(f),
  * a cycle               (period type, year), e.g. (寒假, 2026).
Edges added across notices:
  * revises(f', f): same key, compatible scope, overlapping validity, tau(f') > tau(f);
  * recurs(f', f): same key and period type, earlier cycle (the history of f').
Placement, inheritance, anchoring and edges are deterministic and run when the graph is loaded
(`load_graph`), so every component can be switched off for ablation (`Options`) without recompiling.
"""
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .config import DATA, SYSTEM_MODEL, compiled_path
from .text import anchor, iso, parse_date, squash, undouble

ATTR_GROUP = {"开放时间": "availability", "开放状态": "availability", "班次时刻": "schedule", "地点": "place",
              "电话": "phone", "收费": "fee", "办理方式": "procedure", "安排": "arrangement"}
# default windows of named breaks, used only when a holiday notice states no dates at all
HOLIDAY = {"寒假": ((1, 12), (2, 28)), "暑假": ((7, 8), (8, 31)), "国庆": ((10, 1), (10, 8)), "五一": ((5, 1), (5, 5)),
           "春节": ((1, 25), (2, 20)), "中秋": ((9, 15), (10, 8))}
# notices about a bounded period, whose headings' dates are validities (not promotions)
PERIOD_NOTICE = set(HOLIDAY) | {"考试周", "期末", "供暖", "军训", "开学", "迎新"}
# attribute groups whose value a later notice replaces (revision) or a later cycle renews
# (recurrence); free-form arrangements and procedures accumulate instead
REPLACEABLE = ("availability", "schedule", "place", "phone", "fee")
PERIOD_TYPES = ("寒假", "暑假", "国庆", "五一", "劳动节", "春节", "元旦", "清明", "端午", "中秋", "考试周", "期末",
                "春季学期", "秋季学期", "供暖", "开学", "迎新", "军训")
TYPE_ALIASES = {"食堂": "食堂餐厅", "餐厅": "食堂餐厅", "超市": "超市商店", "商店": "超市商店", "开水": "开水房",
                "快递": "快递收发", "收发室": "快递收发", "打印": "打印复印", "文印": "打印复印", "自习": "教学楼自习室",
                "教学楼": "教学楼自习室", "田径场": "田径球场", "球场": "田径球场", "健身": "健身房", "游泳": "游泳馆",
                "场馆": "体育场馆", "班车": "班车交通", "专线": "班车交通", "校医院": "校医院", "宿舍": "宿舍公寓",
                "公寓": "宿舍公寓", "电费": "水电缴费", "水电": "水电缴费", "报修": "维修报修", "维修": "维修报修",
                "酒店": "酒店住宿"}


@dataclass
class Options:
    inherit_scope: bool = True      # sigma* along the section path (off: fact-local scope only)
    gazetteer: bool = True          # entity/building names -> campus
    anchor_time: bool = True        # validity intervals from explicit + inherited dates
    revisions: bool = True          # latest-wins among same-key overlapping facts
    recurrence: bool = True         # earlier cycles usable as labeled history
    expand_keys: bool = True        # pull every branch of a key, not only retrieved facts
    passages: bool = True           # section-aligned passages with inherited scope as supplementary evidence


def period_type(period):
    p = period or ""
    for t in PERIOD_TYPES:
        if t in p:
            return {"劳动节": "五一"}.get(t, t)
    return None


def year_of(period, published):
    m = re.search(r"(20\d{2})", period or "")
    return int(m.group(1)) if m else int(published[:4])


def canon_type(t, entity=""):
    t = (t or "").strip()
    from .compiler import TYPES
    if t in TYPES:
        return t
    for k, v in TYPE_ALIASES.items():
        if k in t or k in entity:
            return v
    return "其他"


_CN_DIGIT = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}


def entity_key(entity):
    """Normalized service-point key: no campus prefix, no punctuation, Arabic numerals for building numbers
    (公共教学二楼 and 公共教学2楼 are the same building; notices use both)."""
    e = squash(undouble(entity or ""))
    e = re.sub(r"^(中关村校区|通州校区|中关村|通州)", "", e)
    e = re.sub(r"([一二三四五六七八九])(?=[楼层号区栋])", lambda m: _CN_DIGIT[m.group(1)], e)
    e = e.replace("公教", "公共教学").replace("公学", "公学")
    return e


class Gazetteer:
    """Building / place names -> campus (data/gazetteer.json; its provenance is described in data/README.md)."""

    def __init__(self, mapping):
        self.map = {k: v for k, v in mapping.items() if len(k) >= 2}
        self.keys = sorted(self.map, key=len, reverse=True)

    @classmethod
    def load(cls, path):
        return cls(json.loads(path.read_text(encoding="utf8"))) if path.exists() else cls({})

    def campus_of(self, text):
        t = squash(text or "")
        found = {self.map[k] for k in self.keys if k in t}
        return found.pop() if len(found) == 1 else None

    def mentions(self, text):
        t = squash(text or "")
        return [k for k in self.keys if k in t]


@dataclass
class Fact:
    id: str
    doc_id: str
    title: str
    published: str
    entity: str
    ekey: str
    type: str
    attr: str
    group: str
    value: str
    quote: str
    span_ok: bool
    campus: str = None           # inherited (or local only, under ablation)
    campus_src: str = None
    audience: str = None
    start: date = None
    end: date = None
    period: str = None
    ptype: str = None
    cycle: int = None
    sec_path: list = field(default_factory=list)

    def view(self):
        return dict(id=self.id, entity=self.entity, type=self.type, attr=self.attr, value=self.value,
                    campus=self.campus or "未注明", audience=self.audience, valid_from=iso(self.start),
                    valid_to=iso(self.end), period=self.period, published=self.published, title=self.title,
                    quote=self.quote)


def _val(v):
    return None if v in (None, "", "null", "None", "none") else v


def build_facts(doc, compiled, gaz, opt=Options()):
    """Placement, scope inheritance and temporal anchoring for one compiled notice.

    sigma*(f): the fact's own scope, else the deepest enclosing section that states the
    dimension, else the notice-level scope; campus falls back to the gazetteer."""
    from .compiler import locate_outline, path_at
    from .text import clean
    text = clean(doc["text"])
    sq = squash(text)
    dscope = compiled.get("doc") or {}
    nodes = locate_outline(compiled.get("outline"), sq)
    period = _val(dscope.get("period")) or doc.get("cycle")
    ptype, cycle = period_type(period) or period_type(doc["title"]), year_of(period, doc["published"])
    facts = []
    for i, f in enumerate(compiled.get("facts") or []):
        if not isinstance(f, dict) or not _val(f.get("value")):
            continue
        q = squash(str(f.get("quote") or ""))
        a, b = f.get("window") or [0, len(text)]
        lo = len(squash(text[:a]))
        p = sq.find(q, max(0, lo - 20)) if len(q) >= 4 else -1
        if p < 0 and len(q) >= 4:
            p = sq.find(q)
        path = path_at(nodes, p) if (p >= 0 and opt.inherit_scope) else []
        levels = [("fact", f)] + [("section", n) for n in path] + ([("doc", dscope)] if opt.inherit_scope else [])

        def first(key, allowed=None):
            for src, lv in levels:
                v = _val(lv.get(key))
                if v is None or (allowed and v not in allowed):
                    continue
                return v, src
            return None, None

        # A campus the extractor attaches to the fact itself is accepted only if the quote
        # names it; otherwise the fact inherits from its section path (models over-assign).
        stated = _stated_campus(str(f.get("quote") or ""))
        f = dict(f, campus=stated)
        levels[0] = ("fact", f)
        campus, src = first("campus", ("zgc", "tz")) if stated != "both" else ("both", "fact")
        if campus is None and opt.gazetteer:
            g = gaz.campus_of(f.get("entity", "")) or gaz.campus_of(f.get("quote", ""))
            if g:
                campus, src = g, "gazetteer"
        audience, _ = first("audience")
        if opt.anchor_time:
            # dates are inherited from the structure only in period notices (breaks, exam weeks, heating):
            # in guides a dated heading is usually a promotion, not the validity of the hours listed under it
            dated = levels if ptype in PERIOD_NOTICE else levels[:1]

            def first_date(key):
                for src_, lv in dated:
                    v = _val(lv.get(key))
                    if v is not None:
                        return v, src_
                return None, None
            start, _ = first_date("start")
            end, end_src = first_date("end")
            start = anchor(parse_date(start), doc["published"])
            end = anchor(parse_date(end), doc["published"])
            quote = str(f.get("quote") or "")
            if end_src != "fact" and re.search(r"另行通知|恢复时间另|起[，,]?(?:暂停|停止|取消|关闭)", quote):
                end = None          # "suspended from Jan 12 until further notice": open-ended, not the break
            if start is None and end is None and ptype in HOLIDAY:
                (m0, d0), (m1, d1) = HOLIDAY[ptype]     # a holiday notice without dates: the break of its cycle
                start = date(cycle, m0, d0)
                end = date(cycle + (1 if m1 < m0 else 0), m1, d1)
            if start and end and end < start:
                end = None
        else:
            start = end = None
        ent = undouble(str(f.get("entity") or ""))
        attr = f.get("attr") if f.get("attr") in ATTR_GROUP else "安排"
        value = undouble(str(f.get("value")))
        if attr == "安排" and re.search(r"\d{1,2}[:：]\d{2}\s*[—\-–~至到]+\s*(次日)?\d{1,2}[:：]\d{2}|24小时|全天开放", value):
            attr = "开放时间"      # hours filed as an "arrangement" by the extractor
        elif attr == "安排" and re.fullmatch(r"[\s\d\-（）()、,，;；]*(?:\d{8}|1\d{10}|\d{3,4}-\d{7,8})[\s\d\-（）()、,，;；]*", value):
            attr = "电话"          # a bare phone number filed as an "arrangement"
        for j, e in enumerate(split_entities(ent)):
            facts.append(Fact(id=f"{doc['doc_id']}#{i}" + (f".{j}" if j else ""), doc_id=doc["doc_id"], title=doc["title"],
                              published=doc["published"], entity=e, ekey=entity_key(e),
                              type=canon_type(f.get("type"), e), attr=attr, group=ATTR_GROUP[attr],
                              value=value, quote=undouble(str(f.get("quote") or "")),
                              span_ok=p >= 0,
                              campus=None if campus == "both" else campus, campus_src=src,
                              audience=audience, start=start, end=end, period=period, ptype=ptype, cycle=cycle,
                              sec_path=[n["heading"] for n in path]))
    return facts


_PLACE_END = re.compile(r"(场|馆|室|楼|厅|房|店|堂|中心|站|处|院|部|所|库|池|间|园|门)$")


def split_entities(ent):
    """One fact per service point: "田径场、品园篮球场" -> two facts (the extraction prompt asks for this,
    and some models ignore it). Split only if every part is itself a place name."""
    parts = [p.strip() for p in re.split(r"[、/／]", ent) if p.strip()]
    if len(parts) > 1 and all(len(p) >= 2 and _PLACE_END.search(p) for p in parts):
        return parts
    return [ent]


def build_passages(doc, compiled, opt=Options()):
    """Section-aligned passages of a notice, each carrying the scope inherited along its section path
    (the same inheritance as for facts, applied to raw text, so what the extractor missed keeps its scope).

    Without inheritance (ablation) a passage keeps only what its own text says: no campus, dates or
    heading path from the sections above it."""
    from .compiler import path_at, section_passages
    from .text import clean
    text = clean(doc["text"])
    dscope = compiled.get("doc") or {}
    passages, nodes = section_passages(text, compiled.get("outline"))
    period = _val(dscope.get("period")) or doc.get("cycle")
    ptype, cycle = period_type(period) or period_type(doc["title"]), year_of(period, doc["published"])
    above = [dscope] if opt.inherit_scope else []
    out = []
    for k, p in enumerate(passages):
        chain = path_at(nodes, p["pos"]) if opt.inherit_scope else []
        stated = _stated_campus(p["text"])
        campus = stated if stated in ("zgc", "tz") else None
        if campus is None and stated != "both":
            for lv in chain + above:
                if _val(lv.get("campus")) in ("zgc", "tz"):
                    campus = lv["campus"]
                    break
        start = end = None
        if opt.anchor_time and ptype in PERIOD_NOTICE:
            for lv in chain + above:
                start = start or anchor(parse_date(_val(lv.get("start"))), doc["published"])
                end = end or anchor(parse_date(_val(lv.get("end"))), doc["published"])
            if start is None and end is None and ptype in HOLIDAY:
                (m0, d0), (m1, d1) = HOLIDAY[ptype]
                start, end = date(cycle, m0, d0), date(cycle + (1 if m1 < m0 else 0), m1, d1)
        out.append(dict(id=f"{doc['doc_id']}~{k}", doc_id=doc["doc_id"], title=doc["title"], published=doc["published"],
                        text=p["text"], path=list(reversed(p["path"])) if opt.inherit_scope else [], campus=campus,
                        start=start, end=end, ptype=ptype, cycle=cycle))
    return out


class EvidenceGraph:
    def __init__(self, facts, opt=Options(), passages=()):
        self.opt = opt
        self.passages = list(passages)
        self.passage_by_id = {p["id"]: p for p in self.passages}
        self.facts = [f for f in facts if f.span_ok]
        self.by_id = {f.id: f for f in self.facts}
        self.by_key = defaultdict(list)
        self.by_type = defaultdict(list)
        for f in self.facts:
            self.by_key[(f.ekey, f.group)].append(f)
            self.by_type[(f.type, f.group)].append(f)
        self.revises = {}     # superseded fact id -> [revising fact ids]
        self.recurs = {}      # fact id -> earlier-cycle fact ids (same key, same period type)
        if opt.revisions:
            self._revisions()
        if opt.recurrence:
            self._recurrence()

    # ---------------------------------------------------------------- cross-notice edges
    def _revisions(self):
        for key, fs in self.by_key.items():
            if key[1] not in REPLACEABLE:
                continue
            fs = sorted(fs, key=lambda f: f.published)
            for i, old in enumerate(fs):
                for new in fs[i + 1:]:
                    if new.published <= old.published or new.doc_id == old.doc_id:
                        continue
                    if not _scope_compatible(new.campus, old.campus):
                        continue
                    if _overlap(old, new) and squash(new.value) != squash(old.value):
                        self.revises.setdefault(old.id, []).append(new.id)

    def _recurrence(self):
        for key, fs in self.by_key.items():
            if key[1] not in REPLACEABLE:
                continue
            for f in fs:
                if not f.ptype:
                    continue
                prev = [g for g in fs if g.ptype == f.ptype and g.cycle and f.cycle and g.cycle < f.cycle]
                if prev:
                    self.recurs[f.id] = [g.id for g in prev]

    # ---------------------------------------------------------------- query-time reasoning
    def lookup(self, name=None, text=None, group=None):
        """Entity index over the whole graph (not only what retrieval ranked): the service point the user
        named, matched by containment or character-bigram overlap; if the planner gave no name, the longest
        service-point key that occurs in the user's own words."""
        keys = {k for k, g in self.by_key if (group is None or g == group) and len(k) >= 2}

        def grams(s):
            return {s[i:i + 2] for i in range(len(s) - 1)}
        best, score = [], 0.0
        n = entity_key(name or "")
        if len(n) >= 2:
            gn = grams(n)
            for k in keys:
                # containment scores by length ratio: the exact point wins over a generic word inside it
                s = (min(len(k), len(n)) / max(len(k), len(n))) if (k in n or n in k) \
                    else len(gn & grams(k)) / max(1, len(gn | grams(k)))
                if s > score + 1e-9:
                    best, score = [k], s
                elif abs(s - score) <= 1e-9:
                    best.append(k)
            if score < 0.5:
                best = []
        if not best and text:
            t = squash(text)
            hits = [k for k in keys if k in t]
            if hits:
                longest = max(len(k) for k in hits)
                best = [k for k in hits if len(k) == longest]
        out = [f for k in best for g in ([group] if group else {gg for kk, gg in self.by_key if kk == k})
               for f in self.by_key.get((k, g), [])]
        if not out and group is not None and (name or text):
            return self.lookup(name, text, None)      # the point exists but under another attribute group
        return out

    def candidates(self, seeds, etype=None, group=None):
        """Branch set of a question: every fact sharing a key with a retrieved seed fact,
        plus (for type-level questions) every fact of the same service type and attribute."""
        out = {f.id: f for f in seeds}
        if self.opt.expand_keys:
            for f in seeds:
                for g in self.by_key[(f.ekey, f.group)]:
                    out[g.id] = g
            if etype and group:
                for g in self.by_type[(etype, group)]:
                    out[g.id] = g
        return list(out.values())

    def status(self, facts, context, today, target, cycle=None):
        """Applicability A(x, t, T) of candidate facts (Eq. 1): the facts whose scope admits the user context x,
        published by today t, whose validity overlaps the target period T, and not revised by a fact
        published by t.

        target: (lo, hi) dates of the period the user asks about.
        Returns the applicable facts per campus branch (A_b), revised facts and labeled history."""
        today = parse_date(today)
        lo, hi = target
        known = [f for f in facts if f.published <= iso(today)]
        aud = context.get("audience")
        known = [f for f in known if not aud or not f.audience or _aud_ok(f.audience, aud)]
        cur, rev, hist = [], [], []
        for f in known:
            if self.opt.revisions and any(self.by_id[n].published <= iso(today) and _covers(self.by_id[n], lo, hi, self.opt)
                                          for n in self.revises.get(f.id, [])):
                rev.append(f)
                continue
            if _covers(f, lo, hi, self.opt):
                cur.append(f)
            elif self.opt.recurrence and f.end and f.end < lo and (cycle is None or (f.ptype == cycle[0] and (f.cycle or 0) < cycle[1])):
                hist.append(f)      # an earlier cycle of the same period type (rec edge) is the history of the target
        branches = defaultdict(list)
        for f in cur:
            branches[f.campus or "all"].append(f)
        if hist:  # keep only the most recent earlier cycle per key
            best = {}
            for f in hist:
                k = (f.ekey, f.group, f.campus)
                if k not in best or (f.cycle or 0) > (best[k].cycle or 0):
                    best[k] = f
            hist = [f for f in hist if (f.cycle or 0) == (best[(f.ekey, f.group, f.campus)].cycle or 0)]
        return dict(branches=dict(branches), revised=rev, history=hist)


def _stated_campus(quote):
    z = "中关村" in quote
    t = "通州" in quote or "潞城" in quote
    if (z and t) or "双校区" in quote or "两校区" in quote:
        return "both"
    return "zgc" if z else ("tz" if t else None)


def _scope_compatible(a, b):
    return a is None or b is None or a == b


def _aud_ok(fact_aud, user_aud):
    fa, ua = str(fact_aud), str(user_aud)
    return fa in ("all", "所有人", "师生", "全体师生") or fa in ua or ua in fa


def _overlap(a, b):
    a0, a1 = a.start or date.min, a.end or date.max
    b0, b1 = b.start or date.min, b.end or date.max
    return a0 <= b1 and b0 <= a1


def _covers(f, lo, hi, opt):
    """Validity [b, e] overlaps the target period. Facts without dates are valid from
    publication on (standing information) unless time anchoring is ablated."""
    if not opt.anchor_time:
        return True
    b = f.start or parse_date(f.published)
    e = f.end or date.max
    return b <= hi and lo <= e


def target_interval(expr, today):
    """Resolves the planner's target (a date, a named period of a year, or today)."""
    today = parse_date(today)
    if not expr:
        return today, today
    d = parse_date(expr.get("date")) if isinstance(expr, dict) else None
    if d:
        return d, d
    lo, hi = parse_date(expr.get("start")), parse_date(expr.get("end"))
    if lo or hi:
        return lo or today, hi or lo or today
    return today, today + timedelta(days=0)


# ---------------------------------------------------------------------------- loading
_cache = {}


def load_graph(opt=None, model=SYSTEM_MODEL):
    """Builds the evidence graph from data/notices.jsonl and the compiled notices under `opt`.
    Returns (graph, statistics); cached per (model, options)."""
    opt = opt or Options()
    key = (model, tuple(sorted(vars(opt).items())))
    if key in _cache:
        return _cache[key]
    docs = {json.loads(l)["doc_id"]: json.loads(l) for l in open(DATA / "notices.jsonl", encoding="utf8")}
    gaz = Gazetteer.load(DATA / "gazetteer.json")
    facts, passages = [], []
    n_docs = 0
    for line in open(compiled_path(model), encoding="utf8"):
        c = json.loads(line)
        d = docs.get(c["doc_id"])
        if not d:
            continue
        n_docs += 1
        facts += build_facts(d, c, gaz, opt)
        passages += build_passages(d, c, opt)
    g = EvidenceGraph(facts, opt, passages)
    src = Counter(f.campus_src or "none" for f in g.facts)
    stats = dict(notices=n_docs, facts_extracted=len(facts), facts_grounded=len(g.facts),
                 grounded_rate=len(g.facts) / max(1, len(facts)),
                 campus_scoped=sum(f.campus is not None for f in g.facts), campus_source=dict(src),
                 with_validity=sum(bool(f.start or f.end) for f in g.facts),
                 keys=len(g.by_key), revised_facts=len(g.revises), revises_edges=sum(len(v) for v in g.revises.values()),
                 recurs_edges=sum(len(v) for v in g.recurs.values()),
                 passages=len(g.passages), passages_scoped=sum(p["campus"] is not None for p in g.passages),
                 split_keys=sum(1 for fs in g.by_type.values()
                                if len({f.campus for f in fs if f.campus}) == 2))
    _cache[key] = (g, stats)
    return g, stats
