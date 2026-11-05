import { useEffect, useMemo, useState } from "react";
import { fmt, type T } from "../i18n";
import { CAMPUS_COLOR, laneOf, layout, previewStatuses } from "../lib/graph";
import type { Fact, Status, Turn } from "../types";
import FactDrawer from "./FactDrawer";
import GraphView from "./GraphView";
import { Graph as GraphIcon, List } from "./icons";
import { STATUS_COLOR, statusOf } from "./TracePanel";

interface Props { T: T; turn: Turn | null; busy: boolean; onReask: (d: string) => void }

function FactRow({ f, s, T, onClick }: { f: Fact; s: Status; T: T; onClick: () => void }) {
  return <button className={"f-row st-" + s} onClick={onClick}>
    <span className="f-dot" style={{ background: CAMPUS_COLOR[laneOf(f.campus)] }} />
    <span className="f-main">
      <span className="f-v"><em>{f.entity} · {f.attr}</em>{f.value}</span>
      <span className="f-path">{f.path.length ? f.path.map((p, i) => <span key={i}>{p}</span>) : <span>—</span>}</span>
      <span className="f-meta">⏱ {f.start || f.end ? `${f.start || "…"} → ${f.end || "…"}` : T.standing} · {f.pub}</span>
    </span>
    <span className="f-s" style={{ color: STATUS_COLOR[s] === "#E4E7EC" ? "#98A2B3" : STATUS_COLOR[s] }}>{T.status[s]}</span>
  </button>;
}

