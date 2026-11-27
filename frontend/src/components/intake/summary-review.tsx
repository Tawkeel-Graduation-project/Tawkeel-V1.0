"use client";

import { useId, useMemo, useState } from "react";
import { CheckCircle2, ClipboardCheck, Pencil, ShieldCheck } from "lucide-react";
import {
  approveIntakeSummary,
  getIntake,
  IntakeError,
  normalizeSummaryValue,
  SUMMARY_MAX_LENGTH,
  summaryValues,
  updateIntakeSummary,
  type Intake,
  type IntakeSummaryValues,
} from "@/lib/intake/api";
import { intakeErrorCopy } from "@/lib/intake/copy";
import {
  ALL_FIELDS,
  FIELD_LABELS,
  NICHE_LABELS,
  OPTIONAL_FIELDS,
  URGENCY_LABELS,
  displayValue,
  type IntakeFieldKey,
} from "@/lib/intake/fields";
import { Alert, Badge, Button, Card, CardBody, CardHeader, TextArea, TextField } from "@/components/ui";
import { cn } from "@/lib/cn";

interface SummaryReviewProps {
  intake: Intake;
  token: string | null;
  onChange: (intake: Intake) => void;
}

/** Fields edited with a dropdown (fixed keys) instead of free text. */
const SELECT_OPTIONS: Partial<Record<IntakeFieldKey, Record<string, string>>> = {
  niche: NICHE_LABELS,
  urgency: URGENCY_LABELS,
};

/** Fields that get a multi-line box when editing. */
const LONG_FIELDS: IntakeFieldKey[] = ["facts", "parties", "key_dates", "documents", "deadlines"];

const NOT_PROVIDED = "غير مذكور";

/**
 * SCRUM-341: the client reviews the summary the intake agent built, edits any
 * field, and explicitly approves it. Nothing reaches a lawyer before approval
 * (enforced on the server by SCRUM-342/343; this screen only asks for it).
 *
 * Rules:
 * - Values the client did not give are shown as "غير مذكور", never guessed.
 * - Approval sends the exact values shown, so it is disabled while editing.
 * - Once approved, the summary is read-only here.
 *
 * Mount with a `key` that changes when the saved summary changes, so the
 * draft resets to the server's values without an effect.
 */
