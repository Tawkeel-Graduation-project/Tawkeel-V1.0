import { cn } from "@/lib/cn";

/**
 * Orange gradient banner for role home pages.
 * The gradient starts dark on the start (right) side, where the text sits,
 * so white text keeps AA contrast; it brightens towards the decorative end.
 */
export function Hero({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "relative mb-6 overflow-hidden rounded-3xl bg-linear-to-l from-[#9a3412] via-[#c2410c] to-vivid p-6 text-white shadow-lg shadow-vivid/25 sm:p-8",
        className,
      )}
    >
      {/* Decorative glows on the end (left) side */}
      <div aria-hidden className="pointer-events-none absolute -end-16 -top-20 size-64 rounded-full bg-vivid-2/40 blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute -bottom-24 end-24 size-56 rounded-full bg-white/15 blur-2xl" />

      <div className="relative max-w-2xl">
        {eyebrow ? (
          <span className="mb-3 inline-flex rounded-full bg-white/15 px-3 py-1 text-xs font-medium ring-1 ring-white/25">
            {eyebrow}
          </span>
        ) : null}
        <h1 className="text-2xl font-bold sm:text-3xl">{title}</h1>
        {description ? <p className="mt-2 text-sm text-white/90 sm:text-base">{description}</p> : null}
        {actions ? <div className="mt-5 flex flex-wrap gap-3">{actions}</div> : null}
      </div>
    </section>
  );
}

/** White button for use on the orange hero. */
export const heroButton =
  "inline-flex h-10 items-center gap-2 rounded-lg bg-white px-4 text-sm font-semibold text-[#9a3412] shadow-sm transition hover:bg-orange-50";
export const heroGhostButton =
  "inline-flex h-10 items-center gap-2 rounded-lg px-4 text-sm font-semibold text-white ring-1 ring-white/40 transition hover:bg-white/10";
