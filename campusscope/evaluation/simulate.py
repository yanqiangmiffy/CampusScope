"""Simulated users who hold the hidden conditions, and the dialogue loop (paper Section 4.1).

The simulated user is rule-based (no LLM): it detects which slots a clarification asks about from the
question text and answers truthfully, but only about what was asked, with a fixed sentence; the same for
every system. After at most two clarifications the system must answer.
"""
import re
import time

from .judge import judge

CAMPUS_ZH = {"zgc": "中关村校区", "tz": "通州校区"}
SLOTS = {
    "campus": r"校区|中关村|通州|潞城|哪个校|哪边|海淀",
    "identity": r"身份|本科|研究生|教职工|老师还是|学生还是",
    "date": r"哪天|日期|哪一年|哪个时间|什么时间段|今天还是|具体时间|哪个月|几号",
    "place": r"哪栋|哪个楼|哪座|宿舍楼|具体位置|哪个食堂|哪个浴室|哪个场馆|具体是哪|哪一个",
}
MAX_ASKS = 2


def detect_slots(question):
    return [s for s, pat in SLOTS.items() if re.search(pat, question or "")]


def user_reply(slots, hidden):
    parts = []
    if "campus" in slots or "place" in slots:
        parts.append(f"我在{CAMPUS_ZH.get(hidden.get('campus'), '学校')}。")
    if "identity" in slots:
        parts.append("我是本科生。")
    if "date" in slots:
        parts.append(f"就是问现在（今天是{hidden['today']}）。")
    return "".join(parts) or "我也说不清，你按你知道的回答吧。"


def run_dialogue(system, item):
    """Returns the final reply, the transcript, the judgement and cost counters."""
    conv = [dict(role="user", text=item["question"])]
    asked, calls, latency = [], 0, 0.0
    t0 = time.perf_counter()
    trace = []
    for turn in range(MAX_ASKS + 1):
        out = system.respond(conv, item["today"], must_answer=(turn == MAX_ASKS))
        calls += out.get("calls", 0)
        latency += out.get("latency", 0.0)
        trace.append({k: v for k, v in out.items() if k in ("action", "text", "trace", "slot")})
        conv.append(dict(role="assistant", text=out.get("text", "")))
        if out.get("action") != "ask" or turn == MAX_ASKS:
            break
        slots = [out["slot"]] if out.get("slot") else detect_slots(out.get("text", ""))
        asked.append(slots or ["unknown"])
        conv.append(dict(role="user", text=user_reply(slots, item["hidden"])))
    final = dict(action=out.get("action", "answer"), text=out.get("text", ""))
    if final["action"] == "ask":
        final["action"] = "unanswered"
    verdict = judge(item, final, asked)
    return dict(id=item["id"], kind=item["kind"], final=final, conversation=conv, asked=asked, calls=calls,
                latency=round(latency, 2), wall=round(time.perf_counter() - t0, 2), verdict=verdict, trace=trace)
