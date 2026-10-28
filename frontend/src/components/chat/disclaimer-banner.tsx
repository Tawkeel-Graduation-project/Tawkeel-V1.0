"use client";

import { useState } from "react";
import { AlertTriangle, ChevronDown, ChevronUp, Send } from "lucide-react";
import { Badge, ButtonLink, DirectionalIcon } from "@/components/ui";
import { cn } from "@/lib/cn";

interface DisclaimerBannerProps {
  className?: string;
}

/**
 * Acceptance Criteria: Disclaimer is ALWAYS visible.
 * Features an always-visible summary bar with an optional expandable
 * legal compliance & guidelines breakdown, plus a direct CTA to request a lawyer.
 */
export function DisclaimerBanner({ className }: DisclaimerBannerProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <aside
      role="complementary"
      aria-label="إخلاء المسؤولية القانونية"
      className={cn(
        "rounded-2xl border border-warning/30 bg-warning-soft/80 text-foreground shadow-xs transition-all",
        className,
      )}
    >
      {/* Primary visible strip (Always visible) */}
      <div className="flex flex-col gap-2.5 p-3.5 sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:p-4">
        <div className="flex items-start gap-3 min-w-0">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-warning/20 text-warning">
            <AlertTriangle aria-hidden className="size-4.5" />
          </span>

          <div className="min-w-0 text-start">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-bold text-foreground">تنبيه قانوني هام</span>
              <Badge tone="warning" className="text-[10px] font-semibold py-0 px-2">
                للاسترشاد فقط
              </Badge>
            </div>
            <p className="mt-0.5 text-xs leading-relaxed text-muted">
              المعلومات المستخرجة بواسطة المساعد الذكي للاسترشاد القانوني فقط، ولا تُعد استشارة رسمية أو بديلاً عن توكيل محامٍ مختص.
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
          <ButtonLink
            href="/client/requests"
            size="sm"
            variant="secondary"
            className="h-7 border-warning/40 bg-surface/80 text-xs font-semibold text-foreground hover:bg-surface hover:border-warning/60 hover:text-primary shadow-xs"
          >
            <Send aria-hidden className="size-3 rtl:-scale-x-100 text-vivid" />
            <span>طلب محامٍ</span>
          </ButtonLink>

          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-warning hover:bg-warning/10 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
          >
            <span>{expanded ? "إخفاء الضوابط" : "عرض الضوابط"}</span>
            <DirectionalIcon>
              {expanded ? (
                <ChevronUp aria-hidden className="size-3.5" />
              ) : (
                <ChevronDown aria-hidden className="size-3.5" />
              )}
            </DirectionalIcon>
          </button>
        </div>
      </div>

      {/* Expandable legal guidance breakdown */}
      {expanded ? (
        <div className="border-t border-warning/20 bg-surface/60 px-4 py-3 text-start rounded-b-2xl animate-in fade-in duration-200">
          <div className="grid gap-2.5 sm:grid-cols-3 text-xs">
            <div className="rounded-xl border border-warning/20 bg-surface p-2.5">
              <span className="block font-bold text-foreground mb-1">١. نطاق التشريعات</span>
              <p className="text-muted leading-relaxed">
                تقتصر المواد المستخرجة على القوانين الرسمية السارية بجمهورية مصر العربية الصادرة عن السلطة التشريعية.
              </p>
            </div>

            <div className="rounded-xl border border-warning/20 bg-surface p-2.5">
              <span className="block font-bold text-foreground mb-1">٢. انتفاء الوكالة</span>
              <p className="text-muted leading-relaxed">
                لا ينشأ عن استخدام المساعد أو طرح الأسئلة أي علاقة تمثيل قضائي أو وكالة قانونية بين المستخدم والمنصة.
              </p>
            </div>

            <div className="rounded-xl border border-warning/20 bg-surface p-2.5">
              <span className="block font-bold text-foreground mb-1">٣. المواعيد القضائية</span>
              <p className="text-muted leading-relaxed">
                إذا كانت لديك دعوى قائمة أو موعد طعن حتمي، يجب التوجه لمكتب محامٍ مقيد بالنقابة لتفادي سقوط الحقوق بالتقادم.
              </p>
            </div>
          </div>
        </div>
      ) : null}
    </aside>
  );
}
