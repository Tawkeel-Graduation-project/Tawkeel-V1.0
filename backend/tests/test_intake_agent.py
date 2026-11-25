"""Intake agent: guardrails and scripted conversations (SCRUM-248 / 334 / 335).

The model is a scripted MockLLMProvider: each call returns the next JSON
proposal, so these tests pin down what the *code* does with each proposal.
"""

import json

import pytest
from services.intake.agent import (
    ASK_LIMIT_REQUIRED,
    CLOSING_TEXT,
    MAX_AGENT_QUESTIONS,
    OPENING_TEXT,
    new_intake_state,
    next_missing,
    run_turn,
)
from services.intake.fields import (
    ALL_FIELDS,
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    TEMPLATE_QUESTIONS,
    IntakeField,
)
from services.intake.niches import NICHE_LABELS, SELECTABLE_NICHES, Niche, parse_niche
from services.intake.prompts import build_messages, build_system_prompt
from services.llm.providers.mock import MockLLMProvider

F = IntakeField
GARBAGE = "not json at all"


def prop(action="ask", target=None, question=None, declined=None, **fields) -> str:
    return json.dumps(
        {
            "fields": fields,
            "declined": declined or [],
            "action": action,
            "target_field": target,
            "question": question,
        },
        ensure_ascii=False,
    )


def model(*responses: str) -> MockLLMProvider:
    return MockLLMProvider(response_sequence=list(responses))


def status(state, f: IntakeField) -> str:
    return state["fields"][f.value]["status"]


def value(state, f: IntakeField):
    return state["fields"][f.value]["value"]


async def opened(provider=None, context=None):
    """An intake after the opening turn (asks FACTS via template by default)."""
    out = await run_turn(
        provider or model(GARBAGE, GARBAGE),
        new_intake_state(),
        None,
        opening_context=context,
    )
    return out


def with_fields(**values) -> dict:
    """A state where the given fields are already provided."""
    state = new_intake_state()
    for key, v in values.items():
        state["fields"][key] = {"status": "provided", "value": v}
    return state


# --- niche list and fields (SCRUM-333 / 334) --------------------------------


class TestNichesAndFields:
    def test_ten_selectable_niches_plus_unsure(self) -> None:
        assert len(SELECTABLE_NICHES) == 10
        assert Niche.UNSURE not in SELECTABLE_NICHES
        assert set(NICHE_LABELS) == set(Niche)

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("labor", Niche.LABOR),
            (" LABOR ", Niche.LABOR),
            ("عمل وعمال", Niche.LABOR),
            ("اقتصادي", Niche.ECONOMIC),
            ("family", None),
            ("", None),
            (None, None),
            (3, None),
        ],
    )
    def test_parse_niche(self, raw, expected) -> None:
        assert parse_niche(raw) is expected

    def test_seven_required_three_optional(self) -> None:
        assert REQUIRED_FIELDS == (
            F.FACTS,
            F.NICHE,
            F.PARTIES,
            F.KEY_DATES,
            F.URGENCY,
            F.CITY,
            F.BUDGET,
        )
        assert OPTIONAL_FIELDS == (F.DOCUMENTS, F.DEADLINES, F.PREFERRED_TIMES)
        assert set(TEMPLATE_QUESTIONS) == set(ALL_FIELDS)

    def test_new_state_is_all_missing(self) -> None:
        state = new_intake_state()
        assert all(
            v == {"status": "missing", "value": None} for v in state["fields"].values()
        )
        assert state["turns"] == [] and state["complete"] is False
        assert next_missing(state["fields"]) is F.FACTS

    def test_niche_template_lists_every_choice(self) -> None:
        for niche in SELECTABLE_NICHES:
            assert NICHE_LABELS[niche] in TEMPLATE_QUESTIONS[F.NICHE]


# --- prompt (SCRUM-335) -----------------------------------------------------


