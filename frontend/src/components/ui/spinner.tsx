import { cn } from "@/lib/cn";

const sizes = { sm: "size-4 border-2", md: "size-6 border-2", lg: "size-10 border-[3px]" };

export function Spinner({
  size = "md",
  label = "جارٍ التحميل…",
  className,
}: {
  size?: keyof typeof sizes;
  /** Screen-reader text. Pass "" when the spinner sits inside a labelled control. */
  label?: string;
  className?: string;
}) {
  return (
    <span role={label ? "status" : undefined} className={cn("inline-flex", className)}>
      <span
        aria-hidden
        className={cn("animate-spin rounded-full border-current border-e-transparent", sizes[size])}
      />
      {label ? <span className="sr-only">{label}</span> : null}
    </span>
  );
}
