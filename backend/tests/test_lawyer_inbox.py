"""Unit tests for the lawyer inbox and UTC response timestamps (SCRUM-358)."""

import uuid
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from services.requests.inbox import lawyer_inbox
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.client.schemas import (
    ClientRequestResponse,
    IntakeRequestResponse,
    IntakeResponse,
    SentRequestResponse,
)
from app.core.timestamps import UTCDateTime
from app.db.models import LawyerProfile, Request, User, Workflow
from app.db.session import get_db
from app.lawyer.schemas import LawyerRequestResponse
from app.main import app

NAIVE = datetime(2026, 11, 28, 8, 30, 0, 123456)  # how most columns come back
CAIRO = timezone(timedelta(hours=2))
LAWYER_KEYS = {
    "id",
    "client_id",
    "niche",
    "summary",
    "status",
    "decline_reason",
    "created_at",
    "intake_id",
    "responded_at",
    "case_id",
}


class _Stamp(BaseModel):
    at: UTCDateTime | None = None


@pytest.mark.parametrize(
    "value,expected",
    [
        (NAIVE, "2026-11-28T08:30:00.123456Z"),  # naive is UTC
        (datetime(2026, 11, 28, 10, 30, tzinfo=CAIRO), "2026-11-28T08:30:00Z"),
        (datetime(2026, 11, 28, 8, 30, tzinfo=UTC), "2026-11-28T08:30:00Z"),
        ("2026-11-28T10:30:00+02:00", "2026-11-28T08:30:00Z"),
        (None, None),
    ],
)
def test_utc_datetime_serializes_as_z(value, expected) -> None:
    assert _Stamp(at=value).model_dump(mode="json") == {"at": expected}


def test_utc_datetime_stays_a_datetime_in_python() -> None:
    at = _Stamp(at=NAIVE).at
    assert at == NAIVE.replace(tzinfo=UTC)


def _request(**extra) -> Request:
    return Request(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        lawyer_id=uuid.uuid4(),
        intake_id=uuid.uuid4(),
        status="declined",
        summary={"fields": {}},
        created_at=NAIVE,
        client_confirmed_at=NAIVE,
        responded_at=datetime(2026, 11, 28, 11, 0, tzinfo=CAIRO),
        **extra,
    )


@pytest.mark.parametrize(
    "schema",
    [
        ClientRequestResponse,
        SentRequestResponse,
        IntakeRequestResponse,
        LawyerRequestResponse,
    ],
)
def test_every_sprint5_request_schema_returns_z_timestamps(schema) -> None:
    data = schema.model_validate(_request()).model_dump(mode="json")
    assert data["created_at"] == "2026-11-28T08:30:00.123456Z"
    if "responded_at" in data:
        assert data["responded_at"] == "2026-11-28T09:00:00Z"
    if "client_confirmed_at" in data:
        assert data["client_confirmed_at"] == "2026-11-28T08:30:00.123456Z"


def test_intake_response_returns_z_timestamps() -> None:
    wf = Workflow(
        id=uuid.uuid4(),
        kind="intake",
        status="completed",
        conversation_id=uuid.uuid4(),
        created_at=NAIVE,
        state={
            "phase": "APPROVED",
            "summary": {"approved_at": "2026-11-28T08:45:00.5+00:00"},
        },
    )
    data = IntakeResponse.from_workflow(wf, [_request()]).model_dump(mode="json")
    assert data["created_at"] == "2026-11-28T08:30:00.123456Z"
    assert data["approved_at"] == "2026-11-28T08:45:00.500000Z"
    assert data["request"]["created_at"] == "2026-11-28T08:30:00.123456Z"
    assert data["request"]["responded_at"] == "2026-11-28T09:00:00Z"


def test_lawyer_request_has_only_the_approved_summary_fields() -> None:
    data = LawyerRequestResponse.model_validate(_request()).model_dump(mode="json")
    assert set(data) == LAWYER_KEYS


# --- lawyer_inbox ----------------------------------------------------------------


def _inbox_sql(**kwargs) -> str:
    db = Mock(spec=Session)
    db.scalars.return_value.all.return_value = []
    assert lawyer_inbox(db, uuid.uuid4(), **kwargs) == []
    stmt = db.scalars.call_args.args[0]
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_inbox_query_filters_orders_and_pages() -> None:
    sql = _inbox_sql(status="sent", limit=10, offset=20)
    assert "requests.lawyer_id =" in sql
    assert "requests.status = 'sent'" in sql
    assert "ORDER BY requests.created_at DESC, requests.id DESC" in sql
    assert "LIMIT 10" in sql
    assert "OFFSET 20" in sql


def test_inbox_query_without_status_returns_every_status() -> None:
    sql = _inbox_sql()
    assert "requests.status" not in sql.split("FROM")[1]
    assert "LIMIT 50" in sql


# --- query parameter validation ---------------------------------------------------


@pytest.fixture
def as_lawyer():
    user = User(
        id=uuid.uuid4(), email="l@example.com", role="lawyer", password_hash="h"
    )
    db = Mock(spec=Session)
    db.scalar.return_value = LawyerProfile(id=uuid.uuid4(), user_id=user.id)
    db.scalars.return_value.all.return_value = []
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, db
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "query",
    [
        "status=pending",
        "status=SENT",
        "status=",
        "limit=0",
        "limit=101",
        "limit=abc",
        "offset=-1",
    ],
)
def test_bad_inbox_query_is_422(as_lawyer, query: str) -> None:
    client, db = as_lawyer
    assert client.get(f"/lawyer/requests?{query}").status_code == 422
    db.scalars.assert_not_called()


@pytest.mark.parametrize(
    "query",
    [
        "",
        "status=sent",
        "status=accepted",
        "status=declined",
        "status=expired",
        "status=cancelled",
        "limit=1",
        "limit=100&offset=1000",
    ],
)
def test_good_inbox_query_is_200(as_lawyer, query: str) -> None:
    client, _ = as_lawyer
    resp = client.get(f"/lawyer/requests?{query}")
    assert resp.status_code == 200
    assert resp.json() == []
