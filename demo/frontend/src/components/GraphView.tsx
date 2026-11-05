import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { T } from "../i18n";
import { arc, CAMPUS_COLOR, PILL_H, textW, type Layout } from "../lib/graph";

const textWidth = (s: string, size: number, w = 750) => textW(s, size, w);
import type { Fact, Graph, Status } from "../types";
import { Fit, Minus, Plus } from "./icons";

interface Props {
  hideMini?: boolean; emph?: Set<string>;
  T: T; g: Graph; L: Layout; visible: Fact[]; st: Record<string, Status>; mode?: string;
  sel: string | null; setSel: (id: string | null) => void;
  showAll: boolean; previewT: string | null; setPreviewT: (t: string | null) => void; band: [string, string] | null;
}

const LANE_NAME = (T: T, c: string) => (c === "zgc" ? T.zgcFull : c === "tz" ? T.tzFull : T.allFull);
const tipW = 300;

export default function GraphView({ hideMini, emph, T, g, L, visible, st, mode, sel, setSel, showAll, previewT, setPreviewT, band }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 500 });
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const [hover, setHover] = useState<string | null>(null);
  const [tip, setTip] = useState<{ x: number; y: number; html: React.ReactNode } | null>(null);
  const drag = useRef<{ kind: "pan" | "today"; sx: number; sy: number; vx: number; vy: number } | null>(null);
  const today = previewT || g.today;

  useLayoutEffect(() => {
    const el = box.current; if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el); setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  // initial view: as large as the height allows (not smaller than fitting the width), centred on "today"
  const fit = useCallback(() => {
    const wFit = (size.w - 16) / L.W, hFit = (size.h - 8) / L.H;
    const k = Math.max(0.62, Math.min(1.05, Math.max(wFit, Math.min(hFit, 0.92))));     // never below a readable size
    const cw = L.W * k, ch = L.H * k;
    const x = cw <= size.w - 16 ? (size.w - cw) / 2 : Math.min(8, Math.max(size.w - cw - 8, size.w * 0.55 - L.X(g.today) * k));
    setView({ k, x, y: ch < size.h ? Math.min(24, (size.h - ch) / 4) : 4 });
  }, [size.w, size.h, L, g.today]);
  // re-fit when the drawn subgraph changes (not when a status changes)
  const sig = `${L.W}|${L.H}|${visible.length}`;
  useEffect(() => { fit(); }, [sig, size.w]); // eslint-disable-line react-hooks/exhaustive-deps

  const toGraph = (cx: number, cy: number) => {
    const r = box.current!.getBoundingClientRect();
    return { x: (cx - r.left - view.x) / view.k, y: (cy - r.top - view.y) / view.k };
  };
  const zoomAt = (f: number, cx?: number, cy?: number) => {
    const r = box.current!.getBoundingClientRect();
    const px = cx === undefined ? r.width / 2 : cx - r.left, py = cy === undefined ? r.height / 2 : cy - r.top;
    setView(v => { const k = Math.max(0.3, Math.min(2.6, v.k * f)); return { k, x: px - ((px - v.x) * k) / v.k, y: py - ((py - v.y) * k) / v.k }; });
  };
  const onWheel = (e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey) { zoomAt(Math.exp(-e.deltaY * 0.0022), e.clientX, e.clientY); return; }
    setView(v => ({ ...v, x: v.x - (e.shiftKey ? e.deltaY : e.deltaX), y: v.y - (e.shiftKey ? 0 : e.deltaY) }));
  };
  useEffect(() => {   // block the page's own ctrl+wheel zoom inside the graph
    const el = box.current; if (!el) return;
    const h = (e: WheelEvent) => e.preventDefault();
    el.addEventListener("wheel", h, { passive: false });
    return () => el.removeEventListener("wheel", h);
  }, []);

  const setTodayFrom = (clientX: number, clientY: number) => {
    const t = L.INV(toGraph(clientX, clientY).x);
    const clamped = t < L.lo ? L.lo : t > L.hi ? L.hi : t;
    setPreviewT(clamped === g.today ? null : clamped);
  };
  const onDown = (e: React.PointerEvent) => {
    const target = e.target as Element;
    if (target.closest(".pill")) return;
    const isToday = !!target.closest(".today-h") || !!target.closest(".axis-hit");
    drag.current = { kind: isToday ? "today" : "pan", sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y };
    try { (e.currentTarget as Element).setPointerCapture(e.pointerId); } catch { /* synthetic pointer */ }
    if (isToday) setTodayFrom(e.clientX, e.clientY);
    setTip(null);
  };
  const onMove = (e: React.PointerEvent) => {
    const d = drag.current; if (!d) return;
    if (d.kind === "pan") setView(v => ({ ...v, x: d.vx + e.clientX - d.sx, y: d.vy + e.clientY - d.sy }));
    else setTodayFrom(e.clientX, e.clientY);
  };
  const onUp = (e: React.PointerEvent) => {
    const d = drag.current; drag.current = null;
    if (d?.kind === "pan" && Math.abs(e.clientX - d.sx) + Math.abs(e.clientY - d.sy) < 4) setSel(null);
  };

  const byId = useMemo(() => Object.fromEntries(g.facts.map(f => [f.id, f])), [g]);
  const vis = useMemo(() => new Set(visible.map(f => f.id)), [visible]);
  const focus = hover || sel;
  const linked = useMemo(() => {
    if (!focus) return null;
    const s = new Set([focus]);
    for (const e of g.edges) if (e.src === focus || e.dst === focus) { if (e.kind === "rec" && !e.near) continue; s.add(e.src); s.add(e.dst); }
    const f = byId[focus];
    if (f) for (const x of g.facts) if (x.doc === f.doc && x.ekey === f.ekey) s.add(x.id);
    return s;
  }, [focus, g, byId]);

  const years: number[] = [];
  for (let y = +L.lo.slice(0, 4) + 1; y <= +L.hi.slice(0, 4); y++) years.push(y);
  const notices = g.notices.filter(n => L.cols[n.id]);
  const tx = L.X(today);

  // edges to draw
  // revisions: per revised fact only its newest active reviser; by default only where the reviser is what applies
  // now (or the old fact was shown to the writer), so a key with dozens of revisions stays readable
  const newest: Record<string, string> = {};
  for (const e of g.edges) {
    if (e.kind !== "rev" || st[e.dst] !== "revised" || !(byId[e.src]?.pub <= today)) continue;
    if (!newest[e.dst] || byId[e.src].pub > byId[newest[e.dst]].pub) newest[e.dst] = e.src;
  }
  const revEdges = g.edges.filter(e => e.kind === "rev" && vis.has(e.src) && vis.has(e.dst)).map(e => {
    const active = newest[e.dst] === e.src;
    const key = active && (["used", "current"].includes(st[e.src]) || !!emph?.has(e.dst));
    return { ...e, active, show: showAll || key || (focus !== null && (e.src === focus || e.dst === focus)) };
  }).filter(e => e.show);
  const recEdges = g.edges.filter(e => e.kind === "rec" && e.near && vis.has(e.src) && vis.has(e.dst) &&
    (showAll || (focus !== null && (e.src === focus || e.dst === focus))));
  const histUsed = !previewT && mode === "history" ? visible.filter(f => st[f.id] === "used") : [];

  const showTip = (e: React.PointerEvent, f: Fact) => {
    const r = box.current!.getBoundingClientRect();
    const x = Math.min(e.clientX - r.left + 14, r.width - tipW - 8), y = e.clientY - r.top + 16;
    setTip({ x, y, html: <>
      <div className="tt-h">{f.entity} · {f.attr}</div>
      <div className="tt-v">{f.value}</div>
      <div className="tt-r"><span className={"tt-s st-" + st[f.id]}>{T.status[st[f.id]]}</span>
        <span>{LANE_NAME(T, f.campus || "all")}</span></div>
      <div className="tt-r muted">{T.validity} {f.start || f.end ? `${f.start || "…"} → ${f.end || "…"}` : T.standing}</div>
      <div className="tt-r muted">《{g.notices.find(n => n.id === f.doc)?.title}》{f.pub}</div>
    </> });
  };

  const badge = (f: Fact, it: { x: number; y: number; w: number }) => {
    const s = st[f.id];
    let b: [string, string] | null = null;
    if (s === "used") b = mode === "history" ? [`${f.cycle || ""} ✓`, "#7C5CFA"] : ["✓", "#12B76A"];
    else if (mode === "ask" && s === "current" && !previewT) b = ["?", "#12B76A"];
    else if (s === "revised") b = [T.badge.revised, "#E5484D"];
    else if (s === "future") b = [T.badge.future, "#98A2B3"];
    else if (s === "history") b = [String(f.cycle || T.status.history), "#7C5CFA"];
    if (!b) return null;
    const bw = Math.max(20, b[0].length * (/[一-龥]/.test(b[0]) ? 11 : 7) + 12), bx = it.x + it.w - bw + 8, by = it.y - 9;
    return <g className="badge">
      <rect x={bx} y={by} width={bw} height={17} rx={8.5} fill={b[1]} stroke="#fff" strokeWidth={1.5} />
      <text x={bx + bw / 2} y={by + 12.3} textAnchor="middle" fontSize={10.5} fontWeight={800} fill="#fff">{b[0]}</text>
    </g>;
  };

  return (
    <div className="gv" ref={box} onWheel={onWheel} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp}
         onPointerLeave={() => setTip(null)}>
      <svg width={size.w} height={size.h} className="gv-svg">
        <defs>
          <pattern id="grid" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#E4E7EC" /></pattern>
          <marker id="mRev" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#E5484D" /></marker>
          <marker id="mRec" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#7C5CFA" /></marker>
          <filter id="sh" x="-20%" y="-40%" width="140%" height="200%"><feDropShadow dx="0" dy="1.5" stdDeviation="2" floodColor="#101828" floodOpacity=".10" /></filter>
          <filter id="glowOk" x="-30%" y="-80%" width="160%" height="260%"><feDropShadow dx="0" dy="0" stdDeviation="4" floodColor="#12B76A" floodOpacity=".55" /></filter>
          <filter id="glowRec" x="-30%" y="-80%" width="160%" height="260%"><feDropShadow dx="0" dy="0" stdDeviation="4" floodColor="#7C5CFA" floodOpacity=".5" /></filter>
          {(["zgc", "tz", "all"] as const).map(c => (
            <linearGradient key={c} id={`fade-${c}`} x1="0" x2="1" y1="0" y2="0">
              <stop offset="0" stopColor={CAMPUS_COLOR[c]} stopOpacity=".55" /><stop offset=".7" stopColor={CAMPUS_COLOR[c]} stopOpacity=".35" />
              <stop offset="1" stopColor={CAMPUS_COLOR[c]} stopOpacity="0" /></linearGradient>))}
          <linearGradient id="band" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#0891B2" stopOpacity=".13" /><stop offset="1" stopColor="#0891B2" stopOpacity=".04" /></linearGradient>
        </defs>
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          <rect x={0} y={0} width={L.W} height={L.H} fill="url(#grid)" rx={14} />

          {/* notice columns */}
          {notices.map(n => {
            const c = L.cols[n.id];
            return <g key={n.id} className="col-h"
                      onPointerEnter={e => { const r = box.current!.getBoundingClientRect(); setTip({ x: Math.min(e.clientX - r.left + 12, r.width - tipW - 8), y: e.clientY - r.top + 14, html: <><div className="tt-h">{n.title}</div><div className="tt-r muted">{T.published} {n.pub}{n.ptype ? ` · ${n.ptype}` : ""}</div><div className="tt-r muted">{g.facts.filter(f => f.doc === n.id).length} {T.facts}</div></> }); }}
                      onPointerLeave={() => setTip(null)}>
              <rect x={c.x - 6} y={16} width={Math.max(c.w, 96) + 4} height={50} rx={10} className="col-hit" />
              <g transform={`translate(${c.x},${24})`}>
                <path d="M2 0h11l6 6v17a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2z" fill="#EEF0FF" stroke="#6366F1" strokeWidth="1.3" />
                <path d="M13 0v6h6M4.5 12h10M4.5 16.5h7" stroke="#6366F1" strokeWidth="1.2" fill="none" />
              </g>
              <text x={c.x + 26} y={37} className="col-k">{n.kind}</text>
              <text x={c.x + 26} y={52} className="col-d">{n.pub}</text>
              <line x1={c.x} y1={L.axisY - 4} x2={c.x} y2={L.axisY + 4} stroke="#667085" strokeWidth={1.4} />
            </g>;
          })}

          {/* axis */}
          <line x1={L.X0} y1={L.axisY} x2={L.X1} y2={L.axisY} stroke="#98A2B3" strokeWidth={1.2} />
          <path d={`M${L.X1},${L.axisY - 4} l7,4 l-7,4 z`} fill="#98A2B3" />
          {years.map(y => {
            const x = L.X(`${y}-01-01`);
            return <g key={y}>
              <line x1={x} y1={L.axisY + 4} x2={x} y2={L.bottom} stroke="#D0D5DD" strokeDasharray="2 5" />
              <rect x={x - 20} y={L.axisY + 8} width={40} height={17} rx={8.5} fill="#F2F4F7" />
              <text x={x} y={L.axisY + 20.5} textAnchor="middle" className="yr">{y}</text>
            </g>;
          })}
          <rect className="axis-hit" x={L.X0} y={L.axisY - 12} width={L.X1 - L.X0} height={36} fill="transparent" />

          {/* campus lanes (their labels are drawn last, pinned to the left edge of the view) */}
          {L.lanes.map(l => (
            <g key={l.c} className={"lane lane-" + l.c}>
              <rect x={12} y={l.y} width={L.W - 24} height={l.h} rx={16} className="lane-bg" />
            </g>
          ))}

          {/* asked period */}
          {band && (() => {
            const x0 = L.X(band[0]), x1 = Math.max(L.X(band[1]), x0 + 4);
            return <g className="band">
              <rect x={x0} y={L.top - 8} width={x1 - x0} height={L.bottom - L.top + 16} rx={10} fill="url(#band)" stroke="#0891B2" strokeDasharray="5 4" />
              <text x={Math.min(x0 + 6, L.X1 - 160)} y={L.top + 5} className="band-t">{T.askedPeriod} {g.cycle ? `${g.cycle[1]} ${g.cycle[0]}` : band[0]}</text>
            </g>;
          })()}

          {/* today line (under the pills) */}
          <line x1={tx} y1={L.axisY - 6} x2={tx} y2={L.bottom + 8} stroke={previewT ? "#5B47F0" : "#101828"} strokeWidth={1.6} className="today-l" />
          <path d={`M${tx - 6},${L.axisY - 10} L${tx + 6},${L.axisY - 10} L${tx},${L.axisY - 2} z`} fill={previewT ? "#5B47F0" : "#101828"} />

          {/* edges */}
          <g className="edges">
            {recEdges.map(e => { const a = L.items[e.src], b = L.items[e.dst]; if (!a || !b) return null;
              return <path key={`c${e.src}${e.dst}`} d={arc(a.x + 16, a.y - 1, b.x + b.w - 16, b.y - 1, true)} className="e-rec" markerEnd="url(#mRec)" />; })}
            {revEdges.map(e => { const a = L.items[e.src], b = L.items[e.dst]; if (!a || !b) return null;
              return <path key={`r${e.src}${e.dst}`} d={arc(a.x + 16, a.y + PILL_H - 1, b.x + b.w - 16, b.y + PILL_H - 1, false)}
                           className={"e-rev" + (e.active ? " active" : "")} markerEnd="url(#mRev)" />; })}
            {histUsed.map(f => { const b = L.items[f.id]; if (!b) return null; const x1 = band ? L.X(band[0]) : tx;
              return <path key={`h${f.id}`} d={arc(x1, b.y - 12, b.x + b.w - 14, b.y - 2, true)} className="e-hist" markerEnd="url(#mRec)" />; })}
          </g>

          {/* fact pills */}
          <g>
            {visible.map((f, i) => {
              const it = L.items[f.id]; if (!it) return null;
              const s = st[f.id], col = CAMPUS_COLOR[it.lane];
              const dim = linked ? !linked.has(f.id) : false;
              const by = it.y + PILL_H + 6, px = L.X(f.pub);
              const filter = s === "used" ? (mode === "history" ? "url(#glowRec)" : "url(#glowOk)") : "url(#sh)";
              return (
                <g key={f.id} className={`pill st-${s}${sel === f.id ? " sel" : ""}${dim ? " dim" : ""}`} style={{ animationDelay: `${Math.min(i, 40) * 14}ms` }}
                   onPointerEnter={e => { setHover(f.id); showTip(e, f); }} onPointerMove={e => showTip(e, f)}
                   onPointerLeave={() => { setHover(null); setTip(null); }}
                   onClick={e => { e.stopPropagation(); setSel(sel === f.id ? null : f.id); }}>
                  <rect x={it.bx0} y={by} width={Math.max(4, it.bx1 - it.bx0)} height={4} rx={2} fill={it.open ? `url(#fade-${it.lane})` : col} opacity={it.open ? 1 : 0.5} />
                  <path d={`M${px},${by - 2.5} l4.5,4.5 l-4.5,4.5 l-4.5,-4.5 z`} fill="#344054" />
                  <rect className="pb" x={it.x} y={it.y} width={it.w} height={PILL_H} rx={PILL_H / 2} stroke={col} filter={filter} />
                  <circle cx={it.x + 14} cy={it.y + PILL_H / 2} r={4} fill={col} />
                  <text x={it.x + 25} y={it.y + 18.5} className="p-t">{it.label}</text>
                  <line className="strike" x1={it.x + 8} y1={it.y + PILL_H / 2} x2={it.x + it.w - 8} y2={it.y + PILL_H / 2} />
                  {f.err && <g className="err-mark"><circle cx={it.x + 14} cy={it.y + PILL_H / 2} r={7.5} fill="#F59E0B" stroke="#fff" strokeWidth={1.5} />
                    <text x={it.x + 14} y={it.y + PILL_H / 2 + 4} textAnchor="middle" fontSize={11} fontWeight={900} fill="#fff">!</text></g>}
                  {badge(f, it)}
                </g>
              );
            })}
          </g>

          {/* lane labels, sticky on the left */}
          {L.lanes.map(l => {
            const lx = Math.max(16, -view.x / view.k + 8), name = LANE_NAME(T, l.c);
            const w = textWidth(name, 12) + 24;
            return <g key={"lbl" + l.c} className="lane-lbl" transform={`translate(${lx},${l.y + 6})`}>
              <title>{`${name} · ${T.lane}`}</title>
              <rect x={0} y={0} width={w} height={22} rx={11} className="lane-lbl-bg" stroke={CAMPUS_COLOR[l.c]} />
              <circle cx={11} cy={11} r={3.5} fill={CAMPUS_COLOR[l.c]} />
              <text x={19} y={15} className="lane-t" fill={CAMPUS_COLOR[l.c]}>{name}</text>
            </g>;
          })}

          {/* today handle (on top) */}
          <g className="today-h" transform={`translate(${Math.max(L.X0 + 70, Math.min(L.X1 - 80, tx))},${L.bottom + 14})`}>
            <rect x={-82} y={0} width={164} height={30} rx={15} fill={previewT ? "#5B47F0" : "#101828"} filter="url(#sh)" />
            <text x={-68} y={20.5} className="th-a">‹</text>
            <text x={0} y={20} textAnchor="middle" className="th-t">{previewT ? T.previewing : T.todayLbl} {today}</text>
            <text x={62} y={20.5} className="th-a">›</text>
          </g>
        </g>
      </svg>

      {tip && <div className="tt" style={{ left: tip.x, top: tip.y, width: tipW }}>{tip.html}</div>}

      {!hideMini && (L.W * view.k > size.w + 4 || L.H * view.k > size.h + 4) && (() => {
        const m = Math.min(170 / L.W, 64 / L.H), vw = size.w / view.k, vh = size.h / view.k;
        const go = (e: React.PointerEvent) => {
          const r = (e.currentTarget as Element).getBoundingClientRect();
          const gx = (e.clientX - r.left) / m, gy = (e.clientY - r.top) / m;
          setView(v => ({ ...v, x: size.w / 2 - gx * v.k, y: size.h / 2 - gy * v.k }));
        };
        return <svg className="mini" width={L.W * m} height={L.H * m} onPointerDown={e => { e.stopPropagation(); go(e); }}
                    onPointerMove={e => { if (e.buttons) go(e); }}>
          {L.lanes.map(l => <rect key={l.c} x={12 * m} y={l.y * m} width={(L.W - 24) * m} height={l.h * m} rx={3} fill={CAMPUS_COLOR[l.c]} opacity={.08} />)}
          {visible.map(f => { const it = L.items[f.id]; if (!it) return null;
            return <rect key={f.id} x={it.x * m} y={it.y * m} width={Math.max(2, it.w * m)} height={Math.max(2, PILL_H * m)} rx={1}
                         fill={st[f.id] === "used" ? "#12B76A" : st[f.id] === "revised" ? "#E5484D" : CAMPUS_COLOR[it.lane]} opacity={st[f.id] === "inactive" || st[f.id] === "future" ? .3 : .85} />; })}
          <line x1={tx * m} x2={tx * m} y1={0} y2={L.H * m} stroke="#101828" strokeWidth={1} />
          <rect x={-view.x / view.k * m} y={-view.y / view.k * m} width={vw * m} height={vh * m} className="mini-v" />
        </svg>;
      })()}
      <div className="zoom">
        <button title={T.zoomIn} onClick={() => zoomAt(1.2)}><Plus /></button>
        <button title={T.zoomOut} onClick={() => zoomAt(1 / 1.2)}><Minus /></button>
        <button title={T.fit} onClick={fit}><Fit /></button>
      </div>
    </div>
  );
}
