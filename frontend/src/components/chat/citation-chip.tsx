"use client";

import { BookOpen } from "lucide-react";
import type { Citation } from "@/lib/chat/types";
import { cn } from "@/lib/cn";

interface CitationChipProps {
  citation: Citation;
  index: number;
  isActive?: boolean;
  onClick: () => void;
  variant?: "badge" | "inline";
}

export function CitationChip({
  citation,
  index,
  isActive = false,
  onClick,
  variant = "badge",
}: CitationChipProps) {
  const articleLabel = citation.articleNumber ?? `المصدر ${index + 1}`;
  const sourceShortName = citation.sourceName.split(" رقم ")[0] || citation.sourceName;

  if (variant === "inline") {
    return (
      <button
        type="button"
        onClick={onClick}
        title={`فتح السند القانوني: ${articleLabel} (${citation.sourceName})`}
        aria-label={`فتح السند القانوني: ${articleLabel}`}
        aria-pressed={isActive}
        className={cn(
          "inline-flex items-center gap-1 mx-1 px-1.5 py-0.2 rounded font-medium text-xs transition cursor-pointer select-none",
          isActive
            ? "bg-primary text-white shadow-xs"
            : "bg-primary-soft/80 text-primary border border-primary/20 hover:bg-primary hover:text-white",
        )}
      >
        <span className="font-mono text-[10px] font-bold">[{index + 1}]</span>
        <span>{articleLabel}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      title={`انقر لعرض النص القانوني الكامل: ${citation.sourceName} - ${articleLabel}`}
      aria-label={`عرض السند القانوني: ${articleLabel} من ${citation.sourceName}`}
      aria-pressed={isActive}
      className={cn(
        "group inline-flex items-center gap-2 rounded-xl border p-2 text-start transition-all cursor-pointer select-none text-xs",
        isActive
          ? "border-primary bg-primary-soft text-primary ring-2 ring-primary/30 shadow-xs"
          : "border-border/90 bg-surface text-foreground hover:border-vivid/50 hover:bg-primary-soft/30 hover:shadow-xs",
      )}
    >
      <span
        className={cn(
          "flex size-6 shrink-0 items-center justify-center rounded-lg text-[11px] font-bold transition",
          isActive
            ? "bg-primary text-white"
            : "bg-primary-soft text-primary group-hover:bg-primary group-hover:text-white",
        )}
      >
        {index + 1}
      </span>

      <div className="flex flex-col min-w-0">
        <div className="flex items-center gap-1.5">
          <BookOpen aria-hidden className="size-3 text-vivid shrink-0" />
          <span className="font-semibold truncate text-foreground group-hover:text-primary">
            {articleLabel}
          </span>
        </div>
        <span className="text-[11px] text-muted truncate max-w-[200px]">
          {sourceShortName}
        </span>
      </div>

      <span className="ms-1 shrink-0 text-muted/60 group-hover:text-primary">
        ←
      </span>
    </button>
  );
}
