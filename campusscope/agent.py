"""CampusScope's online agent (paper Sections 2.3 and 3.2): plan with the LLM, reason over the condition-scoped
evidence graph, write, verify.

    plan      (LLM)   service point / type, attribute, stated conditions, target period
    ground    (Milvus hybrid over fact nodes) -> seed facts -> branch set via graph keys
    reason    (graph) applicability sigma*(f) |= x, validity at the target, revisions, earlier
                      cycles (Eq. 1); condition frontier; cost-sensitive action (Eq. 2)
    write     (LLM)   from licensed facts only, conditions and years stated
    verify            clock times in the reply must come from licensed facts (else rewrite / template)

The LLM only plans and writes: which evidence applies and whether to guess, list or ask are computed on the
graph. Fact and passage search use the collections built under the agent's own options
(config.collections_for), so an ablation never searches an index that carries the component it removes.
"""
import re
from datetime import date

from .config import SYSTEM_MODEL, collections_for
from .graph import ATTR_GROUP, Options, entity_key, load_graph
from .llm import chat, parse_json
from .policy import DEFAULT_BETA, DEFAULT_LAMBDA, decide
from .search import fact_nodes
from .search import passages as passage_search
from .text import TIME, iso, norm_answer, parse_date, squash, undouble

CAMPUS_ZH = {"zgc": "中关村校区", "tz": "通州校区"}
PERIODS = {"寒假": ((1, 12), (2, 28)), "暑假": ((7, 8), (8, 31)), "国庆": ((10, 1), (10, 7)), "五一": ((5, 1), (5, 5)),
           "春节": ((1, 25), (2, 20)), "考试周": ((6, 1), (7, 5)), "期末": ((12, 1), (1, 10))}
TYPES = ("食堂餐厅、超市商店、理发、浴室、开水房、快递收发、打印复印、图书馆、教学楼自习室、田径球场、健身房、游泳馆、"
         "体育场馆、班车交通、校医院、宿舍公寓、水电缴费、维修报修、供暖、酒店住宿、活动、其他")
ATTRS = "开放时间、开放状态、地点、电话、班次时刻、收费、办理方式、安排"

PLAN = f"""你是校园服务智能体的规划器，今天是{{today}}。读对话，输出JSON：
{{"entity":"用户说到的具体服务点名称（照抄原话），只说了类型就填null","type":"类型","attr":"属性",
"campus":"zgc|tz|null（只有用户在对话中说明了校区才填）","audience":"本科生|研究生|教职工|null",
"target":{{"kind":"now|date|period","date":"YYYY-MM-DD或null","period":"寒假|暑假|国庆|五一|春节|考试周|期末|null","year":年份或null}},
"query":"用于检索的简短中文查询（服务点+属性+时间）"}}
type 取：{TYPES}。attr 取：{ATTRS}（几点开=开放时间；开不开/是否开放=开放状态；几点发车=班次时刻）。
target：问“现在/今天/这周”或没说时间为 now；问具体某天为 date；问“寒假/暑假/国庆期间”等为 period（year 为所指那一次假期的年份）。只输出JSON。"""

WRITE = """你是校园综合服务助手，今天是{today}。只根据“许可证据”写简短中文答复（不超过120字）。
- 写明适用的校区和日期；证据里没有的时间、地点、电话一律不写。优先使用结构化事实；补充原文段落只能在其标注的校区和日期内使用。
- 本次答复方式（mode={mode}）：{mode_rule}
- 同一服务点有多条证据时，以发布日期最新的为准；如果有“已调整的旧安排”，用一句话说明已按新通知调整。
只输出JSON：{{"answer":"..."}}"""
# one rule per mode, filled in only for the mode chosen
MODE_RULE = {"answer": "直接回答。",
             "assume": "先说明“以下按{campus}回答”，并提醒另一校区安排不同。",
             "enumerate": "分校区列出各自的安排，每条写明校区。",
             "history": "说明目前还没有找到今年的正式通知，给出往年的安排并写明年份，仅供参考，以正式通知为准。"}


_NULL = (None, "", "null", "None", "none", "NULL", "无", "未知")
AUDIENCE_WORDS = re.compile(r"本科|研究生|硕士|博士|教职工|老师|教工|留学生")


