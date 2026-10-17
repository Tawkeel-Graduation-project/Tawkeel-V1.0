"use client";

/** Entry point: send visitors to their role's home, or to the login screen. */
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { LoadingState } from "@/components/ui";
import { useAuth } from "@/lib/auth/auth-context";
import { roleHome } from "@/lib/auth/types";

export default function IndexPage() {
  const { user, status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated" && user) router.replace(roleHome[user.role]);
    else if (status === "unauthenticated") router.replace("/login");
  }, [status, user, router]);

  return (
    <main className="grid min-h-screen place-items-center">
      <LoadingState />
    </main>
  );
}
