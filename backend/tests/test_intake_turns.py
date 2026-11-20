"""Persisting intake turns and the turns endpoint (SCRUM-248 / 334)."""

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from services.audit.actions import AuditAction
from services.intake import service as svc
from services.intake.agent import new_intake_state
from services.intake.service import IntakeConflictError, IntakeTurnError, take_turn
from services.llm.providers.mock import MockLLMProvider
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.client.router import get_intake_provider
from app.db.models import Conversation, User
from app.db.session import get_db
from app.main import app

CHAT = [
    {"role": "user", "content": "صاحب العمل فصلني من غير إخطار", "citations": []},
    {"role": "assistant", "content": "وفقاً للمادة 111 من قانون العمل", "citations": []},
]


def run(intake=None, **overrides):
    state = {"phase": "INTAKE", "context": {"messages": CHAT}}
    if intake is not None:
        state["intake"] = intake
    base = dict(
        id=uuid.uuid4(),
        kind="intake",
        status="running",
        conversation_id=uuid.uuid4(),
        state=state,
        created_at=datetime.now(UTC),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def opened_intake() -> dict:
    intake = new_intake_state()
    intake["turns"] = [{"role": "agent", "content": "احكِ لي", "field": "facts"}]
    intake["asked"] = {"facts": 1}
    intake["agent_questions"] = 1
    return intake


# --- service ----------------------------------------------------------------


@pytest.mark.anyio
class TestTakeTurn:
    async def test_opening_saves_state_and_audits(self) -> None:
        db = Mock(spec=Session)
        r = run()
        provider = MockLLMProvider(default_response="garbage")
        with (
            patch.object(svc, "get_run", side_effect=[r, r]),
            patch.object(svc, "log_event") as log_event,
        ):
            saved, outcome = await take_turn(
                db, provider, r.id, actor_id=uuid.uuid4(), client_message=None
            )

        assert saved.state["intake"]["turns"][0]["role"] == "agent"
        assert saved.state["context"]["messages"] == CHAT  # snapshot kept
        db.commit.assert_called_once()
        kwargs = log_event.call_args.kwargs
        assert kwargs["action"] == AuditAction.AI_PROPOSAL_GENERATED
        assert kwargs["after"]["kind"] == "intake_turn"
        assert kwargs["after"]["source"] == "template"
        # Audit records what happened, never the client's words.
        assert "فصلني" not in json.dumps(kwargs["after"], ensure_ascii=False)

    async def test_opening_uses_only_the_clients_chat_messages(self) -> None:
        db = Mock(spec=Session)
        r = run()
        provider = MockLLMProvider(default_response="garbage")
        with (
            patch.object(svc, "get_run", side_effect=[r, r]),
            patch.object(svc, "log_event"),
        ):
            await take_turn(
                db, provider, r.id, actor_id=uuid.uuid4(), client_message=None
            )
        sent = json.loads(provider.recorded_calls[0][1].content)
        assert "فصلني" in sent["client_latest_message"]
        assert "المادة 111" not in sent["client_latest_message"]

    async def test_cannot_open_twice(self) -> None:
        r = run(intake=opened_intake())
        with patch.object(svc, "get_run", return_value=r):
            with pytest.raises(IntakeTurnError):
                await take_turn(
                    Mock(spec=Session),
                    MockLLMProvider(),
                    r.id,
                    actor_id=uuid.uuid4(),
                    client_message=None,
                )

    async def test_cannot_answer_before_opening(self) -> None:
        r = run()
        with patch.object(svc, "get_run", return_value=r):
            with pytest.raises(IntakeTurnError):
                await take_turn(
                    Mock(spec=Session),
                    MockLLMProvider(),
                    r.id,
                    actor_id=uuid.uuid4(),
                    client_message="مرحبا",
                )

    @pytest.mark.parametrize(
        "overrides",
        [
            {"status": "completed"},
            {"kind": "case_prep"},
            {"state": {"phase": "SUMMARY_REVIEW"}},
        ],
    )
    async def test_rejects_runs_not_in_intake(self, overrides) -> None:
        r = run(intake=opened_intake(), **overrides)
        with patch.object(svc, "get_run", return_value=r):
            with pytest.raises(IntakeTurnError):
                await take_turn(
                    Mock(spec=Session),
                    MockLLMProvider(),
                    r.id,
                    actor_id=uuid.uuid4(),
                    client_message="x",
                )

    async def test_rejects_completed_intake(self) -> None:
        intake = opened_intake()
        intake["complete"] = True
        r = run(intake=intake)
        with patch.object(svc, "get_run", return_value=r):
            with pytest.raises(IntakeTurnError):
                await take_turn(
                    Mock(spec=Session),
                    MockLLMProvider(),
                    r.id,
                    actor_id=uuid.uuid4(),
                    client_message="x",
                )

    async def test_concurrent_answer_is_a_conflict(self) -> None:
        db = Mock(spec=Session)
        before = run(intake=opened_intake())
        moved_on = opened_intake()
        moved_on["turns"].append({"role": "client", "content": "x", "field": None})
        after = run(intake=moved_on, id=before.id)
        with (
            patch.object(svc, "get_run", side_effect=[before, after]),
            patch.object(svc, "log_event") as log_event,
        ):
            with pytest.raises(IntakeConflictError):
                await take_turn(
                    db,
                    MockLLMProvider(default_response="garbage"),
                    before.id,
                    actor_id=uuid.uuid4(),
                    client_message="القاهرة",
                )
        db.commit.assert_not_called()
        log_event.assert_not_called()


# --- endpoint ---------------------------------------------------------------


@pytest.fixture
def api():
    db = Mock(spec=Session)
    user = User(
        id=uuid.uuid4(), email="c@example.com", role="client", password_hash="h"
    )
    provider = MockLLMProvider(default_response="garbage")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_intake_provider] = lambda: provider
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, user, db
    finally:
        app.dependency_overrides.clear()


