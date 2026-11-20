/**
 * Intake fields and niches, mirrored from the backend
 * (services/intake/fields.py, services/intake/niches.py). Keep in sync.
 */

export type IntakeFieldKey =
  | "facts"
  | "niche"
  | "parties"
  | "key_dates"
  | "urgency"
  | "city"
  | "budget"
  | "documents"
  | "deadlines"
  | "preferred_times";

export type IntakeFieldStatus = "missing" | "provided" | "not_provided";

export const REQUIRED_FIELDS: IntakeFieldKey[] = [
  "facts",
  "niche",
  "parties",
  "key_dates",
  "urgency",
  "city",
  "budget",
];
export const OPTIONAL_FIELDS: IntakeFieldKey[] = ["documents", "deadlines", "preferred_times"];
export const ALL_FIELDS: IntakeFieldKey[] = [...REQUIRED_FIELDS, ...OPTIONAL_FIELDS];

export const FIELD_LABELS: Record<IntakeFieldKey, string> = {
  facts: "ماذا حدث",
  niche: "نوع القضية",
  parties: "الأطراف",
  key_dates: "التواريخ المهمة",
  urgency: "درجة الاستعجال",
  city: "المدينة",
  budget: "الميزانية",
  documents: "المستندات المتوفرة",
  deadlines: "مواعيد قانونية أو جلسات قريبة",
  preferred_times: "المواعيد المناسبة للقاء",
};

/** DRAFT niche list (SCRUM-333), pending the lawyer survey (SCRUM-420). */
export const NICHE_LABELS: Record<string, string> = {
  personal_status: "أحوال شخصية",
  criminal: "جنائي",
  civil: "مدني",
  commercial: "تجاري وشركات",
  labor: "عمل وعمال",
  real_estate: "عقارات وإيجارات",
  administrative: "إداري ومجلس دولة",
  economic: "اقتصادي (شيكات، جرائم إنترنت)",
  tax_customs: "ضرائب وجمارك",
  intellectual_property: "ملكية فكرية",
  unsure: "غير محدد",
};

export const URGENCY_LABELS: Record<string, string> = {
  urgent: "عاجل (خلال أيام)",
  soon: "قريب (خلال أسابيع)",
  normal: "غير عاجل",
};

/** Human-readable value for display (niche/urgency keys → Arabic labels). */
export function displayValue(field: IntakeFieldKey, value: string | null): string | null {
  if (value == null) return null;
  if (field === "niche") return NICHE_LABELS[value] ?? value;
  if (field === "urgency") return URGENCY_LABELS[value] ?? value;
  return value;
}
