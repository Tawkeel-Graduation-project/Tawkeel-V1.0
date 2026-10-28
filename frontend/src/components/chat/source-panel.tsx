"use client";

import { useEffect, useRef, useState } from "react";
import {
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  Quote,
  Scale,
  ShieldCheck,
  X,
} from "lucide-react";
import type { Citation } from "@/lib/chat/types";
import { Badge, Button, DirectionalIcon } from "@/components/ui";
import { cn } from "@/lib/cn";

interface SourcePanelProps {
  open: boolean;
  citation: Citation | null;
  citations?: Citation[];
  onClose: () => void;
  onSelectCitation?: (citation: Citation) => void;
}

export function SourcePanel({
  open,
  citation,
  citations = [],
  onClose,
  onSelectCitation,
}: SourcePanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);

  // Keyboard navigation & escape listener
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    panelRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);

  // Copy article text
  async function handleCopy() {
    if (!citation) return;
    try {
      const fullText = `${citation.sourceName} - ${citation.articleNumber ?? ""}\n${citation.title ? citation.title + "\n" : ""}\n"${citation.text}"`;
      await navigator.clipboard.writeText(fullText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore
    }
  }

  // Find index of current citation in the list
  const currentIndex = citation ? citations.findIndex((c) => c.id === citation.id) : -1;
  const hasMultiple = citations.length > 1;

  function handlePrev() {
    if (currentIndex > 0 && onSelectCitation) {
      onSelectCitation(citations[currentIndex - 1]);
    }
  }

  function handleNext() {
    if (currentIndex < citations.length - 1 && onSelectCitation) {
      onSelectCitation(citations[currentIndex + 1]);
    }
  }

  if (!open && !citation) return null;

  return (
    <div
      className={cn(
        "fixed inset-0 z-50 transition-opacity duration-300",
        open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none",
      )}
      aria-hidden={!open}
    >
      {/* Backdrop overlay */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-xs transition-opacity"
        onClick={onClose}
      />

      {/* Slide-over panel from the end (left in RTL, right in LTR) */}
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="لوحة السند القانوني"
        tabIndex={-1}
        className={cn(
          "absolute inset-y-0 end-0 flex w-full flex-col bg-surface shadow-2xl transition-transform duration-300 sm:w-[480px] md:w-[540px] focus:outline-none border-s border-border",
          open ? "translate-x-0" : "ltr:translate-x-full rtl:-translate-x-full",
        )}
      >
        {/* Panel Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-4 shrink-0 bg-surface">
          <div className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-xl bg-linear-to-br from-vivid-2 via-vivid to-primary text-white shadow-md shadow-vivid/20">
              <Scale aria-hidden className="size-5" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-foreground">السند القانوني</h2>
                <Badge tone="primary" className="text-[11px]">
                  نص رسمي
                </Badge>
              </div>
              <p className="text-xs text-muted">المرجع التشريعي المعتمد والمؤيد للإجابة</p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="flex size-9 items-center justify-center rounded-lg text-muted hover:bg-surface-muted hover:text-foreground transition focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
            aria-label="إغلاق السند القانوني"
          >
            <X aria-hidden className="size-5" />
          </button>
        </div>

        {/* Multi-citation switcher bar */}
        {hasMultiple ? (
          <div className="flex items-center justify-between border-b border-border/80 bg-surface-muted/50 px-5 py-2.5 shrink-0 text-xs">
            <span className="font-medium text-muted">
              المصدر <span className="font-bold text-foreground">{currentIndex + 1}</span> من{" "}
              <span className="font-bold text-foreground">{citations.length}</span>
            </span>

            <div className="flex items-center gap-1.5">
              <Button
                size="sm"
                variant="ghost"
                disabled={currentIndex <= 0}
                onClick={handlePrev}
                className="h-7 px-2 text-xs"
              >
                <DirectionalIcon>
                  <ChevronRight aria-hidden className="size-4" />
                </DirectionalIcon>
                السابق
              </Button>

              <Button
                size="sm"
                variant="ghost"
                disabled={currentIndex >= citations.length - 1}
                onClick={handleNext}
                className="h-7 px-2 text-xs"
              >
                التالي
                <DirectionalIcon>
                  <ChevronLeft aria-hidden className="size-4" />
                </DirectionalIcon>
              </Button>
            </div>
          </div>
        ) : null}

        {/* Quick pill tabs for citations */}
        {hasMultiple ? (
          <div className="flex gap-1.5 overflow-x-auto px-5 py-2 shrink-0 border-b border-border/50 bg-surface">
            {citations.map((c, i) => {
              const active = c.id === citation?.id;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => onSelectCitation?.(c)}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium whitespace-nowrap transition",
                    active
                      ? "bg-primary text-white shadow-xs"
                      : "bg-surface-muted text-muted hover:bg-primary-soft/50 hover:text-foreground",
                  )}
                >
                  <span className="font-mono text-[10px]">[{i + 1}]</span>
                  <span>{c.articleNumber ?? `مادة ${i + 1}`}</span>
                </button>
              );
            })}
          </div>
        ) : null}

        {/* Scrollable Content Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {citation ? (
            <>
              {/* Document Identity Banner */}
              <div className="rounded-2xl border border-border bg-surface-muted/40 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-primary">
                      <BookOpen aria-hidden className="size-3.5" />
                      {citation.sourceType}
                    </span>
                    <h3 className="text-lg font-bold text-foreground">
                      {citation.articleNumber}
                      {citation.title ? ` — ${citation.title}` : ""}
                    </h3>
                    <p className="text-xs text-muted font-medium">{citation.sourceName}</p>
                  </div>

                  <Badge tone="success" className="shrink-0 flex items-center gap-1">
                    <ShieldCheck aria-hidden className="size-3.5" />
                    تشريع ساري
                  </Badge>
                </div>
              </div>

              {/* Exact Legal Passage */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs font-semibold text-muted">
                  <span className="flex items-center gap-1.5">
                    <Quote aria-hidden className="size-3.5 text-primary" />
                    النص القانوني الرسمي المقتبس:
                  </span>
                  <span className="text-[11px] text-muted/80">الجريدة الرسمية</span>
                </div>

                <div className="relative rounded-2xl border-s-4 border-primary bg-primary-soft/25 p-5 shadow-xs">
                  <Quote
                    aria-hidden
                    className="absolute end-4 top-4 size-10 text-primary/10 pointer-events-none"
                  />
                  <p className="text-sm font-medium leading-loose text-foreground whitespace-pre-wrap select-text">
                    &ldquo;{citation.text}&rdquo;
                  </p>
                </div>
              </div>

              {/* Metadata & Verification Breakdown */}
              <div className="space-y-3 rounded-2xl border border-border bg-surface p-4">
                <h4 className="text-xs font-bold text-foreground">بيانات التوثيق والاعتماد</h4>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="rounded-xl border border-border/60 bg-surface-muted/30 p-2.5">
                    <span className="block text-muted text-[11px]">الجهة المصدرة</span>
                    <span className="font-semibold text-foreground">مجلس النواب المصري</span>
                  </div>
                  <div className="rounded-xl border border-border/60 bg-surface-muted/30 p-2.5">
                    <span className="block text-muted text-[11px]">النطاق القضائي</span>
                    <span className="font-semibold text-foreground">المحاكم المصرية</span>
                  </div>
                  <div className="rounded-xl border border-border/60 bg-surface-muted/30 p-2.5">
                    <span className="block text-muted text-[11px]">الحالة القانونية</span>
                    <span className="font-semibold text-success">مفعل وساري العمل به</span>
                  </div>
                  <div className="rounded-xl border border-border/60 bg-surface-muted/30 p-2.5">
                    <span className="block text-muted text-[11px]">التوثيق</span>
                    <span className="font-semibold text-primary">مطابق لقاعدة بيانات توكيل</span>
                  </div>
                </div>
              </div>

              {/* Disclaimer reminder inside source drawer */}
              <div className="rounded-xl border border-warning/30 bg-warning-soft/60 p-3 text-xs text-warning">
                <p className="leading-relaxed">
                  يُعرض هذا النص للاسترشاد القانوني والتأكد من صحة الإجابة. في حال وجود نزاع قضائي قائم، يُرجى الرجوع لنص المادة بالجريدة الرسمية أو استشارة محامٍ مختص.
                </p>
              </div>
            </>
          ) : null}
        </div>

        {/* Panel Footer Actions */}
        <div className="flex items-center justify-between border-t border-border px-5 py-4 shrink-0 bg-surface">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleCopy}
            icon={
              copied ? (
                <Check aria-hidden className="size-4 text-success" />
              ) : (
                <Copy aria-hidden className="size-4" />
              )
            }
          >
            {copied ? "تم نسخ نص المادة" : "نسخ نص المادة"}
          </Button>

          <Button variant="ghost" size="sm" onClick={onClose}>
            إغلاق
          </Button>
        </div>
      </aside>
    </div>
  );
}