export default function EvidencePanel({ T, turn, busy, onReask }: Props) {
  const g = turn?.graph;
  const [tab, setTab] = useState<"graph" | "list">("graph");
  const [showAll, setShowAll] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const [previewT, setPreviewT] = useState<string | null>(null);
  const [ents, setEnts] = useState<Set<string> | "relevant" | "all">("relevant");

  useEffect(() => { setSel(null); setPreviewT(null); setEnts("relevant"); }, [turn?.id, g]);

  const kind = turn?.stages.target?.data?.kind || "now";
  const target: [string, string] = useMemo(() => {
    if (!g) return ["", ""];
    return previewT && kind === "now" ? [previewT, previewT] : g.target;
  }, [g, previewT, kind]);

  const st = useMemo<Record<string, Status>>(() => {
    if (!g || !turn) return {};
    return previewT ? previewStatuses(g, previewT, target) : statusOf(turn);
  }, [g, turn, previewT, target]);

  const entities = useMemo(() => {
    if (!g) return [] as { e: string; n: number; rel: boolean; used?: boolean }[];
    const m = new Map<string, { n: number; rel: boolean; used?: boolean }>();
    const s0 = statusOf(turn!);
    for (const f of g.facts) {
      const r = m.get(f.ekey) || { n: 0, rel: false };
      r.n++;
      if (["used", "current", "revised", "history"].includes(s0[f.id])) r.rel = true;
      m.set(f.ekey, r);
    }
    const out = [...m.entries()].map(([e, v]) => ({ e, ...v })).sort((a, b) => Number(b.rel) - Number(a.rel) || b.n - a.n);
    // "relevant": the points the visitor named; else those of the facts the answer uses; else every point with an
    // applicable / revised / earlier-cycle fact
    const q = (turn?.question || "").replace(/\s+/g, "");
    const named = new Set(out.filter(o => o.e.length >= 2 && q.includes(o.e)).map(o => o.e));
    const used = new Set((turn?.used?.ids || []).map(id => g.facts.find(f => f.id === id)?.ekey));
    const pick = named.size ? named : used;
    if (pick.size) for (const o of out) { o.used = used.has(o.e); o.rel = pick.has(o.e); }
    else for (const o of out) o.used = o.rel;
    return out;
  }, [g, turn]);

  const visible = useMemo(() => {
    if (!g) return [] as Fact[];
    const keep = ents === "all" ? null : ents === "relevant" ? new Set(entities.filter(e => e.rel).map(e => e.e)) : ents;
    const vs = keep && keep.size ? g.facts.filter(f => keep.has(f.ekey)) : g.facts;
    return vs;
  }, [g, ents, entities]);

  const L = useMemo(() => (g && visible.length ? layout(g, visible) : null), [g, visible]);
  const band: [string, string] | null = g && (g.cycle || kind === "date") ? g.target : null;
  const fSel = g && sel ? g.facts.find(f => f.id === sel) || null : null;
  const toggleEnt = (e: string) => {
    const cur = new Set(ents === "all" ? entities.map(x => x.e) : ents === "relevant" ? entities.filter(x => x.rel).map(x => x.e) : ents);
    if (cur.has(e)) cur.delete(e);
    else cur.add(e);
    setEnts(cur.size ? cur : "all");
  };
  const isOn = (e: string) => ents === "all" || (ents === "relevant" ? entities.find(x => x.e === e)?.rel : ents.has(e));

  const groups = useMemo(() => {
    if (!g) return null;
    const pick = (s: Status[]) => visible.filter(f => s.includes(st[f.id]));
    return [
      [T.listUsed, pick(["used"])], [T.status.current, pick(["current"])], [T.listRevised, pick(["revised"])],
      [T.listHistory, pick(["history"])], [T.listOther, pick(["inactive", "future"])],
    ] as [string, Fact[]][];
  }, [g, visible, st, T]);

  return (
    <section className="panel evid">
      <div className="p-head">
        <h2>{T.evidence}</h2>
        {g && <span className="p-sub">{fmt(T.factsShown, { a: visible.length, b: g.total })}</span>}
        <div className="tabs">
          <button className={tab === "graph" ? "on" : ""} onClick={() => setTab("graph")}><GraphIcon />{T.graphTab}</button>
          <button className={tab === "list" ? "on" : ""} onClick={() => setTab("list")}><List />{T.listTab}</button>
        </div>
      </div>

      {g && entities.length > 1 && (
        <div className="ents-bar">
          <span className="eb-l">{T.entitiesF}</span>
          <button className={"eb-p" + (ents === "relevant" ? " on" : "")} onClick={() => setEnts("relevant")}>{T.relevant}</button>
          <button className={"eb-p" + (ents === "all" ? " on" : "")} onClick={() => setEnts("all")}>{T.all}</button>
          <span className="eb-sep" />
          <div className="eb-list">{entities.map(x => (
            <button key={x.e} className={"eb-e" + (isOn(x.e) ? " on" : "") + (x.used ? " rel" : "")} onClick={() => toggleEnt(x.e)}>{x.e}<i>{x.n}</i></button>))}
          </div>
        </div>
      )}

      <div className="ev-body">
        {!turn && <div className="ev-empty"><EmptyArt /><p>{T.graphEmpty}</p></div>}
        {turn && !g && (busy ? <div className="ev-empty loading"><div className="skel"><i /><i /><i /><i /><i /><i /></div><p>{T.graphLoading}</p></div>
          : <div className="ev-empty"><p>{turn.error || T.noCurrent}</p></div>)}

        {g && L && tab === "graph" && <>
          <GraphView hideMini={!!fSel} emph={previewT ? undefined : new Set(turn?.used?.revisedShown || [])} T={T} g={g} L={L} visible={visible} st={st} mode={turn?.used?.mode} sel={sel} setSel={setSel}
                     showAll={showAll} previewT={previewT} setPreviewT={setPreviewT} band={band} />
          <div className="legend">
            <span><i className="sw" style={{ background: CAMPUS_COLOR.zgc }} />{T.zgc}</span>
            <span><i className="sw" style={{ background: CAMPUS_COLOR.tz }} />{T.tz}</span>
            {(["used", "revised", "history", "future"] as Status[]).map(s => <span key={s}><i className="sw" style={{ background: STATUS_COLOR[s] === "#E4E7EC" ? "#C4CAD4" : STATUS_COLOR[s] }} />{T.status[s]}</span>)}
            <span><i className="ln rev" />{T.legendRev}</span><span><i className="ln rec" />{T.legendRec}</span>
            <label className="chk"><input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} />{T.allEdges}</label>
          </div>
        </>}

        {g && tab === "list" && groups && <div className="list">
          {groups.filter(([, fs]) => fs.length).map(([name, fs]) => (
            <div key={name} className="lg"><h5>{name}<i>{fs.length}</i></h5>
              {fs.map(f => <FactRow key={f.id} f={f} s={st[f.id]} T={T} onClick={() => { setSel(f.id); }} />)}</div>))}
        </div>}

        {previewT && g && <div className="preview-bar">
          <span className="pv-dot" /><span className="pv-t">{fmt(T.previewMsg, { t: previewT })}</span>
          <button onClick={() => onReask(previewT)} disabled={busy}>{T.reask}</button>
          <button className="ghost" onClick={() => setPreviewT(null)}>{T.reset}</button>
        </div>}

        {g && fSel && <FactDrawer T={T} g={g} f={fSel} st={st} today={previewT || g.today} target={target} setSel={setSel} />}
      </div>
    </section>
  );
}

function EmptyArt() {
  return <svg width="220" height="120" viewBox="0 0 220 120" fill="none" className="art">
    <rect x="6" y="18" width="208" height="38" rx="12" fill="#2E6BE6" opacity=".06" stroke="#DCE7FD" />
    <rect x="6" y="64" width="208" height="38" rx="12" fill="#E8772E" opacity=".06" stroke="#FDE3CF" />
    <path d="M30 10H200" stroke="#98A2B3" /><path d="M150 4v110" stroke="#101828" strokeWidth="1.5" />
    <rect x="24" y="27" width="62" height="20" rx="10" fill="#fff" stroke="#2E6BE6" /><rect x="96" y="27" width="46" height="20" rx="10" fill="#fff" stroke="#12B76A" strokeWidth="2" />
    <rect x="40" y="73" width="58" height="20" rx="10" fill="#fff" stroke="#E8772E" /><rect x="118" y="73" width="70" height="20" rx="10" fill="#fff" stroke="#E8772E" />
    <path d="M56 47c10 22 60 22 70 0" stroke="#E5484D" strokeDasharray="4 3" /><path d="M70 73c10-16 40-16 50 0" stroke="#7C5CFA" strokeDasharray="3 3" />
  </svg>;
}
