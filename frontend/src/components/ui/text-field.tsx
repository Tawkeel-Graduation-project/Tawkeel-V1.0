"use client";

import { useId, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/cn";

const inputBase =
  "w-full rounded-lg border bg-surface px-3 text-sm text-foreground placeholder:text-muted/70 " +
  "transition-colors focus:outline-none focus:ring-2 focus:ring-ring/40 disabled:opacity-60";

interface FieldProps {
  label: string;
  hint?: string;
  error?: string;
}

function FieldShell({
  id,
  label,
  hint,
  error,
  required,
  children,
}: FieldProps & { id: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
        {required ? <span className="ms-1 text-danger" aria-hidden>*</span> : null}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-xs text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function TextField({
  label,
  hint,
  error,
  className,
  id: idProp,
  ...props
}: FieldProps & React.InputHTMLAttributes<HTMLInputElement>) {
  const autoId = useId();
  const id = idProp ?? autoId;
  return (
    <FieldShell id={id} label={label} hint={hint} error={error} required={props.required}>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        className={cn(inputBase, "h-10", error ? "border-danger" : "border-border", className)}
        {...props}
      />
    </FieldShell>
  );
}

export function TextArea({
  label,
  hint,
  error,
  className,
  id: idProp,
  ...props
}: FieldProps & React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const autoId = useId();
  const id = idProp ?? autoId;
  return (
    <FieldShell id={id} label={label} hint={hint} error={error} required={props.required}>
      <textarea
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        className={cn(inputBase, "min-h-24 py-2", error ? "border-danger" : "border-border", className)}
        {...props}
      />
    </FieldShell>
  );
}

/** Password input with a show/hide toggle. The value is typed LTR; the toggle sits at the end (left in RTL). */
export function PasswordField({
  label,
  hint,
  error,
  className,
  id: idProp,
  ...props
}: FieldProps & Omit<React.InputHTMLAttributes<HTMLInputElement>, "type">) {
  const autoId = useId();
  const id = idProp ?? autoId;
  const [visible, setVisible] = useState(false);
  return (
    <FieldShell id={id} label={label} hint={hint} error={error} required={props.required}>
      <div className="relative">
        <input
          id={id}
          type={visible ? "text" : "password"}
          dir="ltr"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
          className={cn(inputBase, "h-10 pl-10 text-right", error ? "border-danger" : "border-border", className)}
          {...props}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "إخفاء كلمة المرور" : "إظهار كلمة المرور"}
          aria-pressed={visible}
          aria-controls={id}
          className="absolute inset-y-0 end-0 flex w-10 items-center justify-center rounded-e-lg text-muted hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        >
          {visible ? <EyeOff aria-hidden className="size-4" /> : <Eye aria-hidden className="size-4" />}
        </button>
      </div>
    </FieldShell>
  );
}
