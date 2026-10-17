import { cn } from "@/lib/cn";

/**
 * Wrap icons that imply direction (arrows, chevrons, "next", "back") so they
 * mirror in RTL. Non-directional icons (search, bell, user) must NOT be wrapped.
 *
 *   <DirectionalIcon><ChevronLeft /></DirectionalIcon>
 *
 * Tip: author directional icons in their LTR meaning ("forward" = ChevronRight);
 * this flips them to point left in Arabic.
 */
export function DirectionalIcon({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn("inline-flex rtl:-scale-x-100", className)}>{children}</span>;
}
