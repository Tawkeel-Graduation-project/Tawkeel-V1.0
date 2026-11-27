"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Bot, CheckCircle2, Circle, CircleSlash, User } from "lucide-react";
import type { ChatStatus } from "@/lib/chat/types";
import { getIntake, IntakeError, takeIntakeTurn, type Intake } from "@/lib/intake/api";
import { intakeErrorCopy } from "@/lib/intake/copy";
import {
  ALL_FIELDS,
  FIELD_LABELS,
  OPTIONAL_FIELDS,
  displayValue,
  type IntakeFieldKey,
} from "@/lib/intake/fields";
import { ChatInput } from "@/components/chat/chat-input";
import { Button, Card, CardBody, CardHeader, Spinner } from "@/components/ui";
import { cn } from "@/lib/cn";

interface IntakeChatProps {
  intake: Intake;
  token: string | null;
  onChange: (intake: Intake) => void;
}

/** The intake agent conversation + what has been collected so far (SCRUM-248). */
export function IntakeChat({ intake, token, onChange }: IntakeChatProps) {
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFailed, setLastFailed] = useState<string | null | undefined>(undefined);
  const openedRef = useRef(false);
  const endRef = useRef<HTMLDivElement>(null);

  const send = useCallback(
    async (content: string | null) => {
      setSending(true);
      setError(null);
      try {
        onChange(await takeIntakeTurn(intake.id, content, token));
        setLastFailed(undefined);
        if (content !== null) setInput("");
      } catch (err) {
        const code = err instanceof IntakeError ? err.code : "unknown";
        setError(intakeErrorCopy[code]);
        if (code === "conflict") {
          try {
            onChange(await getIntake(intake.id, token));
          } catch {
            /* keep the current view */
          }
        } else {
          setLastFailed(content);
        }
      } finally {
        setSending(false);
      }
    },
    [intake.id, token, onChange],
  );

  // Open the intake once: the agent pre-fills from the chat and asks first.
  useEffect(() => {
    if (openedRef.current || intake.turns.length > 0 || intake.complete) return;
    openedRef.current = true;
    void send(null);
  }, [intake.turns.length, intake.complete, send]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [intake.turns.length, sending]);

  const currentField = intake.complete
    ? null
    : ([...intake.turns].reverse().find((t) => t.role === "agent")?.field ?? null);
  const status: ChatStatus = sending ? "loading" : "idle";

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_17rem]">
      <Card className="flex min-h-[26rem] flex-col">
        <CardHeader
          title={
            <span className="inline-flex items-center gap-2">
              <Bot aria-hidden className="size-4 text-vivid" />
              وكيل جمع المعلومات
            </span>
          }
          description="أجب باختصار، ويمكنك قول «لا أعرف» لأي سؤال."
        />
        <CardBody className="flex flex-1 flex-col gap-3">
          <ol className="flex-1 space-y-3" aria-live="polite" aria-label="محادثة جمع المعلومات">
            {intake.turns.map((turn, idx) => (
              <li
                key={idx}
                className={cn("flex items-start gap-2.5", turn.role === "client" && "flex-row-reverse")}
              >
                <span
                  className={cn(
                    "flex size-7 shrink-0 items-center justify-center rounded-full text-white",
                    turn.role === "agent" ? "bg-linear-to-br from-vivid-2 via-vivid to-primary" : "bg-secondary",
                  )}
                >
                  {turn.role === "agent" ? (
                    <Bot aria-hidden className="size-3.5" />
                  ) : (
                    <User aria-hidden className="size-3.5" />
                  )}
                </span>
                <p
                  className={cn(
                    "max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm leading-relaxed",
                    turn.role === "agent"
                      ? "rounded-tr-xs border border-border bg-surface text-foreground"
                      : "rounded-tl-xs bg-primary text-primary-foreground",
                  )}
                >
                  {turn.content}
                </p>
              </li>
            ))}
            {sending ? (
              <li className="flex items-center gap-2 text-xs text-muted">
                <Spinner size="sm" label="" />
                {intake.turns.length === 0 ? "جارٍ تجهيز الأسئلة…" : "جارٍ قراءة إجابتك…"}
              </li>
            ) : null}
            <div ref={endRef} />
          </ol>

          {error ? (
            <div
              role="alert"
              className="flex items-center justify-between gap-3 rounded-xl border border-danger/30 bg-danger-soft p-3 text-xs text-danger"
            >
              <span className="flex items-center gap-2">
                <AlertCircle aria-hidden className="size-4 shrink-0" />
                {error}
              </span>
              {lastFailed !== undefined ? (
                <Button size="sm" variant="danger" onClick={() => void send(lastFailed)}>
                  إعادة المحاولة
                </Button>
              ) : null}
            </div>
          ) : null}

          {intake.complete ? (
            <div
              role="status"
              className="flex items-start gap-2 rounded-xl border border-success/30 bg-success-soft p-3 text-sm text-foreground"
            >
              <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0 text-success" />
              <span>
                اكتملت المعلومات. الخطوة التالية هي{" "}
                <a href="#summary-review" className="font-semibold text-primary underline underline-offset-2">
                  مراجعة ملخص طلبك
                </a>{" "}
                بالأسفل وتعديله قبل الموافقة عليه.
              </span>
            </div>
          ) : (
            <ChatInput
              value={input}
              onChange={setInput}
              onSubmit={() => void send(input.trim())}
              onStop={() => {}}
              status={status}
              disabled={sending || intake.turns.length === 0}
              placeholder="اكتب إجابتك هنا… (Enter للإرسال)"
            />
          )}
        </CardBody>
      </Card>

      <Card className="h-fit">
        <CardHeader title="ما جمعناه حتى الآن" />
        <CardBody className="space-y-1.5 p-4">
          {ALL_FIELDS.map((f) => (
            <FieldRow
              key={f}
              field={f}
              status={intake.fields[f]?.status ?? "missing"}
              value={displayValue(f, intake.fields[f]?.value ?? null)}
              current={f === currentField}
            />
          ))}
        </CardBody>
      </Card>
    </div>
  );
}

function FieldRow({
  field,
  status,
  value,
  current,
}: {
  field: IntakeFieldKey;
  status: "missing" | "provided" | "not_provided";
  value: string | null;
  current: boolean;
}) {
  const optional = OPTIONAL_FIELDS.includes(field);
  return (
    <div
      data-field={field}
      data-status={status}
      className={cn("flex items-start gap-2 rounded-lg px-2 py-1.5 text-xs", current && "bg-primary-soft/60")}
    >
      {status === "provided" ? (
        <CheckCircle2 aria-hidden className="mt-0.5 size-3.5 shrink-0 text-success" />
      ) : status === "not_provided" ? (
        <CircleSlash aria-hidden className="mt-0.5 size-3.5 shrink-0 text-muted" />
      ) : (
        <Circle aria-hidden className={cn("mt-0.5 size-3.5 shrink-0", current ? "text-primary" : "text-border")} />
      )}
      <div className="min-w-0">
        <span className="font-semibold text-foreground">
          {FIELD_LABELS[field]}
          {optional ? <span className="ms-1 font-normal text-muted">(اختياري)</span> : null}
        </span>
        <p className="line-clamp-2 text-muted">
          {status === "provided" ? value : status === "not_provided" ? "غير مذكور" : current ? "نسأل عنه الآن…" : "—"}
        </p>
      </div>
    </div>
  );
}
