import { useEffect, useRef, useState } from "react";
import { DICT } from "./i18n";
import type { Campus, Lang } from "./types";
import { useChat } from "./hooks/useChat";
import { useHealth } from "./hooks/useHealth";
import TopBar from "./components/TopBar";
import ChatPanel from "./components/ChatPanel";
import TracePanel from "./components/TracePanel";
import EvidencePanel from "./components/EvidencePanel";

const U = new URLSearchParams(location.search);

export default function App() {
  // English by default; ?lang=zh opens the Chinese interface
  const [lang, setLang] = useState<Lang>(U.get("lang") === "zh" ? "zh" : "en");
  const [today, setToday] = useState(U.get("d") || "2026-01-20");
  const [campus, setCampus] = useState<Campus | null>((U.get("campus") as Campus) || null);
  const [compare, setCompare] = useState(U.get("compare") !== "0");
  const { health, offline, scenarios, modelLabel } = useHealth();
  const chat = useChat({ today, setToday, campus, compare, lang });
  const { current, turns, busy, send } = chat;
  const T = DICT[lang];

  useEffect(() => {
    document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
  }, [lang]);

  // ?q=...&d=...: run a question on load (links in the README / paper)
  const ran = useRef(false);
  useEffect(() => {
    if (!ran.current && U.get("q")) {
      ran.current = true;
      send(U.get("q")!, { day: U.get("d") || undefined });
    }
  }, [send]);

  return (
    <div className="app">
      <TopBar T={T} lang={lang} setLang={setLang} today={today} setToday={setToday} campus={campus} setCampus={setCampus}
              compare={compare} setCompare={setCompare} health={health} offline={offline} modelLabel={modelLabel} onNew={chat.reset} />
      <main className="grid">
        <ChatPanel T={T} lang={lang} turns={turns} sel={current?.id || null} setSel={chat.setSel} busy={busy} send={send}
                   stop={chat.stop} scenarios={scenarios} />
        <TracePanel T={T} turn={current} busy={busy === current?.id} />
        <EvidencePanel T={T} turn={current} busy={busy === current?.id}
                       onReask={(d: string) => current && send(current.question, { day: d, prior: turns.slice(0, turns.indexOf(current)) })} />
      </main>
    </div>
  );
}
