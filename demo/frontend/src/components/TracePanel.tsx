import { fmt, type T } from "../i18n";
import { STAGES, type StageId, type Status, type Turn } from "../types";
import { Check, Cross, Warn } from "./icons";

export const STATUS_COLOR: Record<Status, string> = {
  used: "#12B76A", current: "#2E6BE6", revised: "#E5484D", history: "#7C5CFA", inactive: "#C4CAD4", future: "#E4E7EC",
};
const ORDER: Status[] = ["used", "current", "revised", "history", "inactive", "future"];

export function statusOf(t: Turn) {
  const out: Record<string, Status> = {};
  if (!t.graph) return out;
  const used = new Set(t.used?.ids || []);
  for (const f of t.graph.facts) out[f.id] = used.has(f.id) && t.used?.mode !== "ask" ? "used" : f.status;
  return out;
}

function Chip({ k, v, tone }: { k: string; v: React.ReactNode; tone?: string }) {
  return <span className={"kv " + (tone || "")}><em>{k}</em><b>{v}</b></span>;
}

function Body({ id, t, T }: { id: StageId; t: Turn; T: T }) {
  const s = t.stages[id];
  const d = s?.data || {};
  switch (id) {
    case "plan": {
      if (!s || s.status !== "done") return null;
      const p = d.plan || {}, tg = p.target || {};
      const time = tg.kind === "period" ? `${tg.period || ""}${tg.year ? " " + tg.year : ""}` : tg.kind === "date" ? tg.date : T.now;
      return <div className="kvs">
        <Chip k={T.point} v={p.entity || "—"} /><Chip k={T.type} v={p.type || "—"} /><Chip k={T.attr} v={p.attr || "—"} />
        <Chip k={T.time} v={time} />
        <Chip k={T.campusK} v={d.campus ? `${T[d.campus as "zgc"]} · ${d.campusHow === "gazetteer" ? T.byGaz : T.byUser}` : T.unknown}
              tone={d.campus || "warn"} />
      </div>;
    }
    case "ground":
      if (!s || s.status !== "done") return null;
      return <>
        <div className="flow"><span><b>{d.hits}</b> {T.hits}</span><i>→</i><span><b>{d.candidates}</b> {T.cands}</span><i>·</i><span><b>{d.nEntities}</b> {T.entities}</span></div>
        <div className="ents">{(d.entities || []).slice(0, 8).map((e: string) => <span key={e}>{e}</span>)}{d.nEntities > 8 && <span>+{d.nEntities - 8}</span>}</div>
        {d.degraded && <div className="degraded"><Warn />{T.embDown}</div>}
      </>;
    case "target":
      if (!s) return null;
      return <div className="target">
        {d.cycle ? <><span className="cyc">{d.cycle[1]} {d.cycle[0]}</span><code>{d.lo} → {d.hi}</code></> : <code>{d.lo}</code>}
      </div>;
    case "apply": {
      if (!s || s.status !== "done" || !t.graph) return null;
      const st = statusOf(t), n = t.graph.facts.length || 1;
      const counts = ORDER.map(k => [k, Object.values(st).filter(v => v === k).length] as [Status, number]).filter(x => x[1]);
      return <>
        <div className="stack">{counts.map(([k, v]) => <i key={k} style={{ width: `${(100 * v) / n}%`, background: STATUS_COLOR[k] }} title={`${T.status[k]} ${v}`} />)}</div>
        <div className="stack-l">{counts.map(([k, v]) => <span key={k}><i style={{ background: STATUS_COLOR[k] }} />{T.status[k]} <b>{v}</b></span>)}</div>
        <div className="kvs"><em className="lbl">{T.branches}</em>
          {Object.keys(d.branches || {}).length ? Object.entries(d.branches).map(([k, v]) =>
            <span key={k} className={"br " + k}>{k === "all" ? T.allFull : T[k as "zgc"]} <b>{v as number}</b></span>) : <span className="br">{T.none}</span>}
        </div>
      </>;
    }
    case "decide": {
      if (!s) return null;
      const dec = d.decision as string;
      if (!d.costs || !Object.keys(d.costs).length) {
        return <div className="dec-row"><span className="decision" data-d={dec}>{T.act[dec] || dec}</span>
          {dec === "answer" && <span className="muted">{T.noFrontier}</span>}</div>;
      }
      const c = d.costs as Record<string, number>, max = Math.max(1, ...Object.values(c).map(v => Math.min(v, 12)));
      const win = dec === "enumerate" ? "enumerate" : dec === "ask" ? "ask" : dec === "assume" ? "assume" : "";
      const P = d.prior?.[d.best] ?? 0, sizes = d.sizes || {};
      const extra = Object.entries(sizes).reduce((a, [k, v]) => a + (k === d.best ? 0 : (v as number)), 0);
      const rows: [string, string, string][] = [
        ["assume", T.costGuess, `λ·(1−P) = ${d.lam}×(1−${P.toFixed(2)})`],
        ["enumerate", T.costList, `β·Δ = ${d.beta}×${extra}`],
        ["ask", T.costAsk, "1"],
      ];
      return <>
        <div className="costs">{rows.filter(r => c[r[0]] !== undefined).map(([k, name, f]) => (
          <div key={k} className={"cost" + (k === win ? " win" : "")}>
            <span className="c-n">{name}</span>
            <span className="c-bar"><i style={{ width: `${Math.max(4, (100 * Math.min(c[k], 12)) / max)}%` }} /></span>
            <span className="c-v">{c[k].toFixed(2)}</span>
            <span className="c-f">{f}</span>
          </div>))}
        </div>
        <div className="dec-row"><span className="decision" data-d={dec}>{T.act[dec] || dec}</span>
          <span className="muted small">{fmt(T.priorP, { t: d.etype || "" })}: {Object.entries(d.prior || {}).map(([k, v]) => `${T[k as "zgc"]} ${(v as number).toFixed(2)}`).join(" · ")}</span></div>
      </>;
    }
    case "write":
      if (!s) return null;
      return <div className="flow"><em className="lbl">{T.licensed}</em>
        <span><b>{d.nFacts}</b> {T.facts}</span><span><b>{d.nPassages}</b> {T.passages}</span>{d.nRevised > 0 && <span><b>{d.nRevised}</b> {T.oldArr}</span>}
        {d.cached && <span className="cached">{T.cached}</span>}</div>;
    case "verify":
      if (!s || s.status !== "done") return null;
      return <div className="times">
        {(d.times || []).length ? d.times.map((x: string) => (
          <span key={x} className={"tm " + ((d.bad || []).includes(x) ? "bad" : "ok")}>{(d.bad || []).includes(x) ? <Cross size={10} /> : <Check size={10} />}{x}</span>))
          : <span className="muted">{T.noTimes}</span>}
        {d.rewritten ? <span className="muted">{d.fallback ? T.fallback : T.rewritten}</span> : d.times?.length ? <span className="muted">{T.allGood}</span> : null}
      </div>;
  }
}

