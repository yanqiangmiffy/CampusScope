"""The Milvus collections the systems search (built by scripts/build_index.py and by the demo on first start).

  * chunks:   the deployed chunker (600 characters, overlap 100) on the cleaned notice text (baselines);
  * facts:    one node per grounded fact, rendered with its scope and validity (`fact_unit`);
  * passages: section-aligned passages with their scope and heading path (`passage_unit`).

Fact and passage units are rendered from the graph *under the same options* as the system that searches
them (one pair of collections per option set, see config.collections_for), so an ablated component does
not reach the system through the index text or the filter field.

Embeddings come from llm.embed (cached by text, so a rebuild needs no endpoint when the cache has them).
`vectors` can be replaced, e.g. by the demo, which falls back to zero vectors (BM25-only search) for
texts neither the cache nor the endpoint can embed.
"""
import json

from .chunking import chunk
from .config import DATA, collections_for, compiled_path
from .graph import load_graph
from .llm import embed
from .search import service
from .text import clean

SCOPE_ZH = {"zgc": "中关村校区", "tz": "通州校区"}


def fact_unit(f):
    """A fact node as indexed: its value, scope and validity as the graph (under its options) states them."""
    scope = SCOPE_ZH.get(f.campus, "两校区/未注明")
    when = f"{f.start or ''}至{f.end or ''}" if (f.start or f.end) else "长期"
    return dict(unit_id=f"fact.{f.id}", unit_type="fact", campus=f.campus or "all", title=f.title,
                content=f"{f.entity}（{f.type}）{f.attr}：{f.value}。适用：{scope}；{when}。原文：{f.quote}",
                metadata=dict(published=f.published, fact_id=f.id, doc_id=f.doc_id, title=f.title))


def passage_unit(p):
    """A section passage as indexed: its text, prefixed by its scope and heading path (both empty when
    inheritance is ablated, except a campus the passage names itself)."""
    scope = SCOPE_ZH.get(p["campus"], "两校区/未注明")
    path = " › ".join(p["path"])
    return dict(unit_id=f"passage.{p['id']}", unit_type="passage", campus=p["campus"] or "all", title=p["title"],
                content=f"[{scope}｜{path}] {p['text']}",
                metadata=dict(published=p["published"], passage_id=p["id"], doc_id=p["doc_id"], title=p["title"]))


def chunk_units():
    docs = {json.loads(l)["doc_id"]: json.loads(l) for l in open(DATA / "notices.jsonl", encoding="utf8")}
    units = []
    for line in open(compiled_path(), encoding="utf8"):
        d = docs[json.loads(line)["doc_id"]]
        for i, ch in enumerate(chunk(clean(d["text"]))):
            units.append(dict(unit_id=f"chunk.{d['doc_id']}.{i}", unit_type="notice", campus="all", title=d["title"],
                              content=f"公告：{d['title']}\n发布日期：{d['published']}\n{ch}",
                              metadata=dict(published=d["published"], doc_id=d["doc_id"], title=d["title"], chunk=i)))
    return units


def graph_units(opt=None):
    """(facts collection, fact units), (passages collection, passage units) of the graph under `opt`."""
    g, stats = load_graph(opt)
    fcoll, pcoll = collections_for(opt)
    return [(fcoll, [fact_unit(f) for f in g.facts]), (pcoll, [passage_unit(p) for p in g.passages])], stats


def embed_text(u):
    return f"{u['title']}\n{u['content']}"


def rows_for(units, vectors=embed):
    vecs = vectors([embed_text(u) for u in units])
    return [dict(unit_id=u["unit_id"], item_id="", domain=u.get("domain", ""), campus=u["campus"], unit_type=u["unit_type"],
                 title=u["title"][:500], content=u["content"][:8000], metadata=u["metadata"], dense_vector=v)
            for u, v in zip(units, vecs)]


def insert(collection, units, batch=64, vectors=embed, progress=None):
    """(Re)creates `collection` and inserts `units`; progress(collection, done, total) after each batch."""
    svc = service(collection)
    svc.initialize_collection(drop_existing=True)
    for i in range(0, len(units), batch):
        svc.insert_units(rows_for(units[i:i + batch], vectors))
        if progress:
            progress(collection, min(i + batch, len(units)), len(units))
    svc.settle()                 # compacted + indexed: searches then rank as in the paper's runs
    return svc.get_stats()
