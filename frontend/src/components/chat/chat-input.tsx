"use client";

import { useEffect, useRef } from "react";
import { Send, Square } from "lucide-react";
import type { ChatStatus } from "@/lib/chat/types";
import { Button, DirectionalIcon } from "@/components/ui";
import { cn } from "@/lib/cn";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  status: ChatStatus;
  placeholder?: string;
  disabled?: boolean;
}

const MAX_QUERY_LENGTH = 1000;

export function ChatInput({
  value,
  onChange,
  onSubmit,
  onStop,
  status,
  placeholder = "اطرح استفسارك القانوني هنا... (اضغط Enter للإرسال، Shift + Enter لسطر جديد)",
  disabled = false,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea as text grows
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const nextHeight = Math.min(el.scrollHeight, 160);
    el.style.height = `${nextHeight}px`;
  }, [value]);

  const isTooLong = value.length > MAX_QUERY_LENGTH;
  const isStreaming = status === "streaming";
  const isLoading = status === "loading";
  const canSubmit = Boolean(value.trim()) && !isTooLong && !isStreaming && !isLoading && !disabled;

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSubmit) {
        onSubmit();
      }
    }
  }

  return (
    <div className="w-full">
      <div
        className={cn(
          "relative rounded-2xl border bg-surface shadow-md transition-all focus-within:ring-2",
          isTooLong
            ? "border-danger focus-within:border-danger focus-within:ring-danger/20"
            : "border-border focus-within:border-primary/50 focus-within:ring-primary/20",
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isLoading}
          rows={1}
          className={cn(
            "w-full resize-none bg-transparent px-4 py-3 text-sm leading-relaxed text-foreground placeholder:text-muted/70 focus:outline-none",
            "min-h-[50px] max-h-[160px]",
          )}
        />

        <div className="flex items-center justify-between border-t border-border/40 px-3 py-2 bg-surface-muted/30 rounded-b-2xl">
          <span className="text-[11px] text-muted">
            <kbd className="rounded border border-border bg-surface px-1 py-0.5 text-[10px] font-mono">Enter</kbd> للإرسال •{" "}
            <kbd className="rounded border border-border bg-surface px-1 py-0.5 text-[10px] font-mono">Shift+Enter</kbd> لسطر جديد
          </span>

          <div className="flex items-center gap-2.5">
            {value.length > 500 ? (
              <span
                className={cn(
                  "text-[10px] font-mono",
                  isTooLong ? "font-bold text-danger" : "text-muted",
                )}
              >
                {value.length} / {MAX_QUERY_LENGTH}
              </span>
            ) : null}

            {isStreaming ? (
              <Button
                size="sm"
                variant="danger"
                onClick={onStop}
                icon={<Square aria-hidden className="size-3.5 fill-current" />}
                className="h-8 px-3 text-xs"
              >
                إيقاف التوليد
              </Button>
            ) : (
              <Button
                size="sm"
                variant="primary"
                onClick={onSubmit}
                disabled={!canSubmit}
                loading={isLoading}
                icon={
                  <DirectionalIcon>
                    <Send aria-hidden className="size-3.5" />
                  </DirectionalIcon>
                }
                className="h-8 px-3.5 text-xs font-semibold"
              >
                إرسال
              </Button>
            )}
          </div>
        </div>
      </div>

      {isTooLong ? (
        <p className="mt-1 text-xs text-danger text-start">
          تجاوز السؤال الحد الأقصى المسموح ({MAX_QUERY_LENGTH} حرف). يرجى تقليص السؤال لضمان جودة الاسترجاع.
        </p>
      ) : (
        <p className="mt-1.5 text-center text-[11px] text-muted">
          المساعد الذكي للاسترشاد فقط ويستند إلى التشريعات المصرية. تحقق دائماً من دقة المواد القانونية.
        </p>
      )}
    </div>
  );
}