class TestPrompt:
    def test_system_prompt_has_rules_niches_and_fields(self) -> None:
        prompt = build_system_prompt()
        assert "never give legal advice" in prompt
        assert "Never invent" in prompt
        assert "Never copy facts from the legal assistant" in prompt
        for niche in Niche:
            assert niche.value in prompt
        for f in ALL_FIELDS:
            assert f.value in prompt

    def test_messages_carry_state_and_latest_message(self) -> None:
        state = new_intake_state()
        msgs = build_messages(
            state["fields"], [], "صاحب العمل فصلني", last_target="facts"
        )
        user_content = msgs[1].content
        assert "<intake_state>" in user_content
        assert "<conversation_history>" in user_content
        assert "<client_message>\nصاحب العمل فصلني\n</client_message>" in user_content
        state_inner = user_content[
            user_content.index("<intake_state>")
            + len("<intake_state>") : user_content.index("</intake_state>")
        ].strip()
        payload = json.loads(state_inner)
        assert payload["last_question_was_about"] == "facts"
        assert payload["current_fields"]["city"]["status"] == "missing"
        assert "UNTRUSTED DATA" in msgs[0].content


# --- opening turn -----------------------------------------------------------


@pytest.mark.anyio
class TestOpening:
    async def test_prefills_from_chat_and_uses_agent_question(self) -> None:
        provider = model(
            prop(
                target="parties",
                question="من هو صاحب العمل الذي فصلك؟",
                facts="تم فصلي من العمل دون إخطار",
                niche="labor",
            )
        )
        out = await opened(provider, context=["صاحب العمل فصلني من غير إخطار"])

        assert out.source == "agent" and out.model_ok
        assert out.agent_message.startswith(OPENING_TEXT)
        assert out.target_field == "parties"
        assert value(out.state, F.NICHE) == "labor"
        assert out.state["asked"] == {"parties": 1}
        assert out.state["turns"][-1]["role"] == "agent"
        # The chat text was sent to the model inside the <client_message> block.
        user_content = provider.recorded_calls[0][1].content
        assert "<client_message>" in user_content
        client_block = user_content[user_content.index("<client_message>") :]
        assert "فصلني" in client_block

    async def test_model_failure_falls_back_to_first_template(self) -> None:
        out = await opened(model(GARBAGE, GARBAGE), context=["سؤال"])
        assert out.source == "template" and not out.model_ok
        assert out.target_field == "facts"
        assert TEMPLATE_QUESTIONS[F.FACTS] in out.agent_message

    async def test_no_chat_context_skips_the_model(self) -> None:
        provider = model()
        out = await opened(provider, context=[])
        assert provider.recorded_calls == []
        assert out.target_field == "facts"

    async def test_input_state_is_not_mutated(self) -> None:
        state = new_intake_state()
        await run_turn(model(GARBAGE, GARBAGE), state, None, opening_context=["x"])
        assert state == new_intake_state()


# --- code guardrails over the agent's proposal ------------------------------


