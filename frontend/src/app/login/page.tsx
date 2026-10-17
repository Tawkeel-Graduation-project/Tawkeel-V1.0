"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { LogIn } from "lucide-react";
import { Alert, Button, PasswordField, TextField } from "@/components/ui";
import { AuthLayout } from "@/components/auth/auth-layout";
import { MOCK_AUTH_ENABLED } from "@/components/shell/role-switcher";
import { AuthError, login, MOCK_DEMO_PASSWORD } from "@/lib/auth/api";
import { consumeSessionExpired, useAuth } from "@/lib/auth/auth-context";
import { isEgyptianMobile, isEmail, normalizeDigits } from "@/lib/auth/validation";

const IS_MOCK_API = !process.env.NEXT_PUBLIC_API_URL;

interface Errors {
  identifier?: string;
  password?: string;
}

export default function LoginPage() {
  const { startSession } = useAuth();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    // Read once on mount: sessionStorage is not available during server render.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (consumeSessionExpired()) setExpired(true);
  }, []);

  function validate(): Errors {
    const e: Errors = {};
    const id = identifier.trim();
    if (!id) e.identifier = "أدخل البريد الإلكتروني أو رقم الهاتف.";
    else if (!isEmail(id) && !isEgyptianMobile(id)) e.identifier = "أدخل بريدًا إلكترونيًا أو رقم هاتف مصري صحيحًا.";
    if (!password) e.password = "أدخل كلمة المرور.";
    return e;
  }

  async function onSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    setFormError(null);
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length) return;

    const id = identifier.trim();
    setSubmitting(true);
    try {
      const session = await login({ identifier: isEmail(id) ? id : normalizeDigits(id), password });
      startSession(session); // AuthLayout redirects to the role's home
    } catch (err) {
      const code = err instanceof AuthError ? err.code : "unknown";
      setFormError(
        code === "invalid_credentials"
          ? "البريد الإلكتروني أو رقم الهاتف أو كلمة المرور غير صحيحة."
          : code === "network"
            ? "تعذّر الاتصال بالخادم. تحقّق من اتصالك وحاول مرة أخرى."
            : "حدث خطأ غير متوقع. حاول مرة أخرى.",
      );
      setPassword("");
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="تسجيل الدخول"
      description="ادخل إلى حسابك لمتابعة طلباتك وقضاياك."
      footer={
        <>
          ليس لديك حساب؟{" "}
          <Link href="/register" className="font-semibold text-primary hover:underline">
            إنشاء حساب جديد
          </Link>
        </>
      }
    >
      <form noValidate onSubmit={onSubmit} className="space-y-4">
        {expired ? (
          <Alert tone="warning" title="انتهت الجلسة">
            انتهت صلاحية جلستك لحماية حسابك. سجّل الدخول مرة أخرى.
          </Alert>
        ) : null}
        {formError ? <Alert tone="danger">{formError}</Alert> : null}

        <TextField
          label="البريد الإلكتروني أو رقم الهاتف"
          name="identifier"
          autoComplete="username"
          inputMode="email"
          dir="ltr"
          className="text-right"
          placeholder="name@example.com"
          required
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          error={errors.identifier}
        />
        <PasswordField
          label="كلمة المرور"
          name="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
        />

        <Button
          type="submit"
          size="lg"
          className="w-full"
          loading={submitting}
          icon={<LogIn aria-hidden className="size-5 rtl:-scale-x-100" />}
        >
          {submitting ? "جارٍ تسجيل الدخول…" : "تسجيل الدخول"}
        </Button>
      </form>

      {IS_MOCK_API && MOCK_AUTH_ENABLED ? (
        <Alert tone="info" title="وضع تجريبي" className="mt-6">
          الخادم غير متصل بعد. جرّب <span dir="ltr">client@example.com</span> أو{" "}
          <span dir="ltr">lawyer@example.com</span> بكلمة المرور <span dir="ltr">{MOCK_DEMO_PASSWORD}</span>، أو أنشئ
          حسابًا جديدًا.
        </Alert>
      ) : null}
    </AuthLayout>
  );
}
