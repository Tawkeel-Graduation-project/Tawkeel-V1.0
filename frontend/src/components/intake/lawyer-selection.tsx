"use client";

import { useCallback, useEffect, useState } from "react";
import { Briefcase, CheckCircle2, MapPin, RotateCcw, Send, Sparkles, UserRound, Wallet } from "lucide-react";
import {
  declinedLawyerIds,
  getIntake,
  IntakeError,
  listLawyers,
  sendIntakeToLawyer,
  type Intake,
  type Lawyer,
} from "@/lib/intake/api";
import { intakeErrorCopy } from "@/lib/intake/copy";
import { NICHE_LABELS } from "@/lib/intake/fields";
import {
  Alert,
  Badge,
  Button,
  ButtonLink,
  Card,
  CardBody,
  CardHeader,
  ErrorState,
  LoadingState,
} from "@/components/ui";
import { cn } from "@/lib/cn";
import {
  REQUEST_STATUS_LABELS,
  REQUEST_STATUS_MESSAGES,
  canChooseAnotherLawyer,
  isAwaitingLawyer,
  type RequestStatus,
} from "@/lib/requests/status";
import { MockLawyerResponse } from "@/components/requests/mock-lawyer-response";
import { RequestStatusBadge, formatRequestDate } from "@/components/requests/request-status-badge";

const STATUS_ALERT_TONES: Record<RequestStatus, "info" | "success" | "danger" | "warning"> = {
  sent: "info",
  pending: "info",
  accepted: "success",
  declined: "danger",
  expired: "warning",
  cancelled: "warning",
};

interface LawyerSelectionProps {
  intake: Intake;
  token: string | null;
  onChange: (intake: Intake) => void;
}

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; lawyers: Lawyer[] };

/**
 * SCRUM-345: after the client approves the summary, they pick one lawyer from
 * a simple list (January: the seeded, verified lawyers) and send the request.
 *
 * Only the lawyer id is sent; the server attaches the approved summary
 * (SCRUM-344) and sets the status to SENT (SCRUM-346).
 * Once sent, it shows the request's current status (SCRUM-349). If the lawyer
 * declines, the client may choose another lawyer (lawyers who declined are
 * hidden); that creates a new request with the same approved summary.
 */
