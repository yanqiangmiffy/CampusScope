"""Table 1 from the run records: accuracy overall and per type, SCE, TE and median seconds, plus the 95%
confidence interval of CampusScope's accuracy and paired p-values against every baseline. No model calls.

    python scripts/make_table.py                      # outputs/runs/ -> outputs/table1.md and table1.json
    python scripts/make_table.py --boot 2000          # fewer bootstrap resamples (faster)

Metric definitions: campusscope/evaluation/metrics.py.
"""
import argparse
import json

from campusscope.config import DATA, OUT, SYSTEM_MODEL
from campusscope.evaluation.metrics import KINDS, bootstrap_ci, load_items, load_runs, paired_p, summarize

M = SYSTEM_MODEL
ROWS = [
    (f"{M}__rag", "RAG (deployed)"),
    (f"{M}__rag_rules", "RAG + rules"),
    (f"{M}__clarify", "Clarify-then-answer"),
    (f"{M}__react", "ReAct agent"),
    (f"{M}__passage_rag", "Passage RAG"),
    (f"{M}__passage_rag_valid", "+ date filter"),
    (f"{M}__long_context", "Long context"),
    (f"{M}__campusscope", "CampusScope"),
]
SYSTEM = f"{M}__campusscope"


def fmt(x, digits=1):
    return "–" if x != x else f"{x:.{digits}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=str(OUT / "runs"))
    ap.add_argument("--boot", type=int, default=10000, help="bootstrap resamples")
    ap.add_argument("--time", default="latency", choices=("latency", "wall"), help="run field used for Sec.")
    args = ap.parse_args()
    items = load_items(DATA / "benchmark.jsonl")
    runs = {}
    for cfg, _ in ROWS:
        try:
            runs[cfg] = load_runs(f"{args.runs}/{cfg}.jsonl")
        except FileNotFoundError:
            print(f"missing run: {cfg}.jsonl")
    rows = []
    for cfg, label in ROWS:
        if cfg not in runs:
            continue
        r = summarize(runs[cfg], items, args.time)
        r.update(config=cfg, system=label)
        if cfg != SYSTEM and SYSTEM in runs:
            r["p_vs_campusscope"] = paired_p(runs[SYSTEM], runs[cfg], items, args.boot)
        rows.append(r)
    if SYSTEM in runs:
        lo, hi = bootstrap_ci(runs[SYSTEM], items, args.boot)
        next(r for r in rows if r["config"] == SYSTEM)["ci95"] = [lo, hi]

    head = "| System | Acc | " + " | ".join(KINDS) + " | SCE↓ | TE↓ | Sec. | p |"
    lines = [head, "|" + "---|" * (len(KINDS) + 6)]
    for r in rows:
        cells = [r["system"], fmt(r["acc"])] + [fmt(r["per_kind"][k], 0) for k in KINDS]
        cells += [fmt(r["sce"]), fmt(r["te"]), fmt(r["sec"]), f"{r['p_vs_campusscope']:.4f}" if "p_vs_campusscope" in r else ""]
        lines.append("| " + " | ".join(cells) + " |")
    note = f"\n{len(items)} items; SCE over {'/'.join(('T1', 'T2', 'T6'))}, TE over {'/'.join(('T3', 'T4', 'T5'))}; " \
           f"Sec. = median `{args.time}`; p = one-sided paired bootstrap over source notices ({args.boot} resamples)."
    sys_row = next((r for r in rows if r["config"] == SYSTEM), None)
    if sys_row and "ci95" in sys_row:
        note += f"\nCampusScope accuracy {sys_row['acc']:.1f}% (95% CI {sys_row['ci95'][0]:.1f}–{sys_row['ci95'][1]:.1f})."
    table = "\n".join(lines) + "\n" + note + "\n"
    print(table)
    (OUT / "table1.md").write_text(table, encoding="utf8")
    (OUT / "table1.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf8")


if __name__ == "__main__":
    main()
