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
from services.security.trust import (
    CLIENT_MESSAGE_TAG,
    CONVERSATION_HISTORY_TAG,
    INTAKE_STATE_TAG,
    TRUST_BOUNDARY_DIRECTIVE_EN,
    sanitize_untrusted_text,
    wrap_data_block,
    wrap_raw_block,
)

MAX_PROMPT_TURNS = 12

CLIENT_MESSAGE_OPEN = f"<{CLIENT_MESSAGE_TAG}>"
CLIENT_MESSAGE_CLOSE = f"</{CLIENT_MESSAGE_TAG}>"
CONVERSATION_HISTORY_OPEN = f"<{CONVERSATION_HISTORY_TAG}>"
CONVERSATION_HISTORY_CLOSE = f"</{CONVERSATION_HISTORY_TAG}>"
INTAKE_STATE_OPEN = f"<{INTAKE_STATE_TAG}>"
INTAKE_STATE_CLOSE = f"</{INTAKE_STATE_TAG}>"

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
        + f"\n\n{TRUST_BOUNDARY_DIRECTIVE_EN}"
    )


def _format_turns(turns: list[dict[str, Any]]) -> str:
    """Wrap recent turns in ``<turn>`` tags inside ``<conversation_history>``."""
    turn_blocks = [
        wrap_data_block(
            "turn",
            str(t.get("content", "")),
            attributes={"role": str(t.get("role", "unknown"))},
        )
        for t in turns[-MAX_PROMPT_TURNS:]
    ]
    return wrap_raw_block(CONVERSATION_HISTORY_TAG, "\n".join(turn_blocks))


def build_messages(
    fields: dict[str, dict[str, Any]],
    turns: list[dict[str, Any]],
    client_text: str,
    *,
    last_target: str | None,
) -> list[LLMMessage]:
    """Messages for one agent step. Untrusted data is enclosed in delimited blocks."""
    state_json = json.dumps(
        {
            "current_fields": fields,
            "last_question_was_about": last_target,
        },
        ensure_ascii=False,
    )
    state_block = wrap_raw_block(INTAKE_STATE_TAG, sanitize_untrusted_text(state_json))
    history_block = _format_turns(turns)
    client_block = wrap_data_block(CLIENT_MESSAGE_TAG, client_text)

    user_content = f"{state_block}\n\n{history_block}\n\n{client_block}"
    return [
        LLMMessage.system(build_system_prompt()),
        LLMMessage.user(user_content),
    ]
