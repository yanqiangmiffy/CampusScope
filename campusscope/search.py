"""Hybrid retrieval on Milvus: bge dense vectors + Milvus' built-in BM25 (Chinese analyzer), fused by RRF.

`MilvusStore` creates a collection with the schema, index types and insertion of the department's deployed
prototype, so the baselines and CampusScope differ only in what they index, not in how they search.
Retrieval takes an arbitrary filter expression (knowledge cutoffs by publication date, campus filters) and
the collection to search, so an ablation searches the index built without the component it removes
(config.collections_for). Set MILVUS_DB to keep the collections in a database of their own when the Milvus
instance is shared with other applications.

`EMBEDDER` is the query embedder (default: llm.embed, cached). The demo swaps in one that fails fast and
returns None when the embedding endpoint is down; retrieval is then BM25 only. The paper's runs always use
the default.
"""
import logging
import threading

from pymilvus import AnnSearchRequest, DataType, Function, FunctionType, MilvusClient, RRFRanker

from .config import CHUNK_COLLECTION, EMBEDDING_DIM, FACT_COLLECTION, MILVUS_DB, MILVUS_TOKEN, MILVUS_URI, PASSAGE_COLLECTION
from .llm import embed

log = logging.getLogger(__name__)


def _embed_one(text):
    return embed([text])[0]


EMBEDDER = _embed_one
_local = threading.local()


def bm25_only():
    """True if a search in this thread fell back to BM25 since the last reset_flags()."""
    return getattr(_local, "bm25_only", False)


def reset_flags():
    _local.bm25_only = False


def connect(uri=None, token=None, db=None):
    """A client of `db` (created if missing); the default database when `db` is empty."""
    kw = dict(uri=uri or MILVUS_URI)
    if token or MILVUS_TOKEN:
        kw["token"] = token or MILVUS_TOKEN
    db = db or MILVUS_DB
    if db and db != "default":
        admin = MilvusClient(**kw)
        if db not in admin.list_databases():
            admin.create_database(db)
        admin.close()
        kw["db_name"] = db
    return MilvusClient(**kw)


class MilvusStore:
    """One collection: schema, insertion and stats (the deployed prototype's schema)."""

    def __init__(self, collection, uri=None, token=None, dim=None, db=None):
        self.collection = collection
        self.uri = uri or MILVUS_URI
        self.dim = dim or EMBEDDING_DIM
        self.client = connect(self.uri, token, db)

    def healthy(self):
        try:
            self.client.list_collections()
            return True
        except Exception:  # noqa: BLE001
            return False

    def exists(self):
        return bool(self.client.has_collection(self.collection))

    def initialize_collection(self, drop_existing=False):
        """Creates the collection: bge dense vector (IVF_FLAT, IP) + BM25 sparse field computed by Milvus
        from `content` with the Chinese analyzer (SPARSE_WAND)."""
        if drop_existing and self.exists():
            self.client.drop_collection(self.collection)
        if self.exists():
            return
        schema = MilvusClient.create_schema(enable_dynamic_field=True)
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name="unit_id", datatype=DataType.VARCHAR, max_length=256)
        schema.add_field(field_name="item_id", datatype=DataType.VARCHAR, max_length=128)
        schema.add_field(field_name="domain", datatype=DataType.VARCHAR, max_length=32)
        schema.add_field(field_name="campus", datatype=DataType.VARCHAR, max_length=16)
        schema.add_field(field_name="unit_type", datatype=DataType.VARCHAR, max_length=32)
        schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=8192, enable_analyzer=True,
                         analyzer_params={"type": "chinese"}, enable_match=True)
        schema.add_field(field_name="metadata", datatype=DataType.JSON, max_length=65535)
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=self.dim)
        schema.add_field(field_name="sparse_bm25", datatype=DataType.SPARSE_FLOAT_VECTOR)
        schema.add_function(Function(name="content_bm25", function_type=FunctionType.BM25,
                                     input_field_names=["content"], output_field_names="sparse_bm25"))
        idx = self.client.prepare_index_params()
        idx.add_index(field_name="dense_vector", index_name="dense_index", index_type="IVF_FLAT",
                      metric_type="IP", params={"nlist": 128})
        idx.add_index(field_name="sparse_bm25", index_name="sparse_bm25_index", index_type="SPARSE_WAND",
                      metric_type="BM25")
        self.client.create_collection(collection_name=self.collection, schema=schema, index_params=idx)

    def insert_units(self, rows):
        if not rows:
            return 0
        res = self.client.insert(collection_name=self.collection, data=rows)
        return int(res.get("insert_count", len(rows)) if isinstance(res, dict) else len(rows))

    def settle(self, timeout=300.0):
        """Flush, compact and wait until the rows sit in compacted, fully indexed segments. Right after an
        insert the rows are spread over small segments, each with its own small IVF index, which ranks
        differently from the compacted collection the paper's runs searched; Milvus compacts them in the
        background a minute later. Doing it here makes a fresh build answer like the paper at once."""
        import time
        deadline = time.time() + timeout
        self.client.flush(self.collection)
        try:
            job = self.client.compact(self.collection)
            while time.time() < deadline and "completed" not in str(self.client.get_compaction_state(job)).lower():
                time.sleep(1.0)
        except Exception as e:  # noqa: BLE001  (compaction is an optimisation: never fail a build on it)
            log.warning("%s: compaction skipped (%s)", self.collection, e)
        ok = self.wait_indexed(max(10.0, deadline - time.time()))
        # the query node keeps serving the pre-compaction segments until it hands them over; reloading
        # makes the loaded segments exactly the compacted, indexed ones
        self.client.release_collection(self.collection)
        self.client.load_collection(self.collection)
        return ok

    def wait_indexed(self, timeout=300.0):
        """Waits until both indexes cover every row. Right after an insert Milvus searches the new
        segments without the index, which ranks differently; a collection counts as built only after."""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            states = [self.client.describe_index(self.collection, n) for n in ("dense_index", "sparse_bm25_index")]
            if all(s.get("state") == "Finished" and not s.get("pending_index_rows") and
                   s.get("indexed_rows") == s.get("total_rows") for s in states):
                return True
            time.sleep(1.0)
        log.warning("%s: index not finished after %.0fs", self.collection, timeout)
        return False

    def get_stats(self):
        if not self.exists():
            return {"ready": False, "rows": 0}
        stats = self.client.get_collection_stats(self.collection)
        return {"ready": True, "rows": int(stats.get("row_count", 0))}