def own(db, user, wf) -> None:
    db.scalar.side_effect = [
        wf,
        Conversation(id=wf.conversation_id, user_id=user.id, type="qa"),
    ]


class TestTurnsEndpoint:
    def test_opening_returns_first_question_and_fields(self, api) -> None:
        client, user, db = api
        wf = run()
        own(db, user, wf)
        opened = run(intake=opened_intake(), id=wf.id)
        with patch(
            "app.client.router.take_turn",
            return_value=(opened, SimpleNamespace()),
        ) as take:
            resp = client.post(f"/client/intakes/{wf.id}/turns", json={"content": None})

        assert resp.status_code == 200
        data = resp.json()
        assert data["turns"][0] == {
            "role": "agent",
            "content": "احكِ لي",
            "field": "facts",
        }
        assert data["fields"]["city"] == {"status": "missing", "value": None}
        assert data["complete"] is False
        assert take.call_args.kwargs["client_message"] is None

    def test_turn_error_is_409(self, api) -> None:
        client, user, db = api
        wf = run()
        own(db, user, wf)
        with patch(
            "app.client.router.take_turn", side_effect=IntakeTurnError("complete")
        ):
            resp = client.post(f"/client/intakes/{wf.id}/turns", json={"content": "x"})
        assert resp.status_code == 409

    def test_empty_answer_is_422(self, api) -> None:
        client, _, _ = api
        resp = client.post(
            f"/client/intakes/{uuid.uuid4()}/turns", json={"content": ""}
        )
        assert resp.status_code == 422

    def test_other_clients_intake_is_403(self, api) -> None:
        client, _, db = api
        wf = run()
        db.scalar.side_effect = [
            wf,
            Conversation(id=wf.conversation_id, user_id=uuid.uuid4(), type="qa"),
        ]
        with patch("app.client.router.take_turn") as take:
            resp = client.post(f"/client/intakes/{wf.id}/turns", json={"content": "x"})
        assert resp.status_code == 403
        take.assert_not_called()

    def test_get_includes_intake_progress(self, api) -> None:
        client, user, db = api
        wf = run(intake=opened_intake())
        own(db, user, wf)
        data = client.get(f"/client/intakes/{wf.id}").json()
        assert data["turns"][0]["field"] == "facts"
        assert set(data["fields"]) >= {"facts", "niche", "budget", "preferred_times"}
