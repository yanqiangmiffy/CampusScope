"""Evidence-graph compiler, LLM part (paper Section 2.2): one notice -> a positioned scope tree and
span-grounded facts.

Two LLM passes, then deterministic placement:
  1. outline: the ordered section headings (verbatim) with their level and the scope each
     introduces (campus / audience / dates) -> located in the text -> a tree of intervals;
  2. facts: atomic facts extracted window by window, each with a verbatim quote;
  3. placement: a fact's position is the position of its quote; its section path is the
     chain of outline intervals containing that position.
Scope therefore travels with the document structure, not with text locality; fixed-size
chunking loses exactly this link (a chunk in the middle of the "Tongzhou campus" part
does not say "Tongzhou").
"""
import re
from concurrent.futures import ThreadPoolExecutor

from .config import SYSTEM_MODEL
from .llm import chat, parse_json
from .text import clean, squash

TYPES = ("食堂餐厅", "超市商店", "理发", "浴室", "开水房", "快递收发", "打印复印", "图书馆", "教学楼自习室", "田径球场",
         "健身房", "游泳馆", "体育场馆", "班车交通", "校医院", "宿舍公寓", "水电缴费", "维修报修", "供暖", "酒店住宿",
         "活动", "其他")
ATTRS = ("开放时间", "开放状态", "地点", "电话", "班次时刻", "收费", "办理方式", "安排")
WINDOW_CHARS = 800

CODES = ("校区编码：zgc=中关村校区，tz=通州校区（含潞城），both=两校区通用。日期一律写 YYYY-MM-DD；原文没写年份时，"
         "结合发布日期补全（如“1月12日”、发布于2026-01-07 → 2026-01-12）。")

OUTLINE = f"""你整理一篇高校服务通知的层级结构（条件作用域树）。{CODES}
按原文顺序列出所有小标题/分区标题，每个给出：层级(1为最高)、原文标题(逐字，4-15字，便于在正文中定位)、该标题引入的适用条件。
典型结构：一级“中关村校区”“通州校区”，二级“餐饮服务”“物业服务”，三级“浴室”“开水房”……；
一级标题引入的校区对其下所有内容有效，直到下一个同级标题出现为止。
只输出JSON：{{"doc":{{"campus":"zgc|tz|both|null","audience":"适用人群或null","period":"周期名如2026寒假/2025暑假/2025国庆/2026春季学期或null","start":"日期或null","end":"日期或null"}},
"outline":[[1,"中关村校区","zgc",null,null,null],[2,"餐饮服务",null,null,null,null]]}}
outline 每项为[层级,原文标题,校区或null,人群或null,起始日期或null,结束日期或null]；没有小标题时 outline 为空数组。"""

FACTS = f"""你从高校服务通知的一个片段中抽取原子事实。只依据片段文字，图片里的内容看不到就不要编。{CODES}
每条事实：{{"e":"服务点（原文中的具体名称，如东区浴室、世纪馆、公共教学1楼、快专19；原文只写类型时照写）",
"t":"类型","a":"属性","v":"取值（尽量原文）","c":"事实文字本身写明的校区或null","u":"事实文字本身写明的人群或null",
"s":"起始日期或null","d":"结束日期或null","q":"逐字引文（10-50字，须包含取值，用于在原文中定位）"}}
t 只能取：{"、".join(TYPES)}。a 只能取：{"、".join(ATTRS)}（开放时间=几点到几点；开放状态=某段日期开放/暂停/关闭/停运/恢复；安排=其他日程）。
规则：一个服务点、一个属性、一个取值、一个日期段为一条；多个服务点共用一句时拆成多条；同一服务点不同日期段安排不同时拆开。
所属分区的校区不用你判断（系统按位置继承），c 只在事实文字本身写明校区时填写。
只抽取师生办事用得上的信息（时间、开放、地点、电话、班次、收费、办理方式），忽略宣传语、温馨提示、署名。
只输出JSON：{{"facts":[{{...}},{{...}}]}}"""


def _windows(text, size=WINDOW_CHARS):
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            cut = max(text.rfind("。", start, end), text.rfind("；", start, end), text.rfind(" ", start, end))
            if cut > start + size * 0.5:
                end = cut + 1
        out.append((start, end))
        start = end
    return out


