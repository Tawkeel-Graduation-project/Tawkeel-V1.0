"use client";

import { useState } from "react";
import { BookOpen, Check, Copy, Scale, User } from "lucide-react";
import type { ChatMessage, Citation } from "@/lib/chat/types";
import { cn } from "@/lib/cn";
import { formatTime } from "@/lib/format";
import { CitationChip } from "./citation-chip";
import { ChatErrorMessage } from "./chat-error-message";

interface ChatMessageItemProps {
  message: ChatMessage;
  onSelectCitation?: (citation: Citation, allCitations: Citation[]) => void;
  activeCitationId?: string | null;
  onRetry?: () => void;
  onRephrase?: () => void;
}

export function ChatMessageItem({
  message,
  onSelectCitation,
  activeCitationId,
  onRetry,
  onRephrase,
}: ChatMessageItemProps) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback or ignore
    }
  }

  if (isUser) {
    return (
      <div className="flex w-full justify-start flex-row-reverse items-end gap-2.5 py-1.5">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-secondary text-white shadow-xs">
          <User aria-hidden className="size-4" />
        </div>

        <div className="flex max-w-[85%] flex-col items-end sm:max-w-[75%]">
          <div className="rounded-2xl rounded-tl-xs bg-primary px-4 py-2.5 text-sm leading-relaxed text-primary-foreground shadow-xs">
            <p className="whitespace-pre-wrap">{message.content}</p>
          </div>
          <span className="mt-1 px-1 text-[11px] text-muted">
            {formatTime(message.createdAt)}
          </span>
        </div>
      </div>
    );
  }

  const citations = message.citations ?? [];
  const hasCitations = citations.length > 0;

  // Assistant message
  return (
    <div className="flex w-full items-start gap-3 py-2 text-start">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-linear-to-br from-vivid-2 via-vivid to-primary text-white shadow-xs">
        <Scale aria-hidden className="size-4" />
      </div>

      <div className="flex flex-1 max-w-[95%] flex-col items-start sm:max-w-[88%]">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-bold text-foreground">المساعد القانوني</span>
          {message.status === "streaming" ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-primary-soft px-2 py-0.5 text-[10px] font-medium text-primary animate-pulse">
              <span className="size-1.5 rounded-full bg-primary" />
              جارٍ الرد…
            </span>
          ) : message.status === "error" ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-danger-soft px-2 py-0.5 text-[10px] font-medium text-danger">
              تعذّر الرد
            </span>
          ) : message.hasNoSource ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-warning-soft px-2 py-0.5 text-[10px] font-medium text-warning">
              توجيه قانوني
            </span>
          ) : (
            <span className="text-[11px] text-muted">{formatTime(message.createdAt)}</span>
          )}
        </div>

        {/* If the message resulted in an error state */}
        {message.status === "error" ? (
          <div className="w-full">
            <ChatErrorMessage
              type={message.errorType ?? "general"}
              errorMessage={message.errorMessage}
              onRetry={onRetry}
            />
          </div>
        ) : message.hasNoSource ? (
          /* If no legal source was retrieved (PRD §C2) */
          <div className="w-full">
            <ChatErrorMessage
              type="no_source"
              onRephrase={onRephrase}
            />
          </div>
        ) : (
          /* Standard formatted legal response */
          <div className="w-full rounded-2xl rounded-tr-xs border border-border bg-surface px-4 py-3.5 shadow-xs">
            <div className="space-y-3 text-sm leading-relaxed text-foreground">
              {message.content.split("\n\n").map((paragraph, idx) => {
                if (paragraph.startsWith("> ")) {
                  return (
                    <div
                      key={idx}
                      className="border-s-2 border-primary bg-primary-soft/40 px-3 py-2 text-xs rounded-e-md text-foreground/90 font-medium"
                    >
                      {paragraph.replace(/^>\s*/, "")}
                    </div>
                  );
                }
                return (
                  <p key={idx} className="whitespace-pre-wrap">
                    {paragraph}
                  </p>
                );
              })}

              {/* In-flight streaming typing cursor */}
              {message.status === "streaming" ? (
                <span
                  aria-hidden
                  className="inline-block h-4 w-1.5 ms-1 bg-primary animate-pulse align-middle"
                />
              ) : null}
            </div>

            {/* Legal Citations Section with Interactive Chips */}
            {hasCitations && message.status !== "streaming" ? (
              <div className="mt-4 pt-3.5 border-t border-border/70">
                <div className="flex items-center justify-between mb-2.5">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                    <BookOpen aria-hidden className="size-3.5 text-vivid" />
                    <span>السند القانوني والمصادر المعتمدة ({citations.length}):</span>
                  </div>
                  <span className="text-[11px] text-muted">انقر لعرض النص الكامل للمادة</span>
                </div>

                <div className="flex flex-wrap gap-2">
                  {citations.map((citation, index) => (
                    <CitationChip
                      key={citation.id}
                      citation={citation}
                      index={index}
                      isActive={activeCitationId === citation.id}
                      onClick={() => onSelectCitation?.(citation, citations)}
                    />
                  ))}
                </div>
              </div>
            ) : null}

            {/* Action footer: Copy & Metadata */}
            {message.status !== "streaming" && message.content ? (
              <div className="mt-3.5 flex items-center justify-between border-t border-border/60 pt-2.5">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleCopy}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted transition",
                      "hover:bg-surface-muted hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40",
                    )}
                    title="نسخ الإجابة"
                  >
                    {copied ? (
                      <>
                        <Check aria-hidden className="size-3.5 text-success" />
                        <span className="text-success font-medium">تم النسخ</span>
                      </>
                    ) : (
                      <>
                        <Copy aria-hidden className="size-3.5" />
                        <span>نسخ النص</span>
                      </>
                    )}
                  </button>
                </div>

                {hasCitations ? (
                  <span className="text-[11px] font-medium text-primary">
                    موثّق بـ {citations.length} مراجع قانونية
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
