"""CondQA-Campus (Section 4.1): condition-dependent questions over real notices, with hidden contexts.

    python scripts/build_benchmark.py

The released data/benchmark.jsonl, gold_facts.jsonl and audit_sheet.csv were produced by this script. The
gold facts are extracted by Bonsai-27B and cross-checked by Qwen3-32B, so CondQA-Campus is independent of the
model under test (DeepSeek-V4.1-Flash) and of CampusScope's graph:
  A. source notices: service notices about hours, openings, schedules and adjustments;
  B. extraction by the *other* model (Bonsai-27B) over the whole notice;
  C. three checks, all must pass: (1) the quote occurs in the notice; (2) position check:
     the campus of the nearest preceding campus word in the notice (deterministic, no LLM);
     (3) Qwen3-32B re-reads the notice and independently states campus and dates;
  D. items are generated from verified facts; every item has a hidden context (campus,
     asking date) held by a simulated user, gold key tokens, and negative tokens (the
     value of the other campus / the earlier cycle / the pre-revision notice).
Item types: T1 scope stated, T2 silent campus, T3 stale cycle, T4 no current notice
(history), T5 revision, T6 control (condition implied by the named place).
Outputs data/benchmark_sources.jsonl, data/gold_facts.jsonl, data/benchmark.jsonl and
data/audit_sheet.csv (for manual verification before submission).
"""
import csv
import json
import random
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from campusscope.config import DATA
from campusscope.graph import ATTR_GROUP, Gazetteer, canon_type, entity_key, period_type, year_of
from campusscope.llm import chat, parse_json
from campusscope.text import anchor, clean, iso, parse_date, squash, value_tokens

SOURCE = re.compile(r"营业时间|开放时间|通宵自习|快专19|班车|浴室|熄灯|供暖|留校|开放安排|作息|服务时间|运行时刻|恢复运行|开放时段|免费时段")
TYPES = "食堂餐厅、超市商店、理发、浴室、开水房、快递收发、打印复印、图书馆、教学楼自习室、田径球场、健身房、游泳馆、体育场馆、班车交通、校医院、宿舍公寓、水电缴费、维修报修、供暖、酒店住宿、活动、其他"
ATTRS = "开放时间、开放状态、地点、电话、班次时刻、收费、办理方式、安排"

GOLD = f"""你是数据标注员。通读整篇高校服务通知，列出能回答师生“几点开/开不开/在哪/电话/班次”类问题的事实。
每条事实输出JSON对象：{{"entity":"服务点原文名称","type":"类型","attr":"属性","value":"取值(原文)",
"campus":"zgc|tz|both|unknown","start":"YYYY-MM-DD或null","end":"YYYY-MM-DD或null","quote":"逐字引文10-50字,须含取值"}}
type 取：{TYPES}。attr 取：{ATTRS}。zgc=中关村校区，tz=通州校区（含潞城）。
campus：按该事实所在的校区分区（小标题）判断；通知分“中关村校区”“通州校区”两部分时，后一部分的事实属于通州；通知只涉及一个校区时填该校区；判断不了填 unknown。
日期补全年份（结合发布日期）；该事实适用的日期段写在 start/end；没有写日期时用全文说明的适用期间。
一个服务点一个属性一个日期段一条；多个服务点共用一句时拆开。只输出JSON：{{"facts":[...]}}"""

CHECK = """你核对通知中事实的适用条件。对每个编号的事实，根据整篇通知判断：它适用于哪个校区（zgc=中关村校区，tz=通州校区，both=两校区都适用，unknown=无法判断），以及适用的起止日期（YYYY-MM-DD，没有则null）。
注意通知常按“中关村校区”“通州校区”分成两大部分，事实属于它所在的部分。
只输出JSON：{"checks":[{"i":编号,"campus":"...","start":"...","end":"..."}]}"""

QGEN = """你为校园服务问答评测写一句师生会问的口语化问题。要求：
- 问的是给定服务点/类型的给定属性（开放时间=几点开几点关；开放状态=开不开/开放吗；班次时刻=几点发车）。
- 必须包含“提到的名称”；{campus_rule}
- 时间表达：{time_rule}
- 不要写出答案，不超过30字。只输出JSON：{{"q":"..."}}"""


