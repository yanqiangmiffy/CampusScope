"""Notice corpus: parse the notice PDFs, tag service notices and their periodic families (Section 2.1).

    python scripts/prepare_corpus.py          # needs the PDFs in CAMPUSSCOPE_NOTICE_DIR (not distributed)

The released data/notices.jsonl was produced by this script.

* Parses every notice PDF published since CORPUS_SINCE with pdfplumber, the extractor of the
  department's deployed prototype, so CampusScope and the chunk baselines read identical text.
* doc_id = sha1(filename)[:10], the key the prototype used for its chunk ids
  (notice.<doc_id>.<i>), so graph facts can be traced to the chunks RAG retrieves.
* Qwen3-32B tags each title in batches: is it a service notice (hours, openings,
  closures, schedules, procedures, fees, places, contacts, outages), and which periodic
  family it belongs to (e.g. winter-break service hours), with its cycle (year + period).

Output: data/notices.jsonl (public WeChat notices, no personal data).
"""
import hashlib
import json
import re
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

from campusscope.config import CORPUS_SINCE, DATA, NOTICE_DIR
from campusscope.llm import chat, parse_json

FILENAME = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)$")


def normalize(text):
    text = text.replace("　", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse(path):
    import pdfplumber
    m = FILENAME.match(Path(path).stem)
    published, title = (m.group(1), m.group(2).strip()) if m else (None, Path(path).stem)
    try:
        with pdfplumber.open(path) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages)
            images = sum(len(p.images) for p in pdf.pages)
    except Exception as e:  # noqa: BLE001
        return dict(filename=Path(path).name, error=str(e))
    name = Path(path).name
    return dict(doc_id=hashlib.sha1(name.encode("utf-8")).hexdigest()[:10], filename=name, published=published,
                title=title, text=normalize(text), images=images)


TAG = ("你在整理一所大学综合服务保障部门的公众号通知。对每个标题判断：\n"
       "service：是否为师生可据以办事或安排行程的服务类通知（营业/开放时间、闭馆封楼、停水停电、班车时刻、"
       "办理流程、收费、地点电话、报修、活动报名规则等）。新闻报道、表扬、廉政宣传、菜谱、招聘、人物专访等为 false。\n"
       "family：若它属于每年或每学期重复发布的系列通知，给出系列名（如“寒假服务营业时间”“暑假服务营业时间”"
       "“国庆服务营业时间”“通宵自习室开放”“班车时刻调整”“封楼通知”“停水停电通知”“浴室开放调整”“供暖”），否则 null。\n"
       "cycle：该通知对应的周期，如“2026寒假”“2025暑假”“2025国庆”“2026春季学期”，无法判断则 null。\n"
       '只输出JSON数组：[{"i":序号,"service":true/false,"family":"..."|null,"cycle":"..."|null}]')


def tag(batch):
    lines = "\n".join(f"{i}. {d['published']} {d['title']}" for i, d in batch)
    rec = chat([dict(role="system", content=TAG), dict(role="user", content=lines)], model="qwen",
               max_tokens=3000, tag="corpus_tag")
    out = parse_json(rec["content"])
    return out if isinstance(out, list) else []


def main():
    files = sorted(str(p) for p in NOTICE_DIR.glob("*.pdf") if p.name[:10] >= CORPUS_SINCE)
    with ProcessPoolExecutor(max_workers=8) as ex:
        docs = [d for d in ex.map(parse, files, chunksize=8) if "error" not in d]
    docs.sort(key=lambda d: (d["published"] or "", d["title"]))
    indexed = list(enumerate(docs))
    batches = [indexed[i:i + 40] for i in range(0, len(indexed), 40)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        tags = {}
        for res in ex.map(tag, batches):
            for t in res:
                if isinstance(t, dict) and isinstance(t.get("i"), int):
                    tags[t["i"]] = t
    for i, d in indexed:
        t = tags.get(i, {})
        d["service"] = bool(t.get("service"))
        d["family"] = t.get("family") or None
        d["cycle"] = t.get("cycle") or None
    with open(DATA / "notices.jsonl", "w", encoding="utf8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    n_service = sum(d["service"] for d in docs)
    fams = {}
    for d in docs:
        if d["service"] and d["family"]:
            fams.setdefault(d["family"], set()).add(d["cycle"] or d["published"][:4])
    recurring = {k: sorted(v) for k, v in fams.items() if len(v) >= 2}
    print(f"parsed {len(docs)} notices since {CORPUS_SINCE}; service notices {n_service}; "
          f"untagged {len(docs) - len(tags)}; recurring families {len(recurring)}")
    for k, v in sorted(recurring.items(), key=lambda kv: -len(kv[1]))[:25]:
        print(f"  {k}: {len(v)} cycles {v[:8]}")


if __name__ == "__main__":
    main()
