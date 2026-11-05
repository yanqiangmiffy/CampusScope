"""Text utilities: PDF de-noising, span matching, dates and value tokens."""
import re
from datetime import date, datetime, timedelta

# WeChat exports render bold runs twice, character by character ("中中关关村村校校区区").
# BM25 then cannot match "中关村" in exactly the section headers that carry the scope.
_PAIR_RUN = re.compile(r"((?:([^\d\s])\2){2,})")


def undouble(text):
    text = _PAIR_RUN.sub(lambda m: m.group(1)[::2], text)
    text = re.sub(r"(?<=\d)([月日号时点分年])\1", r"\1", text)
    text = re.sub(r"([月日号时点分年至])\1(?=\d)", r"\1", text)
    return text


_CJK = r"[一-鿿　-〿＀-￯]"


def clean(text):
    """Line breaks from PDF extraction split words; spaces between CJK characters carry no
    meaning, so they are removed before undoubling (a bold run may straddle a line break)."""
    t = re.sub(r"\s+", " ", text or "")
    t = re.sub(rf"(?<={_CJK}) (?={_CJK})", "", t)
    return undouble(t).strip()


def squash(text):
    """Whitespace- and punctuation-insensitive form used for span checks."""
    t = undouble(re.sub(r"\s+", "", text or ""))
    t = t.replace("：", ":").replace("—", "-").replace("–", "-").replace("~", "-").replace("～", "-")
    return re.sub(r"[\s，,。．.、；;（）()【】\[\]“”\"'《》!！?？]", "", t)


def span_ok(quote, text):
    q = squash(quote)
    return len(q) >= 4 and q in squash(text)


TIME = re.compile(r"(\d{1,2})[:：](\d{2})")


def value_tokens(value):
    """Key facts for judging: clock times, dates, phone-like numbers, plus key status words."""
    v = undouble(value or "")
    toks = [f"{int(h)}:{m}" for h, m in TIME.findall(v)]
    toks += [f"{int(a)}月{int(b)}日" for a, b in re.findall(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", v)]
    for ph in re.findall(r"(?<!\d)(\d{8}|\d{3,4}-\d{7,8}|1\d{10})(?!\d)", v):
        toks.append(re.sub(r"^010-?", "", ph))      # 010-62513986 and 62513986 are the same line
    for w in ("暂停", "关闭", "停运", "正常开放", "不开放", "24小时", "通宵", "全天"):
        if w in v:
            toks.append(w)
    alias = {"正常营业": "正常开放", "照常营业": "正常开放", "照常开放": "正常开放", "停业": "暂停", "暂停营业": "暂停",
             "闭馆": "关闭", "停止开放": "暂停", "恢复": "恢复"}
    for w, t in alias.items():
        if w in v and t not in toks and not (t == "正常开放" and "暂停" in toks):
            toks.append(t)
    return list(dict.fromkeys(toks))


def norm_answer(text):
    """Normalizes an answer so value tokens can be found in it."""
    t = undouble(text or "")
    t = t.replace("：", ":")
    t = re.sub(r"[（(]?010[)）]?[-\s]?(?=\d{8}(?!\d))", "", t)     # drop the Beijing area code
    t = re.sub(r"(?<!\d)(\d):(\d{2})", r"\1:\2", t)
    t = re.sub(r"(?<!\d)0(\d):(\d{2})", r"\1:\2", t)       # 07:00 -> 7:00
    t = re.sub(r"(\d{1,2})\s*点\s*半", lambda m: f"{int(m.group(1))}:30", t)
    t = re.sub(r"(\d{1,2})\s*点(?!\d)", lambda m: f"{int(m.group(1))}:00", t)
    t = re.sub(r"(\d{1,2})\s*月\s*0?(\d{1,2})\s*日", lambda m: f"{int(m.group(1))}月{int(m.group(2))}日", t)
    return t


def has_tokens(answer, tokens):
    a = norm_answer(answer)
    return all(t in a for t in tokens)


def parse_date(s):
    if not s:
        return None
    if isinstance(s, date):
        return s
    m = re.match(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", str(s))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def anchor(d, published):
    """Temporal anchoring: keep an LLM-normalized date only if it lies within a plausible
    window around the publication date; otherwise re-anchor the month/day to the nearest
    year after (published - 60 days). Notices announce arrangements, rarely > 13 months ahead."""
    pub = parse_date(published)
    if d is None or pub is None:
        return d
    lo, hi = pub - timedelta(days=200), pub + timedelta(days=400)
    if lo <= d <= hi:
        return d
    for y in (pub.year, pub.year + 1, pub.year - 1):
        try:
            cand = date(y, d.month, d.day)
        except ValueError:
            continue
        if pub - timedelta(days=60) <= cand <= hi:
            return cand
    return d


def iso(d):
    return d.isoformat() if d else None


def today_str(d):
    return d if isinstance(d, str) else d.isoformat()


def to_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()
