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
 *   POST {API}/client/intakes/{id}/turns   { content: string | null }
 *     200 -> Intake (with the agent's next question, or complete: true)
 *     409 -> intake already complete / another answer was saved first
 *
 * Until chat is saved server-side, the browser sends the transcript; the
 * backend stores it and marks it `client_submitted`. The returned
 * `conversationId` is sent on later clicks so the same intake is reused.
 *
 * Without NEXT_PUBLIC_API_URL a browser-only mock answers instead (demo only).
 */
import type { ChatMessage, Citation } from "@/lib/chat/types";
import { ALL_FIELDS, NICHE_LABELS, type IntakeFieldKey, type IntakeFieldStatus } from "./fields";

export type IntakePhase = "INTAKE";
export type IntakeContextSource = "server" | "client_submitted";

export interface IntakeContextMessage {
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
}

export interface IntakeFieldValue {
  status: IntakeFieldStatus;
  value: string | null;
}

export interface IntakeTurn {
  role: "agent" | "client";
  content: string;
  /** For agent turns: the field the question is about. */
  field: IntakeFieldKey | null;
}

export interface Intake {
  id: string;
  kind: "intake";
  status: "pending" | "running" | "awaiting_approval" | "completed" | "failed";
  phase: IntakePhase | null;
  conversationId: string | null;
  contextSource: IntakeContextSource | null;
  contextMessages: IntakeContextMessage[];
  fields: Record<IntakeFieldKey, IntakeFieldValue>;
  turns: IntakeTurn[];
  complete: boolean;
  createdAt: string;
}

export type IntakeErrorCode =
  | "no_answer"
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "conflict"
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

/** Open the intake (`content: null`) or answer the agent's last question. */
export function takeIntakeTurn(id: string, content: string | null, token: string | null): Promise<Intake> {
  return API_URL ? real.turn(id, content, token) : mock.turn(id, content);
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
  fields: Record<IntakeFieldKey, IntakeFieldValue>;
  turns: IntakeTurn[];
  complete: boolean;
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
    fields: data.fields,
    turns: data.turns,
    complete: data.complete,
    createdAt: data.created_at,
  };
}

const statusErrors: Record<number, IntakeErrorCode> = {
  401: "unauthorized",
  403: "forbidden",
  404: "not_found",
  409: "conflict",
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
  turn(id: string, content: string | null, token: string | null) {
    return call(`/client/intakes/${encodeURIComponent(id)}/turns`, token, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
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
      fields: emptyFields(),
      turns: [],
      complete: false,
      createdAt: new Date().toISOString(),
    };
    writeAll([...all, intake]);
    return intake;
  },

  async get(id: string): Promise<Intake> {
    await delay();
    const intake = readAll().find((i) => i.id === id);
    if (!intake) throw new IntakeError("not_found");
    return withIntakeDefaults(intake);
  },

  /** Template-only stand-in for the backend agent (no model in the browser). */
  async turn(id: string, content: string | null): Promise<Intake> {
    await delay();
    const all = readAll();
    const index = all.findIndex((i) => i.id === id);
    if (index < 0) throw new IntakeError("not_found");
    const intake = withIntakeDefaults(all[index]);
    if (intake.complete) throw new IntakeError("conflict");
    if ((content === null) !== (intake.turns.length === 0)) throw new IntakeError("conflict");

    if (content !== null) {
      intake.turns.push({ role: "client", content, field: null });
      const target = [...intake.turns].reverse().find((t) => t.role === "agent")?.field;
      if (target && intake.fields[target].status === "missing") {
        intake.fields[target] = mockAnswer(target, content);
      }
    }

    const next = ALL_FIELDS.find((f) => intake.fields[f].status === "missing");
    if (!next) {
      intake.complete = true;
      intake.turns.push({ role: "agent", content: MOCK_CLOSING, field: null });
    } else {
      const question = MOCK_QUESTIONS[next];
      intake.turns.push({
        role: "agent",
        content: content === null ? `${MOCK_OPENING}\n${question}` : question,
        field: next,
      });
    }
    all[index] = intake;
    writeAll(all);
    return intake;
  },
};

function emptyFields(): Record<IntakeFieldKey, IntakeFieldValue> {
  return Object.fromEntries(ALL_FIELDS.map((f) => [f, { status: "missing", value: null }])) as Record<
    IntakeFieldKey,
    IntakeFieldValue
  >;
}

/** Intakes saved by an older mock may lack the agent fields. */
function withIntakeDefaults(intake: Intake): Intake {
  return {
    ...intake,
    fields: { ...emptyFields(), ...(intake.fields ?? {}) },
    turns: [...(intake.turns ?? [])],
    complete: Boolean(intake.complete),
  };
}

const MOCK_OPENING = "أهلاً بك. سأطرح عليك بعض الأسئلة القصيرة لتجهيز طلبك للمحامي.";
const MOCK_CLOSING =
  "شكراً لك، اكتملت المعلومات المطلوبة. الخطوة التالية: مراجعة ملخص طلبك قبل إرساله لأي محامٍ.";
const MOCK_QUESTIONS: Record<IntakeFieldKey, string> = {
  facts: "احكِ لي باختصار ماذا حدث معك؟",
  niche: `أيّ من هذه الأنواع أقرب لمشكلتك؟ ${Object.entries(NICHE_LABELS)
    .filter(([k]) => k !== "unsure")
    .map(([, v]) => v)
    .join("، ")}. ولو لست متأكداً قل «غير متأكد».`,
  parties: "من هم الأطراف في هذه المشكلة، وما علاقتك بكل طرف؟",
  key_dates: "متى حدثت الوقائع المهمة تقريباً؟",
  urgency: "ما مدى استعجال الأمر؟ هل هناك شيء يجب التصرف فيه خلال أيام، أم خلال أسابيع، أم ليس عاجلاً؟",
  city: "في أي مدينة أو محافظة تقع المشكلة؟",
  budget: "ما الميزانية التقريبية التي تناسبك لأتعاب المحامي؟",
  documents: "ما المستندات المتوفرة لديك؟ (مثل العقد، المحاضر، الإيصالات) ويمكنك قول «لا يوجد».",
  deadlines: "هل هناك جلسة قريبة أو موعد قانوني يجب ألا يفوت (استئناف، معارضة...)؟",
  preferred_times: "ما الأيام والأوقات المناسبة لك للقاء المحامي؟",
};

const MOCK_DECLINE = /(مش عارف|معرفش|لا ?أعرف|لا ?اعرف|مش متأكد|غير متأكد|مش فاكر|تخطي|skip)/i;

function mockAnswer(field: IntakeFieldKey, text: string): IntakeFieldValue {
  if (text.length <= 40 && MOCK_DECLINE.test(text)) return { status: "not_provided", value: null };
  if (field === "niche") {
    const hit = Object.entries(NICHE_LABELS).find(
      ([k, label]) => k !== "unsure" && text.includes(label.split(" (")[0]),
    );
    return hit ? { status: "provided", value: hit[0] } : { status: "not_provided", value: null };
  }
  if (field === "urgency") {
    const value = /(مش عاجل|غير عاجل)/.test(text)
      ? "normal"
      : /(أسبوع|أسابيع|شهر)/.test(text)
        ? "soon"
        : "urgent";
    return { status: "provided", value };
  }
  return { status: "provided", value: text.trim() };
}

