"use client";

import { AlertCircle, RotateCcw, SearchX, Send, WifiOff } from "lucide-react";
import { Button, ButtonLink } from "@/components/ui";

interface ChatErrorMessageProps {
  type?: "network" | "no_source" | "general";
  errorMessage?: string;
  onRetry?: () => void;
  onRephrase?: () => void;
}

export function ChatErrorMessage({
  type = "general",
  errorMessage,
  onRetry,
  onRephrase,
}: ChatErrorMessageProps) {
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

              <ButtonLink
                href="/client/requests"
                size="sm"
                variant="primary"
                className="h-8 text-xs"
              >
                <Send aria-hidden className="size-3.5 rtl:-scale-x-100" />
                <span>طلب استشارة محامٍ متخصص</span>
              </ButtonLink>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const isNetwork = type === "network" || errorMessage?.includes("اتصال") || errorMessage?.includes("network");

  return (
    <div className="rounded-2xl border border-danger/40 bg-danger-soft/60 p-4 text-start shadow-xs">
      <div className="flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-danger/20 text-danger">
          {isNetwork ? (
            <WifiOff aria-hidden className="size-5" />
          ) : (
            <AlertCircle aria-hidden className="size-5" />
          )}
        </div>

        <div className="space-y-2 min-w-0 flex-1">
          <h4 className="text-sm font-bold text-danger">
            {isNetwork ? "تعذّر الاتصال بخادم الاسترجاع القانوني" : "حدث خطأ أثناء صياغة الإجابة"}
          </h4>
          <p className="text-xs leading-relaxed text-muted">
            {errorMessage ||
              "تعذّر استكمال استرجاع النصوص القانونية أو إرسال الاستجابة. يرجى التحقق من اتصالك بالإنترنت ثم إعادة المحاولة."}
          </p>

          {onRetry ? (
            <div className="pt-1">
              <Button
                size="sm"
                variant="danger"
                onClick={onRetry}
                icon={<RotateCcw aria-hidden className="size-3.5" />}
                className="h-8 text-xs"
              >
                إعادة المحاولة
              </Button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
