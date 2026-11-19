"""LLM output contract for source-grounded legal answers.

This is the internal JSON shape the model must return. It is validated with
``services.llm.structured.generate_structured`` and is **not** the PROPOSED
``messages.citations`` database shape in context.md §20.2; mapping to any stored
or API shape happens later.

Source ids: the prompt builder (SCRUM-323) labels each retrieved chunk with a
short id such as ``"S1"``, ``"S2"`` in the order it appears in the context. Each
claim cites those labels in ``source_ids``. Short labels are easier for small
local models to copy correctly than database UUIDs; the caller maps them back to
``legal_chunks`` rows and rejects labels that were not in the context (via a
semantic validator). This module does not check that a label exists.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _reject_nul(value: str) -> str:
    """PostgreSQL text and JSONB cannot store NUL, so reject it at the boundary."""
    if "\x00" in value:
        raise ValueError("text must not contain NUL characters")
    return value


class AnswerStatus(StrEnum):
    """What kind of answer the model produced."""

    ANSWERED = "answered"
    NO_SOURCE = "no_source"
    NEEDS_CLARIFICATION = "needs_clarification"


class Claim(BaseModel):
    """One statement in the answer and the source labels that support it."""

    text: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("claim text must not be blank")
        return _reject_nul(value)

    @field_validator("source_ids")
    @classmethod
    def source_ids_without_nul(cls, value: list[str]) -> list[str]:
        return [_reject_nul(source_id) for source_id in value]


class LegalAnswer(BaseModel):
    """A legal answer split into claims, or a no-source / clarification outcome."""

    status: AnswerStatus
    claims: list[Claim] = Field(default_factory=list)
    clarification_question: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("clarification_question")
    @classmethod
    def clarification_without_nul(cls, value: str | None) -> str | None:
        return None if value is None else _reject_nul(value)

    @model_validator(mode="after")
    def check_status_consistency(self) -> "LegalAnswer":
        if self.status == AnswerStatus.ANSWERED and not self.claims:
            raise ValueError("an answered status needs at least one claim")
        if self.status == AnswerStatus.NEEDS_CLARIFICATION:
            question = self.clarification_question
            if question is None or not question.strip():
                raise ValueError(
                    "needs_clarification needs a non-empty clarification_question"
                )
            if self.claims:
                raise ValueError("needs_clarification must not include claims")
        elif self.clarification_question is not None:
            raise ValueError(
                "clarification_question is only allowed with needs_clarification"
            )
        if self.status == AnswerStatus.NO_SOURCE and self.claims:
            raise ValueError("no_source must not include claims")
        return self
