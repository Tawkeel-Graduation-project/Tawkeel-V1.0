import type { Metadata } from "next";
import { MessagesSquare, Send, FileText, ChevronRight } from "lucide-react";
import Link from "next/link";
import { ButtonLink, Card, CardBody, CardHeader, DirectionalIcon, EmptyState, LegalDisclaimer } from "@/components/ui";
import { Hero, heroButton, heroGhostButton } from "@/components/hero";
import { cn } from "@/lib/cn";

export const metadata: Metadata = { title: "الرئيسية" };

const actions = [
  {
    href: "/client/assistant",
    icon: MessagesSquare,
    title: "اسأل المساعد القانوني",
    text: "إجابات مبسّطة عن أسئلتك القانونية مع ذكر المصدر.",
    tile: "bg-linear-to-br from-vivid-2 to-vivid text-white",
  },
  {
    href: "/client/requests",
    icon: Send,
    title: "اطلب محاميًا",
    text: "نساعدك في تلخيص مشكلتك واختيار المحامي المناسب.",
    tile: "bg-secondary text-white",
  },
  {
    href: "/client/documents",
    icon: FileText,
    title: "ارفع مستندًا",
    text: "أضف العقود أو المستندات المتعلقة بمشكلتك.",
    tile: "bg-primary-soft text-primary",
  },
];

export default function ClientHome() {
  return (
    <>
      <Hero
        eyebrow="بوابة العملاء"
        title="أهلًا بك في توكيل"
        description="ابدأ بسؤال قانوني، أو اطلب محاميًا مناسبًا لمشكلتك. نحن نرتّب المعلومات، وأنت تقرّر."
        actions={
          <>
            <Link href="/client/assistant" className={heroButton}>
              <MessagesSquare aria-hidden className="size-4" />
              اسأل سؤالًا
            </Link>
            <Link href="/client/requests" className={heroGhostButton}>
              اطلب محاميًا
            </Link>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {actions.map(({ href, icon: Icon, title, text, tile }) => (
          <Link key={href} href={href} className="group">
            <Card className="h-full p-5 transition group-hover:-translate-y-0.5 group-hover:border-vivid/50 group-hover:shadow-md group-hover:shadow-vivid/15">
              <div className="flex items-start gap-3">
                <span className={cn("flex size-11 shrink-0 items-center justify-center rounded-xl shadow-sm", tile)}>
                  <Icon aria-hidden className="size-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <h2 className="font-semibold">{title}</h2>
                  <p className="mt-1 text-sm text-muted">{text}</p>
                </div>
                <DirectionalIcon className="mt-1 text-muted transition-transform group-hover:-translate-x-0.5 group-hover:text-vivid">
                  <ChevronRight aria-hidden className="size-4" />
                </DirectionalIcon>
              </div>
            </Card>
          </Link>
        ))}
      </div>

      <LegalDisclaimer className="mt-6" />

      <Card className="mt-6">
        <CardHeader title="طلباتك الأخيرة" description="حالة الطلبات التي أرسلتها إلى المحامين" />
        <CardBody className="p-0">
          <EmptyState
            title="لا توجد طلبات بعد"
            description="عندما ترسل طلبًا إلى محامٍ سيظهر هنا مع حالته."
            action={<ButtonLink href="/client/requests">اطلب محاميًا</ButtonLink>}
          />
        </CardBody>
      </Card>
    </>
  );
}
