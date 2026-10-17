import type { LucideIcon } from "lucide-react";
import {
  Briefcase,
  CalendarDays,
  FileText,
  Home,
  Inbox,
  LayoutDashboard,
  MessagesSquare,
  Scale,
  Search,
  Send,
  UserRound,
} from "lucide-react";
import type { Role } from "./auth/types";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  /** Optional short description, shown as the page subtitle. */
  description?: string;
}

export interface NavSection {
  title?: string;
  items: NavItem[];
}

/**
 * Single source of truth for each role's navigation.
 * Add a screen here and it appears in the sidebar and mobile menu.
 * Order follows the PRD user journey (§7).
 */
export const navigation: Record<Role, NavSection[]> = {
  client: [
    {
      items: [
        { label: "الرئيسية", href: "/client", icon: Home },
        {
          label: "المساعد القانوني",
          href: "/client/assistant",
          icon: MessagesSquare,
          description: "اسأل سؤالًا قانونيًا واحصل على إجابة موثّقة بالمصادر",
        },
        {
          label: "طلباتي",
          href: "/client/requests",
          icon: Send,
          description: "تابع طلباتك المرسلة إلى المحامين وحالتها",
        },
        {
          label: "مستنداتي",
          href: "/client/documents",
          icon: FileText,
          description: "ارفع مستنداتك واستعرضها",
        },
      ],
    },
    {
      title: "الحساب",
      items: [{ label: "الملف الشخصي", href: "/client/profile", icon: UserRound }],
    },
  ],
  lawyer: [
    {
      items: [
        { label: "لوحة التحكم", href: "/lawyer", icon: LayoutDashboard },
        {
          label: "صندوق الطلبات",
          href: "/lawyer/requests",
          icon: Inbox,
          description: "راجع طلبات العملاء واقبلها أو اعتذر عنها",
        },
        {
          label: "القضايا",
          href: "/lawyer/cases",
          icon: Briefcase,
          description: "وقائع القضايا والجدول الزمني والمستندات والأبحاث المحفوظة",
        },
        {
          label: "البحث القانوني",
          href: "/lawyer/research",
          icon: Search,
          description: "ابحث في النصوص القانونية والأحكام مع المصادر",
        },
        {
          label: "المواعيد",
          href: "/lawyer/schedule",
          icon: CalendarDays,
          description: "حدّد أوقات إتاحتك وتابع المواعيد المحجوزة",
        },
      ],
    },
    {
      title: "الحساب",
      items: [{ label: "الملف المهني", href: "/lawyer/profile", icon: Scale }],
    },
  ],
};

export function flatNav(role: Role): NavItem[] {
  return navigation[role].flatMap((s) => s.items);
}

/** Active if exact match, or a nested route (but the role home only matches exactly). */
export function isActive(pathname: string, href: string, role: Role) {
  const home = role === "client" ? "/client" : "/lawyer";
  if (href === home) return pathname === home;
  return pathname === href || pathname.startsWith(href + "/");
}

export function findNavItem(role: Role, href: string): NavItem | undefined {
  return flatNav(role).find((i) => i.href === href);
}
