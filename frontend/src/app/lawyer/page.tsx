import type { Metadata } from "next";
import Link from "next/link";
import { Briefcase, CalendarDays, Inbox, Search } from "lucide-react";
import { Card, CardBody, CardHeader, EmptyState } from "@/components/ui";
import { Hero, heroButton, heroGhostButton } from "@/components/hero";
import { cn } from "@/lib/cn";

export const metadata: Metadata = { title: "لوحة التحكم" };

const stats = [
  { label: "طلبات جديدة", icon: Inbox, tile: "bg-linear-to-br from-vivid-2 to-vivid text-white", bar: "bg-vivid" },
  { label: "قضايا نشطة", icon: Briefcase, tile: "bg-secondary text-white", bar: "bg-secondary" },
  { label: "مواعيد هذا الأسبوع", icon: CalendarDays, tile: "bg-primary-soft text-primary", bar: "bg-vivid-2" },
];

export default function LawyerDashboard() {
  return (
    <>
      <Hero
        eyebrow="مساحة عمل المحامي"
        title="لوحة التحكم"
        description="نظرة سريعة على طلباتك وقضاياك. كل ما يقترحه الذكاء الاصطناعي يبقى مسودة حتى توافق عليه."
        actions={
          <>
            <Link href="/lawyer/requests" className={heroButton}>
              <Inbox aria-hidden className="size-4" />
              فتح صندوق الطلبات
            </Link>
            <Link href="/lawyer/research" className={heroGhostButton}>
              <Search aria-hidden className="size-4" />
              بحث قانوني
            </Link>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        {stats.map(({ label, icon: Icon, tile, bar }) => (
          <Card key={label} className="relative overflow-hidden p-5">
            <span aria-hidden className={cn("absolute inset-x-0 top-0 h-1", bar)} />
            <div className="flex items-center gap-4">
              <span className={cn("flex size-11 items-center justify-center rounded-xl shadow-sm", tile)}>
                <Icon aria-hidden className="size-5" />
              </span>
              <div>
                <p className="text-sm text-muted">{label}</p>
                {/* Real counts come from the API in a later story. */}
                <p className="text-2xl font-bold" aria-label="غير متاح بعد">—</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Card className="mt-6">
        <CardHeader title="أحدث الطلبات" description="طلبات العملاء التي تنتظر ردّك" />
        <CardBody className="p-0">
          <EmptyState title="لا توجد طلبات جديدة" description="ستظهر هنا طلبات العملاء بعد موافقتهم على ملخص القضية." />
        </CardBody>
      </Card>
    </>
  );
}
