import { fmt, type T } from "../i18n";
import { CAMPUS_COLOR, laneOf, relations } from "../lib/graph";
import type { Fact, Graph, Src, Status } from "../types";
import { Cross, Doc } from "./icons";
import { STATUS_COLOR } from "./TracePanel";

interface Props { T: T; g: Graph; f: Fact; st: Record<string, Status>; today: string; target: [string, string]; setSel: (id: string | null) => void }

type Cond = { key: string; name: string; value: string; src?: Src; color: string };

function Highlight({ text, value }: { text: string; value: string }) {
  const core = value.replace(/\s+/g, "").slice(0, 12);
  const i = core.length >= 2 ? text.replace(/\s+/g, "").indexOf(core) : -1;
  if (i < 0) return <>{text}</>;
  // map the index in the squashed text back to the original
  let seen = 0, start = 0;
  for (let k = 0; k < text.length; k++) { if (!/\s/.test(text[k])) { if (seen === i) { start = k; break; } seen++; } }
  let end = start, n = 0;
  while (end < text.length && n < core.length) { if (!/\s/.test(text[end])) n++; end++; }
  return <>{text.slice(0, start)}<mark>{text.slice(start, end)}</mark>{text.slice(end)}</>;
}

export default function FactDrawer({ T, g, f, st, today, target, setSel }: Props) {
  const by = Object.fromEntries(g.facts.map(x => [x.id, x]));
  const notice = g.notices.find(n => n.id === f.doc);
  const s = st[f.id];
  const rel = relations(g, f.id);
  const lane = laneOf(f.campus);
  const conds: Cond[] = [
    { key: "campus", name: T.condCampus, value: f.campus ? T[`${f.campus}Full` as "zgcFull"] : T.allFull, src: f.src.campus, color: CAMPUS_COLOR[lane] },
    { key: "valid", name: T.condValid, value: f.start || f.end ? `${f.start || "…"} → ${f.end || "…"}` : T.standing, src: f.src.valid, color: "#0891B2" },
    { key: "aud", name: T.condAud, value: f.audience || "—", src: f.src.audience, color: "#B54708" },
  ];
  // attach every condition to the level of the section path that supplied it
  const levels = [{ name: notice?.title || f.doc, kind: "doc" }, ...f.path.map(p => ({ name: p, kind: "section" })), { name: f.quote, kind: "fact" }];
  const at = (c: Cond) => {
    const k = c.src?.kind;
    if (!k || k === "none") return -1;
    if (k === "doc") return 0;
    if (k === "section") { const i = f.path.indexOf(c.src?.head || ""); return i >= 0 ? i + 1 : 0; }
    return levels.length - 1;         // fact / gazetteer
  };
  const revisers = rel.revBy.map(e => by[e.src]).filter(x => x && x.pub <= today);
  const why = fmt(T.why[s] || "", {
    by: revisers.map(r => `${r.pub}「${r.value}」`).join("；") || "—",
    c: f.cycle || "", v: f.start || f.end ? `${f.start || "…"} → ${f.end || "…"}` : T.standing,
    t: target[0] === target[1] ? target[0] : `${target[0]} → ${target[1]}`, p: f.pub, today,
  });
  const link = (id: string, label: string) => {
    const x = by[id]; if (!x) return null;
    return <button key={id + label} className="rel" onClick={() => setSel(id)}>
      <span className="rel-k">{label}</span><span className="rel-v">{x.entity} · {x.value}</span><span className="rel-d">{x.pub}</span>
      <span className="rel-s" style={{ background: STATUS_COLOR[st[id]] }} />
    </button>;
  };

  return (
    <aside className="drawer" key={f.id}>
      <div className="dr-head">
        <div className="dr-kicker"><span className="dot" style={{ background: CAMPUS_COLOR[lane] }} />{f.entity} · {f.attr}</div>
        <button className="icon-btn" onClick={() => setSel(null)} title={T.close}><Cross size={12} /></button>
      </div>
      <div className="dr-value">{f.value}</div>
      <div className="dr-status" style={{ ["--c" as any]: STATUS_COLOR[s] }}>
        <b>{T.status[s]}</b><span>{why}</span>
      </div>

      {f.err && <div className="dr-err"><b>{T.knownErr}</b><span>{T.lang === "en" ? f.err[1] : f.err[0]}</span></div>}

      <h4>{T.condFrom}</h4>
      <div className="chain">
        {levels.map((lv, i) => {
          const here = conds.filter(c => at(c) === i);
          return <div key={i} className={"lv lv-" + lv.kind}>
            <div className="lv-node">{lv.kind === "doc" ? <Doc size={12} /> : lv.kind === "fact" ? "“" : "§"}</div>
            <div className="lv-main">
              <div className="lv-name">{lv.kind === "fact" ? <Highlight text={lv.name} value={f.value} /> : lv.name}</div>
              {here.length > 0 && <div className="lv-conds">{here.map(c => (
                <span key={c.key} className="cond" style={{ ["--c" as any]: c.color }}>
                  <em>{c.name}</em>{c.value}{c.src?.kind === "gazetteer" && <i>{T.src.gazetteer}</i>}
                </span>))}</div>}
            </div>
          </div>;
        })}
      </div>
      <div className="src-table">
        {conds.map(c => <div key={c.key}><em>{c.name}</em><b>{c.value}</b>
          <span>{c.src?.kind === "section" && c.src.head ? `${T.src.section}「${c.src.head}」` : T.src[c.src?.kind || "none"] || "—"}</span></div>)}
      </div>

      {(rel.rev.length + rel.revBy.length + rel.rec.length) > 0 && <>
        <h4>{T.relations}</h4>
        <div className="rels">
          {rel.revBy.map(e => link(e.src, T.revisedBy))}
          {rel.rev.map(e => link(e.dst, T.revises))}
          {rel.rec.map(e => link(e.dst, T.recOf))}
        </div>
      </>}

      <h4>{T.source}</h4>
      <div className="dr-src"><Doc size={13} /><div><b>{notice?.title}</b><span>{T.published} {f.pub}{f.ptype ? ` · ${f.ptype}${f.cycle ? " " + f.cycle : ""}` : ""}</span></div></div>
      <div className="dr-id">{f.id}</div>
    </aside>
  );
}