export function LawyerSelection({ intake, token, onChange }: LawyerSelectionProps) {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  /** After a decline: the client chose to pick another lawyer. */
  const [choosingAgain, setChoosingAgain] = useState(false);

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      setState({ status: "success", lawyers: await listLawyers(token) });
    } catch (err) {
      const code = err instanceof IntakeError ? err.code : "unknown";
      setState({ status: "error", message: intakeErrorCopy[code] });
    }
  }, [token]);

  useEffect(() => {
    // Fetch on mount and whenever the session changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const caseNiche = intake.fields.niche?.status === "provided" ? intake.fields.niche.value : null;
  // Lawyers who already declined this intake are not offered again.
  const declined = declinedLawyerIds(intake);
  const lawyers =
    state.status === "success"
      ? sortByMatch(
          state.lawyers.filter((l) => !declined.includes(l.id)),
          caseNiche,
        )
      : [];
  const nameOf = (lawyerId: string) =>
    state.status === "success" ? state.lawyers.find((l) => l.id === lawyerId)?.fullName : undefined;
  const selected = lawyers.find((l) => l.id === selectedId) ?? null;

  async function send() {
    if (!selected) return;
    setSending(true);
    setError(null);
    try {
      onChange(await sendIntakeToLawyer(intake.id, selected.id, token));
      setChoosingAgain(false);
      setSelectedId(null);
    } catch (err) {
      const code = err instanceof IntakeError ? err.code : "unknown";
      setError(intakeErrorCopy[code]);
      if (code === "conflict") {
        // Already sent (e.g. from another tab): show what is stored.
        try {
          onChange(await getIntake(intake.id, token));
        } catch {
          /* keep the current view */
        }
      } else if (code === "lawyer_unavailable") {
        setSelectedId(null);
        void load();
      }
    } finally {
      setSending(false);
    }
  }

  const header = (
    <CardHeader
      title={
        <span className="inline-flex items-center gap-2">
          <UserRound aria-hidden className="size-4 text-vivid" />
          اختيار المحامي
        </span>
      }
      description={
        intake.request && !choosingAgain
          ? "أُرسل طلبك. تظهر هنا حالته الحالية."
          : choosingAgain
            ? "اختر محامياً آخر. سيُرسل إليه الملخص نفسه الذي وافقت عليه."
            : "اختر محامياً واحداً لإرسال ملخصك الموافق عليه إليه."
      }
      action={intake.request && !choosingAgain ? <RequestStatusBadge status={intake.request.status} /> : null}
    />
  );

  // Already sent: show where it went and its current status (SCRUM-349).
  if (intake.request && !choosingAgain) {
    const request = intake.request;
    const lawyerName = nameOf(request.lawyerId) ?? "المحامي الذي اخترته";
    const awaiting = isAwaitingLawyer(request.status);
    const canChooseAnother = canChooseAnotherLawyer(request.status);

    const refresh = async () => {
      setRefreshing(true);
      try {
        onChange(await getIntake(intake.id, token));
      } catch {
        /* keep the current view */
      } finally {
        setRefreshing(false);
      }
    };

    return (
      <Card id="lawyer-selection" className="mt-4">
        {header}
        <CardBody className="space-y-3">
          <Alert tone={STATUS_ALERT_TONES[request.status]} title={`طلبك إلى ${lawyerName}: ${REQUEST_STATUS_LABELS[request.status]}`}>
            {REQUEST_STATUS_MESSAGES[request.status]}
            {request.status === "declined" && request.declineReason ? (
              <span className="mt-1 block">
                <span className="font-semibold">سبب الاعتذار: </span>
                <span dir="auto">{request.declineReason}</span>
              </span>
            ) : null}
          </Alert>
          <p className="text-xs text-muted">
            أُرسل في {formatRequestDate(request.createdAt)}
            {request.respondedAt ? <> · الرد في {formatRequestDate(request.respondedAt)}</> : null}
          </p>
          <div className="flex flex-wrap items-center justify-between gap-2">
            {awaiting ? (
              <MockLawyerResponse
                requestId={request.id}
                onDone={() => void refresh()}
              />
            ) : (
              <span />
            )}
            <div className="flex flex-wrap gap-2">
              <ButtonLink href="/client/requests" variant="ghost" size="sm">
                كل طلباتي
              </ButtonLink>
              {canChooseAnother ? (
                <Button
                  size="sm"
                  icon={<UserRound aria-hidden className="size-3.5" />}
                  onClick={() => {
                    setError(null);
                    setSelectedId(null);
                    setChoosingAgain(true);
                  }}
                >
                  اختيار محامٍ آخر
                </Button>
              ) : null}
              <Button
                variant="secondary"
                size="sm"
                loading={refreshing}
                icon={<RotateCcw aria-hidden className="size-3.5" />}
                onClick={() => void refresh()}
              >
                تحديث الحالة
              </Button>
            </div>
          </div>
        </CardBody>
      </Card>
    );
  }

  return (
    <Card id="lawyer-selection" className="mt-4">
      {header}
      <CardBody className="space-y-4">
        {choosingAgain && declined.length > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-surface-muted px-3 py-2 text-sm">
            <span className="text-muted">
              لن يظهر في القائمة من اعتذر عن طلبك:{" "}
              <span dir="auto">{declined.map((id) => nameOf(id) ?? "محامٍ").join("، ")}</span>
            </span>
            <Button variant="ghost" size="sm" onClick={() => setChoosingAgain(false)} disabled={sending}>
              رجوع
            </Button>
          </div>
        ) : null}

        {state.status === "loading" ? (
          <LoadingState label="جارٍ تحميل قائمة المحامين…" className="py-8" />
        ) : state.status === "error" ? (
          <ErrorState title="تعذّر تحميل قائمة المحامين" description={state.message} onRetry={load} />
        ) : lawyers.length === 0 ? (
          <Alert tone="info" title={choosingAgain ? "لا يوجد محامون آخرون متاحون حالياً" : "لا يوجد محامون متاحون حالياً"}>
            حاول مرة أخرى لاحقاً.
          </Alert>
        ) : (
          <div role="radiogroup" aria-label="قائمة المحامين" className="grid gap-3 sm:grid-cols-2">
            {lawyers.map((lawyer) => (
              <LawyerCard
                key={lawyer.id}
                lawyer={lawyer}
                match={caseNiche !== null && lawyer.niches.includes(caseNiche)}
                selected={lawyer.id === selectedId}
                disabled={sending}
                onSelect={() => setSelectedId(lawyer.id)}
              />
            ))}
          </div>
        )}

        {error ? (
          <Alert tone="danger" title="لم يتم الإرسال">
            {error}
          </Alert>
        ) : null}

        {state.status === "success" && lawyers.length > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
            <p className="text-sm text-muted">
              {selected
                ? `سيُرسل ملخصك الموافق عليه إلى ${selected.fullName} فقط.`
                : "اختر محامياً من القائمة أولاً."}
            </p>
            <Button
              onClick={() => void send()}
              loading={sending}
              disabled={!selected}
              icon={<Send aria-hidden className="size-4" />}
            >
              {selected ? `إرسال الطلب إلى ${selected.fullName}` : "إرسال الطلب"}
            </Button>
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

function LawyerCard({
  lawyer,
  match,
  selected,
  disabled,
  onSelect,
}: {
  lawyer: Lawyer;
  match: boolean;
  selected: boolean;
  disabled: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      disabled={disabled}
      onClick={onSelect}
      data-lawyer={lawyer.id}
      className={cn(
        "flex h-full flex-col gap-2 rounded-xl border p-4 text-start transition",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 disabled:opacity-60",
        selected
          ? "border-primary bg-primary-soft/50 ring-1 ring-primary"
          : "border-border bg-surface hover:border-vivid/50",
      )}
    >
      <span className="flex items-start justify-between gap-2">
        <span className="font-semibold text-foreground" dir="auto">
          {lawyer.fullName}
        </span>
        {selected ? (
          <CheckCircle2 aria-hidden className="size-5 shrink-0 text-primary" />
        ) : match ? (
          <Badge tone="primary">
            <Sparkles aria-hidden className="size-3" />
            يناسب نوع قضيتك
          </Badge>
        ) : null}
      </span>

      {lawyer.niches.length > 0 ? (
        <span className="flex flex-wrap gap-1.5">
          {lawyer.niches.map((n) => (
            <Badge key={n} tone="neutral">
              {NICHE_LABELS[n] ?? n}
            </Badge>
          ))}
        </span>
      ) : null}

      <span className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {lawyer.city ? (
          <span className="inline-flex items-center gap-1" dir="auto">
            <MapPin aria-hidden className="size-3.5" />
            {lawyer.city}
          </span>
        ) : null}
        {lawyer.yearsExperience !== null ? (
          <span className="inline-flex items-center gap-1">
            <Briefcase aria-hidden className="size-3.5" />
            {lawyer.yearsExperience} سنوات خبرة
          </span>
        ) : null}
        {lawyer.feeMin !== null || lawyer.feeMax !== null ? (
          <span className="inline-flex items-center gap-1">
            <Wallet aria-hidden className="size-3.5" />
            {formatFees(lawyer.feeMin, lawyer.feeMax)}
          </span>
        ) : null}
      </span>

      {lawyer.bio ? (
        <span className="line-clamp-2 text-sm text-muted" dir="auto">
          {lawyer.bio}
        </span>
      ) : null}
    </button>
  );
}

/** Lawyers whose niches include the case's niche come first; otherwise keep the server's order. */
function sortByMatch(lawyers: Lawyer[], niche: string | null): Lawyer[] {
  if (!niche) return lawyers;
  return [...lawyers].sort(
    (a, b) => Number(b.niches.includes(niche)) - Number(a.niches.includes(niche)),
  );
}

function formatFees(min: number | null, max: number | null): string {
  if (min !== null && max !== null) return `${min}–${max} ج.م`;
  if (min !== null) return `من ${min} ج.م`;
  return `حتى ${max} ج.م`;
}
