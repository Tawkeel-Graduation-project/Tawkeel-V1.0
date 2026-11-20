"""The intake agent loop (SCRUM-334): the agent proposes, the code decides.

One LLM call per client message returns an ``AgentProposal`` (extracted
fields + next question). Code then:

- validates every extracted value (niche from the controlled list, urgency
  from its enum, bounded text) and drops anything invalid;
- records declined fields as ``not_provided`` (never invented);
- accepts the agent's question only if it targets a sensible field, else falls
  back to a template question for the next missing field;
- decides when intake is complete (the agent's "finish" is only a hint);
- caps the number of questions so intake can never loop forever.

If the model fails entirely, the client's answer is still stored for the field
that was asked about, so no answer is lost.

This module has no database code; ``services.intake.service`` persists state.
"""

import copy
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from services.intake.fields import (
    ALL_FIELDS,
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    TEMPLATE_QUESTIONS,
    FieldStatus,
    IntakeField,
    Urgency,
)
from services.intake.niches import NICHE_LABELS, Niche, parse_niche
from services.intake.prompts import build_messages
from services.llm.provider import BaseLLMProvider
from services.llm.structured import generate_structured

MAX_AGENT_QUESTIONS = 15
MAX_VALUE_CHARS = 2000
MAX_QUESTION_CHARS = 400
# How many times a still-missing field may be asked before it becomes not_provided.
ASK_LIMIT_REQUIRED = 2
ASK_LIMIT_OPTIONAL = 1

OPENING_TEXT = "أهلاً بك. سأطرح عليك بعض الأسئلة القصيرة لتجهيز طلبك للمحامي."
CLOSING_TEXT = (
    "شكراً لك، اكتملت المعلومات المطلوبة. "
    "الخطوة التالية: مراجعة ملخص طلبك قبل إرساله لأي محامٍ."
)

_ARABIC = re.compile(r"[؀-ۿ]")
_DECLINE = re.compile(
    r"(مش عارف|معرفش|ما اعرفش|لا ?أعرف|لا ?اعرف|مش متأكد|غير متأكد|مش فاكر|"
    r"لا ?أتذكر|لا ?اتذكر|مش عايز|لا ?أريد|لا ?اريد|تخطي|تخطى|skip|لا ?يوجد|مفيش|"
    r"ماليش|ليس لدي|معنديش)",
    re.IGNORECASE,
)
_NONE_ANSWER = re.compile(r"^(لا ?يوجد|مفيش|معنديش|ليس لدي|لا شيء|لا)[\s.!،]*$")
# Fields where "none" is itself an answer ("I have no documents").
_NONE_IS_ANSWER = {IntakeField.DOCUMENTS, IntakeField.DEADLINES}
_URGENCY_WORDS: list[tuple[Urgency, re.Pattern[str]]] = [
    (Urgency.NORMAL, re.compile(r"(مش عاجل|غير عاجل|مش مستعجل|غير مستعجل|براحت)")),
    (Urgency.URGENT, re.compile(r"(عاجل|أيام|ايام|بكرة|بكره|غدا|غداً|النهارده|حالا)")),
    (Urgency.SOON, re.compile(r"(أسبوع|اسبوع|أسابيع|اسابيع|شهر)")),
]


# --- what the model returns -------------------------------------------------


class ProposedFields(BaseModel):
    facts: str | None = None
    niche: str | None = None
    parties: str | None = None
    key_dates: str | None = None
    urgency: str | None = None
    city: str | None = None
    budget: str | None = None
    documents: str | None = None
    deadlines: str | None = None
    preferred_times: str | None = None

    model_config = ConfigDict(extra="forbid")


class AgentProposal(BaseModel):
    fields: ProposedFields = Field(default_factory=ProposedFields)
    declined: list[str] = Field(default_factory=list, max_length=len(ALL_FIELDS))
    action: Literal["ask", "finish"]
    target_field: str | None = None
    question: str | None = None

    model_config = ConfigDict(extra="forbid")


# --- state ------------------------------------------------------------------


