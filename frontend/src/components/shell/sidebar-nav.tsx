"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import type { Role } from "@/lib/auth/types";
import { isActive, navigation } from "@/lib/navigation";

export function SidebarNav({ role, onNavigate }: { role: Role; onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <nav aria-label="القائمة الرئيسية" className="space-y-6">
      {navigation[role].map((section, i) => (
        <div key={section.title ?? i}>
          {section.title ? (
            <p className="mb-2 px-3 text-xs font-semibold text-sidebar-muted">{section.title}</p>
          ) : null}
          <ul className="space-y-1">
            {section.items.map((item) => {
              const active = isActive(pathname, item.href, role);
              const Icon = item.icon;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                      active
                        ? "bg-linear-to-l from-primary to-vivid font-semibold text-primary-foreground shadow-md shadow-black/20"
                        : "text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground",
                    )}
                  >
                    <Icon aria-hidden className="size-[18px] shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
