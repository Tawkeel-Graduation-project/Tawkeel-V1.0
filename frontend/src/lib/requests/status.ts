import type { Tone } from "@/components/ui";

/**
 * Status of a request sent to a lawyer (SCRUM-346/347/349).
 *
 *   sent ──► accepted   (lawyer takes the case)
 *        └─► declined   (lawyer says no)
 *
 * `pending`, `expired` and `cancelled` are older backend values; they are
 * labelled too so the screen never breaks on them.
 */
export type RequestStatus = "sent" | "pending" | "accepted" | "declined" | "expired" | "cancelled";

const KNOWN: readonly RequestStatus[] = ["sent", "pending", "accepted", "declined", "expired", "cancelled"];

/** Any value from the server; unknown values fall back to "sent" (still waiting). */
export function toRequestStatus(value: string | null | undefined): RequestStatus {
  return KNOWN.includes(value as RequestStatus) ? (value as RequestStatus) : "sent";
}

export const REQUEST_STATUS_LABELS: Record<RequestStatus, string> = {
  sent: "مُرسل",
  pending: "مُرسل",
  accepted: "مقبول",
  declined: "مرفوض",
  expired: "منتهي",
  cancelled: "ملغى",
};

export const REQUEST_STATUS_TONES: Record<RequestStatus, Tone> = {
  sent: "info",
  pending: "info",
  accepted: "success",
  declined: "danger",
  expired: "neutral",
  cancelled: "neutral",
};

/** What the status means for the client, in one sentence. */
export const REQUEST_STATUS_MESSAGES: Record<RequestStatus, string> = {
  sent: "بانتظار رد المحامي. ستتغير الحالة عندما يقبل الطلب أو يرفضه.",
  pending: "بانتظار رد المحامي. ستتغير الحالة عندما يقبل الطلب أو يرفضه.",
  accepted: "وافق المحامي على طلبك، وسيتواصل معك لبدء العمل على قضيتك.",
  declined: "اعتذر المحامي عن قبول هذا الطلب.",
  expired: "انتهت مهلة الرد على هذا الطلب دون رد من المحامي.",
  cancelled: "أُلغي هذا الطلب.",
};

/**
 * The lawyer said no (or never answered): the client may send the same
 * approved summary to a different lawyer, as a new request.
 */
export function canChooseAnotherLawyer(status: RequestStatus): boolean {
  return status === "declined" || status === "expired";
}

/** Still waiting for the lawyer. */
export function isAwaitingLawyer(status: RequestStatus): boolean {
  return status === "sent" || status === "pending";
}
