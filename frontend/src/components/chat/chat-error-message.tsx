"use client";

import { AlertCircle, Clock, HelpCircle, PenLine, RotateCcw, SearchX, Send, WifiOff } from "lucide-react";
import { Button, ButtonLink } from "@/components/ui";
import type { ChatErrorType } from "@/lib/chat/types";
import { chatNoticeActions, chatNoticeCopy } from "@/lib/errors";

interface ChatErrorMessageProps {
  type?: ChatErrorType | "no_source" | "clarification";
  errorMessage?: string;
  /** The model's follow-up question (type "clarification"). */
  clarificationQuestion?: string;
  /** Overrides the default for the type (backend `notice.retryable`). */
  retryable?: boolean;
  /** Overrides the default for the type (backend `notice.show_lawyer_cta`). */
  showLawyerCta?: boolean;
  onRetry?: () => void;
  onRephrase?: () => void;
}

function LawyerCta() {
  return (
    <ButtonLink href="/client/requests" size="sm" variant="primary" className="h-8 text-xs">
      <Send aria-hidden className="size-3.5 rtl:-scale-x-100" />
      <span>طلب استشارة محامٍ متخصص</span>
    </ButtonLink>
  );
}

export function ChatErrorMessage({
  type = "general",
  errorMessage,
  clarificationQuestion,
  retryable,
  showLawyerCta,
  onRetry,
  onRephrase,
}: ChatErrorMessageProps) {
  if (type === "clarification") {
    const copy = chatNoticeCopy.clarification;
    return (
      <div role="status" className="rounded-2xl border border-info/30 bg-info-soft/50 p-4 text-start shadow-xs">
        <div className="flex items-start gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-info/15 text-info">
            <HelpCircle aria-hidden className="size-5" />
          </div>

          <div className="space-y-2 min-w-0 flex-1">
            <h4 className="text-sm font-bold text-foreground">{copy.title}</h4>
            <p className="text-xs leading-relaxed text-muted">{errorMessage || copy.description}</p>
            {clarificationQuestion ? (
              <p className="border-s-2 border-info bg-surface/80 px-3 py-2 text-sm rounded-e-md font-medium text-foreground whitespace-pre-wrap">
                {clarificationQuestion}
              </p>
            ) : null}
            <p className="text-[11px] text-muted">اكتب التوضيح في خانة الرسالة بالأسفل.</p>
          </div>
        </div>
      </div>
    );
  }

  if (type === "no_source") {
    return (
      <div className="rounded-2xl border border-warning/40 bg-warning-soft/50 p-4 text-start shadow-xs">
        <div className="flex items-start gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-warning/20 text-warning">
            <SearchX aria-hidden className="size-5" />
          </div>

          <div className="space-y-2 min-w-0 flex-1">
            <h4 className="text-sm font-bold text-foreground">
              لم يُعثر على سند قانوني مؤكد لهذا الاستفسار
            </h4>
            <p className="text-xs leading-relaxed text-muted">
              التزاماً بمبادئ الدقة في منصة <strong className="text-foreground">توكيل</strong>، يمتنع المساعد الذكي عن تقديم إجابات أو تكييفات دون الاستناد إلى نصوص تشريعية صريحة من القوانين المصرية المعتمدة.
            </p>

            <div className="rounded-xl border border-warning/30 bg-surface/80 p-3 text-xs text-muted space-y-1">
              <span className="block font-semibold text-foreground">خيارات مقترحة للمتابعة:</span>
              <ul className="list-disc list-inside space-y-0.5 ps-1">
                <li>إعادة صياغة السؤال باستخدام مصطلحات قانونية أكثر تحديداً.</li>
                <li>التأكد من أن الاستفسار يقع ضمن نطاق القوانين والتشريعات المصرية.</li>
                <li>إحالة مشكلتك إلى محامٍ متخصص لدراسة المستندات والوقائع يدوياً.</li>
              </ul>
            </div>

            <div className="flex flex-wrap items-center gap-2 pt-1">
              {onRephrase ? (
                <Button size="sm" variant="secondary" onClick={onRephrase} className="h-8 text-xs">
                  إعادة صياغة السؤال
                </Button>
              ) : null}

              <LawyerCta />
            </div>
          </div>
        </div>
      </div>
    );
  }

  const isNetwork = type === "network" || errorMessage?.includes("اتصال") || errorMessage?.includes("network");
  const isAssistantKind =
    type === "invalid_question" || type === "temporarily_unavailable" || type === "answer_failed";
  const defaults = isAssistantKind ? chatNoticeActions[type] : { retryable: true, showLawyerCta: false };
  const canRetry = Boolean(onRetry) && (retryable ?? defaults.retryable);
  const withLawyerCta = showLawyerCta ?? defaults.showLawyerCta;
  // "invalid_question" is the user's to fix, so it uses the softer warning tone.
  const isWarning = type === "invalid_question";

  const title = isAssistantKind
    ? chatNoticeCopy[type].title
    : isNetwork
      ? "تعذّر الاتصال بخادم الاسترجاع القانوني"
      : "حدث خطأ أثناء صياغة الإجابة";
  const description =
    errorMessage ||
    (isAssistantKind
      ? chatNoticeCopy[type].description
      : "تعذّر استكمال استرجاع النصوص القانونية أو إرسال الاستجابة. يرجى التحقق من اتصالك بالإنترنت ثم إعادة المحاولة.");
  const Icon = isWarning
    ? PenLine
    : type === "temporarily_unavailable"
      ? Clock
      : isNetwork
        ? WifiOff
        : AlertCircle;

  return (
    <div
      role="alert"
      className={
        isWarning
          ? "rounded-2xl border border-warning/40 bg-warning-soft/50 p-4 text-start shadow-xs"
          : "rounded-2xl border border-danger/40 bg-danger-soft/60 p-4 text-start shadow-xs"
      }
    >
      <div className="flex items-start gap-3">
        <div
          className={
            isWarning
              ? "flex size-9 shrink-0 items-center justify-center rounded-xl bg-warning/20 text-warning"
              : "flex size-9 shrink-0 items-center justify-center rounded-xl bg-danger/20 text-danger"
          }
        >
          <Icon aria-hidden className="size-5" />
        </div>

        <div className="space-y-2 min-w-0 flex-1">
          <h4 className={isWarning ? "text-sm font-bold text-foreground" : "text-sm font-bold text-danger"}>
            {title}
          </h4>
          <p className="text-xs leading-relaxed text-muted">{description}</p>

          {canRetry || withLawyerCta ? (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              {canRetry ? (
                <Button
                  size="sm"
                  variant={isWarning ? "secondary" : "danger"}
                  onClick={onRetry}
                  icon={<RotateCcw aria-hidden className="size-3.5" />}
                  className="h-8 text-xs"
                >
                  إعادة المحاولة
                </Button>
              ) : null}
              {withLawyerCta ? <LawyerCta /> : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
