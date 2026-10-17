import Link from "next/link";
import { cn } from "@/lib/cn";
import { Spinner } from "./spinner";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition " +
  "disabled:pointer-events-none disabled:opacity-50 whitespace-nowrap select-none";

const variants: Record<Variant, string> = {
  primary: "bg-primary text-primary-foreground shadow-sm shadow-primary/30 hover:bg-primary-hover hover:shadow-md hover:shadow-primary/30",
  secondary: "border border-border bg-surface text-foreground hover:border-vivid/50 hover:bg-primary-soft/50",
  ghost: "text-foreground hover:bg-surface-muted",
  danger: "bg-danger text-white hover:opacity-90",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-base",
};

interface CommonProps {
  variant?: Variant;
  size?: Size;
  /** Icon placed before the label (on the right in RTL). */
  icon?: React.ReactNode;
}

export function buttonClasses({ variant = "primary", size = "md" }: CommonProps = {}) {
  return cn(base, variants[variant], sizes[size]);
}

export function Button({
  variant,
  size,
  icon,
  loading = false,
  className,
  children,
  disabled,
  type = "button",
  ...props
}: CommonProps & React.ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean }) {
  return (
    <button
      type={type}
      className={cn(buttonClasses({ variant, size }), className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <Spinner size="sm" label="" /> : icon}
      {children}
    </button>
  );
}

export function ButtonLink({
  variant,
  size,
  icon,
  className,
  children,
  ...props
}: CommonProps & React.ComponentProps<typeof Link>) {
  return (
    <Link className={cn(buttonClasses({ variant, size }), className)} {...props}>
      {icon}
      {children}
    </Link>
  );
}