def new_intake_state() -> dict[str, Any]:
    """Empty intake state stored at ``workflow.state["intake"]``."""
    return {
        "fields": {
            f.value: {"status": FieldStatus.MISSING.value, "value": None}
            for f in ALL_FIELDS
        },
        "turns": [],
        "asked": {},
        "agent_questions": 0,
        "complete": False,
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _status(fields: dict, f: IntakeField) -> FieldStatus:
    return FieldStatus(fields[f.value]["status"])


def _set(fields: dict, f: IntakeField, status: FieldStatus, value: str | None) -> None:
    fields[f.value] = {"status": status.value, "value": value}


def _clean_text(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    text = " ".join(raw.split())
    return text[:MAX_VALUE_CHARS] or None


def _parse_urgency(raw: object) -> Urgency | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip().lower()
    for u in Urgency:
        if text == u.value:
            return u
    for u, pattern in _URGENCY_WORDS:
        if pattern.search(text):
            return u
    return None


def _niche_from_text(text: str) -> Niche | None:
    direct = parse_niche(text)
    if direct is not None:
        return direct
    for niche, label in NICHE_LABELS.items():
        if label.split(" (")[0] in text:
            return niche
    return None


def _validated_value(f: IntakeField, raw: object) -> str | None:
    """A value the code accepts for this field, or None to drop it."""
    if f is IntakeField.NICHE:
        niche = parse_niche(raw)
        return niche.value if niche is not None else None
    if f is IntakeField.URGENCY:
        urgency = _parse_urgency(raw)
        return urgency.value if urgency is not None else None
    return _clean_text(raw)


# --- one turn ---------------------------------------------------------------


@dataclass
class TurnOutcome:
    state: dict[str, Any]
    agent_message: str
    target_field: str | None
    complete: bool
    # "agent": the model's question was used; "template": code fallback;
    # "closing": intake finished.
    source: Literal["agent", "template", "closing"]
    model_ok: bool
    changed_fields: list[str] = field(default_factory=list)
    overrides: list[str] = field(default_factory=list)


def _apply_proposal(
    fields: dict, proposal: AgentProposal, last_target: IntakeField | None
) -> tuple[list[str], list[str]]:
    """Merge validated values and declines into ``fields``.

    Returns (changed field keys, dropped invalid keys).
    """
    changed: list[str] = []
    dropped: list[str] = []
    for f in ALL_FIELDS:
        raw = getattr(proposal.fields, f.value)
        if raw is None:
            continue
        value = _validated_value(f, raw)
        if value is None:
            dropped.append(f.value)
            continue
        if f is IntakeField.NICHE and value == Niche.UNSURE.value:
            # Unclear niche stays missing so the client is shown the list,
            # unless they were already asked to choose.
            if last_target is IntakeField.NICHE:
                _set(fields, f, FieldStatus.NOT_PROVIDED, None)
                changed.append(f.value)
            continue
        _set(fields, f, FieldStatus.PROVIDED, value)
        changed.append(f.value)

    for key in proposal.declined:
        try:
            f = IntakeField(key)
        except ValueError:
            dropped.append(str(key))
            continue
        if f.value not in changed and _status(fields, f) is FieldStatus.MISSING:
            _set(fields, f, FieldStatus.NOT_PROVIDED, None)
            changed.append(f.value)
    return changed, dropped


def _apply_raw_answer(fields: dict, target: IntakeField, text: str) -> list[str]:
    """Model failed: store the client's answer for the field that was asked."""
    if _status(fields, target) is not FieldStatus.MISSING:
        return []
    if _NONE_ANSWER.match(text.strip()) and target in _NONE_IS_ANSWER:
        _set(fields, target, FieldStatus.PROVIDED, "لا يوجد")
        return [target.value]
    if len(text) <= 40 and _DECLINE.search(text):
        _set(fields, target, FieldStatus.NOT_PROVIDED, None)
        return [target.value]
    if target is IntakeField.NICHE:
        niche = _niche_from_text(text)
        if niche is None or niche is Niche.UNSURE:
            return []
        _set(fields, target, FieldStatus.PROVIDED, niche.value)
        return [target.value]
    value = _validated_value(target, text)
    if value is None:
        return []
    _set(fields, target, FieldStatus.PROVIDED, value)
    return [target.value]


def _limit(f: IntakeField) -> int:
    return ASK_LIMIT_OPTIONAL if f in OPTIONAL_FIELDS else ASK_LIMIT_REQUIRED


def _give_up_exhausted(fields: dict, asked: dict[str, int]) -> list[str]:
    """Fields asked their maximum number of times and still missing -> not_provided."""
    changed = []
    for f in ALL_FIELDS:
        if _status(fields, f) is FieldStatus.MISSING and asked.get(
            f.value, 0
        ) >= _limit(f):
            _set(fields, f, FieldStatus.NOT_PROVIDED, None)
            changed.append(f.value)
    return changed


def next_missing(fields: dict) -> IntakeField | None:
    """The field the code would ask about next (required first, in order)."""
    for f in REQUIRED_FIELDS + OPTIONAL_FIELDS:
        if _status(fields, f) is FieldStatus.MISSING:
            return f
    return None


def _accept_question(
    proposal: AgentProposal | None, fields: dict, asked: dict[str, int]
) -> tuple[IntakeField, str] | str:
    """The agent's (field, question) if acceptable, else the reason it was rejected."""
    if proposal is None:
        return "model_failed"
    if proposal.action != "ask":
        return "finish_rejected"
    try:
        target = IntakeField(proposal.target_field or "")
    except ValueError:
        return "unknown_field"
    question = " ".join((proposal.question or "").split())
    if (
        not question
        or len(question) > MAX_QUESTION_CHARS
        or not _ARABIC.search(question)
    ):
        return "bad_question"
    status = _status(fields, target)
    times = asked.get(target.value, 0)
    if status is FieldStatus.MISSING:
        required_missing = any(
            _status(fields, f) is FieldStatus.MISSING for f in REQUIRED_FIELDS
        )
        if required_missing and target in OPTIONAL_FIELDS:
            return "optional_before_required"
        if times >= _limit(target):
            return "asked_too_often"
    elif status is FieldStatus.PROVIDED:
        if times >= 1:  # one clarifying follow-up per field at most
            return "already_clarified"
    else:
        return "field_declined"
    return target, question


def _last_target(state: dict[str, Any]) -> IntakeField | None:
    for turn in reversed(state["turns"]):
        if turn["role"] == "agent":
            try:
                return IntakeField(turn.get("field") or "")
            except ValueError:
                return None
    return None


async def run_turn(
    provider: BaseLLMProvider,
    state: dict[str, Any],
    client_message: str | None,
    *,
    opening_context: list[str] | None = None,
) -> TurnOutcome:
    """Process one client message (or the opening turn) and return the next step.

    ``state`` is not mutated; the returned ``TurnOutcome.state`` replaces it.
    ``opening_context``: the client's own messages from the legal chat, used
    to pre-fill fields on the opening turn (assistant answers are never used).
    """
    new = copy.deepcopy(state)
    fields: dict = new["fields"]
    asked: dict[str, int] = new["asked"]
    last_target = _last_target(new)

    opening = client_message is None
    if opening:
        source_text = "\n".join(t for t in (opening_context or []) if t.strip())
    else:
        source_text = client_message
        new["turns"].append(
            {"role": "client", "content": client_message, "field": None, "at": _now()}
        )

    proposal: AgentProposal | None = None
    changed: list[str] = []
    overrides: list[str] = []
    if source_text.strip():
        result = await generate_structured(
            provider,
            build_messages(
                fields,
                state["turns"],
                source_text,
                last_target=(last_target.value if last_target else None),
            ),
            AgentProposal,
        )
        if result.ok and result.value is not None:
            proposal = result.value
            changed, dropped = _apply_proposal(fields, proposal, last_target)
            overrides += [f"dropped_invalid:{d}" for d in dropped]
        elif last_target is not None and not opening:
            changed = _apply_raw_answer(fields, last_target, client_message or "")

    # A field asked about that is still missing counts against its limit.
    changed += _give_up_exhausted(fields, asked)
    model_ok = proposal is not None

    done = next_missing(fields) is None
    if not done and new["agent_questions"] >= MAX_AGENT_QUESTIONS:
        for f in ALL_FIELDS:
            if _status(fields, f) is FieldStatus.MISSING:
                _set(fields, f, FieldStatus.NOT_PROVIDED, None)
                changed.append(f.value)
        overrides.append("max_questions_reached")
        done = True

    if done:
        new["complete"] = True
        new["turns"].append(
            {"role": "agent", "content": CLOSING_TEXT, "field": None, "at": _now()}
        )
        return TurnOutcome(
            state=new,
            agent_message=CLOSING_TEXT,
            target_field=None,
            complete=True,
            source="closing",
            model_ok=model_ok,
            changed_fields=sorted(set(changed)),
            overrides=overrides,
        )

    accepted = _accept_question(proposal, fields, asked)
    if isinstance(accepted, tuple):
        target, question = accepted
        source: Literal["agent", "template"] = "agent"
    else:
        if proposal is not None:
            overrides.append(f"question_rejected:{accepted}")
        target = next_missing(fields)  # not None: done is False
        assert target is not None
        question = TEMPLATE_QUESTIONS[target]
        source = "template"

    message = f"{OPENING_TEXT}\n{question}" if opening else question
    asked[target.value] = asked.get(target.value, 0) + 1
    new["agent_questions"] += 1
    new["turns"].append(
        {"role": "agent", "content": message, "field": target.value, "at": _now()}
    )
    return TurnOutcome(
        state=new,
        agent_message=message,
        target_field=target.value,
        complete=False,
        source=source,
        model_ok=model_ok,
        changed_fields=sorted(set(changed)),
        overrides=overrides,
    )
