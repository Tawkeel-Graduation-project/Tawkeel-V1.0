import { Scale } from "lucide-react";

export function ChatTypingIndicator() {
  return (
    <div className="flex items-start gap-3 py-2 text-start">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-linear-to-br from-vivid-2 via-vivid to-primary text-white shadow-xs">
        <Scale aria-hidden className="size-4" />
      </div>

      <div className="flex flex-col gap-1.5 rounded-2xl rounded-tr-xs border border-border bg-surface px-4 py-3 shadow-xs">
        <div className="flex items-center gap-1.5">
          <span className="size-2 animate-bounce rounded-full bg-primary/70 [animation-delay:-0.3s]" />
          <span className="size-2 animate-bounce rounded-full bg-primary/70 [animation-delay:-0.15s]" />
          <span className="size-2 animate-bounce rounded-full bg-primary/70" />
          <span className="ms-2 text-xs font-medium text-muted">جارٍ فحص القوانين والتشريعات ذات الصلة…</span>
        </div>
      </div>
    </div>
  );
}
