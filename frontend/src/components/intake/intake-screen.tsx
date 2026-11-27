"use client";

import { useCallback, useEffect, useState } from "react";
import { BookOpen, ChevronDown, Info, MessageSquareText, Scale, User } from "lucide-react";
import { useAuth } from "@/lib/auth/auth-context";
import { getIntake, IntakeError, type Intake } from "@/lib/intake/api";
import { intakeErrorCopy, intakePhaseLabel } from "@/lib/intake/copy";
import { IntakeChat } from "./intake-chat";
import { SummaryReview } from "./summary-review";
import { LawyerSelection } from "./lawyer-selection";
import {
  Badge,
  ButtonLink,
  Card,
  CardBody,
  ErrorState,
  PageHeader,
  PageSkeleton,
} from "@/components/ui";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; intake: Intake };

/**
 * One page per lawyer request (SCRUM-330): the INTAKE phase, the chat carried
 * over from the assistant, the intake agent conversation (SCRUM-248), and,
 * once the intake is complete, the summary review and approval (SCRUM-341),
 * then, once approved, choosing a lawyer and sending the request (SCRUM-345).
 */
export function IntakeScreen({ id }: { id: string }) {
  const { token } = useAuth();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      setState({ status: "success", intake: await getIntake(id, token) });
    } catch (err) {
      const code = err instanceof IntakeError ? err.code : "unknown";
      setState({ status: "error", message: intakeErrorCopy[code] });
    }
  }, [id, token]);

  useEffect(() => {
    // Fetch on mount and whenever the id/session changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const backToChat = (
    <ButtonLink href="/client/assistant" variant="secondary" size="sm">
      العودة إلى المساعد القانوني
    </ButtonLink>
  );

  if (state.status === "loading") {
    return (
      <>
        <PageHeader title="طلب محامٍ" />
        <PageSkeleton rows={3} />
      </>
    );
  }

  if (state.status === "error") {
    return (
      <>
        <PageHeader title="طلب محامٍ" actions={backToChat} />
        <ErrorState title="تعذّر تحميل الطلب" description={state.message} onRetry={load} />
      </>
    );
  }

  const { intake } = state;
  const phase = intake.phase ? intakePhaseLabel[intake.phase] : null;

  return (
    <div className="mx-auto w-full max-w-4xl">
      <PageHeader
        title="طلب محامٍ"
        description="نجمع الآن معلومات قضيتك لتجهيز طلب واضح للمحامي."
        actions={backToChat}
      />

      <Card className="mb-4">
        <CardBody className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-semibold text-foreground">المرحلة الحالية:</span>
          {phase ? (
            <Badge tone="primary" data-phase={intake.phase}>
              <span className="size-1.5 rounded-full bg-primary" />
              {phase}
            </Badge>
          ) : null}
          <span className="text-xs text-muted">
            لن يُرسل أي شيء إلى محامٍ قبل أن تراجع الملخّص وتوافق عليه.
          </span>
        </CardBody>
      </Card>

      <Card className="mb-4">
        <details className="group">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-5 [&::-webkit-details-marker]:hidden">
          <span className="min-w-0">
            <span className="inline-flex items-center gap-2 text-base font-semibold">
              <MessageSquareText aria-hidden className="size-4 text-vivid" />
              المحادثة المنقولة إلى الطلب ({intake.contextMessages.length})
            </span>
            <span className="mt-0.5 block text-sm text-muted">
              ما يعتمد عليه وكيل جمع المعلومات من محادثتك مع المساعد القانوني.
            </span>
          </span>
          <ChevronDown aria-hidden className="size-4 shrink-0 text-muted transition group-open:rotate-180" />
        </summary>
        <CardBody className="space-y-3 border-t border-border">
          {intake.contextSource === "client_submitted" ? (
            <p className="flex items-start gap-2 rounded-xl bg-info-soft/60 px-3 py-2 text-xs text-foreground">
              <Info aria-hidden className="mt-0.5 size-3.5 shrink-0 text-info" />
              نُقلت هذه المحادثة من متصفحك، وسيظهر ذلك للمحامي عند مراجعة الطلب.
            </p>
          ) : null}

          <ol className="space-y-3">
            {intake.contextMessages.map((m, idx) => (
              <li key={idx} className="flex items-start gap-2.5">
                <span
                  className={
                    m.role === "user"
                      ? "flex size-7 shrink-0 items-center justify-center rounded-full bg-secondary text-white"
                      : "flex size-7 shrink-0 items-center justify-center rounded-lg bg-linear-to-br from-vivid-2 via-vivid to-primary text-white"
                  }
                >
                  {m.role === "user" ? (
                    <User aria-hidden className="size-3.5" />
                  ) : (
                    <Scale aria-hidden className="size-3.5" />
                  )}
                </span>
                <div className="min-w-0 flex-1 rounded-xl border border-border bg-surface-muted/40 px-3 py-2">
                  <span className="mb-0.5 block text-[11px] font-semibold text-muted">
                    {m.role === "user" ? "سؤالك" : "إجابة المساعد"}
                  </span>
                  <p className="line-clamp-6 whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                    {m.content}
                  </p>
                  {m.citations.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {m.citations.map((c, i) => (
                        <Badge key={c.id ?? i} tone="neutral" title={c.sourceName}>
                          <BookOpen aria-hidden className="size-3" />
                          {c.articleNumber ?? c.sourceName ?? `المصدر ${i + 1}`}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        </CardBody>
        </details>
      </Card>

      <IntakeChat
        intake={intake}
        token={token}
        onChange={(next) => setState({ status: "success", intake: next })}
      />

      {intake.complete ? (
        <SummaryReview
          // Remount (and reset the draft) whenever the saved summary changes.
          key={`${intake.approvedAt ?? "draft"}:${JSON.stringify(intake.fields)}`}
          intake={intake}
          token={token}
          onChange={(next) => setState({ status: "success", intake: next })}
        />
      ) : null}

      {intake.approvedAt ? (
        <LawyerSelection
          intake={intake}
          token={token}
          onChange={(next) => setState({ status: "success", intake: next })}
        />
      ) : null}
    </div>
  );
}
