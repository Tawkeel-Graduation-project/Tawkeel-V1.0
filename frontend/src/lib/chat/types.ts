export interface Citation {
  id: string;
  sourceType: string;
  sourceName: string;
  articleNumber?: string;
  title?: string;
  text: string;
  url?: string;
}

/**
 * Reply kinds sent by the backend (`services/rag/presenter.py`, `ReplyKind`).
 * Keep in sync: the frontend relies on these exact codes.
 */
export type ChatReplyKind =
  | "answered"
  | "clarification"
  | "no_source"
  | "invalid_question"
  | "temporarily_unavailable"
  | "answer_failed";

/** Failure kinds shown with <ChatErrorMessage />. "network"/"general" are client-side. */
export type ChatErrorType =
  | "network"
  | "general"
  | "invalid_question"
  | "temporarily_unavailable"
  | "answer_failed";

/** A notice attached to a reply (backend `UserNotice`, camelCased). */
export interface ChatNotice {
  kind: ChatReplyKind;
  message?: string;
  retryable?: boolean;
  showLawyerCta?: boolean;
}

/** One statement of an answer; `supported: false` means no source backs it. */
export interface ChatClaim {
  text: string;
  sourceIds?: string[];
  supported?: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  createdAt: number;
  status?: "complete" | "streaming" | "error";
  hasNoSource?: boolean;
  errorType?: ChatErrorType;
  errorMessage?: string;
  /** When present, rendered one per line instead of `content`. */
  claims?: ChatClaim[];
  hasUnsupportedClaims?: boolean;
  clarificationQuestion?: string;
  notice?: ChatNotice;
}

export type ChatStatus = "idle" | "loading" | "streaming" | "error";

export interface SuggestedQuestion {
  id: string;
  category: string;
  question: string;
}

export const SUGGESTED_QUESTIONS: SuggestedQuestion[] = [
  {
    id: "labor-notice",
    category: "قانون العمل",
    question: "ما هي المهلة القانونية لإخطار إنهاء عقد العمل غير محدد المدة؟",
  },
  {
    id: "labor-termination",
    category: "قانون العمل",
    question: "ما هي الحالات التي يجوز فيها لصاحب العمل فصل العامل دون إنذار طبقاً للمادة 69؟",
  },
  {
    id: "rent-contract",
    category: "الإيجارات",
    question: "ما هي شروط وإجراءات توثيق عقد الإيجار الجديد وإثبات تاريخه بالشهر العقاري؟",
  },
  {
    id: "annual-leave",
    category: "قانون العمل",
    question: "كيف يُحتسب رصيد الإجازات السنوية ومقابلها المادي عند انتهاء الخدمة؟",
  },
];
