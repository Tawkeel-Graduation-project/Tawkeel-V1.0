import { Scale } from "lucide-react";
import { cn } from "@/lib/cn";

export function Brand({
  subtitle,
  onDark = false,
  className,
}: {
  subtitle?: string;
  /** Use on the dark sidebar. */
  onDark?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <span className="flex size-9 items-center justify-center rounded-xl bg-linear-to-br from-vivid-2 via-vivid to-primary text-white shadow-md shadow-vivid/30">
        <Scale aria-hidden className="size-5" />
      </span>
      <span className="leading-tight">
        <span className={cn("block text-lg font-bold", onDark && "text-sidebar-foreground")}>توكيل</span>
        {subtitle ? (
          <span className={cn("block text-xs", onDark ? "text-sidebar-muted" : "text-muted")}>{subtitle}</span>
        ) : null}
      </span>
    </div>
  );
}
