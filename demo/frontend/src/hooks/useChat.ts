import { useCallback, useMemo, useRef, useState } from "react";
import { streamChat } from "../api";
import { applyEvent, conversationOf } from "../lib/events";
import type { Campus, ChatEvent, Lang, Turn } from "../types";

let seq = 0;
// not crypto.randomUUID: it only exists on https / localhost, and the demo is often opened by LAN IP
const nextId = () => `${Date.now().toString(36)}-${(seq++).toString(36)}`;

export interface SendOptions {
  day?: string;
  prior?: Turn[];
}

interface Options {
  today: string;
  setToday: (d: string) => void;
  campus: Campus | null;
  compare: boolean;
  lang: Lang;
}

/** The dialogue: one Turn per question, updated event by event; one stream at a time. */
export function useChat(o: Options) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const turnsRef = useRef<Turn[]>([]);
  turnsRef.current = turns;

  const patch = useCallback((id: string, fn: (t: Turn) => Turn) => {
    setTurns(prev => prev.map(t => (t.id === id ? fn(t) : t)));
  }, []);

  const { today, setToday, campus, compare, lang } = o;
  const send = useCallback(
    async (raw: string, so?: SendOptions) => {
      const q = raw.trim();
      if (!q || abort.current) return;
      const day = so?.day || today;
      if (so?.day) setToday(so.day);
      // a re-ask on another date replays the dialogue up to that turn in a fresh chat
      const history = so?.prior ?? turnsRef.current;
      const id = nextId();
      const turn: Turn = { id, question: q, today: day, campus, stages: {}, answer: "", final: false, gloss: {}, startedAt: Date.now() };
      setTurns([...history, turn]);
      setSel(id);
      setBusy(id);
      const ctl = new AbortController();
      abort.current = ctl;
      try {
        const ended = await streamChat(
          { conversation: conversationOf(history, q), today: day, campus, model: "deepseek", compare, lang },
          (ev: ChatEvent) => patch(id, t => applyEvent(t, ev)),
          ctl.signal,
        );
        // the stream closed without [DONE]: the connection dropped
        if (!ended) patch(id, t => (t.done || t.error ? t : { ...t, error: lang === "en" ? "Connection lost" : "连接中断" }));
      } catch (e: any) {
        if (e?.name === "AbortError") patch(id, t => ({ ...t, aborted: true }));
        else patch(id, t => ({ ...t, error: String(e?.message || e) }));
      } finally {
        patch(id, t => ({ ...t, finishedAt: t.finishedAt || Date.now() }));
        setBusy(null);
        abort.current = null;
      }
    },
    [today, setToday, campus, compare, lang, patch],
  );

  const stop = useCallback(() => abort.current?.abort(), []);
  const reset = useCallback(() => {
    abort.current?.abort();
    setTurns([]);
    setSel(null);
  }, []);
  const current = useMemo(() => turns.find(t => t.id === sel) || turns[turns.length - 1] || null, [turns, sel]);

  return { turns, current, sel, setSel, busy, send, stop, reset };
}
