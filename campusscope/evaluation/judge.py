"""Outcome-based judging of a finished dialogue against the hidden context.

No gold label says whether a system *should* ask. A system is judged on what the user ends
up being told: the value that applies to the user's hidden campus and date.
  correct   final reply contains every gold token (clock times, dates, status words),
            and, if it lists several campuses, attributes them to the user's campus;
            for T4 the reply must also label the year of the historical arrangement;
  SCE       silent-condition error: a real value from another campus reaches the user as
            the answer (grounded but inapplicable);
  TE        temporal error: an earlier cycle's / pre-revision value is given as current, or
            a historical value is given without its year;
  over-ask  the system asked although the item's answer did not depend on anything unknown.
"""
import re

from ..text import norm_answer

STATUS = {
    # every alias that text.value_tokens folds into a gold status word must be accepted here too (停业 -> 暂停)
    "暂停": ("暂停", "关闭", "停止", "不开放", "闭馆", "停运", "不营业", "停业", "暂不开放", "暂时关闭", "取消"),
    "关闭": ("关闭", "暂停", "不开放", "闭馆", "停止开放", "不营业", "停业"),
    "停运": ("停运", "暂停", "不运行", "停开", "取消"),
    # a bare "开放" matches any sentence about opening ("其开放情况未提及"); require an affirmative phrase,
    # or opening hours (a time range answers "is it open?")
    "正常开放": ("正常开放", "正常营业", "照常开放", "照常营业", "正常服务", "开放时间为", "营业时间为", "营业时间是",
             "开放时间是", "正在营业", "目前开放", "目前营业", "可以正常", "已开业", "开业", "均开放", "均正常",
             "长期开放", "开放中", "营业中", "照常", "可以预约"),
    "不开放": ("不开放", "关闭", "暂停"),
    "24小时": ("24小时", "二十四小时", "全天"),
    "通宵": ("通宵", "24小时", "全天", "次日"),
    "全天": ("全天", "24小时"),
    "恢复": ("恢复", "重新开放", "重新营业"),
}
CAMPUS_WORDS = {"zgc": ("中关村",), "tz": ("通州", "潞城")}
HEDGE = ("往年", "去年", "参考", "以正式通知为准", "尚未发布", "暂未发布", "未发布", "还没有发布", "没有找到", "未找到", "暂无", "仅供参考")


RANGE = re.compile(r"\d{1,2}:\d{2}\s*[—\-–~至到]+\s*(?:次日)?\d{1,2}:\d{2}")


def _present(tok, ans):
    if tok in STATUS:
        return any(w in ans for w in STATUS[tok]) or (tok == "正常开放" and bool(RANGE.search(ans)))
    return tok in ans


def _positions(tok, ans):
    words = STATUS.get(tok, (tok,))
    pos = [m.start() for w in words for m in re.finditer(re.escape(w), ans)]
    if tok == "正常开放":
        pos += [m.start() for m in RANGE.finditer(ans)]
    return pos


def _attributed(ans, tokens, campus):
    """Every gold token has an occurrence whose nearest preceding campus word is the user's."""
    marks = sorted((m.start(), c) for c, ws in CAMPUS_WORDS.items() for w in ws for m in re.finditer(w, ans))
    if not marks:
        return True
    for t in tokens:
        ok = False
        for p in _positions(t, ans):
            before = [c for q, c in marks if q <= p]
            if not before or before[-1] == campus:
                ok = True
                break
        if not ok:
            return False
    return True


NOT_FOUND = re.compile(r"没有找到|未找到|无法提供|无法确定|未提及|没有提及|未说明|没有说明|不清楚|暂无相关|没有相关|无相关|资料中没有")
VALUE = re.compile(r"\d{1,2}:\d{2}|\d{1,2}月\d{1,2}日|\d{8}|1\d{10}")


def judge(item, final, asked_slots):
    ans = norm_answer(final.get("text") or "")
    action = final.get("action", "answer")
    gold = item["gold_tokens"]
    neg = item.get("neg_tokens") or []
    campus = item["hidden"].get("campus")
    has_gold = all(_present(t, ans) for t in gold)
    # outcome-based: the user reads the text, not the system's label, so the text decides whether it is a refusal
    if action in ("answer", "enumerate", "history") and not has_gold and NOT_FOUND.search(ans) and not VALUE.search(ans):
        action = "abstain"      # "no information found" without any value asserted is a refusal, whatever the label
    elif action == "abstain" and (has_gold or VALUE.search(ans)):
        action = "answer"       # a reply labeled abstain that still asserts a value is judged as an answer
    has_neg = any(_present(t, ans) for t in neg if t not in STATUS) or \
        any(_present(t, ans) for t in neg if t in STATUS and not any(_present(g, ans) for g in gold))
    mentions = {c for c, ws in CAMPUS_WORDS.items() if any(w in ans for w in ws)}
    correct = False
    if action in ("answer", "history", "enumerate") and has_gold:
        correct = _attributed(ans, gold, campus) if len(mentions) > 1 else (not mentions or campus in mentions or not campus)
        if item["gold_action"] == "history":
            year = str(item.get("history_year") or "")
            correct = correct and year in ans and any(h in ans for h in HEDGE)
    kind = item["kind"]
    wrong_value = action in ("answer", "history", "enumerate") and not correct and (has_neg or (len(mentions) == 1 and campus not in mentions and has_gold))
    sce = kind in ("T1", "T2", "T6") and wrong_value
    te = kind in ("T3", "T4", "T5") and (wrong_value or (item["gold_action"] == "history" and action != "abstain" and has_gold and not correct))
    over_ask = bool(asked_slots) and kind != "T2"
    return dict(correct=correct, sce=sce, te=te, over_ask=over_ask, abstain=action == "abstain", asked=len(asked_slots))
