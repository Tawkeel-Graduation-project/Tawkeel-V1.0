"""Controlled list of legal niches the intake agent classifies into (SCRUM-333).

DRAFT: taken from the options in the lawyer survey (SCRUM-420). Once the
lawyers' answers are in, confirm or adjust this list; the keys are stable IDs
stored in the database, the Arabic labels are what clients and lawyers see.
"""

from enum import StrEnum


class Niche(StrEnum):
    PERSONAL_STATUS = "personal_status"
    CRIMINAL = "criminal"
    CIVIL = "civil"
    COMMERCIAL = "commercial"
    LABOR = "labor"
    REAL_ESTATE = "real_estate"
    ADMINISTRATIVE = "administrative"
    ECONOMIC = "economic"
    TAX_CUSTOMS = "tax_customs"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    # The client's case doesn't clearly fit; the agent asks them to choose.
    UNSURE = "unsure"


NICHE_LABELS: dict[Niche, str] = {
    Niche.PERSONAL_STATUS: "أحوال شخصية",
    Niche.CRIMINAL: "جنائي",
    Niche.CIVIL: "مدني",
    Niche.COMMERCIAL: "تجاري وشركات",
    Niche.LABOR: "عمل وعمال",
    Niche.REAL_ESTATE: "عقارات وإيجارات",
    Niche.ADMINISTRATIVE: "إداري ومجلس دولة",
    Niche.ECONOMIC: "اقتصادي (شيكات، جرائم إنترنت)",
    Niche.TAX_CUSTOMS: "ضرائب وجمارك",
    Niche.INTELLECTUAL_PROPERTY: "ملكية فكرية",
    Niche.UNSURE: "غير محدد",
}

# Niches a case can actually be filed under (everything except UNSURE).
SELECTABLE_NICHES: tuple[Niche, ...] = tuple(n for n in Niche if n is not Niche.UNSURE)


def parse_niche(raw: object) -> Niche | None:
    """Map a model or client value (key or Arabic label) to a Niche, else None."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    lowered = text.lower()
    for niche in Niche:
        if lowered == niche.value:
            return niche
    for niche, label in NICHE_LABELS.items():
        if text == label or text == label.split(" (")[0]:
            return niche
    return None
