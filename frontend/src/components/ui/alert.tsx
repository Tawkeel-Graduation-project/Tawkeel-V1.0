import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import { cn } from "@/lib/cn";

type AlertTone = "info" | "success" | "warning" | "danger";

const styles: Record<AlertTone, { box: string; icon: React.ElementType }> = {
  info: { box: "bg-info-soft text-info border-info/20", icon: Info },
  success: { box: "bg-success-soft text-success border-success/20", icon: CheckCircle2 },
  warning: { box: "bg-warning-soft text-warning border-warning/20", icon: AlertTriangle },
  danger: { box: "bg-danger-soft text-danger border-danger/20", icon: XCircle },
};

export function Alert({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: AlertTone;
  title?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}) {
  const { box, icon: Icon } = styles[tone];
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn("flex gap-3 rounded-lg border p-4 text-sm", box, className)}
    >
      <Icon aria-hidden className="mt-0.5 size-5 shrink-0" />
      <div className="min-w-0 text-foreground">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children ? <div className={cn(title && "mt-0.5", "text-muted")}>{children}</div> : null}
      </div>
    </div>
  );
}

/** PRD §9.2: AI output is not a substitute for professional legal judgment. */
export function LegalDisclaimer({ className }: { className?: string }) {
  return (
    <Alert tone="warning" title="تنبيه قانوني" className={className}>
      المعلومات التي يقدّمها المساعد الذكي للاسترشاد فقط، ولا تُغني عن استشارة محامٍ مختص.
    </Alert>
  );
}
