"""API integration tests using a disposable PostgreSQL/pgvector database."""

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, inspect
from sqlalchemy.orm import Session

from app.auth.security import create_access_token
from app.db.models import LegalChunk, User
from app.db.session import get_db
from app.db.vector_store import EMBEDDING_DIMENSIONS, add_legal_chunk
from app.main import app

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


@pytest.fixture(scope="session")
def test_engine():
    url = os.environ["TEST_DATABASE_URL"].replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
    engine = create_engine(url, pool_pre_ping=True)
    tables = inspect(engine).get_table_names()
    if not {"users", "legal_chunks"}.issubset(tables):
        pytest.fail(
            "Required database tables are missing; run alembic upgrade head",
            pytrace=False,
        )
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


@pytest.fixture
def client(db_session):
    existing_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(existing_overrides)


@pytest.fixture
def authorization_headers(db_session: Session) -> dict[str, str]:
    user = User(
        id=uuid.uuid4(),
        full_name="Retrieval Test User",
        role="client",
        email=f"retrieval-{uuid.uuid4()}@example.com",
        password_hash="not-used-by-retrieval-tests",
    )
    db_session.add(user)
    db_session.flush()
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


def vector(first: float, second: float = 0.0) -> list[float]:
    return [first, second] + [0.0] * (EMBEDDING_DIMENSIONS - 2)


def clear_legal_chunks(db_session: Session) -> None:
    db_session.execute(delete(LegalChunk))


def test_search_returns_ordered_results_and_citation_metadata(
    client: TestClient, db_session: Session, authorization_headers: dict[str, str]
) -> None:
    clear_legal_chunks(db_session)
    nearest = add_legal_chunk(
        db_session,
        LegalChunk(
            source_type="law",
            source_name="Civil Code",
            article_number="147",
            text="Article text",
            url="https://example.test/civil-code/147",
        ),
        vector(1.0),
    )
    add_legal_chunk(
        db_session,
        LegalChunk(
            source_type="ruling",
            source_name="Published ruling",
            article_number=None,
            text="Ruling text",
        ),
        vector(0.8, 0.6),
    )

    response = client.post(
        "/retrieval/search",
        headers=authorization_headers,
        json={"embedding": vector(1.0), "limit": 2},
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    assert results[0] == {
        "id": str(nearest.id),
        "source_type": "law",
        "source_name": "Civil Code",
        "article_number": "147",
        "source_date": None,
        "url": "https://example.test/civil-code/147",
        "text": "Article text",
        "cosine_distance": pytest.approx(0.0),
    }
    assert results[0]["cosine_distance"] <= results[1]["cosine_distance"]


def test_search_returns_empty_results_when_corpus_has_no_embeddings(
    client: TestClient,
    db_session: Session,
    authorization_headers: dict[str, str],
) -> None:
    clear_legal_chunks(db_session)
    db_session.add(
        LegalChunk(source_type="law", source_name="No vector", text="No vector")
    )
    db_session.flush()

    response = client.post(
        "/retrieval/search",
        headers=authorization_headers,
        json={"embedding": vector(1.0)},
    )

    assert response.status_code == 200
    assert response.json() == {"results": []}


def test_search_requires_authentication(
    client: TestClient,
) -> None:
    response = client.post("/retrieval/search", json={"embedding": vector(1.0)})

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "payload,submitted_value",
    [
        ({"embedding": [7.25] * (EMBEDDING_DIMENSIONS - 1)}, "7.25"),
        (
            {"embedding": [float("nan")] + [0.0] * (EMBEDDING_DIMENSIONS - 1)},
            "NaN",
        ),
        ({"embedding": [0.0] * EMBEDDING_DIMENSIONS}, "0.0"),
    ],
)
def test_search_rejects_invalid_vectors_without_echoing_them(
    client: TestClient,
    authorization_headers: dict[str, str],
    payload: dict[str, object],
    submitted_value: str,
) -> None:
    if submitted_value == "NaN":
        response = client.post(
            "/retrieval/search",
            headers={**authorization_headers, "Content-Type": "application/json"},
            content=json.dumps(payload, allow_nan=True),
        )
    else:
        response = client.post(
            "/retrieval/search", headers=authorization_headers, json=payload
        )

    assert response.status_code == 422
    assert submitted_value not in response.text


@pytest.mark.parametrize("limit", [0, -1, 51, True, 1.5, "2"])
def test_search_rejects_invalid_limits(
    client: TestClient,
    authorization_headers: dict[str, str],
    limit: object,
) -> None:
    response = client.post(
        "/retrieval/search",
        headers=authorization_headers,
        json={"embedding": vector(1.0), "limit": limit},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"embedding": "not a vector"},
        {"embedding": vector(1.0), "unexpected": "field"},
    ],
)
def test_search_rejects_malformed_request_payloads(
    client: TestClient,
    authorization_headers: dict[str, str],
    payload: dict[str, object],
) -> None:
    response = client.post(
        "/retrieval/search", headers=authorization_headers, json=payload
    )

    assert response.status_code == 422
