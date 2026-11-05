import type { Campus, Edge, Fact, Graph, Status } from "../types";

/* ------------------------------------------------------------------ status at another "today" */
// Mirrors EvidenceGraph.status (campusscope/graph.py): known -> revised -> covers -> earlier cycle.
const covers = (f: Fact, lo: string, hi: string) => (f.start || f.pub) <= hi && lo <= (f.end || "9999-12-31");

export function previewStatuses(g: Graph, t: string, target: [string, string]): Record<string, Status> {
  const [lo, hi] = target;
  const by = Object.fromEntries(g.facts.map(f => [f.id, f]));
  const revBy: Record<string, string[]> = {};
  for (const e of g.edges) if (e.kind === "rev") (revBy[e.dst] ||= []).push(e.src);
  const out: Record<string, Status> = {};
  const hist: Fact[] = [];
  for (const f of g.facts) {
    if (f.pub > t) { out[f.id] = "future"; continue; }
    if ((revBy[f.id] || []).some(n => by[n] && by[n].pub <= t && covers(by[n], lo, hi))) { out[f.id] = "revised"; continue; }
    if (covers(f, lo, hi)) { out[f.id] = "current"; continue; }
    if (f.end && f.end < lo && (!g.cycle || (f.ptype === g.cycle[0] && (f.cycle || 0) < g.cycle[1]))) { hist.push(f); out[f.id] = "inactive"; continue; }
    out[f.id] = "inactive";
  }
  const best: Record<string, number> = {};
  for (const f of hist) { const k = `${f.ekey}|${f.group}|${f.campus}`; best[k] = Math.max(best[k] ?? -1, f.cycle || 0); }
  for (const f of hist) if ((f.cycle || 0) === best[`${f.ekey}|${f.group}|${f.campus}`]) out[f.id] = "history";
  return out;
}

/* ------------------------------------------------------------------ text measurement */
let ctx: CanvasRenderingContext2D | null = null;
const FONT = `"Inter","PingFang SC","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif`;
export function textW(s: string, size = 12.5, weight = 700) {
  if (!ctx) ctx = document.createElement("canvas").getContext("2d");
  if (!ctx) return s.length * size;
  ctx.font = `${weight} ${size}px ${FONT}`;
  return ctx.measureText(s).width;
}
export const clip = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

/* ------------------------------------------------------------------ layout: time × campus lanes */
export type Lane = "zgc" | "all" | "tz";
export interface Item { f: Fact; x: number; y: number; w: number; bx0: number; bx1: number; open: boolean; lane: Lane; row: number; label: string }
export interface Col { x: number; w: number; id: string; i: number }
export interface LaneBox { c: Lane; y: number; h: number; rows: number }
export interface Layout {
  W: number; H: number; X: (d: string) => number; INV: (x: number) => string;
  cols: Record<string, Col>; lanes: LaneBox[]; items: Record<string, Item>;
  X0: number; X1: number; axisY: number; top: number; bottom: number; lo: string; hi: string;
}

export const X0 = 150, PILL_H = 28, RH = 54, AXIS_Y = 86, TOP = 122;
const DAY = 86400000;
const ms = (s: string) => Date.parse(s + "T00:00:00Z");
const iso = (m: number) => new Date(m).toISOString().slice(0, 10);

export function labelOf(f: Fact, multi: boolean) {
  const v = clip(f.value.replace(/\s+/g, " "), multi ? 13 : 18);
  return multi ? `${clip(f.entity, 6)} · ${v}` : v;
}

