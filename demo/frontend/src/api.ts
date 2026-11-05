import type { ChatEvent, Health, Scenario } from "./types";

// the frontend only ever requests the relative path /api (nginx in Docker, the Vite proxy in development)

export async function getHealth(): Promise<Health> {
  const r = await fetch("/api/health");
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}

export async function getMeta(): Promise<{ scenarios: Scenario[]; models: { id: string; label: string }[]; stats: any }> {
  const r = await fetch("/api/meta");
  if (!r.ok) throw new Error(`meta ${r.status}`);
  return r.json();
}

export interface ChatBody {
  conversation: { role: "user" | "assistant"; text: string }[];
  today: string;
  campus: string | null;
  model: string;
  compare: boolean;
  lang: string;
}

/** POST /api/chat and hand every event to `onEvent` until `data: [DONE]` (EventSource cannot POST).
 *  Resolves true if the stream ended with [DONE], false if the connection dropped before it. */
export async function streamChat(body: ChatBody, onEvent: (ev: ChatEvent) => void, signal: AbortSignal): Promise<boolean> {
  const r = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok || !r.body) throw new Error(r.status === 422 ? "Invalid request" : `HTTP ${r.status}`);
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return false;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const data = block.split("\n").filter(l => l.startsWith("data:")).map(l => l.slice(5).trimStart()).join("\n");
      if (!data) continue; // ": keep-alive" comments
      if (data === "[DONE]") return true;
      try {
        onEvent(JSON.parse(data));
      } catch {
        /* ignore a malformed frame */
      }
    }
  }
}
