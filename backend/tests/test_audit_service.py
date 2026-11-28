"""Unit tests for the audit service (SCRUM-276).

Covers: event creation, action validation, append-only behavior,
ownership-filtered listing, and the action vocabulary.
"""

import uuid
from unittest.mock import Mock, patch

import pytest
from services.audit.actions import VALID_ACTIONS, AuditAction
from services.audit.service import (
    InvalidAuditActionError,
    list_events_for_user,
    log_event,
)
from sqlalchemy.orm import Session

from app.db.models import (
    AuditEvent,
    Case,
    LawyerProfile,
    Request,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def actor_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def case_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def request_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def workflow_id() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# AuditAction enum tests
# ---------------------------------------------------------------------------


class TestAuditActionEnum:
    def test_all_actions_are_strings(self) -> None:
        for action in AuditAction:
            assert isinstance(action.value, str)
            assert "." in action.value  # e.g. "ai.proposal_generated"

    def test_valid_actions_set_matches_enum(self) -> None:
        assert VALID_ACTIONS == {a.value for a in AuditAction}

    def test_required_event_types_present(self) -> None:
        """Acceptance criteria: AI proposals, tool calls, approvals,
        request transitions, case edits."""
        required = {
            "ai.proposal_generated",
            "ai.tool_call",
            "approval.requested",
            "approval.approved",
            "approval.rejected",
            "request.created",
            "request.accepted",
            "request.declined",
            "request.cancelled",
            "case.created",
            "case.notes_updated",
            "workflow.started",
            "workflow.transition",
            "workflow.completed",
        }
        assert required.issubset(VALID_ACTIONS)


# ---------------------------------------------------------------------------
# log_event tests
# ---------------------------------------------------------------------------


class TestLogEvent:
    def test_creates_audit_event_with_all_fields(
        self,
        actor_id: uuid.UUID,
        case_id: uuid.UUID,
        request_id: uuid.UUID,
        workflow_id: uuid.UUID,
    ) -> None:
        """log_event creates an AuditEvent with actor, time, workflow_id."""
        db = Mock(spec=Session)
        event = log_event(
            db,
            actor_id=actor_id,
            action=AuditAction.CASE_NOTES_UPDATED,
            case_id=case_id,
            request_id=request_id,
            workflow_id=workflow_id,
            before={"notes": "old"},
            after={"notes": "new"},
        )
        assert isinstance(event, AuditEvent)
        assert event.actor_id == actor_id
        assert event.action == "case.notes_updated"
        assert event.case_id == case_id
        assert event.request_id == request_id
        assert event.workflow_id == workflow_id
        assert event.before == {"notes": "old"}
        assert event.after == {"notes": "new"}
        db.add.assert_called_once_with(event)
        db.flush.assert_called_once()

    def test_minimal_event(self, actor_id: uuid.UUID) -> None:
        """log_event works with only required fields."""
        db = Mock(spec=Session)
        event = log_event(
            db,
            actor_id=actor_id,
            action=AuditAction.REQUEST_CREATED,
        )
        assert event.case_id is None
        assert event.request_id is None
        assert event.workflow_id is None
        assert event.before is None
        assert event.after is None

    def test_rejects_invalid_action(self, actor_id: uuid.UUID) -> None:
        """log_event raises InvalidAuditActionError for unknown actions."""
        db = Mock(spec=Session)
        with pytest.raises(InvalidAuditActionError, match="Unknown audit action"):
            log_event(db, actor_id=actor_id, action="not.a.real.action")
        db.add.assert_not_called()

    def test_append_only_no_update_no_delete(self) -> None:
        """The service module has no update or delete function."""
        import services.audit.service as mod

        public_names = [n for n in dir(mod) if not n.startswith("_")]
        for name in public_names:
            assert "update" not in name.lower()
            assert "delete" not in name.lower()
            assert "remove" not in name.lower()


# ---------------------------------------------------------------------------
# list_events_for_user tests
# ---------------------------------------------------------------------------


class TestListEventsForUser:
    def test_admin_sees_all(self) -> None:
        """Admin should see all events without ownership filtering."""
        admin_id = uuid.uuid4()
        db = Mock(spec=Session)
        events = [Mock(spec=AuditEvent)]
        db.scalars.return_value = Mock()
        db.scalars.return_value.__iter__ = Mock(return_value=iter(events))

        # We mock the query chain — admin path applies no ownership filter
        with patch("services.audit.service.select") as mock_select:
            mock_stmt = Mock()
            mock_select.return_value = mock_stmt
            mock_stmt.where.return_value = mock_stmt
            mock_stmt.order_by.return_value = mock_stmt
            mock_stmt.offset.return_value = mock_stmt
            mock_stmt.limit.return_value = mock_stmt

            mock_scalars = Mock()
            mock_scalars.__iter__ = Mock(return_value=iter(events))
            db.scalars.return_value = mock_scalars

            result = list_events_for_user(db, admin_id, "admin")
            assert result == events

    def test_unknown_role_returns_empty(self) -> None:
        """Unknown roles should get empty results."""
        db = Mock(spec=Session)
        result = list_events_for_user(db, uuid.uuid4(), "unknown_role")
        assert result == []

    def test_lawyer_without_profile_returns_empty(self) -> None:
        """Lawyer without a profile should get empty results."""
        db = Mock(spec=Session)
        db.scalar.return_value = None  # No LawyerProfile found
        result = list_events_for_user(db, uuid.uuid4(), "lawyer")
        assert result == []

    def test_lawyer_cannot_see_other_lawyers_case_events(self) -> None:
        """Lawyer asking for another lawyer's case gets empty results."""
        lawyer_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        other_case_id = uuid.uuid4()

        profile = LawyerProfile(id=profile_id, user_id=lawyer_id)
        other_case = Case(
            id=other_case_id,
            request_id=uuid.uuid4(),
            lawyer_id=uuid.uuid4(),  # Different lawyer
            status="open",
        )
        db = Mock(spec=Session)
        db.scalar.side_effect = [profile, other_case]

        result = list_events_for_user(db, lawyer_id, "lawyer", case_id=other_case_id)
        assert result == []

    def test_client_cannot_see_other_clients_request_events(self) -> None:
        """Client asking for another client's request gets empty results."""
        client_id = uuid.uuid4()
        other_request_id = uuid.uuid4()

        other_request = Request(
            id=other_request_id,
            client_id=uuid.uuid4(),  # Different client
            lawyer_id=uuid.uuid4(),
            status="sent",
        )
        db = Mock(spec=Session)
        db.scalar.return_value = other_request

        result = list_events_for_user(
            db, client_id, "client", request_id=other_request_id
        )
        assert result == []
