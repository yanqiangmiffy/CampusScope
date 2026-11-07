# Data

Files read by `campusscope/` and written by `scripts/`. They are not included in this repository; this file
documents their format. The MIT license of this repository covers the code; the notices are public posts of a
university's logistics department and remain theirs.

| File | Content | Produced by |
| --- | --- | --- |
| `notices.jsonl` | the 1,009 notices published from January 2023 to September 2026 on the department's website and WeChat account: `doc_id`, `published`, `title`, `text`, and the tags `service`, `family`, `cycle` | `scripts/prepare_corpus.py` (from the notice PDFs; titles tagged by Qwen3-32B) |
| `compiled_deepseek.jsonl` | raw compiler output for the 342 service notices: notice-level scope, outline (headings with the conditions they state) and span-grounded facts | `scripts/compile_graph.py` (DeepSeek-V4.1-Flash, temperature 0) |
| `graph_stats.json` | statistics of the full evidence graph (4,031 facts, 1,947 passages, 1,964 revision and 627 recurrence edges) | `scripts/build_index.py` |
| `gazetteer.json` | place names → campus (`zgc` / `tz`), the last resort of scope inheritance and the cue of T6 items | see *Provenance* below |
| `campus_prior.json` | per-service-type campus prior P(campus \| type) of the cost-sensitive responder (Eq. 2) | see *Provenance* below |
| `benchmark.jsonl` | CondQA-Campus: 247 items with question, hidden context (campus, date), gold and negative tokens, source fact | `scripts/build_benchmark.py` |
| `gold_facts.jsonl` | the verified gold facts of the 57 source notices | `scripts/build_benchmark.py` |
| `benchmark_sources.jsonl` | the source notices of the benchmark | `scripts/build_benchmark.py` |
| `audit_sheet.csv` | one row per item for manual verification | `scripts/build_benchmark.py` |
| `benchmark_stats.json` | counts per item type | `scripts/build_benchmark.py` |

The graph itself is not stored: `campusscope.graph.load_graph()` builds it from `notices.jsonl`,
`compiled_deepseek.jsonl` and `gazetteer.json` in about a second.

## Provenance

All files except two are derived from the public notices only. `gazetteer.json` and `campus_prior.json` were
derived from the department's internal service log as aggregates: the place names of requests whose campus is
recorded (a name is kept only if at least 97% of its requests come from one campus), and the campus shares of
the requests per service type (smoothed). No request text, person or other record of the log is contained in
them, and the log itself is not distributed.

## Cache

`cache/llm_cache.sqlite` (at the repository root, git-ignored) holds every LLM reply and embedding of the paper's
runs, keyed by the request. With it, `scripts/` and the demo replay the paper's runs without any model endpoint.
It is not included in this repository either.