GUIDES = re.compile(r"攻略|指南|篇|专线|公交|开业|上新|短宿|空调|学习空间|打印机|离校|充值|街区")
NOT_GUIDES = re.compile(r"开放日|品鉴|投票|科普|光盘|招募|病虫害|消杀|绿植|趣味赛|面对面|座谈|代茶饮|鲜牛奶|安全小贴士|智慧餐饮|操作")


def pick_sources(docs):
    """Hours / openings / schedules (by title), plus practical guides whose text covers both campuses or
    Tongzhou (so that silent-campus questions have gold on both sides)."""
    out = []
    for d in docs:
        if not d["service"]:
            continue
        t = clean(d["text"])
        two = ("中关村" in t and re.search("通州|潞城", t)) or re.search("通州|潞城", d["title"])
        if SOURCE.search(d["title"]) or (two and GUIDES.search(d["title"]) and not NOT_GUIDES.search(d["title"])):
            out.append(d)
    return out


def _gold_items(content):
    got = parse_json(content)
    items = got.get("facts") if isinstance(got, dict) else got
    if not isinstance(items, list) or not items:
        items = [parse_json(m.group(0)) for m in re.finditer(r"\{[^{}]*\}", content or "")]
    return [x for x in items if isinstance(x, dict) and x.get("value")]


def extract_gold(doc):
    """Bonsai reads the whole notice; long notices are annotated window by window (the whole
    text stays in the prompt, so the campus part of each fact can still be judged)."""
    text = clean(doc["text"])
    head = f"标题：{clean(doc['title'])}\n发布日期：{doc['published']}\n"
    try:
        if len(text) <= 2000:
            rec = chat([dict(role="system", content=GOLD), dict(role="user", content=head + f"正文：{text[:8000]}")],
                       model="bonsai", max_tokens=7000, tag="gold_extract")
            return _gold_items(rec["content"])
        out = []
        for a in range(0, min(len(text), 9000), 1000):
            rec = chat([dict(role="system", content=GOLD),
                        dict(role="user", content=head + f"全文（仅用于判断事实属于哪个校区分区）：{text[:8000]}\n\n"
                                                         f"【只抽取下面这个片段中的事实】：{text[a:a + 1000]}")],
                       model="bonsai", max_tokens=2500, tag="gold_extract_win")
            out += _gold_items(rec["content"])
        return out
    except Exception as e:  # noqa: BLE001
        print("gold extraction failed:", doc["published"], doc["title"][:30], e, flush=True)
        return []


def position_campus(sq, p, quote_sq):
    """Deterministic check: campus word inside the quote, else the nearest one before it."""
    for w, c in (("中关村", "zgc"), ("通州", "tz"), ("潞城", "tz")):
        if w in quote_sq:
            return c
    best, pos = None, -1
    for w, c in (("中关村", "zgc"), ("通州", "tz"), ("潞城", "tz")):
        k = sq.rfind(w, 0, p)
        if k > pos:
            best, pos = c, k
    return best


def cross_check(doc, facts):
    text = clean(doc["text"])
    listing = "\n".join(f"{i}. {f.get('entity')}｜{f.get('attr')}｜{f.get('value')}｜引文：{f.get('quote')}" for i, f in enumerate(facts))
    rec = chat([dict(role="system", content=CHECK),
                dict(role="user", content=f"标题：{clean(doc['title'])}\n发布日期：{doc['published']}\n正文：{text[:8000]}\n\n事实：\n{listing}")],
               model="qwen", max_tokens=4000, tag="gold_check")
    got = parse_json(rec["content"])
    checks = got.get("checks") if isinstance(got, dict) else got
    return {c.get("i"): c for c in checks or [] if isinstance(c, dict)}


