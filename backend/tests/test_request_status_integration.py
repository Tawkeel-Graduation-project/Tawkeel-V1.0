"""Database tests for the request status model (SCRUM-346).

Covers the CHECK constraint and server default, ``transition_request`` against a
real row (status + audit event), and the migration's upgrade/downgrade.
"""

import os
import uuid

import pytest
from alembic.config import Config
from services.requests.service import transition_request
from services.requests.states import InvalidRequestTransitionError
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.db.models import AuditEvent, LawyerProfile, Request, User

test_db_url = os.environ.get("TEST_DATABASE_URL")
if not test_db_url:
    if os.environ.get("CI"):
        pytest.fail(
            "TEST_DATABASE_URL is required in CI but was not set.", pytrace=False
        )
    pytest.skip(
        "TEST_DATABASE_URL is not set; skipping database integration tests.",
        allow_module_level=True,
    )

MIGRATION = "c3e8f0a2d417"
PREVIOUS = "b7d4e2f1a9c3"


@pytest.fixture(scope="module")
def test_engine():
    url = os.environ["TEST_DATABASE_URL"].replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
    engine = create_engine(url, pool_pre_ping=True)
    if "requests" not in inspect(engine).get_table_names():
        pytest.fail("Table 'requests' missing; run alembic upgrade head", pytrace=False)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def _parties(session: Session) -> tuple[User, LawyerProfile]:
    tag = uuid.uuid4().hex[:8]
    client = User(role="client", email=f"c-{tag}@example.com", password_hash="x")
    lawyer = User(role="lawyer", email=f"l-{tag}@example.com", password_hash="x")
    session.add_all([client, lawyer])
    session.flush()
    profile = LawyerProfile(user_id=lawyer.id)
    session.add(profile)
    session.flush()
    return client, profile


def test_new_request_defaults_to_sent(db_session: Session) -> None:
    client, profile = _parties(db_session)
    request_id = uuid.uuid4()
    db_session.execute(
        text("INSERT INTO requests (id, client_id, lawyer_id) VALUES (:i, :c, :l)"),
        {"i": request_id, "c": client.id, "l": profile.id},
    )
    status = db_session.scalar(
        text("SELECT status FROM requests WHERE id = :i"), {"i": request_id}
    )
    assert status == "sent"


@pytest.mark.parametrize("bad", ["pending", "approved", "SENT", ""])
def test_check_constraint_rejects_other_values(db_session: Session, bad: str) -> None:
    client, profile = _parties(db_session)
    db_session.add(Request(client_id=client.id, lawyer_id=profile.id, status=bad))
    with pytest.raises(IntegrityError, match="ck_requests_status"):
        db_session.flush()


def test_transition_request_persists_status_and_audit(db_session: Session) -> None:
    client, profile = _parties(db_session)
    req = Request(client_id=client.id, lawyer_id=profile.id)
    db_session.add(req)
    db_session.flush()

    transition_request(db_session, req, "accepted", profile.user_id)
    db_session.flush()

    assert db_session.scalar(select(Request.status).where(Request.id == req.id)) == (
        "accepted"
    )
    event = db_session.scalars(
        select(AuditEvent).where(AuditEvent.request_id == req.id)
    ).one()
    assert event.action == "request.accepted"
    assert event.actor_id == profile.user_id
    assert (event.before, event.after) == ({"status": "sent"}, {"status": "accepted"})

    with pytest.raises(InvalidRequestTransitionError):
        transition_request(db_session, req, "declined", profile.user_id)


def _alembic_config(monkeypatch: pytest.MonkeyPatch) -> Config:
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    return Config("alembic.ini")


def _constraint_names(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_check_constraints("requests")}


def _status_default(engine) -> str | None:
    columns = inspect(engine).get_columns("requests")
    return next(c["default"] for c in columns if c["name"] == "status")


def test_migration_downgrade_and_upgrade(test_engine, monkeypatch) -> None:
    config = _alembic_config(monkeypatch)
    with test_engine.connect() as conn:
        # At MIGRATION or a later head (e.g. SCRUM-344's d5a1c9e7b203).
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) != (
            PREVIOUS
        )

    with Session(test_engine) as session:
        client, profile = _parties(session)
        sent = Request(client_id=client.id, lawyer_id=profile.id)
        session.add(sent)
        session.commit()
        ids = {"client": client.id, "lawyer": profile.user_id, "profile": profile.id}
        sent_id = sent.id
    legacy_id = uuid.uuid4()

    try:
        command.downgrade(config, PREVIOUS)
        assert "ck_requests_status" not in _constraint_names(test_engine)
        assert _status_default(test_engine) is None
        with test_engine.begin() as conn:
            assert conn.scalar(
                text("SELECT status FROM requests WHERE id = :i"), {"i": sent_id}
            ) == ("pending")
            conn.execute(
                text(
                    "INSERT INTO requests (id, client_id, lawyer_id, status) "
                    "VALUES (:i, :c, :l, 'pending')"
                ),
                {"i": legacy_id, "c": ids["client"], "l": ids["profile"]},
            )

        command.upgrade(config, "head")
        assert "ck_requests_status" in _constraint_names(test_engine)
        assert "sent" in _status_default(test_engine)
        with test_engine.connect() as conn:
            statuses = conn.scalars(
                text("SELECT status FROM requests WHERE id IN (:a, :b)"),
                {"a": sent_id, "b": legacy_id},
            ).all()
        assert statuses == ["sent", "sent"]
    finally:
        command.upgrade(config, "head")
        with test_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM requests WHERE id IN (:a, :b)"),
                {"a": sent_id, "b": legacy_id},
            )
            conn.execute(
                text("DELETE FROM lawyer_profiles WHERE id = :p"), {"p": ids["profile"]}
            )
            conn.execute(
                text("DELETE FROM users WHERE id IN (:a, :b)"),
                {"a": ids["client"], "b": ids["lawyer"]},
            )
