"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Card, LoadingState } from "@/components/ui";
import { Brand } from "@/components/shell/brand";
import { useAuth } from "@/lib/auth/auth-context";
import { roleHome } from "@/lib/auth/types";

/**
 * Frame shared by the login and register screens. Signed-in users are sent
 * straight to their role's home.
 */
export function AuthLayout({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  const { user, status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated" && user) router.replace(roleHome[user.role]);
  }, [status, user, router]);

  if (status !== "unauthenticated") {
    return (
      <main className="grid min-h-screen place-items-center">
        <LoadingState label={status === "loading" ? undefined : "جارٍ التحويل…"} />
      </main>
    );
  }

  return (
    <main className="relative grid min-h-screen place-items-center overflow-hidden px-4 py-12">
      {/* Warm background glows */}
      <div aria-hidden className="pointer-events-none absolute -top-32 -start-32 size-[28rem] rounded-full bg-vivid/25 blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute -bottom-40 -end-24 size-[26rem] rounded-full bg-vivid-2/25 blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-linear-to-l from-vivid-2 via-vivid to-primary" />
      <div className="relative w-full max-w-lg">
        <Brand className="mb-8 justify-center" subtitle="مساعدك القانوني الذكي" />
        <Card className="p-6 shadow-xl shadow-vivid/10 sm:p-8">
          <h1 className="text-xl font-bold">{title}</h1>
          {description ? <p className="mt-1 text-sm text-muted">{description}</p> : null}
          <div className="mt-6">{children}</div>
        </Card>
        {footer ? <div className="mt-6 text-center text-sm text-muted">{footer}</div> : null}
      </div>
    </main>
  );
}