def verify(doc, facts, gaz):
    text = clean(doc["text"])
    sq = squash(text)
    checks = cross_check(doc, facts) if facts else {}
    out, stats = [], defaultdict(int)
    for i, f in enumerate(facts):
        stats["extracted"] += 1
        q = squash(str(f.get("quote") or ""))
        p = sq.find(q) if len(q) >= 4 else -1
        if p < 0:
            stats["drop_span"] += 1
            continue
        c_b = f.get("campus") if f.get("campus") in ("zgc", "tz", "both") else None
        c_pos = position_campus(sq, p, q) if ("中关村" in sq or "通州" in sq or "潞城" in sq) else None
        c_q = (checks.get(i) or {}).get("campus")
        c_q = c_q if c_q in ("zgc", "tz", "both") else None
        c_gaz = gaz.campus_of(str(f.get("entity") or "")) or gaz.campus_of(str(f.get("quote") or ""))
        votes = [c for c in (c_b, c_q, c_pos) if c]
        if not votes:
            campus = None                              # no campus stated anywhere: applies to both
        else:
            top, n = Counter(votes).most_common(1)[0]
            if n < 2:
                stats["drop_campus_disagree"] += 1     # fewer than two of the three checks agree
                continue
            campus = top
        s_b, e_b = anchor(parse_date(f.get("start")), doc["published"]), anchor(parse_date(f.get("end")), doc["published"])
        chk = checks.get(i) or {}
        s_q, e_q = anchor(parse_date(chk.get("start")), doc["published"]), anchor(parse_date(chk.get("end")), doc["published"])
        if s_b and s_q and s_b != s_q:
            stats["drop_dates"] += 1
            continue
        toks = value_tokens(str(f.get("value")))
        if not toks:
            stats["drop_no_tokens"] += 1
            continue
        attr = f.get("attr") if f.get("attr") in ATTR_GROUP else "安排"
        ent = str(f.get("entity") or "")
        stats["kept"] += 1
        out.append(dict(gid=f"{doc['doc_id']}#{i}", doc_id=doc["doc_id"], published=doc["published"], title=doc["title"],
                        entity=ent, ekey=entity_key(ent), type=canon_type(f.get("type"), ent), attr=attr,
                        group=ATTR_GROUP[attr], value=str(f.get("value")), tokens=toks,
                        campus=None if campus == "both" else campus, campus_votes=[c_b, c_q, c_pos, c_gaz],
                        start=iso(s_b or s_q), end=iso(e_b or e_q), quote=str(f.get("quote")),
                        ptype=period_type(doc.get("cycle") or "") or period_type(doc["title"]),
                        cycle=year_of(doc.get("cycle") or "", doc["published"])))
    return out, stats


# ------------------------------------------------------------------ item generation
TIME_TODAY = ["", "今天", "现在"]
CAMPUS_ZH = {"zgc": "中关村校区", "tz": "通州校区"}
PERIOD_ZH = {"寒假": "寒假期间", "暑假": "暑假期间", "国庆": "国庆假期", "考试周": "考试周", "期末": "期末", "春季学期": "这学期",
             "秋季学期": "这学期", "供暖": "供暖季"}


def ask_date(f):
    """Well inside the validity: the midpoint of a bounded interval, otherwise five days after it starts
    (a notice published on 4 July about arrangements starting on 7 July is not asked about on 6 July)."""
    s, e, pub = parse_date(f["start"]), parse_date(f["end"]), parse_date(f["published"])
    s = max(s or pub, pub)
    if e and e >= s:
        return s + (e - s) // 2
    return s + timedelta(days=5)


def common_date(a, b):
    """A date well inside the overlap of two validity intervals (None if they do not overlap)."""
    s = max(max(parse_date(x["start"]) or parse_date(x["published"]), parse_date(x["published"])) for x in (a, b))
    ends = [parse_date(x["end"]) for x in (a, b) if parse_date(x["end"])]
    e = min(ends) if ends else None
    if e and e < s:
        return None
    return s + (e - s) // 2 if e else s + timedelta(days=5)


def valid_on(f, d):
    s = parse_date(f["start"]) or parse_date(f["published"])
    e = parse_date(f["end"])
    return s <= d and (e is None or d <= e) and parse_date(f["published"]) <= d


def phrase(name, attr, time_phrase, campus_zh=None, style=0):
    campus_rule = f"必须写明“{campus_zh}”。" if campus_zh else "不要出现任何校区名称（中关村、通州、潞城、校区）。"
    time_rule = f"使用“{time_phrase}”" if time_phrase else "不写时间词（默认问当前）"
    styles = ["口语、简短", "像在微信群里随口一问", "礼貌地请问"]
    rec = chat([dict(role="system", content=QGEN.format(campus_rule=campus_rule, time_rule=time_rule)),
                dict(role="user", content=f"提到的名称：{name}\n属性：{attr}\n风格：{styles[style % 3]}")],
               model="qwen", max_tokens=80, tag="bench_q")
    q = (parse_json(rec["content"]) or {}).get("q", "") if isinstance(parse_json(rec["content"]), dict) else ""
    bad = (not q) or (name[:2] not in q) or (campus_zh is None and re.search(r"中关村|通州|潞城|校区", q)) \
        or (campus_zh is not None and campus_zh[:2] not in q)
    if bad:
        verb = {"开放时间": "几点开放", "开放状态": "开放吗", "班次时刻": "几点发车", "地点": "在哪里", "电话": "电话是多少"}.get(attr, "怎么安排")
        q = f"{time_phrase}{campus_zh or ''}{name}{verb}？"
    return q


