"use client";

/**
 * Standardized loading / error / empty states.
 * Every screen should use these (directly or via <AsyncView/>) rather than
 * inventing its own, so users see the same patterns everywhere.
 */
import { AlertOctagon, Inbox, RotateCcw, WifiOff, Lock, SearchX } from "lucide-react";
import { cn } from "@/lib/cn";
import { errorCopy, getErrorKind, type AppErrorKind } from "@/lib/errors";
import { Button } from "./button";
import { Skeleton } from "./skeleton";
import { Spinner } from "./spinner";

function StateFrame({
  icon,
  title,
  description,
  action,
  tone = "neutral",
  className,
  role,
}: {
  icon: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  tone?: "neutral" | "danger";
  className?: string;
  role?: "alert" | "status";
}) {
  return (
    <div
      role={role}
      className={cn("flex flex-col items-center justify-center px-6 py-14 text-center", className)}
    >
      <div
        className={cn(
          "mb-4 flex size-12 items-center justify-center rounded-full",
          tone === "danger" ? "bg-danger-soft text-danger" : "bg-primary-soft text-primary",
        )}
      >
        {icon}
      </div>
      <h3 className="text-base font-semibold">{title}</h3>
      {description ? <p className="mt-1 max-w-md text-sm text-muted">{description}</p> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

/** Centered spinner with a label. Use for short waits or whole-page loads. */
export function LoadingState({ label = "جارٍ التحميل…", className }: { label?: string; className?: string }) {
  return (
    <div role="status" className={cn("flex flex-col items-center justify-center gap-3 py-14 text-muted", className)}>
      <Spinner size="lg" label="" className="text-vivid" />
      <p className="text-sm">{label}</p>
    </div>
  );
}

/** Skeleton that mimics a typical page: header + list of cards. */
export function PageSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div role="status" aria-label="جارٍ التحميل…" className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-4 w-72 max-w-full" />
      </div>
      <div className="space-y-3">
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="rounded-2xl border border-border bg-surface p-5">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="mt-3 h-3 w-5/6" />
            <Skeleton className="mt-2 h-3 w-2/3" />
          </div>
        ))}
      </div>
    </div>
  );
}

const errorIcons: Record<AppErrorKind, React.ElementType> = {
  network: WifiOff,
  unauthorized: Lock,
  forbidden: Lock,
  not_found: SearchX,
  validation: AlertOctagon,
  server: AlertOctagon,
  unknown: AlertOctagon,
};

/**
 * Error state. Pass the thrown `error` and the message is picked from the
 * standard Arabic copy (see lib/errors.ts); override with title/description.
 */
export function ErrorState({
  error,
  title,
  description,
  onRetry,
  className,
}: {
  error?: unknown;
  title?: string;
  description?: string;
  onRetry?: () => void;
  className?: string;
}) {
  const kind = getErrorKind(error);
  const copy = errorCopy[kind];
  const Icon = errorIcons[kind];
  return (
    <StateFrame
      role="alert"
      tone="danger"
      icon={<Icon aria-hidden className="size-6" />}
      title={title ?? copy.title}
      description={description ?? copy.description}
      className={className}
      action={
        onRetry ? (
          <Button variant="secondary" icon={<RotateCcw aria-hidden className="size-4" />} onClick={onRetry}>
            إعادة المحاولة
          </Button>
        ) : null
      }
    />
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <StateFrame
      icon={icon ?? <Inbox aria-hidden className="size-6" />}
      title={title}
      description={description}
      action={action}
      className={className}
    />
  );
}

export type AsyncStatus = "loading" | "error" | "success";

/**
 * Renders the right standard state for async data:
 *   <AsyncView status={status} error={error} onRetry={refetch}
 *              isEmpty={items.length === 0} empty={{ title: "لا توجد طلبات" }}>
 *     {list}
 *   </AsyncView>
 */
export function AsyncView({
  status,
  error,
  onRetry,
  isEmpty = false,
  empty,
  loading,
  children,
}: {
  status: AsyncStatus;
  error?: unknown;
  onRetry?: () => void;
  isEmpty?: boolean;
  empty?: React.ComponentProps<typeof EmptyState>;
  /** Custom loading UI (e.g. a skeleton). Defaults to <LoadingState/>. */
  loading?: React.ReactNode;
  children: React.ReactNode;
}) {
  if (status === "loading") return <>{loading ?? <LoadingState />}</>;
  if (status === "error") return <ErrorState error={error} onRetry={onRetry} />;
  if (isEmpty && empty) return <EmptyState {...empty} />;
  return <>{children}</>;
}
