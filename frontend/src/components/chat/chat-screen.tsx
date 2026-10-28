"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { AlertCircle, ArrowDown, RotateCcw, Scale, WifiOff } from "lucide-react";
import type { ChatMessage, ChatStatus, Citation } from "@/lib/chat/types";
import { streamLegalResponse } from "@/lib/chat/mock-stream";
import { Button } from "@/components/ui";
import { ChatEmptyState } from "./chat-empty-state";
import { ChatInput } from "./chat-input";
import { ChatMessageItem } from "./chat-message-item";
import { ChatTypingIndicator } from "./chat-typing-indicator";
import { DisclaimerBanner } from "./disclaimer-banner";
import { SourcePanel } from "./source-panel";

function subscribeOnline(callback: () => void) {
  window.addEventListener("online", callback);
  window.addEventListener("offline", callback);
  return () => {
    window.removeEventListener("online", callback);
    window.removeEventListener("offline", callback);
  };
}

function getSnapshot() {
  return navigator.onLine;
}

function getServerSnapshot() {
  return true;
}

export function ChatScreen() {
  const isOnline = useSyncExternalStore(subscribeOnline, getSnapshot, getServerSnapshot);
  const isOffline = !isOnline;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [lastQuery, setLastQuery] = useState<string>("");
  const [showScrollBottom, setShowScrollBottom] = useState(false);

  // Source passage panel state
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [activeCitationsList, setActiveCitationsList] = useState<Citation[]>([]);

  const abortControllerRef = useRef<AbortController | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom smoothly
  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  }, []);

  // Monitor user scroll position to toggle "scroll to bottom" button
  function handleScroll() {
    const el = scrollContainerRef.current;
    if (!el) return;
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    setShowScrollBottom(!isNearBottom);
  }

  // Scroll to bottom on status or messages change if already near bottom
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 240;
    if (isNearBottom || status === "loading") {
      scrollToBottom(status === "streaming" ? "auto" : "smooth");
    }
  }, [messages, status, scrollToBottom]);

  // Clean up abort controller on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const handleStopStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setStatus("idle");
    setMessages((prev) =>
      prev.map((msg) => (msg.status === "streaming" ? { ...msg, status: "complete" } : msg)),
    );
  }, []);

  const handleSelectCitation = useCallback(
    (citation: Citation, allCitations: Citation[]) => {
      setSelectedCitation(citation);
      setActiveCitationsList(allCitations);
    },
    [],
  );

  const handleSendMessage = useCallback(
    async (textToSend?: string) => {
      const query = (textToSend ?? input).trim();
      if (!query || status === "loading" || status === "streaming") return;

      if (isOffline) {
        setErrorText("تعذّر إرسال السؤال؛ أنت غير متصل بالإنترنت حالياً.");
        return;
      }

      setInput("");
      setErrorText(null);
      setLastQuery(query);

      // Create and append user message
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content: query,
        createdAt: Date.now(),
        status: "complete",
      };

      // Create placeholder assistant message
      const assistantId = `assistant-${Date.now() + 1}`;
      const assistantMessage: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        citations: [],
        createdAt: Date.now() + 1,
        status: "streaming",
      };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setStatus("loading");

      // Setup abort controller for streaming cancellation
      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        await streamLegalResponse(
          query,
          {
            onChunk: (accumulated) => {
              setStatus("streaming");
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId
                    ? { ...msg, content: accumulated, status: "streaming" }
                    : msg,
                ),
              );
            },
            onFinish: (finalText, citations: Citation[], hasNoSource?: boolean) => {
              setStatus("idle");
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId
                    ? {
                        ...msg,
                        content: finalText,
                        citations,
                        status: "complete",
                        hasNoSource: Boolean(hasNoSource),
                      }
                    : msg,
                ),
              );
              abortControllerRef.current = null;
            },
            onError: (err) => {
              if (err.message === "aborted") {
                setStatus("idle");
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantId ? { ...msg, status: "complete" } : msg,
                  ),
                );
              } else {
                setStatus("error");
                const isNetErr = err.message === "network";
                const msg = isNetErr
                  ? "تعذّر الاتصال بخادم الاسترجاع القانوني. يرجى التحقق من اتصالك بالإنترنت."
                  : "حدث خطأ غير متوقع أثناء معالجة السؤال القانوني.";
                setErrorText(msg);
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? {
                          ...m,
                          status: "error",
                          errorType: isNetErr ? "network" : "general",
                          errorMessage: msg,
                        }
                      : m,
                  ),
                );
              }
              abortControllerRef.current = null;
            },
          },
          controller.signal,
        );
      } catch (err: unknown) {
        if ((err as Error)?.name !== "AbortError") {
          setStatus("error");
          setErrorText("حدث خطأ في الاتصال بنظام الاسترجاع القانوني.");
        }
      }
    },
    [input, status, isOffline],
  );

  function handleResetChat() {
    handleStopStream();
    setMessages([]);
    setInput("");
    setErrorText(null);
    setSelectedCitation(null);
    setActiveCitationsList([]);
  }

  function handleRetry() {
    if (!lastQuery) return;
    setErrorText(null);
    // Remove last error assistant message
    setMessages((prev) => prev.filter((m) => m.status !== "error"));
    handleSendMessage(lastQuery);
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8.5rem)] min-h-[550px] w-full max-w-4xl mx-auto">
      {/* Header toolbar */}
      <div className="flex items-center justify-between border-b border-border/80 pb-3 mb-3 shrink-0">
        <div className="flex items-center gap-2.5">
          <span className="flex size-9 items-center justify-center rounded-xl bg-linear-to-br from-vivid-2 via-vivid to-primary text-white shadow-xs">
            <Scale aria-hidden className="size-5" />
          </span>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold text-foreground">المساعد القانوني</h1>
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                  isOffline
                    ? "bg-danger-soft text-danger"
                    : "bg-success-soft text-success"
                }`}
              >
                <span
                  className={`size-1.5 rounded-full ${
                    isOffline ? "bg-danger" : "bg-success"
                  }`}
                />
                {isOffline ? "غير متصل" : "متصل بالتشريعات"}
              </span>
            </div>
            <p className="text-xs text-muted">اسأل أي استفسار قانوني مع التوثيق المباشر بالنصوص</p>
          </div>
        </div>

        {messages.length > 0 ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={handleResetChat}
            icon={<RotateCcw aria-hidden className="size-3.5" />}
          >
            محادثة جديدة
          </Button>
        ) : null}
      </div>

      {/* Network offline alert bar */}
      {isOffline ? (
        <div className="shrink-0 mb-3 rounded-xl border border-danger/30 bg-danger-soft p-3 text-xs text-danger flex items-center justify-between gap-3 shadow-xs">
          <div className="flex items-center gap-2">
            <WifiOff aria-hidden className="size-4 shrink-0" />
            <span>
              أنت غير متصل بالإنترنت حالياً. تم إيقاف الاتصال بمحرك البحث القانوني مؤقتاً.
            </span>
          </div>
        </div>
      ) : null}

      {/* Acceptance Criteria: Disclaimer is ALWAYS visible */}
      <div className="shrink-0 mb-3">
        <DisclaimerBanner />
      </div>

      {/* Scrollable messages container */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="relative flex-1 overflow-y-auto px-1 py-2 space-y-4 rounded-xl"
        tabIndex={0}
        aria-label="سجل المحادثة"
      >
        {messages.length === 0 ? (
          <ChatEmptyState onSelectQuestion={(q) => handleSendMessage(q)} />
        ) : (
          <>
            {messages.map((message) => (
              <ChatMessageItem
                key={message.id}
                message={message}
                onSelectCitation={handleSelectCitation}
                activeCitationId={selectedCitation?.id}
                onRetry={handleRetry}
                onRephrase={() => {
                  setInput(lastQuery);
                }}
              />
            ))}

            {status === "loading" ? <ChatTypingIndicator /> : null}

            {errorText ? (
              <div className="flex items-center justify-between gap-3 rounded-xl border border-danger/30 bg-danger-soft p-3 text-sm text-danger">
                <div className="flex items-center gap-2">
                  <AlertCircle aria-hidden className="size-4 shrink-0" />
                  <span>{errorText}</span>
                </div>
                <Button size="sm" variant="danger" onClick={handleRetry}>
                  إعادة المحاولة
                </Button>
              </div>
            ) : null}

            <div ref={messagesEndRef} />
          </>
        )}

        {/* Scroll to bottom button if user scrolled up */}
        {showScrollBottom ? (
          <button
            type="button"
            onClick={() => scrollToBottom("smooth")}
            className="sticky bottom-2 start-1/2 -translate-x-1/2 z-10 flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-foreground shadow-lg hover:bg-surface-muted transition"
            aria-label="النزول إلى آخر الرسائل"
          >
            <ArrowDown aria-hidden className="size-3.5 text-primary" />
            <span>رسائل جديدة</span>
          </button>
        ) : null}
      </div>

      {/* Docked bottom input area */}
      <div className="shrink-0 pt-3 border-t border-border/80">
        <ChatInput
          value={input}
          onChange={setInput}
          onSubmit={() => handleSendMessage()}
          onStop={handleStopStream}
          status={status}
          disabled={isOffline}
        />
      </div>

      {/* Slide-over Source Passage Panel */}
      <SourcePanel
        open={Boolean(selectedCitation)}
        citation={selectedCitation}
        citations={activeCitationsList}
        onClose={() => setSelectedCitation(null)}
        onSelectCitation={(cit) => setSelectedCitation(cit)}
      />
    </div>
  );
}
