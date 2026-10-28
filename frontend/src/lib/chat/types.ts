export interface Citation {
  id: string;
  sourceType: string;
  sourceName: string;
  articleNumber?: string;
  title?: string;
  text: string;
  url?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  createdAt: number;
  status?: "complete" | "streaming" | "error";
  hasNoSource?: boolean;
  errorType?: "network" | "general";
  errorMessage?: string;
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
