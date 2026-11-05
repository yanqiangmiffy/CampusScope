"""CampusScope's answer, one event per step (the system's CampusScope.respond as a generator).

The decisions are the system's (same plan prompt, retrieval, graph reasoning, policy, writer prompt and
check: campusscope/agent.py), so a scenario gives the answer the paper reports;
what changes is that every step is sent as soon as it is done, the writer's reply is streamed token
by token, and the evidence subgraph is sent for the interactive graph.

Events (see docs/event-protocol.md): stage, graph, used, delta, retry, answer, and an internal
`summary` (calls, latency, cached) that QAService folds into the terminal `complete` event.
"""
import re
import time
from collections.abc import Iterator

from app import system  # noqa: F401
from app.services import graph_service, llm_probe
from app.services.llm_stream import AnswerStream, stream_chat

from campusscope import search
from campusscope.agent import (
    AUDIENCE_WORDS,
    CAMPUS_ZH,
    MODE_RULE,
    PLAN,
    WRITE,
    CampusScope,
    _clean_plan,
    _dialog,
    _fmt,
    _gazetteer,
)
from campusscope.llm import chat, parse_json
from campusscope.policy import campus_prior, decide
from campusscope.text import TIME, iso, norm_answer, undouble

# the system's fixed replies (CampusScope.respond)
ASK_TEXT = "请问您在哪个校区（中关村校区还是通州校区）？两个校区的安排不同。"
ABSTAIN_TEXT = "目前的通知里没有找到适用于您情况的安排，建议咨询相关服务部门或关注“温馨人大”通知。"


def _ms(t0: float) -> int:
    return round((time.perf_counter() - t0) * 1000)


def stage(sid: str, status: str, t0: float | None = None, **data) -> dict:
    ev = dict(type="stage", id=sid, status=status, data=data)
    if t0 is not None:
        ev["ms"] = _ms(t0)
    return ev


