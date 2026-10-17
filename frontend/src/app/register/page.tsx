"use client";

import { useState } from "react";
import Link from "next/link";
import { Briefcase, Check, UserPlus, UserRound } from "lucide-react";
import { Alert, Button, PasswordField, TextField } from "@/components/ui";
import { AuthLayout } from "@/components/auth/auth-layout";
import { cn } from "@/lib/cn";
import { AuthError, register } from "@/lib/auth/api";
import { useAuth } from "@/lib/auth/auth-context";
import type { Role } from "@/lib/auth/types";
import { isEgyptianMobile, isEmail, normalizeDigits, PASSWORD_MIN, passwordError } from "@/lib/auth/validation";

const roleChoices: { role: Role; title: string; text: string; icon: React.ElementType }[] = [
  { role: "client", title: "عميل", text: "أبحث عن إجابة قانونية أو محامٍ مناسب.", icon: UserRound },
  { role: "lawyer", title: "محامٍ", text: "أستقبل الطلبات وأُدير القضايا.", icon: Briefcase },
];

type Field = "role" | "name" | "email" | "phone" | "password" | "confirm" | "terms" | "privacy";
type Errors = Partial<Record<Field, string>>;

export default function RegisterPage() {
  const { startSession } = useAuth();
  const [role, setRole] = useState<Role | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  // PRD: explicit, unticked, and the privacy consent is not bundled with the terms.
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [acceptPrivacy, setAcceptPrivacy] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function validate(): Errors {
    const e: Errors = {};
    if (!role) e.role = "اختر نوع الحساب.";
    if (name.trim().length < 3) e.name = "أدخل الاسم الكامل.";
    if (!email.trim()) e.email = "أدخل البريد الإلكتروني.";
    else if (!isEmail(email)) e.email = "صيغة البريد الإلكتروني غير صحيحة.";
    if (phone.trim() && !isEgyptianMobile(phone)) e.phone = "أدخل رقم هاتف مصري صحيحًا، مثل 01012345678.";
    e.password = passwordError(password);
    if (!confirm) e.confirm = "أعد إدخال كلمة المرور.";
    else if (confirm !== password) e.confirm = "كلمتا المرور غير متطابقتين.";
    if (!acceptTerms) e.terms = "يجب الموافقة على شروط الاستخدام.";
    if (!acceptPrivacy) e.privacy = "يجب الموافقة على إشعار الخصوصية.";
    return Object.fromEntries(Object.entries(e).filter(([, v]) => v)) as Errors;
  }

  async function onSubmit(ev: React.FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    setFormError(null);
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length) {
      // Move focus to the first invalid control.
      ev.currentTarget.querySelector<HTMLElement>("input[aria-invalid='true'], input[data-invalid]")?.focus();
      return;
    }

    setSubmitting(true);
    try {
      const session = await register({
        role: role!,
        name: name.trim(),
        email: email.trim().toLowerCase(),
        phone: phone.trim() ? normalizeDigits(phone) : undefined,
        password,
      });
      startSession(session); // AuthLayout redirects to the role's home
    } catch (err) {
      const code = err instanceof AuthError ? err.code : "unknown";
      if (code === "email_taken") {
        setErrors({ email: "هذا البريد الإلكتروني مسجّل بالفعل." });
        setFormError("يوجد حساب بهذا البريد الإلكتروني. سجّل الدخول بدلًا من ذلك.");
      } else {
        setFormError(
          code === "network"
            ? "تعذّر الاتصال بالخادم. تحقّق من اتصالك وحاول مرة أخرى."
            : "حدث خطأ غير متوقع. حاول مرة أخرى.",
        );
      }
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="إنشاء حساب"
      description="أنشئ حسابك في توكيل خلال دقيقة."
      footer={
        <>
          لديك حساب بالفعل؟{" "}
          <Link href="/login" className="font-semibold text-primary hover:underline">
            تسجيل الدخول
          </Link>
        </>
      }
    >
      <form noValidate onSubmit={onSubmit} className="space-y-4">
        {formError ? <Alert tone="danger">{formError}</Alert> : null}

        <fieldset>
          <legend className="mb-1.5 block text-sm font-medium">
            نوع الحساب<span className="ms-1 text-danger" aria-hidden>*</span>
          </legend>
          <div className="grid gap-3 sm:grid-cols-2">
            {roleChoices.map(({ role: r, title, text, icon: Icon }) => {
              const selected = role === r;
              return (
                <label
                  key={r}
                  className={cn(
                    "relative flex cursor-pointer items-start gap-3 rounded-2xl border p-4 transition",
                    "has-focus-visible:ring-2 has-focus-visible:ring-ring/40",
                    selected
                      ? "border-primary bg-primary-soft/60"
                      : errors.role
                        ? "border-danger hover:border-vivid/60"
                        : "border-border hover:border-vivid/60 hover:bg-primary-soft/40",
                  )}
                >
                  <input
                    type="radio"
                    name="role"
                    value={r}
                    checked={selected}
                    onChange={() => setRole(r)}
                    data-invalid={errors.role ? true : undefined}
                    className="sr-only"
                  />
                  <span
                    className={cn(
                      "flex size-10 shrink-0 items-center justify-center rounded-xl transition",
                      selected
                        ? "bg-linear-to-br from-vivid-2 to-vivid text-white"
                        : "bg-primary-soft text-primary",
                    )}
                  >
                    <Icon aria-hidden className="size-5" />
                  </span>
                  <span className="min-w-0">
                    <span className="block font-semibold">{title}</span>
                    <span className="block text-xs text-muted">{text}</span>
                  </span>
                  {selected ? (
                    <Check aria-hidden className="absolute top-3 end-3 size-4 text-primary" />
                  ) : null}
                </label>
              );
            })}
          </div>
          {errors.role ? <p className="mt-1.5 text-xs text-danger">{errors.role}</p> : null}
        </fieldset>

        <TextField
          label="الاسم الكامل"
          name="name"
          autoComplete="name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={errors.name}
        />
        <TextField
          label="البريد الإلكتروني"
          name="email"
          type="email"
          autoComplete="email"
          dir="ltr"
          className="text-right"
          placeholder="name@example.com"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
        />
        <TextField
          label="رقم الهاتف"
          name="phone"
          type="tel"
          autoComplete="tel"
          inputMode="tel"
          dir="ltr"
          className="text-right"
          placeholder="01012345678"
          hint="اختياري. يمكنك تسجيل الدخول به لاحقًا."
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          error={errors.phone}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <PasswordField
            label="كلمة المرور"
            name="password"
            autoComplete="new-password"
            required
            hint={`${PASSWORD_MIN} أحرف على الأقل، حروف وأرقام.`}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={errors.password}
          />
          <PasswordField
            label="تأكيد كلمة المرور"
            name="confirm"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            error={errors.confirm}
          />
        </div>

        <div className="space-y-3 rounded-xl border border-border bg-surface-muted/50 p-4">
          <Consent checked={acceptTerms} onChange={setAcceptTerms} error={errors.terms}>
            قرأت <span className="font-semibold text-foreground">شروط الاستخدام</span> وأوافق عليها.
          </Consent>
          <Consent checked={acceptPrivacy} onChange={setAcceptPrivacy} error={errors.privacy}>
            أوافق على معالجة بياناتي كما هو موضّح في{" "}
            <span className="font-semibold text-foreground">إشعار الخصوصية</span> (ما يُخزَّن، ومن يطّلع عليه، وأين
            يُعالَج).
          </Consent>
        </div>

        <Button
          type="submit"
          size="lg"
          className="w-full"
          loading={submitting}
          icon={<UserPlus aria-hidden className="size-5" />}
        >
          {submitting ? "جارٍ إنشاء الحساب…" : "إنشاء الحساب"}
        </Button>
      </form>
    </AuthLayout>
  );
}

function Consent({
  checked,
  onChange,
  error,
  children,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="flex cursor-pointer items-start gap-2.5 text-sm text-muted">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          aria-invalid={error ? true : undefined}
          className="mt-0.5 size-4 shrink-0 accent-primary"
        />
        <span>{children}</span>
      </label>
      {error ? <p className="ms-6.5 mt-1 text-xs text-danger">{error}</p> : null}
    </div>
  );
}
