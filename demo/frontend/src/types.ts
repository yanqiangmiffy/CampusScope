export type Campus = "zgc" | "tz";
export type Lang = "zh" | "en";
export type Status = "used" | "current" | "revised" | "history" | "inactive" | "future";
export type StageId = "plan" | "ground" | "target" | "apply" | "decide" | "write" | "verify";
export const STAGES: StageId[] = ["plan", "ground", "target", "apply", "decide", "write", "verify"];
export type Action = "answer" | "enumerate" | "assume" | "ask" | "history" | "abstain";

export interface Src { kind: "fact" | "section" | "doc" | "gazetteer" | "none" | string; head?: string | null }

export interface Fact {
  id: string; doc: string; entity: string; ekey: string; type: string; attr: string; group: string;
  value: string; quote: string; campus: Campus | null; campusSrc: string | null; audience: string | null;
  start: string | null; end: string | null; pub: string; period: string | null; ptype: string | null;
  cycle: number | null; path: string[]; status: Status; src: { campus?: Src; valid?: Src; audience?: Src };
  err?: [string, string] | null;
}
export interface Notice { id: string; title: string; pub: string; ptype: string | null; kind: string }
export interface Edge { kind: "rev" | "rec"; src: string; dst: string; active?: boolean; near?: boolean }
export interface Graph {
  today: string; target: [string, string]; cycle: [string, number] | null;
  notices: Notice[]; facts: Fact[]; edges: Edge[]; total: number; shown: number; keys: number;
}

export interface Stage { status: "running" | "done"; ms?: number; data: any }
export interface Used { ids: string[]; mode: string; passages: string[]; revisedShown?: string[] }
export interface Baseline { status: "running" | "done" | "error"; text?: string; action?: string; ms?: number; message?: string }

export interface Turn {
  id: string;
  question: string;
  today: string;
  campus: Campus | null;
  stages: Partial<Record<StageId, Stage>>;
  graph?: Graph;
  used?: Used;
  answer: string;
  final: boolean;
  action?: Action;
  rewritten?: boolean;
  baseline?: Baseline;
  gloss: { main?: string; baseline?: string };
  done?: { calls: number; latency: number; cached: boolean };
  error?: string;
  retry?: number;
  warming?: boolean;
  startedAt: number;
  finishedAt?: number;
  aborted?: boolean;
}

/** Server-sent events of POST /api/chat (docs/event-protocol.md; backend app/services/qa_service.py). */
export type ChatEvent =
  | { type: "open"; baseline: boolean }
  | { type: "status"; text: "warming"; stage?: string }
  | { type: "stage"; id: StageId; status: "running" | "done"; ms?: number; data: any }
  | { type: "graph"; graph: Graph }
  | { type: "used"; ids: string[]; mode: string; passages: string[]; revisedShown?: string[] }
  | { type: "delta"; text: string }
  | { type: "retry"; attempt: number }
  | { type: "answer"; text: string; action: Action; rewritten?: boolean }
  | { type: "baseline"; status: "running" | "done" | "error"; text?: string; action?: string; ms?: number; message?: string; retrieved?: string[] }
  | { type: "gloss"; target: "main" | "baseline"; text: string }
  | { type: "complete"; answer: string; action: Action; rewritten: boolean; calls: number; latency: number; cached: boolean }
  | { type: "error"; message: string };

export interface Scenario { id: string; q: string; d: string; zh: string; en: string; dzh: string; den: string }
export interface Health {
  ready: boolean; stage: string; error: string | null;
  index?: { state: string; progress: { collection: string; done: number; total: number } | null; zero_vectors: number };
  embedding?: { state: string; error: string | null };
  llm?: { configured: boolean; reachable: boolean | null; model: string };
}