def similar(a, b):
    """Same service point across notices: equal or contained keys, same attribute group, compatible campus."""
    if a["group"] != b["group"]:
        return False
    ka, kb = a["ekey"], b["ekey"]
    if not (ka == kb or (min(len(ka), len(kb)) >= 2 and (ka in kb or kb in ka))):
        return False
    return a["campus"] is None or b["campus"] is None or a["campus"] == b["campus"]


TYPE_WORD = {"田径球场": "田径场", "教学楼自习室": "自习室", "食堂餐厅": "食堂", "超市商店": "超市", "班车交通": "班车",
             "快递收发": "快递点", "打印复印": "打印店", "体育场馆": "体育场馆", "宿舍公寓": "宿舍", "水电缴费": "水电缴费"}


def build_items(gold, gaz, rng, corpus=()):
    """Item specs; the question is phrased later, only for the sampled items."""
    items = []
    by_type = defaultdict(list)
    for f in gold:
        by_type[(f["type"], f["group"])].append(f)

    def item(kind, f, spec, hidden, gold_tokens, neg=(), action="answer", extra=None):
        items.append(dict(kind=kind, spec=spec, hidden=hidden, today=hidden["today"], gold_action=action,
                          gold_tokens=list(gold_tokens), neg_tokens=[t for t in dict.fromkeys(neg) if t not in gold_tokens],
                          source=dict(gid=f["gid"], title=f["title"], published=f["published"], value=f["value"],
                                      quote=f["quote"], campus=f["campus"]), **(extra or {})))

    avail = [f for f in gold if f["group"] in ("availability", "schedule", "place", "phone")]
    # T1 scope stated / T6 scope implied by the named place
    for f in avail:
        d = ask_date(f)
        if not f["campus"] or not valid_on(f, d):
            continue
        others = [g for g in by_type[(f["type"], f["group"])] if g["campus"] and g["campus"] != f["campus"] and valid_on(g, d)]
        neg = [t for g in others for t in g["tokens"]]
        tp = rng.choice(TIME_TODAY)
        if gaz.campus_of(f["entity"]) == f["campus"]:
            item("T6", f, (f["entity"], f["attr"], tp, None), dict(campus=f["campus"], today=iso(d)), f["tokens"], neg)
        else:
            item("T1", f, (f["entity"], f["attr"], tp, CAMPUS_ZH[f["campus"]]), dict(campus=f["campus"], today=iso(d)),
                 f["tokens"], neg)
    # T2 silent campus (a): the same place name on both campuses (chains, "track field", ...), values differ
    seen = set()
    by_name = defaultdict(list)
    for f in avail:
        if f["campus"] and len(f["ekey"]) >= 2:
            by_name[(f["ekey"], f["group"])].append(f)
    for (ek, grp), fs in by_name.items():
        for fz in [f for f in fs if f["campus"] == "zgc"]:
            for ft in [f for f in fs if f["campus"] == "tz"]:
                d = common_date(fz, ft)
                if d is None:
                    continue
                if not (valid_on(fz, d) and valid_on(ft, d)) or set(fz["tokens"]) <= set(ft["tokens"]) or set(ft["tokens"]) <= set(fz["tokens"]):
                    continue
                name = re.sub(r"^(中关村校区|通州校区|中关村|通州)", "", fz["entity"]) or fz["entity"]
                key = (ek, grp, iso(d))
                if key in seen:
                    continue
                seen.add(key)
                tp = rng.choice(TIME_TODAY)
                for c, g, o in (("zgc", fz, ft), ("tz", ft, fz)):
                    item("T2", g, (name, fz["attr"], tp, None), dict(campus=c, today=iso(d)), g["tokens"], o["tokens"],
                         extra=dict(pair=len(seen)))
    # T2 silent campus (b): the same service type, homogeneous within each campus, different across campuses
    for (typ, _grp), fs in by_type.items():
        if typ == "其他":
            continue
        for fz in [f for f in fs if f["campus"] == "zgc"]:
            for ft in [f for f in fs if f["campus"] == "tz"]:
                d = common_date(fz, ft)
                if d is None:
                    continue
                if not (valid_on(fz, d) and valid_on(ft, d)) or set(fz["tokens"]) <= set(ft["tokens"]) or set(ft["tokens"]) <= set(fz["tokens"]) or fz["attr"] != ft["attr"]:
                    continue
                same_name = fz["ekey"] == ft["ekey"]
                if not same_name:     # type-level question: every place of that type must agree within each campus
                    per = {c: {tuple(g["tokens"]) for g in fs if g["campus"] == c and g["attr"] == fz["attr"] and valid_on(g, d)}
                           for c in ("zgc", "tz")}
                    if any(len(v) != 1 for v in per.values()):
                        continue
                name = fz["entity"] if same_name else TYPE_WORD.get(typ, typ)
                key = (name, fz["attr"], iso(d))
                if key in seen:
                    continue
                seen.add(key)
                tp = rng.choice(TIME_TODAY)
                for c, g, o in (("zgc", fz, ft), ("tz", ft, fz)):
                    item("T2", g, (name, fz["attr"], tp, None), dict(campus=c, today=iso(d)), g["tokens"], o["tokens"],
                         extra=dict(pair=len(seen)))
    # T3 stale cycle, T4 no current notice (history), T5 revision; one earlier fact per later fact
    ordered = sorted(avail, key=lambda f: f["published"])

    def distinct(a, b):
        """Values that a reader can tell apart: neither token set contains the other."""
        return not (set(a) <= set(b) or set(b) <= set(a))

    for i, new in enumerate(ordered):
        earlier = [o for o in ordered[:i] if o["doc_id"] != new["doc_id"] and o["published"] < new["published"]
                   and similar(o, new)]
        if not earlier:
            continue
        cz = CAMPUS_ZH.get(new["campus"]) if new["campus"] and not gaz.campus_of(new["entity"]) else None
        same_cycle_type = [o for o in earlier if new["ptype"] and o["ptype"] == new["ptype"] and o["cycle"] < new["cycle"]]
        if same_cycle_type:
            # the immediately preceding cycle of this kind of period in the whole gold set (not just for this
            # service point): if the point is missing from that cycle's notice, no stale/history item is made
            last = max(o["cycle"] for o in same_cycle_type)
            # the earlier cycle must be the immediately preceding one in the whole corpus: no other service notice
            # about the same kind of period may lie between it and the later notice (its facts may be images)
            first_old = min(o["published"] for o in same_cycle_type if o["cycle"] == last)
            between = [c for c in corpus if c["source"] and c["ptype"] == new["ptype"] and first_old < c["published"] < new["published"]
                       and not any(c["doc_id"] == o["doc_id"] for o in same_cycle_type)]
            if between:
                continue
            prev = [o for o in same_cycle_type if o["cycle"] == last]
            pp = PERIOD_ZH.get(new["ptype"], "")
            stale = [o for o in prev if distinct(o["tokens"], new["tokens"])]
            d = ask_date(new)
            if stale and valid_on(new, d):
                old = max(stale, key=lambda o: o["published"])
                item("T3", new, (new["entity"], new["attr"], pp, cz), dict(campus=new["campus"] or old["campus"], today=iso(d)),
                     new["tokens"], old["tokens"], extra=dict(stale=dict(published=old["published"], value=old["value"])))
            old = max(prev, key=lambda o: o["published"])
            d4 = parse_date(new["published"]) - timedelta(days=10)
            # "no current notice yet" must hold for the whole corpus: no other notice between the earlier cycle
            # and the asking date may mention this service point together with the same kind of period
            ek = squash(new["entity"])
            newer = [c for c in corpus if old["published"] < c["published"] <= iso(d4) and c["doc_id"] != old["doc_id"]
                     and len(ek) >= 2 and ek in c["sq"] and (new["ptype"] or "") in c["sq"]]
            if parse_date(old["end"] or old["published"]) < d4 and not newer:
                item("T4", old, (new["entity"], new["attr"], "今年" + (pp or "这段时间"), cz),
                     dict(campus=new["campus"] or old["campus"], today=iso(d4)), old["tokens"], [], action="history",
                     extra=dict(history_year=old["cycle"]))
            continue
        if re.search(r"增加|新增|增设|延长|增开", new["quote"] + new["value"]):
            continue          # an added slot does not replace the earlier value: not a revision
        s_new = parse_date(new["start"]) or parse_date(new["published"])
        rev = [o for o in earlier if not (new["ptype"] and o["ptype"] == new["ptype"]) and distinct(o["tokens"], new["tokens"])
               and (parse_date(o["end"]) is None or parse_date(o["end"]) >= s_new)]
        if rev:
            old = max(rev, key=lambda o: o["published"])
            d = max(s_new, parse_date(new["published"])) + timedelta(days=2)
            if valid_on(new, d):
                item("T5", new, (new["entity"], new["attr"], "", cz), dict(campus=new["campus"] or old["campus"], today=iso(d)),
                     new["tokens"], old["tokens"], extra=dict(revised=dict(published=old["published"], value=old["value"])))
    return items


