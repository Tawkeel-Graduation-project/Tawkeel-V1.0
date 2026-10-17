"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Menu, X } from "lucide-react";
import { Badge, Button } from "@/components/ui";
import { cn } from "@/lib/cn";
import { useAuth } from "@/lib/auth/auth-context";
import { roleLabel, type Role } from "@/lib/auth/types";
import { Brand } from "./brand";
import { RoleGuard } from "./role-guard";
import { SidebarNav } from "./sidebar-nav";

const roleSubtitle: Record<Role, string> = {
  client: "بوابة العملاء",
  lawyer: "مساحة عمل المحامي",
};

/**
 * The one layout every signed-in screen renders inside.
 * Desktop: fixed sidebar on the start (right) edge. Mobile: slide-in drawer.
 */
export function AppShell({ role, children }: { role: Role; children: React.ReactNode }) {
  return (
    <RoleGuard role={role}>
      <ShellFrame role={role}>{children}</ShellFrame>
    </RoleGuard>
  );
}

function ShellFrame({ role, children }: { role: Role; children: React.ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const pathname = usePathname();
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  // Close the drawer whenever the route changes.
  const [lastPath, setLastPath] = useState(pathname);
  if (pathname !== lastPath) {
    setLastPath(pathname);
    setDrawerOpen(false);
  }

  return (
    <div className="flex min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:start-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-4 focus:py-2 focus:shadow"
      >
        تخطَّ إلى المحتوى
      </a>

      {/* Desktop sidebar */}
      <aside className="hidden w-64 shrink-0 bg-sidebar text-sidebar-foreground lg:block">
        <div className="sticky top-0 h-screen">
          <SidebarContent role={role} />
        </div>
      </aside>

      {/* Mobile drawer */}
      <MobileDrawer open={drawerOpen} onClose={closeDrawer}>
        <SidebarContent role={role} onNavigate={closeDrawer} />
      </MobileDrawer>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Brand strip */}
        <div aria-hidden className="h-1 bg-linear-to-l from-vivid-2 via-vivid to-primary" />
        <Topbar role={role} onOpenMenu={() => setDrawerOpen(true)} />
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 focus:outline-none sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}

function SidebarContent({ role, onNavigate }: { role: Role; onNavigate?: () => void }) {
  const { user } = useAuth();
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-sidebar-border px-5 py-4">
        <Brand onDark subtitle={roleSubtitle[role]} />
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-5">
        <SidebarNav role={role} onNavigate={onNavigate} />
      </div>
      {user ? (
        <div className="flex items-center gap-3 border-t border-sidebar-border px-5 py-4">
          <Avatar name={user.name} />
          <div className="min-w-0 leading-tight">
            <p className="truncate text-sm font-medium">{user.name}</p>
            <p className="truncate text-xs text-sidebar-muted" dir="ltr">
              {user.email}
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Topbar({ role, onOpenMenu }: { role: Role; onOpenMenu: () => void }) {
  const { signOut } = useAuth();
  const router = useRouter();

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-border bg-surface/90 px-4 backdrop-blur sm:px-6 lg:px-8">
      <button
        type="button"
        onClick={onOpenMenu}
        className="-ms-2 rounded-lg p-2 text-muted hover:bg-surface-muted lg:hidden"
        aria-label="فتح القائمة"
      >
        <Menu aria-hidden className="size-5" />
      </button>
      <Brand className="lg:hidden" />

      <div className="ms-auto flex items-center gap-2 sm:gap-3">
        <Badge tone={role === "lawyer" ? "primary" : "secondary"}>{roleLabel[role]}</Badge>
        <Button
          variant="ghost"
          size="sm"
          icon={<LogOut aria-hidden className="size-4 rtl:-scale-x-100" />}
          onClick={() => {
            signOut();
            router.replace("/login");
          }}
        >
          <span className="hidden sm:inline">تسجيل الخروج</span>
          <span className="sr-only sm:hidden">تسجيل الخروج</span>
        </Button>
      </div>
    </header>
  );
}

function MobileDrawer({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  return (
    <div className={cn("fixed inset-0 z-40 lg:hidden", !open && "pointer-events-none")} aria-hidden={!open}>
      <div
        className={cn("absolute inset-0 bg-black/40 transition-opacity", open ? "opacity-100" : "opacity-0")}
        onClick={onClose}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="القائمة"
        tabIndex={-1}
        inert={!open}
        className={cn(
          "absolute inset-y-0 start-0 w-72 max-w-[85vw] bg-sidebar text-sidebar-foreground shadow-xl transition-transform duration-200 focus:outline-none",
          // Slide in from the start edge: right in RTL, left in LTR.
          open ? "translate-x-0" : "ltr:-translate-x-full rtl:translate-x-full",
        )}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute end-3 top-4 rounded-lg p-2 text-sidebar-muted hover:bg-sidebar-hover"
          aria-label="إغلاق القائمة"
        >
          <X aria-hidden className="size-5" />
        </button>
        {children}
      </div>
    </div>
  );
}

function Avatar({ name }: { name: string }) {
  // First letter of the first name, skipping titles like "أ."
  const initial = name.replace(/^(أ\.|د\.|م\.)\s*/, "").trim().charAt(0);
  return (
    <span
      aria-hidden
      className="flex size-9 shrink-0 items-center justify-center rounded-full bg-linear-to-br from-vivid-2 to-vivid text-sm font-bold text-white ring-2 ring-sidebar-border"
    >
      {initial}
    </span>
  );
}
