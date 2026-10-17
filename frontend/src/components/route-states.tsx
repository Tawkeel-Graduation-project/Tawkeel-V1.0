"use client";

/**
 * Shared implementations for Next.js route files (loading.tsx / error.tsx).
 * Each segment's file just re-exports one of these, so route-level states look
 * identical across the app.
 */
import { useEffect } from "react";
import { ErrorState, PageSkeleton } from "@/components/ui";

export function RouteLoading() {
  return <PageSkeleton />;
}

export function RouteError({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    // TODO: send to logging/audit once the backend endpoint exists.
    console.error(error);
  }, [error]);

  return (
    <div className="rounded-2xl border border-border bg-surface">
      <ErrorState error={error} onRetry={retry} />
    </div>
  );
}
