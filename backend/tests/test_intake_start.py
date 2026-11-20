"""Tests for starting the client intake workflow from a chat (SCRUM-247/331)."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from services.audit.actions import AuditAction
from services.workflows import intake as intake_mod
from services.workflows.intake import (
    ContextSource,
    IntakeContextError,
    IntakePhase,
    StartIntakeResult,
    SubmittedMessage,
    start_intake,
)
from services.workflows.states import WorkflowKind, WorkflowStatus
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.models import Conversation, Message, User
from app.db.session import get_db
from app.main import app

ANSWER = SubmittedMessage(
    role="assistant",
    content="وفقاً للمادة 111 ...",
    citations=[{"id": "cit-labor-111", "sourceName": "قانون العمل"}],
)
QUESTION = SubmittedMessage(role="user", content="ما مهلة الإخطار؟")


def _client(**kw) -> User:
    return User(
        id=kw.get("id", uuid.uuid4()),
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        role=kw.get("role", "client"),
        password_hash="hash",
    )


def _workflow(**overrides):
    """A stand-in for a Workflow row as the router serializes it."""
    base = dict(
        id=uuid.uuid4(),
        kind="intake",
        status="running",
        conversation_id=uuid.uuid4(),
        state={
            "phase": "INTAKE",
            "context": {
                "source": "client_submitted",
                "messages": [
                    {"role": "user", "content": "سؤال", "citations": []},
                    {"role": "assistant", "content": "إجابة", "citations": []},
                ],
            },
        },
        created_at=datetime.now(UTC),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# --- service ------------------------------------------------------------------


class TestStartIntakeService:
    def test_requires_exactly_one_source(self) -> None:
        db = Mock(spec=Session)
        with pytest.raises(ValueError):
            start_intake(db, client_id=uuid.uuid4())
        with pytest.raises(ValueError):
            start_intake(
                db,
                client_id=uuid.uuid4(),
                conversation=Conversation(id=uuid.uuid4()),
                submitted_messages=[ANSWER],
            )

    def test_rejects_chat_without_an_answer(self) -> None:
        db = Mock(spec=Session)
        blank_answer = SubmittedMessage(role="assistant", content="   ")
        with pytest.raises(IntakeContextError):
            start_intake(
                db, client_id=uuid.uuid4(), submitted_messages=[QUESTION, blank_answer]
            )
        db.add.assert_not_called()

    def test_submitted_chat_is_saved_snapshotted_and_set_to_intake(self) -> None:
        db = Mock(spec=Session)
        client_id = uuid.uuid4()
        run = SimpleNamespace(id=uuid.uuid4())
        running = SimpleNamespace(id=run.id, status="running")

        with (
            patch.object(intake_mod, "create_run", return_value=run) as create_run,
            patch.object(intake_mod, "transition", return_value=running) as trans,
            patch.object(intake_mod, "log_event") as log_event,
        ):
            result = start_intake(
                db, client_id=client_id, submitted_messages=[QUESTION, ANSWER]
            )

        assert result.created is True
        assert result.workflow is running

        # The browser chat is persisted as a qa conversation with its messages.
        added = [c.args[0] for c in db.add.call_args_list]
        convs = [o for o in added if isinstance(o, Conversation)]
        msgs = [o for o in added if isinstance(o, Message)]
        assert len(convs) == 1
        assert convs[0].user_id == client_id and convs[0].type == "qa"
        assert [m.sender for m in msgs] == ["user", "assistant"]

        # Workflow is an intake linked to that conversation, with the snapshot.
        args, kwargs = create_run.call_args
        assert args[1] == WorkflowKind.INTAKE
        assert kwargs["conversation_id"] == convs[0].id
        context = kwargs["state"]["context"]
        assert context["source"] == ContextSource.CLIENT_SUBMITTED.value
        assert [m["content"] for m in context["messages"]] == [
            QUESTION.content,
            ANSWER.content,
        ]
        assert context["messages"][1]["citations"][0]["id"] == "cit-labor-111"

        # Started is audited, then moved to running with phase INTAKE.
        assert log_event.call_args.kwargs["action"] == AuditAction.WORKFLOW_STARTED
        assert log_event.call_args.kwargs["actor_id"] == client_id
        t_args, t_kwargs = trans.call_args
        assert t_args[2] == WorkflowStatus.RUNNING
        assert t_kwargs["state_patch"] == {"phase": IntakePhase.INTAKE.value}
        assert t_kwargs["actor_id"] == client_id

    def test_saved_conversation_reuses_active_intake(self) -> None:
        db = Mock(spec=Session)
        existing = SimpleNamespace(id=uuid.uuid4())
        conv = Conversation(id=uuid.uuid4(), user_id=uuid.uuid4(), type="qa")

        with (
            patch.object(intake_mod, "find_active_intake", return_value=existing),
            patch.object(intake_mod, "create_run") as create_run,
        ):
            result = start_intake(db, client_id=conv.user_id, conversation=conv)

        assert result == StartIntakeResult(workflow=existing, created=False)
        create_run.assert_not_called()

    def test_saved_conversation_snapshot_is_trusted_source(self) -> None:
        db = Mock(spec=Session)
        conv = Conversation(id=uuid.uuid4(), user_id=uuid.uuid4(), type="qa")
        rows = [
            Message(sender="user", content="س", citations=None),
            Message(sender="assistant", content="ج", citations=[{"id": "c1"}]),
        ]
        db.scalars.return_value.all.return_value = rows

        with (
            patch.object(intake_mod, "find_active_intake", return_value=None),
            patch.object(
                intake_mod, "create_run", return_value=SimpleNamespace(id=uuid.uuid4())
            ) as create_run,
            patch.object(intake_mod, "transition"),
            patch.object(intake_mod, "log_event"),
        ):
            start_intake(db, client_id=conv.user_id, conversation=conv)

        db.add.assert_not_called()  # nothing new to persist
        context = create_run.call_args.kwargs["state"]["context"]
        assert context["source"] == ContextSource.SERVER.value
        assert context["conversation_id"] == str(conv.id)
        assert context["messages"][0]["citations"] == []
        assert context["messages"][1]["citations"] == [{"id": "c1"}]


# --- API ----------------------------------------------------------------------

CHAT = {
    "messages": [
        {"role": "user", "content": "ما مهلة الإخطار؟"},
        {
            "role": "assistant",
            "content": "وفقاً للمادة 111 ...",
            "citations": [
                {
                    "id": "cit-labor-111",
                    "sourceType": "تشريع مصري",
                    "sourceName": "قانون العمل",
                    "articleNumber": "المادة 111",
                    "text": "يجب أن يتم الإخطار...",
                }
            ],
        },
    ]
}


@pytest.fixture
def api():
    """Yields (client, set_user, db) with auth and DB overridden."""
    db = Mock(spec=Session)
    state = {"user": _client()}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    app.dependency_overrides[get_db] = lambda: db

    def set_user(user: User) -> None:
        state["user"] = user

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, set_user, db
    finally:
        app.dependency_overrides.clear()


class TestStartIntakeEndpoint:
    def test_unauthenticated_returns_401(self) -> None:
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.post("/client/intakes", json=CHAT).status_code == 401

    def test_lawyer_cannot_start_intake(self, api) -> None:
        client, set_user, _ = api
        set_user(_client(role="lawyer"))
        assert client.post("/client/intakes", json=CHAT).status_code == 403

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"conversation_id": str(uuid.uuid4()), **CHAT},
            {"messages": []},
            {"messages": [{"role": "system", "content": "x"}]},
            {"messages": [{"role": "user", "content": "x" * 20_001}]},
        ],
        ids=["no-source", "both-sources", "empty", "bad-role", "too-long"],
    )
    def test_invalid_body_returns_422(self, api, body) -> None:
        client, _, _ = api
        assert client.post("/client/intakes", json=body).status_code == 422

    def test_starts_intake_from_browser_chat(self, api) -> None:
        client, _, _ = api
        wf = _workflow()
        with patch(
            "app.client.router.start_intake",
            return_value=StartIntakeResult(workflow=wf, created=True),
        ) as start:
            resp = client.post("/client/intakes", json=CHAT)

        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == str(wf.id)
        assert data["kind"] == "intake"
        assert data["status"] == "running"
        assert data["phase"] == "INTAKE"
        assert data["context_source"] == "client_submitted"
        assert len(data["context_messages"]) == 2

        kwargs = start.call_args.kwargs
        assert kwargs["conversation"] is None
        sent = kwargs["submitted_messages"]
        assert [m.role for m in sent] == ["user", "assistant"]
        # Citations keep the frontend's field names in the snapshot.
        assert sent[1].citations[0]["articleNumber"] == "المادة 111"

    def test_existing_active_intake_returns_200(self, api) -> None:
        client, set_user, db = api
        user = _client()
        set_user(user)
        conv = Conversation(id=uuid.uuid4(), user_id=user.id, type="qa")
        db.scalar.return_value = conv
        with patch(
            "app.client.router.start_intake",
            return_value=StartIntakeResult(workflow=_workflow(), created=False),
        ):
            resp = client.post(
                "/client/intakes", json={"conversation_id": str(conv.id)}
            )
        assert resp.status_code == 200

    def test_no_answer_yet_returns_422(self, api) -> None:
        client, _, _ = api
        with patch(
            "app.client.router.start_intake",
            side_effect=IntakeContextError("no answer"),
        ):
            resp = client.post("/client/intakes", json=CHAT)
        assert resp.status_code == 422

    def test_other_clients_conversation_is_forbidden(self, api) -> None:
        client, _, db = api
        db.scalar.return_value = Conversation(
            id=uuid.uuid4(), user_id=uuid.uuid4(), type="qa"
        )
        with patch("app.client.router.start_intake") as start:
            resp = client.post(
                "/client/intakes", json={"conversation_id": str(uuid.uuid4())}
            )
        assert resp.status_code == 403
        start.assert_not_called()

    def test_non_qa_conversation_is_rejected(self, api) -> None:
        client, set_user, db = api
        user = _client()
        set_user(user)
        db.scalar.return_value = Conversation(
            id=uuid.uuid4(), user_id=user.id, type="case_research"
        )
        with patch("app.client.router.start_intake") as start:
            resp = client.post(
                "/client/intakes", json={"conversation_id": str(uuid.uuid4())}
            )
        assert resp.status_code == 422
        start.assert_not_called()


class TestGetIntakeEndpoint:
    def test_owner_can_read_intake(self, api) -> None:
        client, set_user, db = api
        user = _client()
        set_user(user)
        wf = _workflow()
        conv = Conversation(id=wf.conversation_id, user_id=user.id, type="qa")
        db.scalar.side_effect = [wf, conv]
        resp = client.get(f"/client/intakes/{wf.id}")
        assert resp.status_code == 200
        assert resp.json()["phase"] == "INTAKE"

    def test_other_client_is_forbidden(self, api) -> None:
        client, _, db = api
        wf = _workflow()
        conv = Conversation(id=wf.conversation_id, user_id=uuid.uuid4(), type="qa")
        db.scalar.side_effect = [wf, conv]
        assert client.get(f"/client/intakes/{wf.id}").status_code == 403

    def test_missing_intake_returns_404(self, api) -> None:
        client, _, db = api
        db.scalar.return_value = None
        assert client.get(f"/client/intakes/{uuid.uuid4()}").status_code == 404
