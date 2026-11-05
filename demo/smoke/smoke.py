"""Smoke test: wait until the demo is ready, ask the five scenarios, check the protocol and the answers.

    python smoke/smoke.py                                # through nginx: http://localhost:8795
    python smoke/smoke.py --base http://localhost:8796   # the backend directly
    python smoke/smoke.py --only S1                      # one scenario

Standard library only. Checks for every scenario: the stream ends with exactly one terminal event and
[DONE], the evidence graph arrives before the answer text, and the decision is the expected one.
"""
import argparse
import sys
import time

from sse_client import ask, get_json, terminal

# decision of the system per scenario (S1-S4 as in outputs/demo_scenarios.json; S5 lists the branches)
EXPECT = {"S1": "enumerate", "S2": "answer", "S3": "answer", "S4": "history", "S5": "enumerate"}


def wait_ready(base: str, timeout: float) -> dict:
    deadline, last = time.time() + timeout, ""
    while time.time() < deadline:
        try:
            h = get_json(f"{base}/api/health")
            if h["error"]:
                sys.exit(f"[fail] backend error: {h['error']}")
            if h["ready"]:
                return h
            p = (h.get("index") or {}).get("progress")
            now = f"{h['stage']}" + (f" {p['collection']} {p['done']}/{p['total']}" if p else "")
            if now != last:
                print(f"[..] {now}", flush=True)
                last = now
        except Exception as e:  # noqa: BLE001
            if str(e) != last:
                print(f"[..] {e}", flush=True)
                last = str(e)
        time.sleep(2)
    sys.exit("[fail] not ready in time")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:8795")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    h = wait_ready(args.base, args.timeout)
    print(f"[ok] ready · index {h['index']['state']} · zero vectors {h['index']['zero_vectors']} · "
          f"embedding {h['embedding']['state']}")
    scenarios = get_json(f"{args.base}/api/meta")["scenarios"]
    failed = 0
    for s in scenarios:
        if args.only and s["id"] not in args.only.split(","):
            continue
        events, first, total, done = ask(args.base, s["q"], s["d"])
        types = [e["type"] for e in events]
        end = terminal(events)
        decision = next((e["data"].get("decision") for e in events if e["type"] == "stage" and e["id"] == "decide"
                         and e["status"] == "done"), None)
        problems = []
        if not done:
            problems.append("no [DONE]")
        if not end or events[-1] is not end or sum(t in ("complete", "error") for t in types) != 1:
            problems.append("terminal event")
        if end and end["type"] == "error":
            problems.append(f"error: {end['message']}")
        if "graph" not in types or ("delta" in types and types.index("graph") > types.index("delta")):
            problems.append("graph after text")
        if decision != EXPECT.get(s["id"], decision):
            problems.append(f"decision {decision} != {EXPECT[s['id']]}")
        base = next((e for e in events if e["type"] == "baseline" and e.get("status") == "done"), None)
        tag = "[ok]  " if not problems else "[FAIL]"
        failed += bool(problems)
        answer = end.get("answer", "")[:48] if end else ""
        print(f"{tag} {s['id']} {s['q']} · first step {first or 0:.2f}s · total {total:.1f}s · {decision} · "
              f"{end.get('calls', '?') if end else '?'} calls{' · cached' if end and end.get('cached') else ''}"
              f"{' · RAG ok' if base else ''}\n       {answer}{'  ' + '; '.join(problems) if problems else ''}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