@pytest.mark.anyio
class TestGuardrails:
    async def test_invalid_niche_and_urgency_are_dropped(self) -> None:
        start = await opened()
        out = await run_turn(
            model(
                prop(
                    target="parties",
                    question="من الأطراف؟",
                    facts="فصل تعسفي",
                    niche="family",
                    urgency="ASAP",
                )
            ),
            start.state,
            "اتفصلت",
        )
        assert value(out.state, F.FACTS) == "فصل تعسفي"
        assert status(out.state, F.NICHE) == "missing"
        assert status(out.state, F.URGENCY) == "missing"
        assert "dropped_invalid:niche" in out.overrides
        assert "dropped_invalid:urgency" in out.overrides

    async def test_arabic_urgency_words_map_to_enum(self) -> None:
        start = await opened()
        out = await run_turn(
            model(prop(target="city", question="في أي مدينة؟", urgency="خلال أيام")),
            start.state,
            "عندي جلسة بعد يومين",
        )
        assert value(out.state, F.URGENCY) == "urgent"

    async def test_finish_is_rejected_while_required_missing(self) -> None:
        start = await opened()
        out = await run_turn(
            model(prop(action="finish", facts="مشكلة في الإيجار")), start.state, "..."
        )
        assert out.complete is False
        assert out.source == "template"
        assert out.target_field == "niche"  # next missing required field
        assert "question_rejected:finish_rejected" in out.overrides

    @pytest.mark.parametrize(
        "target,question,reason",
        [
            ("documents", "ما المستندات؟", "optional_before_required"),
            ("salary", "كم راتبك؟", "unknown_field"),
            ("parties", "Who is your employer?", "bad_question"),
            ("parties", "", "bad_question"),
            ("parties", "س" * 401, "bad_question"),
        ],
    )
    async def test_bad_agent_questions_fall_back_to_template(
        self, target, question, reason
    ) -> None:
        start = await opened()
        out = await run_turn(
            model(prop(target=target, question=question, facts="وقائع")),
            start.state,
            "وقائع",
        )
        assert out.source == "template"
        assert out.target_field == "niche"
        assert f"question_rejected:{reason}" in out.overrides

    async def test_one_clarifying_follow_up_per_provided_field(self) -> None:
        state = with_fields(facts="فصلني صاحب العمل")
        state["turns"] = [{"role": "agent", "content": "؟", "field": "facts"}]
        first = await run_turn(
            model(prop(target="facts", question="متى وكيف تم إبلاغك بالفصل؟")),
            state,
            "فصلني",
        )
        assert first.source == "agent" and first.target_field == "facts"

        second = await run_turn(
            model(prop(target="facts", question="هل يمكنك التوضيح أكثر؟")),
            first.state,
            "بالتليفون",
        )
        assert second.source == "template"
        assert "question_rejected:already_clarified" in second.overrides

    async def test_declined_field_becomes_not_provided_and_is_not_reasked(
        self,
    ) -> None:
        start = await opened()
        out = await run_turn(
            model(
                prop(
                    target="budget",
                    question="وما ميزانيتك؟",
                    facts="نزاع إيجار",
                    declined=["budget", "nonsense"],
                )
            ),
            start.state,
            "مش عارف الميزانية",
        )
        assert status(out.state, F.BUDGET) == "not_provided"
        assert value(out.state, F.BUDGET) is None
        assert "question_rejected:field_declined" in out.overrides
        assert "dropped_invalid:nonsense" in out.overrides

    async def test_unsure_niche_stays_missing_until_list_was_shown(self) -> None:
        start = await opened()
        out = await run_turn(
            model(
                prop(
                    target="niche",
                    question="ما نوع مشكلتك؟",
                    facts="مشكلة",
                    niche="unsure",
                )
            ),
            start.state,
            "مشكلة",
        )
        assert status(out.state, F.NICHE) == "missing"
        assert out.target_field == "niche"

        after_list = await run_turn(
            model(prop(target="parties", question="من الأطراف؟", niche="unsure")),
            out.state,
            "غير متأكد",
        )
        assert status(after_list.state, F.NICHE) == "not_provided"

    async def test_required_field_given_up_after_ask_limit(self) -> None:
        start = await opened()
        state = start.state
        # FACTS asked once already; client answers vaguely twice.
        for _ in range(ASK_LIMIT_REQUIRED):
            out = await run_turn(
                model(prop(target="facts", question="ممكن توضح أكثر؟")), state, "..."
            )
            state = out.state
        assert status(state, F.FACTS) == "not_provided"
        assert out.target_field != "facts"


# --- model failing mid-conversation: no answer is lost ----------------------


@pytest.mark.anyio
class TestModelFailureMidway:
    async def ask(self, target: IntakeField, answer: str):
        state = new_intake_state()
        state["turns"] = [{"role": "agent", "content": "؟", "field": target.value}]
        state["asked"] = {target.value: 1}
        return await run_turn(model(GARBAGE, GARBAGE), state, answer)

    async def test_raw_answer_is_stored_for_the_asked_field(self) -> None:
        out = await self.ask(F.CITY, "القاهرة، مدينة نصر")
        assert value(out.state, F.CITY) == "القاهرة، مدينة نصر"
        assert out.source == "template" and not out.model_ok

    async def test_decline_words_become_not_provided(self) -> None:
        out = await self.ask(F.BUDGET, "مش عارف")
        assert status(out.state, F.BUDGET) == "not_provided"

    async def test_none_is_an_answer_for_documents(self) -> None:
        out = await self.ask(F.DOCUMENTS, "لا يوجد")
        assert status(out.state, F.DOCUMENTS) == "provided"
        assert value(out.state, F.DOCUMENTS) == "لا يوجد"

    async def test_niche_and_urgency_parsed_from_free_text(self) -> None:
        niche = await self.ask(F.NICHE, "أعتقد أنها عمل وعمال")
        assert value(niche.state, F.NICHE) == "labor"
        urgency = await self.ask(F.URGENCY, "مش عاجل خالص")
        assert value(urgency.state, F.URGENCY) == "normal"


# --- whole conversations ----------------------------------------------------