def main():
    rng = random.Random(20260925)
    docs = [json.loads(l) for l in open(DATA / "notices.jsonl", encoding="utf8")]
    src = pick_sources(docs)
    with open(DATA / "benchmark_sources.jsonl", "w", encoding="utf8") as f:
        for d in src:
            f.write(json.dumps(dict(doc_id=d["doc_id"], published=d["published"], title=d["title"]), ensure_ascii=False) + "\n")
    gaz = Gazetteer.load(DATA / "gazetteer.json")
    with ThreadPoolExecutor(max_workers=8) as ex:
        raw = list(ex.map(extract_gold, src))
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(lambda a: verify(a[0], a[1], gaz), zip(src, raw)))
    gold = [g for r, _ in res for g in r]
    stats = defaultdict(int)
    for _, s in res:
        for k, v in s.items():
            stats[k] += v
    with open(DATA / "gold_facts.jsonl", "w", encoding="utf8") as f:
        for g in gold:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    src_ids = {d["doc_id"] for d in src}
    corpus = [dict(doc_id=d["doc_id"], published=d["published"], sq=squash(clean(d["text"])), title=d["title"],
                   source=d["doc_id"] in src_ids, ptype=period_type(d.get("cycle") or "") or period_type(d["title"]))
              for d in docs]
    items = build_items(gold, gaz, rng, corpus)
    # cap each type (T2 pairs stay together), then phrase only the sampled questions
    by_kind = defaultdict(list)
    for it in items:
        by_kind[it["kind"]].append(it)
    final = []
    caps = dict(T1=60, T2=120, T3=70, T4=60, T5=60, T6=50)
    for k in sorted(by_kind):
        its = by_kind[k]
        if k == "T2":
            pairs = defaultdict(list)
            for it in its:
                pairs[it["pair"]].append(it)
            keys = sorted(pairs)
            rng.shuffle(keys)
            for key in keys[:caps[k] // 2]:
                final += pairs[key]
        else:
            rng.shuffle(its)
            final += its[:caps.get(k, 60)]
    specs = sorted({it["spec"] for it in final}, key=str)
    with ThreadPoolExecutor(max_workers=8) as ex:
        qs = dict(zip(specs, ex.map(lambda sp: phrase(sp[0], sp[1], sp[2], sp[3], len(sp[0])), specs)))
    for i, it in enumerate(final):
        it["id"] = f"{it['kind']}-{i:04d}"
        it["question"] = qs[it.pop("spec")]
    final.sort(key=lambda x: x["id"])
    with open(DATA / "benchmark.jsonl", "w", encoding="utf8") as f:
        for it in final:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    with open(DATA / "audit_sheet.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "kind", "question", "hidden_campus", "today", "gold_action", "gold_tokens", "neg_tokens",
                    "source_title", "source_published", "source_quote", "ok(Y/N)", "note"])
        for it in final:
            s = it["source"]
            w.writerow([it["id"], it["kind"], it["question"], it["hidden"]["campus"], it["today"], it["gold_action"],
                        " ".join(it["gold_tokens"]), " ".join(it["neg_tokens"]), s["title"], s["published"], s["quote"], "", ""])
    (DATA / "benchmark_stats.json").write_text(json.dumps(dict(
        sources=len(src), gold_stats=dict(stats), gold_facts=len(gold),
        generated=dict(Counter(i["kind"] for i in items)), kept=dict(Counter(i["kind"] for i in final)), items=len(final)),
        ensure_ascii=False, indent=1), encoding="utf8")
    print("sources", len(src), "| gold stats", dict(stats), "| gold facts", len(gold))
    print("items generated", Counter(i["kind"] for i in items), "-> kept", Counter(i["kind"] for i in final), len(final))


if __name__ == "__main__":
    main()
