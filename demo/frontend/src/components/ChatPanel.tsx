import { useEffect, useRef, useState } from "react";
import { fmt, type T } from "../i18n";
import type { Lang, Scenario, Turn } from "../types";
import { Arrow, Send, Sparkle, Stop, Warn } from "./icons";

interface Props {
  T: T; lang: Lang; turns: Turn[]; sel: string | null; setSel: (id: string) => void; busy: string | null;
  send: (q: string, o?: { day?: string; prior?: Turn[] }) => void; stop: () => void; scenarios: Scenario[];
}

export const ACTION_COLOR: Record<string, string> = {
  answer: "#2E6BE6", enumerate: "#5B47F0", assume: "#2E6BE6", ask: "#12B76A", history: "#7C5CFA", abstain: "#98A2B3",
};

function Elapsed({ from, to }: { from: number; to?: number }) {
  const [, tick] = useState(0);
  useEffect(() => { if (to) return; const i = setInterval(() => tick(x => x + 1), 100); return () => clearInterval(i); }, [to]);
  return <>{(((to || Date.now()) - from) / 1000).toFixed(1)}s</>;
}

function Assistant({ t, T, lang, selected, busy, onSelect, onQuick }: {
  t: Turn; T: T; lang: Lang; selected: boolean; busy: boolean; onSelect: () => void; onQuick: (q: string) => void;
}) {
  const color = t.action ? ACTION_COLOR[t.action] : "#98A2B3";
  const writing = busy && !t.final;
  const phase = !t.answer && busy ? (t.warming ? T.warmingMsg : t.retry ? fmt(T.retry, { n: t.retry }) : T.thinking) : null;
  return (
    <div className={"a-wrap" + (selected ? " sel" : "")} onClick={onSelect}>
      <div className="a-card">
        <div className="a-head">
          <span className="a-tag" style={{ background: t.action ? color : undefined }}>
            <Sparkle size={11} />CampusScope{t.action ? ` · ${T.act[t.action]}` : ""}
          </span>
          <span className="a-meta">
            {t.done ? <>{t.done.calls} {T.calls} · {t.done.latency.toFixed(1)}s{t.done.cached ? ` · ${T.cached}` : ""}</>
              : <Elapsed from={t.startedAt} to={t.finishedAt} />}
          </span>
        </div>
        {phase && <div className="a-phase"><span className="dots"><i /><i /><i /></span>{phase}</div>}
        {t.answer && <div className={"a-text" + (writing ? " typing" : "")}>{t.answer}</div>}
        {lang === "en" && t.gloss.main && <div className="gloss">{t.gloss.main}</div>}
        {t.rewritten && <div className="a-note"><Warn />{T.rewritten}</div>}
        {t.error && <div className="a-err"><Warn />{T.errorPrefix}{t.error}</div>}
        {t.aborted && <div className="a-note">{T.stopped}</div>}
        {t.action === "ask" && t.final && (
          <div className="quick">
            <button onClick={e => { e.stopPropagation(); onQuick(T.quickZgc); }}><span className="dot zgc" />{T.quickZgc}</button>
            <button onClick={e => { e.stopPropagation(); onQuick(T.quickTz); }}><span className="dot tz" />{T.quickTz}</button>
          </div>
        )}
      </div>
      {t.baseline && (
        <div className="b-card">
          <div className="b-head"><span>{T.baseline}</span>
            <span className="a-meta">{t.baseline.status === "done" ? `${((t.baseline.ms || 0) / 1000).toFixed(1)}s` : t.baseline.status === "error" ? "error" : ""}</span></div>
          {t.baseline.status === "running" && <div className="a-phase"><span className="dots"><i /><i /><i /></span>{T.baselineRunning}</div>}
          {t.baseline.text && <div className="b-text">{t.baseline.text}</div>}
          {lang === "en" && t.gloss.baseline && <div className="gloss">{t.gloss.baseline}</div>}
          {t.baseline.status === "error" && <div className="a-err">{t.baseline.message}</div>}
        </div>
      )}
    </div>
  );
}

export default function ChatPanel({ T, lang, turns, sel, setSel, busy, send, stop, scenarios }: Props) {
  const [q, setQ] = useState("");
  const body = useRef<HTMLDivElement>(null);
  const last = turns[turns.length - 1];
  useEffect(() => { body.current?.scrollTo({ top: body.current.scrollHeight, behavior: "smooth" }); },
    [turns.length, last?.answer.length, last?.baseline?.status, last?.final]);
  const submit = (e: React.FormEvent) => { e.preventDefault(); if (q.trim() && !busy) { send(q.trim()); setQ(""); } };

  return (
    <section className="panel chat">
      <div className="p-head"><h2>{T.dialogue}</h2>
        {turns.length > 0 && <div className="scen-mini">
          {scenarios.map(s => <button key={s.id} disabled={!!busy} title={`${s.q} · ${s.d}`} onClick={() => send(s.q, { day: s.d, prior: [] })}>{s.id}</button>)}
        </div>}
      </div>
      <div className="p-body" ref={body}>
        {turns.length === 0 && (
          <div className="hero">
            <div className="hero-badge"><Sparkle size={12} />WWW 2027 Demo · FastAPI + SSE</div>
            <h3>{T.heroTitle}</h3>
            <p>{T.heroSub}</p>
            <div className="hero-l">{T.tryThese}</div>
            <div className="scen-cards">
              {scenarios.map((s, i) => (
                <button key={s.id} className="scen-card" style={{ animationDelay: `${i * 60}ms` }} disabled={!!busy}
                        onClick={() => send(s.q, { day: s.d, prior: [] })}>
                  <div className="sc-top"><span className="sc-id">{s.id}</span><span className="sc-name">{lang === "en" ? s.en : s.zh}</span><span className="sc-date">{s.d}</span></div>
                  <div className="sc-q">{s.q}</div>
                  <div className="sc-d">{lang === "en" ? s.den : s.dzh}</div>
                  <Arrow />
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map(t => (
          <div key={t.id} className="turn">
            <div className="u-msg"><div className="u-bubble">{t.question}</div>
              <div className="u-meta">{T.today} {t.today}{t.campus ? ` · ${T[t.campus]}` : ""}</div></div>
            <Assistant t={t} T={T} lang={lang} selected={t.id === sel && turns.length > 1} busy={busy === t.id}
                       onSelect={() => setSel(t.id)} onQuick={qq => send(qq)} />
          </div>
        ))}
      </div>
      <form className="composer" onSubmit={submit}>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder={T.placeholder} autoComplete="off" />
        {busy ? <button type="button" className="btn stop" onClick={stop}><Stop />{T.stop}</button>
          : <button className="btn go" disabled={!q.trim()}><Send />{T.send}</button>}
      </form>
    </section>
  );
}