@pytest.mark.anyio
class TestConversations:
    async def test_labor_case_end_to_end_with_agent(self) -> None:
        provider = model(
            # opening: pre-fill from the chat question
            prop(
                target="parties",
                question="من هو صاحب العمل؟",
                facts="فُصلت من العمل دون إخطار",
                niche="labor",
            ),
            prop(
                target="key_dates",
                question="متى تم فصلك؟",
                parties="شركة النور للمقاولات (صاحب العمل)",
            ),
            prop(
                target="urgency",
                question="هل الأمر عاجل؟",
                key_dates="تم الفصل في ١ أكتوبر ٢٠٢٦",
            ),
            prop(target="city", question="في أي مدينة؟", urgency="soon"),
            prop(target="budget", question="ما ميزانيتك؟", city="الجيزة"),
            prop(
                target="documents",
                question="ما المستندات لديك؟",
                budget="من ٢٠٠٠ إلى ٥٠٠٠ جنيه",
            ),
            prop(
                target="deadlines",
                question="هل هناك جلسة قريبة؟",
                documents="عقد العمل وخطاب الفصل",
            ),
            prop(
                target="preferred_times",
                question="متى يناسبك اللقاء؟",
                declined=["deadlines"],
            ),
            prop(action="finish", preferred_times="مساء أيام الأحد"),
        )
        out = await opened(provider, context=["ما مهلة الإخطار لإنهاء عقد العمل؟"])
        answers = [
            "شركة النور للمقاولات",
            "أول أكتوبر",
            "خلال أسابيع",
            "الجيزة",
            "من ٢٠٠٠ لـ ٥٠٠٠",
            "عقد العمل وخطاب الفصل",
            "مش عارف",
            "مساء الأحد",
        ]
        for answer in answers:
            assert not out.complete
            assert out.source == "agent"
            out = await run_turn(provider, out.state, answer)

        assert out.complete and out.source == "closing"
        assert out.agent_message == CLOSING_TEXT
        state = out.state
        assert state["complete"] is True
        assert value(state, F.NICHE) == "labor"
        assert value(state, F.URGENCY) == "soon"
        assert status(state, F.DEADLINES) == "not_provided"
        assert next_missing(state["fields"]) is None
        assert state["agent_questions"] == 8  # opening + 7 follow-ups
        # Every turn alternates agent/client and ends with the closing message.
        roles = [t["role"] for t in state["turns"]]
        assert roles[0] == "agent" and roles[-1] == "agent"

    async def test_completes_with_templates_when_model_always_fails(self) -> None:
        provider = MockLLMProvider(default_response=GARBAGE)
        answers = {
            "facts": "المالك يرفض رد التأمين",
            "niche": "عقارات وإيجارات",
            "parties": "المالك وأنا المستأجر",
            "key_dates": "انتهى العقد في سبتمبر",
            "urgency": "غير عاجل",
            "city": "الإسكندرية",
            "budget": "مش متأكد",
            "documents": "عقد الإيجار",
            "deadlines": "لا يوجد",
            "preferred_times": "أي وقت",
        }
        out = await opened(provider, context=["هل يحق للمالك حجز التأمين؟"])
        guard = 0
        while not out.complete:
            guard += 1
            assert guard <= MAX_AGENT_QUESTIONS
            out = await run_turn(provider, out.state, answers[out.target_field])

        state = out.state
        assert value(state, F.NICHE) == "real_estate"
        assert value(state, F.URGENCY) == "normal"
        assert value(state, F.CITY) == "الإسكندرية"
        assert status(state, F.BUDGET) == "not_provided"
        assert value(state, F.DEADLINES) == "لا يوجد"

    async def test_question_cap_ends_intake_with_not_provided(self) -> None:
        provider = MockLLMProvider(default_response=GARBAGE)
        out = await opened(provider)
        state = out.state
        state["agent_questions"] = MAX_AGENT_QUESTIONS
        out = await run_turn(provider, state, "...")
        assert out.complete
        assert "max_questions_reached" in out.overrides
        assert all(v["status"] != "missing" for v in out.state["fields"].values())

    async def test_never_invents_missing_values(self) -> None:
        """Whatever wasn't said ends as not_provided with value None."""
        provider = MockLLMProvider(default_response=GARBAGE)
        out = await opened(provider)
        while not out.complete:
            out = await run_turn(provider, out.state, "مش عارف")
        for v in out.state["fields"].values():
            assert v == {"status": "not_provided", "value": None}
