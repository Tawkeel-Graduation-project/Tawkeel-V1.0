"""What the intake agent collects (SCRUM-334).

Each field has a status:

- ``missing``: not collected yet; required fields are asked for.
- ``provided``: the client gave a value.
- ``not_provided``: the client doesn't know or won't say, or intake ended
  without it. Never invented: the summary shows "not provided".
"""

from enum import StrEnum

from services.intake.niches import NICHE_LABELS, SELECTABLE_NICHES


class IntakeField(StrEnum):
    FACTS = "facts"
    NICHE = "niche"
    PARTIES = "parties"
    KEY_DATES = "key_dates"
    URGENCY = "urgency"
    CITY = "city"
    BUDGET = "budget"
    DOCUMENTS = "documents"
    DEADLINES = "deadlines"
    PREFERRED_TIMES = "preferred_times"


class FieldStatus(StrEnum):
    MISSING = "missing"
    PROVIDED = "provided"
    NOT_PROVIDED = "not_provided"


class Urgency(StrEnum):
    URGENT = "urgent"  # days: a hearing, arrest, eviction or deadline soon
    SOON = "soon"  # weeks
    NORMAL = "normal"  # no time pressure


URGENCY_LABELS: dict[Urgency, str] = {
    Urgency.URGENT: "عاجل (خلال أيام)",
    Urgency.SOON: "قريب (خلال أسابيع)",
    Urgency.NORMAL: "غير عاجل",
}

# Asked for, in this order, until provided or declined.
REQUIRED_FIELDS: tuple[IntakeField, ...] = (
    IntakeField.FACTS,
    IntakeField.NICHE,
    IntakeField.PARTIES,
    IntakeField.KEY_DATES,
    IntakeField.URGENCY,
    IntakeField.CITY,
    IntakeField.BUDGET,
)
# Asked once each after the required ones; skipping is fine.
OPTIONAL_FIELDS: tuple[IntakeField, ...] = (
    IntakeField.DOCUMENTS,
    IntakeField.DEADLINES,
    IntakeField.PREFERRED_TIMES,
)
ALL_FIELDS: tuple[IntakeField, ...] = REQUIRED_FIELDS + OPTIONAL_FIELDS

# Longest value a client may enter per field when editing the summary
# (SCRUM-342). Mirrors SUMMARY_MAX_LENGTH in frontend/src/lib/intake/api.ts.
SUMMARY_MAX_LENGTH: dict[IntakeField, int] = {
    IntakeField.FACTS: 4000,
    IntakeField.NICHE: 64,
    IntakeField.PARTIES: 1000,
    IntakeField.KEY_DATES: 1000,
    IntakeField.URGENCY: 64,
    IntakeField.CITY: 200,
    IntakeField.BUDGET: 200,
    IntakeField.DOCUMENTS: 1000,
    IntakeField.DEADLINES: 1000,
    IntakeField.PREFERRED_TIMES: 500,
}

FIELD_LABELS: dict[IntakeField, str] = {
    IntakeField.FACTS: "ماذا حدث",
    IntakeField.NICHE: "نوع القضية",
    IntakeField.PARTIES: "الأطراف",
    IntakeField.KEY_DATES: "التواريخ المهمة",
    IntakeField.URGENCY: "درجة الاستعجال",
    IntakeField.CITY: "المدينة",
    IntakeField.BUDGET: "الميزانية",
    IntakeField.DOCUMENTS: "المستندات المتوفرة",
    IntakeField.DEADLINES: "مواعيد قانونية أو جلسات قريبة",
    IntakeField.PREFERRED_TIMES: "المواعيد المناسبة للقاء",
}

# What each field means, for the agent prompt.
FIELD_DESCRIPTIONS: dict[IntakeField, str] = {
    IntakeField.FACTS: "What happened, in the client's own words (short summary).",
    IntakeField.NICHE: "Legal area: one key from the niche list.",
    IntakeField.PARTIES: (
        "Who is involved and their relation to the client "
        "(e.g. employer, landlord, spouse)."
    ),
    IntakeField.KEY_DATES: "When the main events happened (dates as the client says).",
    IntakeField.URGENCY: "One of: urgent (days), soon (weeks), normal.",
    IntakeField.CITY: "City/governorate where the case is or the client lives.",
    IntakeField.BUDGET: "Budget range for the lawyer's fees, as the client says it.",
    IntakeField.DOCUMENTS: "Documents the client has (contract, ID, police report...).",
    IntakeField.DEADLINES: "Legal deadlines or upcoming hearings (appeal, session...).",
    IntakeField.PREFERRED_TIMES: "When the client can meet the lawyer.",
}


def _niche_choices() -> str:
    return "، ".join(NICHE_LABELS[n] for n in SELECTABLE_NICHES)


# Fallback questions, used when the agent's own question is rejected or fails.
TEMPLATE_QUESTIONS: dict[IntakeField, str] = {
    IntakeField.FACTS: "احكِ لي باختصار ماذا حدث معك؟",
    IntakeField.NICHE: (
        f"أيّ من هذه الأنواع أقرب لمشكلتك؟ {_niche_choices()}. "
        "ولو لست متأكداً قل «غير متأكد»."
    ),
    IntakeField.PARTIES: "من هم الأطراف في هذه المشكلة، وما علاقتك بكل طرف؟",
    IntakeField.KEY_DATES: "متى حدثت الوقائع المهمة تقريباً؟",
    IntakeField.URGENCY: (
        "ما مدى استعجال الأمر؟ هل هناك شيء يجب التصرف فيه خلال أيام، "
        "أم خلال أسابيع، أم ليس عاجلاً؟"
    ),
    IntakeField.CITY: "في أي مدينة أو محافظة تقع المشكلة؟",
    IntakeField.BUDGET: "ما الميزانية التقريبية التي تناسبك لأتعاب المحامي؟",
    IntakeField.DOCUMENTS: (
        "ما المستندات المتوفرة لديك؟ (مثل العقد، المحاضر، الإيصالات) "
        "ويمكنك قول «لا يوجد»."
    ),
    IntakeField.DEADLINES: (
        "هل هناك جلسة قريبة أو موعد قانوني يجب ألا يفوت (استئناف، معارضة...)؟"
    ),
    IntakeField.PREFERRED_TIMES: "ما الأيام والأوقات المناسبة لك للقاء المحامي؟",
}