_services = {}
_lock = threading.Lock()


def service(collection):
    with _lock:
        if collection not in _services:
            _services[collection] = MilvusStore(collection)
        return _services[collection]


def hybrid(collection, query, expr=None, limit=10, candidates=30, output_fields=None):
    """Dense (bge, IP) + sparse (BM25) search fused by RRF(60), with a filter expression; BM25 only
    when the embedder returns None (demo, embedding endpoint down)."""
    svc = service(collection)
    vec = EMBEDDER(query)
    fields = output_fields or ["unit_id", "title", "content", "campus", "metadata"]
    if vec is not None:
        reqs = [
            AnnSearchRequest(data=[vec], anns_field="dense_vector",
                             param={"metric_type": "IP", "params": {"nprobe": 16}}, limit=candidates, expr=expr),
            AnnSearchRequest(data=[query], anns_field="sparse_bm25", param={"metric_type": "BM25"},
                             limit=candidates, expr=expr),
        ]
        res = svc.client.hybrid_search(collection_name=collection, reqs=reqs, ranker=RRFRanker(60), limit=limit,
                                       output_fields=fields)
    else:
        _local.bm25_only = True
        res = svc.client.search(collection_name=collection, data=[query], anns_field="sparse_bm25",
                                search_params={"metric_type": "BM25"}, limit=limit, filter=expr or "",
                                output_fields=fields)
    hits = []
    for h in res[0]:
        e = dict(h.get("entity", {}))
        e["score"] = float(h.get("distance", 0.0))
        hits.append(e)
    return hits


def chunks(query, cutoff, limit=6):
    """Chunk baselines: the deployed chunker over the same (cleaned) service notices as CampusScope."""
    return hybrid(CHUNK_COLLECTION, query, expr=f'metadata["published"] <= "{cutoff}"', limit=limit)


def fact_nodes(query, cutoff, campus=None, limit=30, collection=FACT_COLLECTION):
    """Fact nodes of the evidence graph, scope-filtered when the campus is known."""
    expr = f'metadata["published"] <= "{cutoff}"'
    if campus:
        expr += f' and campus in ["{campus}", "all"]'
    return hybrid(collection, query, expr=expr, limit=limit, candidates=max(60, limit * 2))


def passages(query, cutoff, campus=None, limit=6, collection=PASSAGE_COLLECTION, candidates=40):
    """Section-aligned passages with their inherited scope (CampusScope's supplementary evidence, and the
    evidence of the section-passage RAG baseline)."""
    expr = f'metadata["published"] <= "{cutoff}"'
    if campus:
        expr += f' and campus in ["{campus}", "all"]'
    return hybrid(collection, query, expr=expr, limit=limit, candidates=candidates)