class StreamingCampusScope(CampusScope):

    def stream(self, conv: list[dict], today: str) -> Iterator[dict]:
        t_all = time.perf_counter()
        search.reset_flags()
        calls, cached_all = 0, True
        user_text = " ".join(t["text"] for t in conv if t["role"] == "user")

        def summary():
            return dict(type="summary", calls=calls, latency=round(time.perf_counter() - t_all, 2), cached=cached_all)

        # ---------------------------------------------------------------- 1 plan (LLM)
        yield stage("plan", "running")
        t0 = time.perf_counter()
        rec = chat([dict(role="system", content=PLAN.replace("{today}", today)), dict(role="user", content=_dialog(conv))],
                   model=self.model, max_tokens=300, tag="agent_plan", retries=llm_probe.retries(self.model))
        calls += 1
        cached_all &= bool(rec.get("cached"))
        p = parse_json(rec["content"])
        plan = _clean_plan(p if isinstance(p, dict) else {})
        stated = "tz" if re.search("通州|潞城", user_text) else ("zgc" if "中关村" in user_text else None)
        campus, campus_how = stated, ("stated" if stated else None)
        if campus is None and self.opt.gazetteer:
            campus = _gazetteer().campus_of(user_text)
            campus_how = "gazetteer" if campus else None
        yield stage("plan", "done", t0, plan=plan, campus=campus, campusHow=campus_how, cached=bool(rec.get("cached")))

        # ---------------------------------------------------------------- 2 retrieval + graph expansion
        yield stage("ground", "running")
        t0 = time.perf_counter()
        cands, etype, specific = self.ground(plan, conv, today)
        keys = sorted({f.entity for f in cands})
        yield stage("ground", "done", t0, hits=len(getattr(self, "_rank", {})), candidates=len(cands),
                    specific=specific, etype=etype, entities=keys[:12], nEntities=len(keys), degraded=search.bm25_only())

        # ---------------------------------------------------------------- 3 target period
        t0 = time.perf_counter()
        lo, hi, cycle = self.target(plan, cands, today, user_text)
        tg = plan.get("target") or {}
        yield stage("target", "done", t0, lo=iso(lo), hi=iso(hi), cycle=list(cycle) if cycle else None,
                    kind=tg.get("kind") or "now")

        # ---------------------------------------------------------------- 4 applicability on the graph
        yield stage("apply", "running")
        t0 = time.perf_counter()
        audience = plan.get("audience") if AUDIENCE_WORDS.search(user_text) else None
        st = self.g.status(cands, dict(campus=None, audience=audience), today, (lo, hi), cycle)
        branches = st["branches"]
        hist_passages = []
        if cycle and self.opt.recurrence:
            of_cycle = [f for fs in branches.values() for f in fs if f.ptype == cycle[0] and f.cycle == cycle[1]]
            if not of_cycle:
                if self.opt.passages:
                    hist_passages = self.history_passages(plan, conv, today, campus, cycle)
                if st["history"] or hist_passages:
                    branches = {}
        future = sum(f.published > today for f in cands)
        yield dict(type="graph", graph=graph_service.build(self.g, cands, st, today, lo, hi, cycle, branches))
        yield stage("apply", "done", t0, branches={k: len(v) for k, v in branches.items()}, revised=len(st["revised"]),
                    history=len(st["history"]), future=future, audience=audience)

        # ---------------------------------------------------------------- 5 cost-sensitive decision
        t0 = time.perf_counter()
        costs, best, prior, assumed = None, None, None, None
        if campus:
            use = {campus: branches.get(campus, []) + branches.get("all", [])}
            use = {k: v for k, v in use.items() if v}
            mode = "answer" if use else None
        else:
            camp = {k: v for k, v in branches.items() if k in ("zgc", "tz")}
            common = branches.get("all", [])
            if len(camp) >= 2:
                action, best, costs = decide(camp, etype, self.lam, self.beta, can_ask=True)
                prior = campus_prior(etype)
                if action == "ask":
                    yield stage("decide", "done", t0, decision="ask", costs=costs, best=best, prior=prior, lam=self.lam,
                                beta=self.beta, sizes={k: len(v) for k, v in camp.items()}, etype=etype)
                    ids = [f.id for fs in camp.values() for f in fs] + [f.id for f in common]
                    yield dict(type="used", ids=ids, mode="ask", passages=[])
                    yield dict(type="answer", text=ASK_TEXT, action="ask")
                    yield summary()
                    return
                if action == "assume":
                    use, mode, assumed = {best: camp[best] + common}, "assume", best
                elif action == "enumerate":
                    use, mode = {k: v + common for k, v in camp.items()}, "enumerate"
                else:
                    use, mode = {k: v + common for k, v in camp.items()}, "answer"
            else:
                use = {k: v for k, v in branches.items() if v}
                mode = "answer" if use else None
        facts = [f for fs in (use or {}).values() for f in fs] if mode else []
        scoped = []
        if not facts:
            hist = [f for f in st["history"] if not campus or f.campus in (campus, None)]
            if hist or hist_passages:
                mode, facts, scoped = "history", hist, hist_passages
        if mode != "history" and self.opt.passages:
            scoped = self.scoped_passages(plan, conv, today, campus or assumed, (lo, hi))
            if not facts and scoped:
                mode = "answer"
        decision = mode if (facts or scoped) else "abstain"
        yield stage("decide", "done", t0, decision=decision, costs=costs, best=best, prior=prior, lam=self.lam,
                    beta=self.beta, etype=etype, assumed=assumed, degraded=search.bm25_only(),
                    sizes={k: len(v) for k, v in branches.items() if k in ("zgc", "tz")} if costs else None,
                    passages=[dict(id=p["id"], title=p["title"], published=p["published"], campus=p["campus"],
                                   path=p["path"], text=p["text"][:240]) for p in scoped])
        if decision == "abstain":
            yield dict(type="used", ids=[], mode="abstain", passages=[])
            yield dict(type="answer", text=ABSTAIN_TEXT, action="abstain")
            yield summary()
            return

        rank = getattr(self, "_rank", {})
        facts = sorted(facts, key=lambda f: (-int(f.published.replace("-", "")), rank.get(f.id, 999)))[:12]
        facts = sorted(facts, key=lambda f: (f.campus or "", f.entity, f.published))
        revised = [f for f in st["revised"] if f.ekey in {x.ekey for x in facts}][:3]
        yield dict(type="used", ids=[f.id for f in facts], mode=mode, passages=[p["id"] for p in scoped],
                   revisedShown=[f.id for f in revised])

        # ---------------------------------------------------------------- 6 write (LLM, streamed)
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
        yield stage("write", "running", nFacts=len(facts), nPassages=len(scoped), nRevised=len(revised))
        t0 = time.perf_counter()
        dec, rec = AnswerStream(), None
        for kind, v in stream_chat(msgs, model=self.model, max_tokens=400, tag="agent_write"):
            if kind == "delta":
                s = dec.feed(v)
                if s:
                    yield dict(type="delta", text=s)
            elif kind == "retry":
                yield dict(type="retry", attempt=v)
            else:
                rec = v
        calls += 1
        cached_all &= bool(rec.get("cached"))
        p = parse_json(rec["content"])
        ans = str(p.get("answer")) if isinstance(p, dict) and p.get("answer") else rec["content"]
        yield stage("write", "done", t0, cached=bool(rec.get("cached")), nFacts=len(facts), nPassages=len(scoped),
                    nRevised=len(revised))

        # ---------------------------------------------------------------- 7 verify
        yield stage("verify", "running")
        t0 = time.perf_counter()
        allowed = {f"{int(h)}:{m}" for f in facts + revised for h, m in TIME.findall(undouble(f.value + f.quote))}
        allowed |= {f"{int(h)}:{m}" for p in scoped for h, m in TIME.findall(p["text"])}

        def times(text):
            return sorted({f"{int(h)}:{m}" for h, m in TIME.findall(norm_answer(text))})

        found = times(ans)
        bad = [t for t in found if t not in allowed]
        rewritten, fallback = False, False
        if bad:
            msgs += [dict(role="assistant", content=rec["content"]),
                     dict(role="user", content=f"答复中的时间 {bad} 不在许可证据里，请只用证据中的时间重写。只输出JSON。")]
            rec2 = chat(msgs, model=self.model, max_tokens=400, tag="agent_revise", retries=llm_probe.retries(self.model))
            calls += 1
            p = parse_json(rec2["content"])
            ans = str(p.get("answer")) if isinstance(p, dict) and p.get("answer") else ans
            rewritten = True
            if [t for t in times(ans) if t not in allowed]:
                fallback = True
                ans = "；".join(f"{CAMPUS_ZH.get(f.campus, '')}{f.entity}{f.attr}：{f.value}" +
                               (f"（{f.cycle}年，仅供参考）" if mode == "history" else "") for f in facts[:6])
        yield stage("verify", "done", t0, times=found, bad=bad, rewritten=rewritten, fallback=fallback)
        action = mode if mode in ("history", "enumerate", "assume") else "answer"
        yield dict(type="answer", text=ans, action=action, rewritten=rewritten)
        yield summary()