export default function TracePanel({ T, turn, busy }: { T: T; turn: Turn | null; busy: boolean }) {
  const t = turn;
  const decided = t?.stages.decide?.data?.decision;
  const stages = STAGES.filter(id => !(t?.final && !t.stages[id] && (id === "write" || id === "verify") && (decided === "ask" || decided === "abstain")));
  const firstPending = t ? stages.find(id => !t.stages[id] || t.stages[id]!.status !== "done") : undefined;
  return (
    <section className="panel trace">
      <div className="p-head"><h2>{T.trace}</h2>
        {t?.done && <span className="p-sub">{t.done.calls} {T.calls} · {t.done.latency.toFixed(1)}s</span>}</div>
      <div className="p-body">
        {!t && <p className="empty">{T.traceEmpty}</p>}
        {t && <ol className="steps">
          {stages.map((id, i) => {
            const s = t.stages[id];
            const state = s?.status === "done" ? "done" : s?.status === "running" || (busy && id === firstPending && !t.error) ? "run" : "wait";
            const llm = id === "plan" || id === "write";
            return (
              <li key={id} className={"step " + state + (llm ? " llm" : "")} style={{ animationDelay: `${i * 30}ms` }}>
                <div className="s-dot">{state === "done" ? <Check size={11} /> : state === "run" ? <span className="spin" /> : i + 1}</div>
                <div className="s-main">
                  <div className="s-head">
                    <span className="s-t">{T.st[id]}</span>
                    <span className="s-h">{llm && <span className="llm-tag">LLM</span>}{T.stHint[id]}</span>
                    {s?.ms !== undefined && <span className="s-ms">{s.ms < 1000 ? `${s.ms} ms` : `${(s.ms / 1000).toFixed(1)} s`}</span>}
                  </div>
                  <div className="s-body"><Body id={id} t={t} T={T} /></div>
                </div>
              </li>
            );
          })}
        </ol>}
      </div>
    </section>
  );
}
