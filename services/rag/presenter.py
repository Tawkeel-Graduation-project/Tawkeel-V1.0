"""Turn an ``AnswerOutcome`` into a safe Arabic reply for the user (SCRUM-309).

``present_outcome`` returns an ``AssistantReply``: a frozen Pydantic model the
HTTP endpoint can return as-is. Its ``kind`` values are stable codes the
frontend relies on.

Safety: user-facing strings come only from ``MESSAGES_AR``. Failure codes,
exception text, and internal details never reach the reply. The internal
failure kind is logged at INFO, with no question or answer text.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from services.rag.chain import AnswerFailure, AnswerOutcome
from services.rag.schemas import AnswerStatus, Citation, GroundedAnswer

logger = logging.getLogger(__name__)


class ReplyKind(StrEnum):
    """What the reply is. Stable codes shared with the frontend."""

    ANSWERED = "answered"
    CLARIFICATION = "clarification"
    NO_SOURCE = "no_source"
    INVALID_QUESTION = "invalid_question"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    ANSWER_FAILED = "answer_failed"


# All user-facing Arabic copy, in one place for review. The tone matches the
# frontend (frontend/src/lib/errors.ts and components/chat). "disclaimer" is the
# same text as the chat DisclaimerBanner.
MESSAGES_AR: dict[str, str] = {
    "disclaimer": (
        "المعلومات المستخرجة بواسطة المساعد الذكي للاسترشاد القانوني فقط، "
        "ولا تُعد استشارة رسمية أو بديلاً عن توكيل محامٍ مختص."
    ),
    "unsupported_claims": (
        "بعض العبارات في هذه الإجابة غير مدعومة بسند من المصادر المعروضة، "
        "فيرجى التعامل معها بحذر."
    ),
    ReplyKind.CLARIFICATION: "لنتمكن من الإجابة بدقة، نحتاج إلى توضيح بسيط منك.",
    ReplyKind.NO_SOURCE: (
        "لم يُعثر على سند قانوني مؤكد لهذا الاستفسار. يمكنك إعادة صياغة السؤال "
        "أو طلب استشارة محامٍ متخصص."
    ),
    ReplyKind.INVALID_QUESTION: (
        "تعذّر قراءة السؤال. يرجى كتابة سؤالك القانوني بوضوح وباختصار "
        "ثم المحاولة مرة أخرى."
    ),
    ReplyKind.TEMPORARILY_UNAVAILABLE: (
        "المساعد القانوني غير متاح مؤقتاً. حاول مرة أخرى بعد قليل، "
        "أو اطلب استشارة محامٍ متخصص."
    ),
    ReplyKind.ANSWER_FAILED: (
        "تعذّر صياغة إجابة موثّقة لهذا السؤال. حاول مرة أخرى، أو اطلب استشارة محامٍ متخصص."
    ),
}

# Every AnswerFailure must appear here (enforced by tests).
FAILURE_REPLY_KINDS: dict[AnswerFailure, ReplyKind] = {
    AnswerFailure.INVALID_QUESTION: ReplyKind.INVALID_QUESTION,
    AnswerFailure.EMBEDDING_UNAVAILABLE: ReplyKind.TEMPORARILY_UNAVAILABLE,
    AnswerFailure.RETRIEVAL_UNAVAILABLE: ReplyKind.TEMPORARILY_UNAVAILABLE,
    AnswerFailure.PROVIDER_UNAVAILABLE: ReplyKind.TEMPORARILY_UNAVAILABLE,
    AnswerFailure.TIMEOUT: ReplyKind.TEMPORARILY_UNAVAILABLE,
    AnswerFailure.CONFIGURATION_ERROR: ReplyKind.TEMPORARILY_UNAVAILABLE,
    AnswerFailure.INVALID_JSON: ReplyKind.ANSWER_FAILED,
    AnswerFailure.SCHEMA_MISMATCH: ReplyKind.ANSWER_FAILED,
    AnswerFailure.SEMANTIC_INVALID: ReplyKind.ANSWER_FAILED,
}

# (retryable, show_lawyer_cta) per notice kind.
NOTICE_FLAGS: dict[ReplyKind, tuple[bool, bool]] = {
    ReplyKind.ANSWERED: (False, False),
    ReplyKind.CLARIFICATION: (False, False),
    ReplyKind.NO_SOURCE: (False, True),
    ReplyKind.INVALID_QUESTION: (True, False),
    ReplyKind.TEMPORARILY_UNAVAILABLE: (True, True),
    ReplyKind.ANSWER_FAILED: (True, True),
}


class UserNotice(BaseModel):
    """A short Arabic message about the reply, with what the UI may offer."""

    kind: ReplyKind
    message_ar: str
    retryable: bool
    show_lawyer_cta: bool

    model_config = ConfigDict(extra="forbid", frozen=True)


class ReplyClaim(BaseModel):
    """One claim of the answer, as shown to the user."""

    text: str
    source_ids: list[str] = Field(default_factory=list)
    supported: bool

    model_config = ConfigDict(extra="forbid", frozen=True)


class AssistantReply(BaseModel):
    """The assistant's reply, ready to return from a FastAPI endpoint."""

    kind: ReplyKind
    claims: list[ReplyClaim] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    has_unsupported_claims: bool = False
    clarification_question: str | None = None
    notice: UserNotice | None = None
    disclaimer_ar: str = MESSAGES_AR["disclaimer"]

    model_config = ConfigDict(extra="forbid", frozen=True)


def _notice(kind: ReplyKind, message_key: str | None = None) -> UserNotice:
    retryable, show_lawyer_cta = NOTICE_FLAGS[kind]
    return UserNotice(
        kind=kind,
        message_ar=MESSAGES_AR[message_key or kind],
        retryable=retryable,
        show_lawyer_cta=show_lawyer_cta,
    )


def _present_answer(answer: GroundedAnswer) -> AssistantReply:
    if answer.status == AnswerStatus.NO_SOURCE:
        return AssistantReply(
            kind=ReplyKind.NO_SOURCE, notice=_notice(ReplyKind.NO_SOURCE)
        )
    if answer.status == AnswerStatus.NEEDS_CLARIFICATION:
        return AssistantReply(
            kind=ReplyKind.CLARIFICATION,
            clarification_question=answer.clarification_question,
            notice=_notice(ReplyKind.CLARIFICATION),
        )
    return AssistantReply(
        kind=ReplyKind.ANSWERED,
        claims=[
            ReplyClaim(text=c.text, source_ids=c.source_ids, supported=c.supported)
            for c in answer.claims
        ],
        citations=answer.citations,
        has_unsupported_claims=answer.has_unsupported_claims,
        notice=(
            _notice(ReplyKind.ANSWERED, "unsupported_claims")
            if answer.has_unsupported_claims
            else None
        ),
    )


def present_outcome(outcome: AnswerOutcome) -> AssistantReply:
    """The user-facing reply for a chain outcome. Never raises for any outcome."""
    if outcome.ok and outcome.answer is not None:
        reply = _present_answer(outcome.answer)
        logger.info(
            "RAG reply: kind=%s status=%s", reply.kind.value, outcome.answer.status
        )
        return reply

    kind = FAILURE_REPLY_KINDS.get(outcome.failure, ReplyKind.ANSWER_FAILED)
    logger.info(
        "RAG reply: kind=%s failure=%s attempts=%d sources=%d",
        kind.value,
        getattr(outcome.failure, "value", outcome.failure),
        outcome.attempts,
        outcome.source_count,
    )
    return AssistantReply(kind=kind, notice=_notice(kind))
