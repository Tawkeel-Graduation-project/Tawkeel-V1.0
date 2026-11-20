/**
 * Lawyer-request intake API (SCRUM-247 / SCRUM-330 / SCRUM-331).
 *
 * When NEXT_PUBLIC_API_URL is set, requests go to the FastAPI backend:
 *
 *   POST {API}/client/intakes   { conversation_id } | { messages: ChatMessage[] }
 *     201 -> Intake (started)   200 -> Intake (already active for this chat)
 *     422 -> the chat has no answer yet / invalid body
 *   GET  {API}/client/intakes/{id}
 *     200 -> Intake             403 / 404
 *
 * Until chat is saved server-side, the browser sends the transcript; the
 * backend stores it and marks it `client_submitted`. The returned
 * `conversationId` is sent on later clicks so the same intake is reused.
 *
 * Without NEXT_PUBLIC_API_URL a browser-only mock answers instead (demo only).
 */
import type { ChatMessage, Citation } from "@/lib/chat/types";

export type IntakePhase = "INTAKE";
export type IntakeContextSource = "server" | "client_submitted";

export interface IntakeContextMessage {
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
}

export interface Intake {
  id: string;
  kind: "intake";
  status: "pending" | "running" | "awaiting_approval" | "completed" | "failed";
  phase: IntakePhase | null;
  conversationId: string | null;
  contextSource: IntakeContextSource | null;
  contextMessages: IntakeContextMessage[];
  createdAt: string;
}

export type IntakeErrorCode =
  | "no_answer"
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "network"
  | "unknown";

export class IntakeError extends Error {
  constructor(public code: IntakeErrorCode) {
    super(code);
  }
}

export interface StartIntakeInput {
  token: string | null;
  /** Set after the first successful start, so later clicks reuse the intake. */
  conversationId?: string | null;
  messages: ChatMessage[];
}

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

/** Only finished, non-empty questions and answers are carried over. */
export function carriedOverMessages(messages: ChatMessage[]): IntakeContextMessage[] {
  return messages
    .filter((m) => m.status !== "error" && m.status !== "streaming")
    .map((m) => ({
      role: m.role,
      content:
        m.content.trim() || (m.claims ?? []).map((c) => c.text).join("\n").trim(),
      citations: m.citations ?? [],
    }))
    .filter((m) => m.content.length > 0);
}

export function startIntake(input: StartIntakeInput): Promise<Intake> {
  return API_URL ? real.start(input) : mock.start(input);
}

export function getIntake(id: string, token: string | null): Promise<Intake> {
  return API_URL ? real.get(id, token) : mock.get(id);
}

// --- real backend -----------------------------------------------------------
interface IntakeResponse {
  id: string;
  kind: "intake";
  status: Intake["status"];
  phase: IntakePhase | null;
  conversation_id: string | null;
  context_source: IntakeContextSource | null;
  context_messages: IntakeContextMessage[];
  created_at: string;
}

function fromResponse(data: IntakeResponse): Intake {
  return {
    id: data.id,
    kind: data.kind,
    status: data.status,
    phase: data.phase,
    conversationId: data.conversation_id,
    contextSource: data.context_source,
    contextMessages: data.context_messages,
    createdAt: data.created_at,
  };
}

const statusErrors: Record<number, IntakeErrorCode> = {
  401: "unauthorized",
  403: "forbidden",
  404: "not_found",
  422: "no_answer",
};

async function call(path: string, token: string | null, init?: RequestInit): Promise<Intake> {
  let res: Response;
  try {
    res = await fetch(API_URL + path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
  } catch {
    throw new IntakeError("network");
  }
  if (!res.ok) throw new IntakeError(statusErrors[res.status] ?? "unknown");
  return fromResponse((await res.json()) as IntakeResponse);
}

const real = {
  start({ token, conversationId, messages }: StartIntakeInput) {
    const body = conversationId
      ? { conversation_id: conversationId }
      : { messages: carriedOverMessages(messages) };
    return call("/client/intakes", token, { method: "POST", body: JSON.stringify(body) });
  },
  get(id: string, token: string | null) {
    return call(`/client/intakes/${encodeURIComponent(id)}`, token);
  },
};

// --- browser-only mock --------------------------------------------------------
const MOCK_KEY = "tawkeel.mockIntakes";

function readAll(): Intake[] {
  try {
    return JSON.parse(window.localStorage.getItem(MOCK_KEY) ?? "[]") as Intake[];
  } catch {
    return [];
  }
}

function writeAll(intakes: Intake[]) {
  try {
    window.localStorage.setItem(MOCK_KEY, JSON.stringify(intakes));
  } catch {
    /* storage unavailable — the intake lasts for this page only */
  }
}

const delay = () => new Promise((r) => setTimeout(r, 500));

const mock = {
  async start({ conversationId, messages }: StartIntakeInput): Promise<Intake> {
    await delay();
    const all = readAll();
    if (conversationId) {
      const existing = all.find(
        (i) => i.conversationId === conversationId && i.status !== "completed" && i.status !== "failed",
      );
      if (existing) return existing;
    }
    const context = carriedOverMessages(messages);
    if (!context.some((m) => m.role === "assistant")) throw new IntakeError("no_answer");
    const intake: Intake = {
      id: crypto.randomUUID(),
      kind: "intake",
      status: "running",
      phase: "INTAKE",
      conversationId: conversationId ?? crypto.randomUUID(),
      contextSource: "client_submitted",
      contextMessages: context,
      createdAt: new Date().toISOString(),
    };
    writeAll([...all, intake]);
    return intake;
  },

  async get(id: string): Promise<Intake> {
    await delay();
    const intake = readAll().find((i) => i.id === id);
    if (!intake) throw new IntakeError("not_found");
    return intake;
  },
};
