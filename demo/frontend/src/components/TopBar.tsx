import type { T } from "../i18n";
import type { Campus, Health, Lang } from "../types";
import { Calendar, External, Globe, Logo, Pin, Plus } from "./icons";

interface Props {
  T: T; lang: Lang; setLang: (l: Lang) => void; today: string; setToday: (d: string) => void;
  campus: Campus | null; setCampus: (c: Campus | null) => void; compare: boolean; setCompare: (b: boolean) => void;
  health: Health | null; offline: boolean; modelLabel: string; onNew: () => void;
}

export default function TopBar(p: Props) {
  const { T } = p;
  const state = p.offline ? "off" : p.health?.error ? "off" : !p.health?.ready ? "warm"
    : p.health?.llm?.reachable === false ? "nollm" : p.health?.embedding?.state === "down" ? "degraded" : "ok";
  const prog = p.health?.index?.progress;
  const warmText = prog ? `${T.indexing} ${Math.round((100 * prog.done) / Math.max(1, prog.total))}%` : T.warming;
  const label = { off: p.health?.error ? p.health.error : T.offline, warm: prog ? `${T.indexing} ${prog.collection} ${prog.done}/${prog.total}` : `${T.warming} · ${p.health?.stage || ""}`, degraded: T.embDown, nollm: T.llmDown, ok: T.ready }[state];
  return (
    <header className="top">
      <div className="brand">
        <div className="logo"><Logo /></div>
        <div className="brand-t">
          <h1>CampusScope</h1>
          <span>{T.brandSub}</span>
        </div>
      </div>

      <div className="controls">
        <label className="ctl" title={T.today}>
          <Calendar /><span className="ctl-l">{T.today}</span>
          <input type="date" value={p.today} onChange={e => e.target.value && p.setToday(e.target.value)} />
        </label>
        <div className="ctl seg-wrap" title={T.campus}>
          <Pin /><span className="ctl-l">{T.campus}</span>
          <div className="seg">
            {([null, "zgc", "tz"] as (Campus | null)[]).map(c => (
              <button key={c || "none"} className={p.campus === c ? "on " + (c || "") : ""} onClick={() => p.setCampus(c)}>
                {c ? T[c] : T.unstated}
              </button>
            ))}
          </div>
        </div>
        <button className={"ctl switch" + (p.compare ? " on" : "")} onClick={() => p.setCompare(!p.compare)} role="switch" aria-checked={p.compare}>
          <i /><span>{T.compare}</span>
        </button>
        <span className="ctl model" title={T.model}><b>{p.modelLabel}</b></span>
      </div>

      <div className="right">
        <span className={"health " + state} title={label}><i />{state === "ok" ? T.ready : state === "warm" ? warmText : state === "degraded" ? "BM25" : state === "nollm" ? T.llmShort : T.offline}</span>
        <a className="ghost" href={`/cseg.html?lang=${p.lang}`} target="_blank" rel="noreferrer"><External />{T.walkthrough}</a>
        <button className="ghost" onClick={() => p.setLang(p.lang === "en" ? "zh" : "en")}><Globe />{p.lang === "en" ? "中文" : "English"}</button>
        <button className="primary-s" onClick={p.onNew}><Plus />{T.newChat}</button>
      </div>
    </header>
  );
}
