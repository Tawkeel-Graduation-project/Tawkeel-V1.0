import { cn } from "@/lib/cn";

export type Tone = "neutral" | "primary" | "secondary" | "success" | "warning" | "danger" | "info";

const tones: Record<Tone, string> = {
  neutral: "bg-surface-muted text-muted",
  primary: "bg-primary-soft text-primary",
  secondary: "bg-secondary-soft text-secondary",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
  info: "bg-info-soft text-info",
};

export function Badge({
  tone = "neutral",
  className,
  ...props
}: { tone?: Tone } & React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}
