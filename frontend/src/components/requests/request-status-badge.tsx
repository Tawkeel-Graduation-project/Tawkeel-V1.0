import { CheckCircle2, Clock, Send, XCircle } from "lucide-react";
import { Badge } from "@/components/ui";
import {
  REQUEST_STATUS_LABELS,
  REQUEST_STATUS_TONES,
  type RequestStatus,
} from "@/lib/requests/status";

const ICONS: Record<RequestStatus, typeof Send> = {
  sent: Send,
  pending: Send,
  accepted: CheckCircle2,
  declined: XCircle,
  expired: Clock,
  cancelled: XCircle,
};

/** Colored badge for a request's status (SCRUM-349). */
export function RequestStatusBadge({ status }: { status: RequestStatus }) {
  const Icon = ICONS[status];
  return (
    <Badge tone={REQUEST_STATUS_TONES[status]} data-request-status={status}>
      <Icon aria-hidden className="size-3" />
      {REQUEST_STATUS_LABELS[status]}
    </Badge>
  );
}

/** "27 نوفمبر 2026، 2:40 م" in the client's locale. */
export function formatRequestDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("ar-EG", { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
  } catch {
    return iso;
  }
}
