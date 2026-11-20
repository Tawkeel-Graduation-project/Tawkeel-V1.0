"""Prompt for the intake agent (SCRUM-335).

The model only *proposes* (extracted fields + next question). Code in
``services.intake.agent`` validates and may override every proposal.
"""

import json
from typing import Any

from services.intake.fields import (
    ALL_FIELDS,
    FIELD_DESCRIPTIONS,
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    Urgency,
)
from services.intake.niches import NICHE_LABELS
from services.llm.models import LLMMessage

MAX_PROMPT_TURNS = 12

SYSTEM_PROMPT = """You are Tawkeel's intake assistant. A client in Egypt wants a \
lawyer. Your job is to collect the information a lawyer needs, by asking short \
questions. You are NOT a lawyer: never give legal advice, opinions or predictions.

Each turn you receive the fields collected so far, the recent conversation, and \
the client's latest message. Return a JSON proposal:

1. "fields": ONLY fields for which the client's messages give new or corrected \
information. Give the full updated value (merge with the current value). Leave \
every other field null.
   - Use ONLY what the client said. Never invent names, dates, amounts or places. \
Never copy facts from the legal assistant's earlier answers.
   - Write values in Arabic, close to the client's words.
   - "niche": exactly one key from the niche list, or "unsure" if unclear.
   - "urgency": exactly one of "urgent" (days), "soon" (weeks), "normal".
2. "declined": field keys the client says they don't know or won't share.
3. Next step:
   - "action": "ask" with "target_field" (one field key) and "question": ONE \
short, polite question in Arabic (max 2 sentences). Prefer required fields that \
are still missing. You may ask one follow-up if an answer is vague. Do not ask \
again about fields already provided or declined.
   - "action": "finish" only when every required field is provided or declined.

Niche list (key: label):
{niches}

Fields (key: meaning):
{fields}

Required fields: {required}
Optional fields (ask once each, after the required ones): {optional}"""


def build_system_prompt() -> str:
    niches = "\n".join(f"- {n.value}: {label}" for n, label in NICHE_LABELS.items())
    fields = "\n".join(f"- {f.value}: {FIELD_DESCRIPTIONS[f]}" for f in ALL_FIELDS)
    return (
        SYSTEM_PROMPT.format(
            niches=niches,
            fields=fields,
            required=", ".join(f.value for f in REQUIRED_FIELDS),
            optional=", ".join(f.value for f in OPTIONAL_FIELDS),
        )
        + f"\nUrgency values: {', '.join(u.value for u in Urgency)}"
    )


def build_messages(
    fields: dict[str, dict[str, Any]],
    turns: list[dict[str, Any]],
    client_text: str,
    *,
    last_target: str | None,
) -> list[LLMMessage]:
    """Messages for one agent step. ``client_text`` is what to extract from now."""
    recent = [
        {"role": t["role"], "content": t["content"]} for t in turns[-MAX_PROMPT_TURNS:]
    ]
    payload = {
        "current_fields": fields,
        "last_question_was_about": last_target,
        "recent_conversation": recent,
        "client_latest_message": client_text,
    }
    return [
        LLMMessage.system(build_system_prompt()),
        LLMMessage.user(json.dumps(payload, ensure_ascii=False)),
    ]
