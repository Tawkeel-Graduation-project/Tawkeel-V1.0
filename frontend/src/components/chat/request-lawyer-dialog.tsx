"use client";

import { useEffect } from "react";
import { AlertCircle, Briefcase, X } from "lucide-react";
import { Button } from "@/components/ui";

interface RequestLawyerDialogProps {
  open: boolean;
  loading?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Confirms starting the lawyer-request intake (SCRUM-330). */
export function RequestLawyerDialog({ open, loading = false, error, onConfirm, onCancel }: RequestLawyerDialogProps) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !loading) onCancel();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, loading, onCancel]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        aria-hidden
        className="absolute inset-0 bg-foreground/40 backdrop-blur-[2px]"
        onClick={loading ? undefined : onCancel}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="request-lawyer-title"
        aria-describedby="request-lawyer-desc"
        className="relative w-full max-w-md rounded-2xl border border-border bg-surface p-5 text-start shadow-xl"
      >
        <button
          type="button"
          onClick={onCancel}
          disabled={loading}
          aria-label="إغلاق"
          className="absolute end-3 top-3 rounded-md p-1 text-muted transition hover:bg-surface-muted hover:text-foreground disabled:opacity-50"
        >
          <X aria-hidden className="size-4" />
        </button>

        <div className="flex items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary">
            <Briefcase aria-hidden className="size-5" />
          </span>
          <div className="min-w-0 space-y-1">
            <h2 id="request-lawyer-title" className="text-base font-bold text-foreground">
              طلب محامٍ متخصص
            </h2>
            <p id="request-lawyer-desc" className="text-sm leading-relaxed text-muted">
              سنبدأ بجمع معلومات قضيتك لتجهيز طلب واضح للمحامي.
            </p>
          </div>
        </div>

        <ul className="mt-4 list-disc space-y-1.5 ps-5 text-sm leading-relaxed text-foreground">
          <li>سيُنقل نص هذه المحادثة والمصادر القانونية المذكورة فيها إلى وكيل جمع المعلومات.</li>
          <li>قد يطرح عليك الوكيل أسئلة إضافية لاستكمال بيانات القضية.</li>
          <li>
            <strong>لن يُرسل أي شيء إلى محامٍ</strong> قبل أن تراجع الملخّص وتوافق عليه صراحةً.
          </li>
        </ul>

        {error ? (
          <div role="alert" className="mt-4 flex items-start gap-2 rounded-xl border border-danger/30 bg-danger-soft p-3 text-xs text-danger">
            <AlertCircle aria-hidden className="mt-0.5 size-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}

        <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
          <Button variant="secondary" onClick={onCancel} disabled={loading}>
            إلغاء
          </Button>
          <Button autoFocus onClick={onConfirm} loading={loading}>
            متابعة وبدء الطلب
          </Button>
        </div>
      </div>
    </div>
  );
}