export function SummaryReview({ intake, token, onChange }: SummaryReviewProps) {
  const saved = useMemo(() => summaryValues(intake), [intake]);
  const approved = intake.approvedAt !== null;

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<IntakeSummaryValues>(saved);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState<"save" | "approve" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const confirmId = useId();

  const changed = ALL_FIELDS.filter((f) => normalizeSummaryValue(draft[f]) !== saved[f]);
  const tooLong = ALL_FIELDS.filter((f) => (draft[f] ?? "").trim().length > SUMMARY_MAX_LENGTH[f]);

  async function handleFailure(err: unknown) {
    const code = err instanceof IntakeError ? err.code : "unknown";
    setError(intakeErrorCopy[code]);
    if (code === "conflict") {
      // Someone (or another tab) changed it: show the latest saved version.
      try {
        onChange(await getIntake(intake.id, token));
      } catch {
        /* keep the current view */
      }
    }
  }

  async function save() {
    if (changed.length === 0) {
      setEditing(false);
      return;
    }
    setBusy("save");
    setError(null);
    try {
      const patch = Object.fromEntries(changed.map((f) => [f, normalizeSummaryValue(draft[f])]));
      onChange(await updateIntakeSummary(intake.id, patch, token));
      setEditing(false);
      setConfirmed(false); // approving again is about the new version
    } catch (err) {
      await handleFailure(err);
    } finally {
      setBusy(null);
    }
  }

  function cancel() {
    setDraft(saved);
    setEditing(false);
    setError(null);
  }

  async function approve() {
    setBusy("approve");
    setError(null);
    try {
      onChange(await approveIntakeSummary(intake.id, saved, token));
    } catch (err) {
      await handleFailure(err);
    } finally {
      setBusy(null);
    }
  }

  const canApprove = !approved && !editing && confirmed && busy === null;

  return (
    <Card id="summary-review" className="mt-4" data-approved={approved || undefined}>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <ClipboardCheck aria-hidden className="size-4 text-vivid" />
            ملخص طلبك
          </span>
        }
        description={
          approved
            ? "هذا هو الملخص الذي وافقت عليه."
            : "راجع ما سيراه المحامي عنك. يمكنك تعديل أي معلومة قبل الموافقة."
        }
        action={
          approved ? (
            <Badge tone="success">
              <CheckCircle2 aria-hidden className="size-3" />
              تمت الموافقة
            </Badge>
          ) : !editing ? (
            <Button
              size="sm"
              variant="secondary"
              icon={<Pencil aria-hidden className="size-3.5" />}
              onClick={() => {
                setDraft(saved);
                setEditing(true);
              }}
            >
              تعديل
            </Button>
          ) : null
        }
      />

      <CardBody className="space-y-4">
        {editing ? (
          <div className="grid gap-4 sm:grid-cols-2">
            {ALL_FIELDS.map((f) => (
              <div key={f} className={cn(LONG_FIELDS.includes(f) && "sm:col-span-2")}>
                <FieldEditor
                  field={f}
                  value={draft[f] ?? ""}
                  onChange={(value) => setDraft((d) => ({ ...d, [f]: value }))}
                  disabled={busy !== null}
                />
              </div>
            ))}
          </div>
        ) : (
          <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
            {ALL_FIELDS.map((f) => (
              <div key={f} data-field={f} className={cn("min-w-0", LONG_FIELDS.includes(f) && "sm:col-span-2")}>
                <dt className="text-xs font-semibold text-muted">
                  {FIELD_LABELS[f]}
                  {OPTIONAL_FIELDS.includes(f) ? <span className="ms-1 font-normal">(اختياري)</span> : null}
                </dt>
                <dd
                  className={cn(
                    "mt-0.5 whitespace-pre-wrap break-words text-sm leading-relaxed",
                    saved[f] === null ? "italic text-muted" : "text-foreground",
                  )}
                >
                  {saved[f] === null ? NOT_PROVIDED : displayValue(f, saved[f])}
                </dd>
              </div>
            ))}
          </dl>
        )}

        {error ? (
          <Alert tone="danger" title="لم تكتمل العملية">
            {error}
          </Alert>
        ) : null}

        {editing ? (
          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border pt-4">
            <Button variant="ghost" onClick={cancel} disabled={busy !== null}>
              إلغاء
            </Button>
            <Button onClick={() => void save()} loading={busy === "save"} disabled={tooLong.length > 0}>
              حفظ التعديلات
            </Button>
          </div>
        ) : approved ? (
          <Alert tone="success" title="تمت الموافقة على الملخص">
            لن يطّلع أي محامٍ إلا على هذا الملخص كما وافقت عليه. الخطوة التالية:{" "}
            <a href="#lawyer-selection" className="font-semibold text-primary underline underline-offset-2">
              اختيار المحامي
            </a>
            .
          </Alert>
        ) : (
          <div className="space-y-3 border-t border-border pt-4">
            <label htmlFor={confirmId} className="flex cursor-pointer items-start gap-2.5 text-sm">
              <input
                id={confirmId}
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
                className="mt-0.5 size-4 shrink-0 accent-primary"
              />
              <span>
                راجعت الملخص، وأوافق على مشاركته مع المحامي الذي سأختاره.
                <span className="block text-xs text-muted">
                  لن يُرسل أي شيء إلى محامٍ قبل موافقتك، وتُسجَّل موافقتك.
                </span>
              </span>
            </label>
            <div className="flex justify-end">
              <Button
                onClick={() => void approve()}
                loading={busy === "approve"}
                disabled={!canApprove}
                icon={<ShieldCheck aria-hidden className="size-4" />}
              >
                الموافقة على الملخص
              </Button>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function FieldEditor({
  field,
  value,
  onChange,
  disabled,
}: {
  field: IntakeFieldKey;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  const label = FIELD_LABELS[field] + (OPTIONAL_FIELDS.includes(field) ? " (اختياري)" : "");
  const max = SUMMARY_MAX_LENGTH[field];
  const over = value.trim().length > max;
  const error = over ? `الحد الأقصى ${max} حرفاً.` : undefined;
  const hint = "اتركه فارغاً إن لم ترغب في ذكره.";
  const options = SELECT_OPTIONS[field];
  const selectId = useId();

  if (options) {
    return (
      <div className="space-y-1.5">
        <label htmlFor={selectId} className="block text-sm font-medium">
          {label}
        </label>
        <select
          id={selectId}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-ring/40 disabled:opacity-60"
        >
          <option value="">{NOT_PROVIDED}</option>
          {Object.entries(options).map(([key, text]) => (
            <option key={key} value={key}>
              {text}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return LONG_FIELDS.includes(field) ? (
    <TextArea
      label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      error={error}
      hint={hint}
      placeholder={NOT_PROVIDED}
    />
  ) : (
    <TextField
      label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      error={error}
      hint={hint}
      placeholder={NOT_PROVIDED}
    />
  );
}
