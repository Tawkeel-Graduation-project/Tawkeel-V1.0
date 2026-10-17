import { SearchX } from "lucide-react";
import { ButtonLink, EmptyState } from "@/components/ui";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-xl p-6 pt-20">
      <div className="rounded-2xl border border-border bg-surface">
        <EmptyState
          icon={<SearchX aria-hidden className="size-6" />}
          title="الصفحة غير موجودة"
          description="الرابط الذي فتحته غير صحيح أو أن الصفحة نُقلت."
          action={<ButtonLink href="/">العودة إلى الرئيسية</ButtonLink>}
        />
      </div>
    </main>
  );
}
