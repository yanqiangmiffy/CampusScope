"""Runs the demonstration scenarios of Section 4.2 through CampusScope and stores their traces.

    python scripts/run_scenarios.py

S1 silent campus (C2), S2 scope stated (C1), S3 revision (C3), S4 no notice yet (C3); S5 is an extra
type-level question with many branches. The demo server makes the same calls, so all are cached.
Writes outputs/demo_scenarios.json (decision, costs, branch sizes, answer per scenario).
"""
import json

from campusscope.agent import CampusScope
from campusscope.config import OUT

SCENARIOS = {
    "S1": ("今天田径场几点开放？", "2026-01-20"),           # When is the track field open today?
    "S2": ("通州校区寒假健身房开吗？", "2026-02-12"),       # Tongzhou campus: is the gym open in the winter break?
    "S3": ("东区浴室早上几点开门？", "2026-03-09"),         # When does the East bathhouse open in the morning?
    "S4": ("今年寒假浴室几点开放？", "2025-12-28"),         # Bathhouse hours in this winter break?
    "S5": ("今天体育馆几点开放？", "2026-01-20"),           # When are the sports venues open today?
}


def main():
    c = CampusScope()
    path = OUT / "demo_scenarios.json"
    out = json.loads(path.read_text(encoding="utf8")) if path.exists() else {}
    for s, (q, day) in SCENARIOS.items():
        try:
            r = c.respond([dict(role="user", text=q)], day)
        except Exception as e:  # noqa: BLE001  (e.g. the embedding endpoint is down: keep the others, rerun later)
            print(s, "failed:", str(e)[:120])
            continue
        tr = r.get("trace", {})
        br = tr.get("branches") or {}
        out[s] = dict(question=q, today=day, action=r["action"], decision=tr.get("decision"), costs=tr.get("costs"),
                      branch_sizes={k: len(v) for k, v in br.items()}, revised=len(tr.get("revised") or []),
                      history=len(tr.get("history") or []), answer=r["text"], calls=r.get("calls"),
                      latency=round(r.get("latency", 0.0), 1))
        print(s, out[s]["decision"], out[s]["costs"], out[s]["branch_sizes"], "|", r["text"][:80])
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf8")


if __name__ == "__main__":
    main()