def _clean_plan(p):
    """Models write the string "null" for unknown fields; unknown must mean None."""
    out = {k: (None if v in _NULL else v) for k, v in p.items() if not isinstance(v, dict)}
    t = p.get("target") if isinstance(p.get("target"), dict) else {}
    out["target"] = {k: (None if v in _NULL else v) for k, v in t.items()}
    return out


_GAZ = None


def _gazetteer():
    global _GAZ
    if _GAZ is None:
        from .config import DATA
        from .graph import Gazetteer
        _GAZ = Gazetteer.load(DATA / "gazetteer.json")
    return _GAZ


def _dialog(conv):
    return "\n".join(("用户：" if t["role"] == "user" else "助手：") + t["text"] for t in conv)


def _fmt(f):
    when = f"{iso(f.start) or ''}至{iso(f.end) or ''}" if (f.start or f.end) else "长期有效"
    return (f"[{f.id}] {f.entity}｜{f.attr}：{f.value}｜校区：{CAMPUS_ZH.get(f.campus, '未注明/通用')}｜适用：{when}"
            f"｜来源：《{f.title}》{f.published}")


class CampusScope:
    def __init__(self, model=SYSTEM_MODEL, opt=None, lam=DEFAULT_LAMBDA, beta=DEFAULT_BETA, planner=True,
                 compile_model=SYSTEM_MODEL, name=None):
        self.model, self.opt, self.lam, self.beta, self.use_planner = model, opt or Options(), lam, beta, planner
        self.g, _ = load_graph(self.opt, compile_model)
        self.fact_coll, self.passage_coll = collections_for(self.opt)     # the index built under the same options
        self.name = name or "CampusScope"

    # ------------------------------------------------------------------ plan
    def plan(self, conv, today):
        if self.use_planner:
            rec = chat([dict(role="system", content=PLAN.replace("{today}", today)), dict(role="user", content=_dialog(conv))],
                       model=self.model, max_tokens=300, tag="agent_plan")
            p = parse_json(rec["content"])
            return _clean_plan(p if isinstance(p, dict) else {}), 1, rec["latency"]
        text = " ".join(t["text"] for t in conv if t["role"] == "user")
        target = {"kind": "now"}
        for per in PERIODS:
            if per in text:
                target = {"kind": "period", "period": per}
        campus = "tz" if re.search("通州|潞城", text) else ("zgc" if "中关村" in text else None)
        return dict(entity=None, type=None, attr=None, campus=campus, target=target, query=text), 0, 0.0

    def target(self, plan, cands, today, user_text=""):
        t = plan.get("target") or {}
        d0 = parse_date(today)
        if t.get("kind") == "date" and parse_date(t.get("date")):
            d = parse_date(t["date"])
            return d, d, None
        per = t.get("period")
        if t.get("kind") == "period" and per in PERIODS:
            (m0, d0_), (m1, d1) = PERIODS[per]
            # "this winter break" asked in December means the coming one: the cycle is the current or next
            # occurrence unless the user names a year or says last/next year
            explicit = re.search(r"20\d{2}|去年|前年|明年|上一?个|下一?个", user_text)
            year = t.get("year") if (explicit and isinstance(t.get("year"), int)) else None
            if year is None:
                end_this = date(d0.year, m1, d1)
                if m1 < m0:       # a break spanning new year (e.g. 期末 Dec-Jan) is keyed by its start year
                    end_this = date(d0.year + (0 if d0.month <= m1 else 1), m1, d1)
                year = d0.year if d0 <= end_this else d0.year + 1
                if m1 < m0:
                    year = end_this.year - 1
            same = [f for f in cands if f.ptype == per and f.cycle == year and f.start]
            if same:
                return min(f.start for f in same), max((f.end or f.start) for f in same), (per, year)
            lo = date(year, m0, d0_)
            hi = date(year + (1 if m1 < m0 else 0), m1, d1)
            return lo, hi, (per, year)
        return d0, d0, None

    # ------------------------------------------------------------------ reason
    def ground(self, plan, conv, today):
        q = plan.get("query") or " ".join(t["text"] for t in conv if t["role"] == "user")
        hits = fact_nodes(q, today, limit=40, collection=self.fact_coll)
        facts = [self.g.by_id[h["metadata"]["fact_id"]] for h in hits if h["metadata"].get("fact_id") in self.g.by_id]
        ent = squash(undouble(plan.get("entity") or ""))
        typ, attr = plan.get("type"), plan.get("attr")
        grp = ATTR_GROUP.get(attr)
        user_text = " ".join(t["text"] for t in conv if t["role"] == "user")
        # the named service point, looked up in the whole graph (retrieval may not rank it in the top 40)
        specific = self.g.lookup(plan.get("entity"), user_text, grp) if self.opt.expand_keys else []
        if not specific:
            specific = [f for f in facts if ent and len(ent) >= 2 and (ent in f.ekey or f.ekey in ent) and (not grp or f.group == grp)]
        typed = [f for f in facts if typ and f.type == typ and (not grp or f.group == grp)]
        seeds = specific or typed or facts[:5]
        etype = None if specific else (typ or (seeds[0].type if seeds else None))
        group = grp or (seeds[0].group if seeds else None)
        cands = self.g.candidates(seeds, etype=etype, group=group)
        if specific:     # a named service point: keep its key only (its campus is implied)
            keys = {(f.ekey, f.group) for f in specific}
            cands = [f for f in cands if (f.ekey, f.group) in keys]
        self._rank = {f.id: i for i, f in enumerate(facts)}      # retrieval order, used to keep the best evidence
        return cands, etype or (seeds[0].type if seeds else "其他"), bool(specific)

    def scoped_passages(self, plan, conv, today, campus, target, k=4):
        """Supplementary evidence: section passages whose inherited scope admits the user's campus and whose
        validity (for period notices) overlaps the target period."""
        q = plan.get("query") or " ".join(t["text"] for t in conv if t["role"] == "user")
        hits = passage_search(q, today, campus=campus, limit=10, collection=self.passage_coll)
        lo, hi = target
        out = []
        for h in hits:
            p = self.g.passage_by_id.get(h["metadata"].get("passage_id"))
            if not p or (campus and p["campus"] not in (campus, None)):
                continue
            if (p["start"] or p["end"]) and not ((p["start"] or date.min) <= hi and lo <= (p["end"] or date.max)):
                continue
            out.append(p)
        return out[:k]

    def cycle_facts(self, plan, cycle, today, group):
        """Facts of the target cycle's own notice for the named service point, matched by containment of the
        normalized name (a notice may list 拳道馆 as 拳道馆健身房 or 公共教学2楼 by floor), so that a published
        notice of this cycle is not mistaken for one that is not out yet."""
        n = entity_key(plan.get("entity") or "")
        if len(n) < 2:
            return []
        return [f for f in self.g.facts if f.ptype == cycle[0] and f.cycle == cycle[1] and f.published <= today
                and (not group or f.group == group) and (n in f.ekey or (len(f.ekey) >= 2 and f.ekey in n))]

    def current_passages(self, plan, conv, today, campus, target, cycle):
        """Scoped passages that state the arrangement in force at the target: of the target cycle's own notice
        for a named break, or carrying dates that cover the target otherwise. Undated passages do not count,
        so standing text never stands in for a break whose notice is not out yet."""
        lo, hi = target
        out = []
        for p in self.scoped_passages(plan, conv, today, campus, target):
            if cycle:
                if p["ptype"] == cycle[0] and p["cycle"] == cycle[1]:
                    out.append(p)
            elif (p["start"] or p["end"]) and (p["start"] or date.min) <= lo and hi <= (p["end"] or date.max):
                out.append(p)
        return out

    def cycle_status(self, plan, conv, today, campus, cands, st, target, cycle, audience):
        """For a named break: decide whether its own notice is out before falling back to an earlier cycle.

        Returns (cands, st, branches, hist_passages, cur_passages). Labeled history is used only if no notice
        of the target cycle published by today mentions the service point (by fact or by scoped passage)."""
        branches = st["branches"]
        hist_passages, cur_passages = [], []
        if not (cycle and self.opt.recurrence):
            return cands, st, branches, hist_passages, cur_passages

        def of_cycle(br):
            return [f for fs in br.values() for f in fs if f.ptype == cycle[0] and f.cycle == cycle[1]]

        if not of_cycle(branches):
            seen = {f.id for f in cands}
            extra = [f for f in self.cycle_facts(plan, cycle, iso(parse_date(today)), ATTR_GROUP.get(plan.get("attr")))
                     if f.id not in seen]
            if extra:
                cands = cands + extra
                st = self.g.status(cands, dict(campus=None, audience=audience), today, target, cycle)
                branches = st["branches"]
        if not of_cycle(branches):
            if self.opt.passages:
                cur_passages = self.current_passages(plan, conv, today, campus, target, cycle)
                if not cur_passages:
                    hist_passages = self.history_passages(plan, conv, today, campus, cycle)
            if (st["history"] or hist_passages) and not cur_passages:
                branches = {}
        return cands, st, branches, hist_passages, cur_passages

    def history_passages(self, plan, conv, today, campus, cycle, k=3):
        """Passages of the same kind of period from the most recent earlier cycle (passage-level rec edges)."""
        q = plan.get("query") or " ".join(t["text"] for t in conv if t["role"] == "user")
        hits = passage_search(q, today, campus=campus, limit=12, collection=self.passage_coll)
        ps = [self.g.passage_by_id.get(h["metadata"].get("passage_id")) for h in hits]
        ps = [p for p in ps if p and p["ptype"] == cycle[0] and (p["cycle"] or 0) < cycle[1]
              and (not campus or p["campus"] in (campus, None))]
        if not ps:
            return []
        last = max(p["cycle"] for p in ps)
        return [p for p in ps if p["cycle"] == last][:k]

    def respond(self, conv, today, must_answer=False):
        plan, calls, lat = self.plan(conv, today)
        user_text = " ".join(t["text"] for t in conv if t["role"] == "user")
        # a campus is known only if the user said it (the planner's guess is not evidence), or, as an
        # implicit condition, if a place the user named belongs to one campus (gazetteer)
        stated = "tz" if re.search("通州|潞城", user_text) else ("zgc" if "中关村" in user_text else None)
        campus = stated
        if campus is None and self.opt.gazetteer:
            campus = _gazetteer().campus_of(user_text)
        cands, etype, specific = self.ground(plan, conv, today)
        lo, hi, cycle = self.target(plan, cands, today, user_text)
        # an audience restricts the evidence only if the user said who they are
        audience = plan.get("audience") if AUDIENCE_WORDS.search(user_text) else None
        st = self.g.status(cands, dict(campus=None, audience=audience), today, (lo, hi), cycle)
        # a named break whose own notice is not out yet: regular (standing) arrangements do not tell what
        # happens during the break, the same break of the last cycle (rec edge) does -> labeled history
        cands, st, branches, hist_passages, cur_passages = self.cycle_status(
            plan, conv, today, campus, cands, st, (lo, hi), cycle, audience)
        trace = dict(plan=plan, campus=campus, target=[iso(lo), iso(hi)], cycle=cycle, candidates=len(cands),
                     branches={k: [f.id for f in v] for k, v in branches.items()},
                     history=[f.id for f in st["history"]], revised=[f.id for f in st["revised"]])
        if campus:
            use = {campus: branches.get(campus, []) + branches.get("all", [])}
            use = {k: v for k, v in use.items() if v}
            mode, assumed = ("answer", None) if use else (None, None)
        else:
            camp = {k: v for k, v in branches.items() if k in ("zgc", "tz")}
            common = branches.get("all", [])
            if len(camp) >= 2:
                action, best, costs = decide(camp, etype, self.lam, self.beta, can_ask=not must_answer)
                trace["costs"] = costs
                trace["frontier"] = bool(costs)         # the campus branches disagree
                if action == "ask":
                    trace["decision"] = "ask"
                    return dict(action="ask", slot="campus", text="请问您在哪个校区（中关村校区还是通州校区）？两个校区的安排不同。",
                                calls=calls, latency=lat, trace=trace)
                if action == "assume":
                    use, mode, assumed = {best: camp[best] + common}, "assume", best
                elif action == "enumerate":
                    use, mode, assumed = {k: v + common for k, v in camp.items()}, "enumerate", None
                else:
                    use, mode, assumed = {k: v + common for k, v in camp.items()}, "answer", None
            else:
                use = {k: v for k, v in branches.items() if v}
                mode, assumed = ("answer", None) if use else (None, None)
        facts = [f for fs in (use or {}).values() for f in fs] if mode else []
        scoped = []
        if not facts and self.opt.passages and not cur_passages and not hist_passages:
            # before falling back to an earlier cycle, a dated passage in force at the target answers
            cur_passages = self.current_passages(plan, conv, today, campus or assumed, (lo, hi), cycle)
        if not facts and not cur_passages:
            hist = [f for f in st["history"] if not campus or f.campus in (campus, None)]
            if hist or hist_passages:
                mode, facts, scoped = "history", hist, hist_passages
        if mode != "history" and self.opt.passages:
            # what the extractor missed is still reachable, with the scope of its section
            scoped = self.scoped_passages(plan, conv, today, campus or assumed, (lo, hi))
            if not facts and scoped:
                mode = "answer"
        trace["passages"] = [p["id"] for p in scoped]
        if not facts and not scoped:
            trace["decision"] = "abstain"
            return dict(action="abstain", text="目前的通知里没有找到适用于您情况的安排，建议咨询相关服务部门或关注“温馨人大”通知。",
                        calls=calls, latency=lat, trace=trace)
        trace["decision"] = mode
        rank = getattr(self, "_rank", {})
        # the newest notice first: when one service point has several standing facts, the latest governs
        facts = sorted(facts, key=lambda f: (-int(f.published.replace("-", "")), rank.get(f.id, 999)))[:12]
        facts = sorted(facts, key=lambda f: (f.campus or "", f.entity, f.published), reverse=False)
        revised = [f for f in st["revised"] if f.ekey in {x.ekey for x in facts}][:3]
        evidence = "\n".join(_fmt(f) for f in facts) or "（无结构化事实）"
        if scoped:
            evidence += "\n补充原文段落（已标注作用域，只能在所标校区和日期内使用）：\n" + "\n".join(
                f"[{CAMPUS_ZH.get(p['campus'], '未注明校区')}{'｜' + ' › '.join(p['path']) if p['path'] else ''}"
                f"｜《{p['title']}》{p['published']}] "
                f"{p['text'][:300]}" for p in scoped)
        if revised:
            evidence += "\n已调整的旧安排（不要当作当前安排）：\n" + "\n".join(_fmt(f) for f in revised)
        ctx = f"mode={mode}" + (f"；按{CAMPUS_ZH[assumed]}" if assumed else "") + (f"；用户校区：{CAMPUS_ZH[campus]}" if campus else "")
        if cycle:
            ctx += f"；用户问的是{cycle[1]}年{cycle[0]}"
            if mode == "history":
                years = sorted({f.cycle for f in facts if f.cycle} | {p["cycle"] for p in scoped if p.get("cycle")})
                ctx += f"（尚无该期通知），证据来自{'、'.join(str(y) for y in years)}年{cycle[0]}"
        rule = MODE_RULE[mode].format(campus=CAMPUS_ZH.get(assumed, ""))
        msgs = [dict(role="system", content=WRITE.format(today=today, mode=mode, mode_rule=rule)),
                dict(role="user", content=f"对话：\n{_dialog(conv)}\n\n{ctx}\n许可证据：\n{evidence}")]
        rec = chat(msgs, model=self.model, max_tokens=400, tag="agent_write")
        calls, lat = calls + 1, lat + rec["latency"]
        ans = str((parse_json(rec["content"]) or {}).get("answer") if isinstance(parse_json(rec["content"]), dict) else rec["content"])
        allowed = {f"{int(h)}:{m}" for f in facts + revised for h, m in TIME.findall(undouble(f.value + f.quote))}
        allowed |= {f"{int(h)}:{m}" for p in scoped for h, m in TIME.findall(p["text"])}
        bad = [t for t in {f"{int(h)}:{m}" for h, m in TIME.findall(norm_answer(ans))} if t not in allowed]
        trace["verify"] = bad
        if bad:
            msgs += [dict(role="assistant", content=rec["content"]),
                     dict(role="user", content=f"答复中的时间 {bad} 不在许可证据里，请只用证据中的时间重写。只输出JSON。")]
            rec = chat(msgs, model=self.model, max_tokens=400, tag="agent_revise")
            calls, lat = calls + 1, lat + rec["latency"]
            p = parse_json(rec["content"])
            ans = str(p.get("answer")) if isinstance(p, dict) and p.get("answer") else ans
            bad = [t for t in {f"{int(h)}:{m}" for h, m in TIME.findall(norm_answer(ans))} if t not in allowed]
            if bad:
                trace["fallback"] = True
                ans = "；".join(f"{CAMPUS_ZH.get(f.campus, '')}{f.entity}{f.attr}：{f.value}" +
                               (f"（{f.cycle}年，仅供参考）" if mode == "history" else "") for f in facts[:6])
        action = "history" if mode == "history" else ("enumerate" if mode == "enumerate" else "answer")
        return dict(action=action, text=ans, calls=calls, latency=lat, trace=trace)
