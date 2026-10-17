"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { LoadingState } from "@/components/ui";
import { useAuth } from "@/lib/auth/auth-context";
import { roleHome, type Role } from "@/lib/auth/types";

/**
 * Keeps each role inside its own area:
 *  - not signed in      -> /login
 *  - wrong role's area  -> own role's home
 * UX only; the backend must still reject unauthorized requests (PRD §10).
 */
export function RoleGuard({ role, children }: { role: Role; children: React.ReactNode }) {
  const { user, status } = useAuth();
  const router = useRouter();
  const allowed = status === "authenticated" && user?.role === role;

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
    else if (status === "authenticated" && user && user.role !== role) router.replace(roleHome[user.role]);
  }, [status, user, role, router]);

  if (!allowed) {
    return (
      <div className="grid min-h-screen place-items-center">
        <LoadingState label={status === "loading" ? "جارٍ التحقق من الجلسة…" : "جارٍ التحويل…"} />
      </div>
    );
  }
  return <>{children}</>;
}