export function layout(g: Graph, visible: Fact[]): Layout {
  const multi = new Set(visible.map(f => f.ekey)).size > 1;
  const docs = g.notices.filter(n => visible.some(f => f.doc === n.id));
  const pillW = (f: Fact) => Math.min(250, Math.ceil(textW(labelOf(f, multi))) + 40);
  const colW = docs.map(n => Math.max(96, ...visible.filter(f => f.doc === n.id).map(pillW)));
  const gap = 26;
  const cols: Record<string, Col> = {};
  let cx = X0 + 24;
  docs.forEach((n, i) => { cols[n.id] = { x: cx, w: colW[i], id: n.id, i }; cx += colW[i] + gap; });
  const tail = 150;
  const X1 = Math.max(cx - gap + tail, 720);
  // piecewise-linear time: every notice's date sits exactly at its column
  const dates = visible.flatMap(f => [f.start, f.end, f.pub]).filter(Boolean) as string[];
  dates.push(g.today, g.target[0], g.target[1]);
  const lo = dates.reduce((a, b) => (a < b ? a : b));
  const hi = iso(Math.max(ms(dates.reduce((a, b) => (a > b ? a : b))) + 20 * DAY, docs.length ? ms(docs[docs.length - 1].pub) + DAY : 0));
  const anchors: [number, number][] = docs.map(n => [ms(n.pub), cols[n.id].x]);
  // merge notices published the same day (keep the first column)
  const A: [number, number][] = [];
  for (const a of anchors) if (!A.length || a[0] > A[A.length - 1][0]) A.push(a);
  if (!A.length || ms(lo) < A[0][0]) A.unshift([ms(lo), X0 + 4]);
  A.push([Math.max(ms(hi), A[A.length - 1][0] + DAY), X1]);
  const X = (s: string) => {
    const m = ms(s);
    if (m <= A[0][0]) return A[0][1];
    for (let i = 1; i < A.length; i++) {
      const [m0, x0] = A[i - 1], [m1, x1] = A[i];
      if (m <= m1) return m1 === m0 ? x1 : x0 + ((m - m0) / (m1 - m0)) * (x1 - x0);
    }
    return A[A.length - 1][1];
  };
  const INV = (x: number) => {
    if (x <= A[0][1]) return iso(A[0][0]);
    for (let i = 1; i < A.length; i++) {
      const [m0, x0] = A[i - 1], [m1, x1] = A[i];
      if (x <= x1) return iso(Math.round((m0 + ((x - x0) / Math.max(1e-6, x1 - x0)) * (m1 - m0)) / DAY) * DAY);
    }
    return iso(A[A.length - 1][0]);
  };
  // items packed into rows inside their campus lane
  const items: Item[] = visible.map(f => {
    const c = cols[f.doc], w = pillW(f);
    const bx0 = Math.min(X(f.start || f.pub), c.x + 8);
    const open = !f.end;
    const bx1 = open ? c.x + w + 64 : Math.max(X(f.end!), bx0 + 6);
    return { f, x: c.x, y: 0, w, bx0, bx1, open, lane: (f.campus || "all") as Lane, row: 0, label: labelOf(f, multi) };
  });
  const laneOrder: Lane[] = ["zgc", "all", "tz"];
  const present = new Set(items.map(i => i.lane));
  const lanes: LaneBox[] = [];
  let y = TOP;
  for (const c of laneOrder) {
    if (c === "all" && !present.has("all")) continue;
    const its = items.filter(i => i.lane === c).sort((a, b) => cols[a.f.doc].i - cols[b.f.doc].i || (a.f.start || a.f.pub).localeCompare(b.f.start || b.f.pub) || a.f.id.localeCompare(b.f.id));
    const ends: number[] = [];
    for (const it of its) {
      const s = Math.min(it.x, it.bx0);
      let r = ends.findIndex(e => e <= s);
      if (r < 0) { r = ends.length; ends.push(0); }
      ends[r] = Math.max(it.x + it.w, it.bx1) + 10;
      it.row = r;
    }
    const rows = ends.length;
    const h = rows ? rows * RH + 34 : 50;
    lanes.push({ c, y, h, rows });
    for (const it of its) it.y = y + 30 + it.row * RH;
    y += h + 12;
  }
  const bottom = y - 12;
  return {
    W: X1 + 24, H: bottom + 70, X, INV, cols, lanes, items: Object.fromEntries(items.map(i => [i.f.id, i])),
    X0, X1, axisY: AXIS_Y, top: TOP, bottom, lo: iso(A[0][0]), hi: iso(A[A.length - 1][0]),
  };
}

export function arc(x1: number, y1: number, x2: number, y2: number, up: boolean) {
  const dx = Math.abs(x2 - x1), h = Math.max(22, Math.min(90, 14 + dx * 0.16));
  const ym = up ? Math.min(y1, y2) - h : Math.max(y1, y2) + h, s = x1 > x2 ? -1 : 1;
  return `M${x1},${y1} C${x1 + s * dx * 0.22},${ym} ${x2 - s * dx * 0.22},${ym} ${x2},${y2}`;
}

export function relations(g: Graph, id: string) {
  const rev: Edge[] = [], revBy: Edge[] = [], rec: Edge[] = [];
  for (const e of g.edges) {
    if (e.kind === "rev" && e.src === id) rev.push(e);
    if (e.kind === "rev" && e.dst === id) revBy.push(e);
    if (e.kind === "rec" && e.src === id && e.near) rec.push(e);
  }
  return { rev, revBy, rec };
}

export const CAMPUS_COLOR: Record<Lane, string> = { zgc: "#2E6BE6", tz: "#E8772E", all: "#667085" };
export const laneOf = (c: Campus | null): Lane => (c || "all") as Lane;
