"use client";

/**
 * /ui — living reference of the shared components and standard states.
 * Use it when building screens, and to review RTL/visual consistency.
 */
import { useState } from "react";
import { ArrowRight, Plus, Search } from "lucide-react";
import {
  Alert,
  AsyncView,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  DirectionalIcon,
  EmptyState,
  ErrorState,
  LegalDisclaimer,
  LoadingState,
  PageHeader,
  PageSkeleton,
  TextArea,
  TextField,
  type AsyncStatus,
} from "@/components/ui";
import { Brand } from "@/components/shell/brand";
import { AppError } from "@/lib/errors";
import { formatCurrencyEGP, formatDateTime, formatNumber } from "@/lib/format";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader title={title} />
      <CardBody className="space-y-4">{children}</CardBody>
    </Card>
  );
}

export default function UiGallery() {
  const [status, setStatus] = useState<AsyncStatus | "empty">("loading");

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-6">
      <Brand subtitle="مكوّنات الواجهة المشتركة" />
      <PageHeader
        title="دليل المكوّنات"
        description="كل الشاشات تُبنى من هذه المكوّنات لضمان تجربة موحّدة من اليمين إلى اليسار."
        actions={<Button icon={<Plus aria-hidden className="size-4" />}>إجراء رئيسي</Button>}
      />

      <Section title="الأزرار">
        <div className="flex flex-wrap gap-3">
          <Button>أساسي</Button>
          <Button variant="secondary">ثانوي</Button>
          <Button variant="ghost">شفاف</Button>
          <Button variant="danger">حذف</Button>
          <Button loading>جارٍ الإرسال</Button>
          <Button disabled>معطّل</Button>
          <Button variant="secondary" icon={<Search aria-hidden className="size-4" />}>
            بحث
          </Button>
          <Button variant="secondary">
            التالي
            <DirectionalIcon>
              <ArrowRight aria-hidden className="size-4" />
            </DirectionalIcon>
          </Button>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button size="sm">صغير</Button>
          <Button size="md">متوسط</Button>
          <Button size="lg">كبير</Button>
        </div>
      </Section>

      <Section title="الشارات">
        <div className="flex flex-wrap gap-2">
          <Badge>مسودة</Badge>
          <Badge tone="primary">قيد المراجعة</Badge>
          <Badge tone="success">مقبول</Badge>
          <Badge tone="warning">بانتظار الموافقة</Badge>
          <Badge tone="danger">مرفوض</Badge>
          <Badge tone="info">جديد</Badge>
        </div>
      </Section>

      <Section title="الحقول">
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="الاسم الكامل" placeholder="مثال: أحمد محمود" required />
          <TextField label="البريد الإلكتروني" type="email" dir="ltr" placeholder="name@example.com" hint="لن نشاركه مع أي جهة." />
          <TextField label="رقم الهاتف" defaultValue="01" error="رقم الهاتف غير مكتمل" />
          <TextField label="حقل معطّل" disabled defaultValue="غير قابل للتعديل" />
        </div>
        <TextArea label="وصف المشكلة" placeholder="اكتب ما حدث بالتفصيل…" />
      </Section>

      <Section title="التنبيهات">
        <Alert tone="info" title="معلومة">تم حفظ المسودة تلقائيًا.</Alert>
        <Alert tone="success" title="تم الإرسال">أُرسل طلبك إلى المحامي.</Alert>
        <Alert tone="danger" title="تعذّر الإرسال">تحقّق من البيانات وحاول مرة أخرى.</Alert>
        <LegalDisclaimer />
      </Section>

      <Section title="الحالات الموحّدة (تحميل / خطأ / فارغ)">
        <div className="flex flex-wrap gap-2" role="group" aria-label="اختر الحالة">
          {(["loading", "error", "empty", "success"] as const).map((s) => (
            <Button key={s} size="sm" variant={status === s ? "primary" : "secondary"} onClick={() => setStatus(s)}>
              {{ loading: "تحميل", error: "خطأ", empty: "فارغ", success: "بيانات" }[s]}
            </Button>
          ))}
        </div>
        <Card>
          <AsyncView
            status={status === "empty" ? "success" : status}
            error={new AppError("network")}
            onRetry={() => setStatus("loading")}
            isEmpty={status === "empty"}
            empty={{ title: "لا توجد طلبات", description: "ستظهر الطلبات هنا عند وصولها." }}
          >
            <ul className="divide-y divide-border">
              {["قضية إيجار — الدقي", "نزاع عمالي — مدينة نصر"].map((t) => (
                <li key={t} className="flex items-center justify-between p-4 text-sm">
                  {t}
                  <Badge tone="info">جديد</Badge>
                </li>
              ))}
            </ul>
          </AsyncView>
        </Card>

        <div className="grid gap-4 md:grid-cols-2">
          <Card><LoadingState /></Card>
          <Card><EmptyState title="لا توجد نتائج" description="جرّب كلمات بحث مختلفة." /></Card>
          <Card><ErrorState error={new AppError("forbidden")} /></Card>
          <Card><ErrorState error={AppError.fromStatus(500)} onRetry={() => {}} /></Card>
        </div>
        <p className="text-sm font-medium">هيكل تحميل الصفحة (يُستخدم تلقائيًا في loading.tsx):</p>
        <PageSkeleton rows={2} />
      </Section>

      <Section title="التنسيق المحلي">
        <ul className="space-y-1 text-sm">
          <li>رقم: {formatNumber(1234567)}</li>
          <li>مبلغ: {formatCurrencyEGP(2500)}</li>
          <li>تاريخ: {formatDateTime("2026-10-17T10:30:00")}</li>
        </ul>
      </Section>
    </main>
  );
}
