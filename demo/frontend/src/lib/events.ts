import type { ChatEvent, Turn } from "../types";

/** Applies one server-sent event to a turn. Pure: easy to test, and the only place that knows the protocol. */
export function applyEvent(t: Turn, ev: ChatEvent): Turn {
  switch (ev.type) {
    case "open":
      return t;
    case "status":
      return { ...t, warming: true };
    case "stage":
      return { ...t, warming: false, stages: { ...t.stages, [ev.id]: { status: ev.status, ms: ev.ms, data: ev.data } } };
    case "graph":
      return { ...t, graph: ev.graph };
    case "used":
      return { ...t, used: { ids: ev.ids, mode: ev.mode, passages: ev.passages, revisedShown: ev.revisedShown } };
    case "delta":
      return { ...t, answer: t.answer + ev.text, retry: undefined };
    case "retry":
      return { ...t, retry: ev.attempt };
    case "answer":
      // the checked reply replaces the streamed text (it may have been rewritten)
      return { ...t, answer: ev.text, final: true, action: ev.action, rewritten: ev.rewritten };
    case "baseline":
      return { ...t, baseline: { ...t.baseline, ...ev } };
    case "gloss":
      return { ...t, gloss: { ...t.gloss, [ev.target]: ev.text } };
    case "complete":
      return {
        ...t, answer: ev.answer || t.answer, final: true, action: ev.action, rewritten: ev.rewritten,
        done: { calls: ev.calls, latency: ev.latency, cached: ev.cached }, finishedAt: Date.now(),
      };
    case "error":
      return { ...t, error: ev.message, finishedAt: Date.now() };
  }
}

/** The dialogue sent with a question: earlier questions and their final answers. */
export function conversationOf(turns: Turn[], q: string) {
  const conv = turns.flatMap(t => [
    { role: "user" as const, text: t.question },
    ...(t.final && t.answer ? [{ role: "assistant" as const, text: t.answer }] : []),
  ]);
  conv.push({ role: "user", text: q });
  return conv;
}
