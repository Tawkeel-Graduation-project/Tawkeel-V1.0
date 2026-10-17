import { Construction } from "lucide-react";
import { Card, EmptyState, PageHeader } from "@/components/ui";
import type { Role } from "@/lib/auth/types";
import { findNavItem } from "@/lib/navigation";

/**
 * Stand-in for screens owned by later stories. Title and description come
 * from the navigation config so the sidebar and page header never drift.
 */
export function PlaceholderPage({ role, href, story }: { role: Role; href: string; story?: string }) {
  const item = findNavItem(role, href);
  return (
    <>
      <PageHeader title={item?.label ?? ""} description={item?.description} />
      <Card>
        <EmptyState
          icon={<Construction aria-hidden className="size-6" />}
          title="هذه الصفحة قيد التطوير"
          description={story ? `سيتم بناؤها ضمن: ${story}` : "سيتم بناؤها في سبرنت قادم."}
        />
      </Card>
    </>
  );
}

export function pageTitle(role: Role, href: string) {
  return findNavItem(role, href)?.label;
}