def locate_outline(outline, sq_text):
    """Locates headings in order (repeated headings under different campuses resolve by order)."""
    nodes, pos = [], 0
    for item in outline or []:
        if not isinstance(item, list) or len(item) < 2:
            continue
        item = item + [None] * (6 - len(item))
        level = item[0] if isinstance(item[0], int) else 1
        h = squash(str(item[1] or ""))
        if len(h) < 2:
            continue
        p = sq_text.find(h, pos)
        if p < 0:
            p = sq_text.find(h[:6], pos) if len(h) >= 6 else -1
        if p < 0:
            continue
        nodes.append(dict(level=level, heading=str(item[1]), campus=item[2], audience=item[3], start=item[4],
                          end=item[5], pos=p))
        pos = p + 1
    # interval end = next node at the same or higher level
    for i, n in enumerate(nodes):
        n["endpos"] = next((m["pos"] for m in nodes[i + 1:] if m["level"] <= n["level"]), len(sq_text))
    return nodes


_DROP = set(" \t\r\n，,。．.、；;（）()【】[]“”\"'《》!！?？")
_SWAP = {"：": ":", "—": "-", "–": "-", "~": "-", "～": "-"}


def squash_index(text):
    """squash() for already-cleaned text, with the map back to original positions (for slicing passages)."""
    out, idx = [], []
    for i, ch in enumerate(text):
        if ch in _DROP:
            continue
        out.append(_SWAP.get(ch, ch))
        idx.append(i)
    return "".join(out), idx


def section_passages(text, outline, max_len=420):
    """Splits a notice at its outline headings: every passage lies inside one section and can carry the
    scope of that section (the passage-level counterpart of scope inheritance)."""
    sq, idx = squash_index(text)
    nodes = locate_outline(outline, sq)
    cuts = sorted({0} | {n["pos"] for n in nodes} | {len(sq)})
    out = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a < 8:
            continue
        s, e = idx[a], (idx[b] if b < len(idx) else len(text))
        seg = text[s:e].strip()
        for k in range(0, len(seg), max_len):
            piece = seg[k:k + max_len + 40].strip()
            if len(piece) >= 12:
                out.append(dict(pos=a, text=piece, path=[n["heading"] for n in path_at(nodes, a)]))
    return out, nodes


def path_at(nodes, p):
    """Section chain containing squashed position p, deepest first."""
    inside = [n for n in nodes if n["pos"] <= p < n["endpos"]]
    return sorted(inside, key=lambda n: -n["level"])


def compile_notice(doc, model=SYSTEM_MODEL):
    text = clean(doc["text"])
    head = f"标题：{clean(doc['title'])}\n发布日期：{doc['published']}\n"
    calls = []
    rec = chat([dict(role="system", content=OUTLINE), dict(role="user", content=head + "正文：" + text[:9000])],
               model=model, max_tokens=1600, tag=f"compile_outline_{model}")
    calls.append(rec)
    o = parse_json(rec["content"])
    o = o if isinstance(o, dict) else {}
    facts = []
    wins = _windows(text[:12000])

    def one(win):
        a, b = win
        return win, chat([dict(role="system", content=FACTS), dict(role="user", content=head + "片段：" + text[a:b])],
                         model=model, max_tokens=4000, tag=f"compile_facts_{model}")

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(one, wins))
    for (a, b), r in results:
        calls.append(r)
        for f in salvage_objects(r["content"]):
            if isinstance(f, dict):
                facts.append(dict(entity=f.get("e"), type=f.get("t"), attr=f.get("a"), value=f.get("v"),
                                  campus=f.get("c"), audience=f.get("u"), start=f.get("s"), end=f.get("d"),
                                  quote=f.get("q"), window=[a, b]))
    return dict(doc=o.get("doc") or {}, outline=o.get("outline") or [], facts=facts, text_len=len(text)), calls


def salvage_objects(content):
    """All complete flat JSON objects in a (possibly truncated) reply."""
    got = parse_json(content)
    items = got.get("facts") if isinstance(got, dict) else got
    if isinstance(items, list) and items:
        return [x for x in items if isinstance(x, dict)]
    out = []
    for m in re.finditer(r"\{[^{}]*\}", content or ""):
        obj = parse_json(m.group(0))
        if isinstance(obj, dict) and obj.get("v"):
            out.append(obj)
    return out
