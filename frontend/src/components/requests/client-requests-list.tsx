"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ChevronLeft, MessagesSquare, RotateCcw, Send, UserRound } from "lucide-react";
import { useAuth } from "@/lib/auth/auth-context";
import { IntakeError, listClientRequests, type ClientRequest } from "@/lib/intake/api";
import { intakeErrorCopy } from "@/lib/intake/copy";
import { NICHE_LABELS } from "@/lib/intake/fields";
import { REQUEST_STATUS_MESSAGES, canChooseAnotherLawyer, isAwaitingLawyer } from "@/lib/requests/status";
import {
  Button,
  ButtonLink,
  Card,
  CardBody,
  EmptyState,
  ErrorState,
  PageHeader,
  PageSkeleton,
} from "@/components/ui";
import { MockLawyerResponse } from "./mock-lawyer-response";
import { RequestStatusBadge, formatRequestDate } from "./request-status-badge";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; requests: ClientRequest[] };

/**
 * SCRUM-349: the client's "My requests" page. Every request they sent, with
 * its current status (sent / accepted / declined). The list is re-read when
 * the page opens, when the tab regains focus, and on "تحديث".
 */
export function ClientRequestsList() {
  const { token } = useAuth();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    async (quiet = false) => {
      if (quiet) setRefreshing(true);
      else setState({ status: "loading" });
      try {
        setState({ status: "success", requests: await listClientRequests(token) });
      } catch (err) {
        const code = err instanceof IntakeError ? err.code : "unknown";
        // A failed background refresh keeps the list that is already shown.
        if (!quiet) setState({ status: "error", message: intakeErrorCopy[code] });
      } finally {
        setRefreshing(false);
      }
    },
    [token],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    const onFocus = () => void load(true);
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load]);

  function replace(updated: ClientRequest) {
    setState((s) =>
      s.status === "success"
        ? { status: "success", requests: s.requests.map((r) => (r.id === updated.id ? updated : r)) }
        : s,
    );
  }

  const latest = state.status === "success" ? latestPerIntake(state.requests) : new Set<string>();

  const refreshButton = (
    <Button
      variant="secondary"
      size="sm"
      loading={refreshing}
      disabled={state.status === "loading"}
      icon={<RotateCcw aria-hidden className="size-3.5" />}
      onClick={() => void load(true)}
    >
      تحديث
    </Button>
  );

  return (
    <>
      <PageHeader
        title="طلباتي"
        description="تابع طلباتك المرسلة إلى المحامين وحالتها"
        actions={refreshButton}
      />

      {state.status === "loading" ? (
        <PageSkeleton rows={3} />
      ) : state.status === "error" ? (
        <ErrorState title="تعذّر تحميل طلباتك" description={state.message} onRetry={() => void load()} />
      ) : state.requests.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Send aria-hidden className="size-6" />}
            title="لم ترسل أي طلب بعد"
            description="اسأل المساعد القانوني أولاً، ثم اطلب محامياً من المحادثة."
            action={
              <ButtonLink href="/client/assistant" icon={<MessagesSquare aria-hidden className="size-4" />}>
                الذهاب إلى المساعد القانوني
              </ButtonLink>
            }
          />
        </Card>
      ) : (
        <ul className="space-y-3" aria-label="قائمة الطلبات">
          {state.requests.map((request) => (
            <li key={request.id}>
              <RequestRow
                request={request}
                isLatest={latest.has(request.id)}
                onUpdated={replace}
              />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** Ids of the newest request of each intake (the list is already newest first). */
function latestPerIntake(requests: ClientRequest[]): Set<string> {
  const seen = new Set<string>();
  const latest = new Set<string>();
  for (const r of requests) {
    const key = r.intakeId ?? r.id;
    if (!seen.has(key)) {
      seen.add(key);
      latest.add(r.id);
    }
  }
  return latest;
}

function RequestRow({
  request,
  isLatest,
  onUpdated,
}: {
  request: ClientRequest;
  /** Only the newest request of a case can lead to choosing another lawyer. */
  isLatest: boolean;
  onUpdated: (request: ClientRequest) => void;
}) {
  const niche = request.niche ? (NICHE_LABELS[request.niche] ?? request.niche) : null;
  const awaiting = isAwaitingLawyer(request.status);
  const chooseAnother = isLatest && request.intakeId !== null && canChooseAnotherLawyer(request.status);

  return (
    <Card data-request={request.id}>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <p className="font-semibold text-foreground">
              {request.lawyerName ? (
                <>
                  إلى <span dir="auto">{request.lawyerName}</span>
                </>
              ) : (
                "طلب إلى محامٍ"
              )}
            </p>
            <p className="text-xs text-muted">
              {niche ? <>{niche} · </> : null}
              أُرسل في {formatRequestDate(request.createdAt)}
              {request.respondedAt ? <> · الرد في {formatRequestDate(request.respondedAt)}</> : null}
            </p>
          </div>
          <RequestStatusBadge status={request.status} />
        </div>

        <p className="text-sm text-muted">{REQUEST_STATUS_MESSAGES[request.status]}</p>

        {request.status === "declined" && request.declineReason ? (
          <p className="rounded-lg bg-surface-muted px-3 py-2 text-sm">
            <span className="font-semibold">سبب الاعتذار: </span>
            <span dir="auto">{request.declineReason}</span>
          </p>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-2">
          {awaiting ? <MockLawyerResponse requestId={request.id} onDone={onUpdated} /> : <span />}
          {request.intakeId ? (
            <div className="flex flex-wrap items-center gap-3">
              {chooseAnother ? (
                <ButtonLink
                  href={`/client/requests/${request.intakeId}#lawyer-selection`}
                  size="sm"
                  icon={<UserRound aria-hidden className="size-3.5" />}
                >
                  اختيار محامٍ آخر
                </ButtonLink>
              ) : null}
              <Link
                href={`/client/requests/${request.intakeId}`}
                className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
              >
                عرض الطلب
                <ChevronLeft aria-hidden className="size-4" />
              </Link>
            </div>
          ) : null}
        </div>
      </CardBody>
    </Card>
  );
}
