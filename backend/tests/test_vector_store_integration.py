"""Database integration tests for legal chunk storage and vector indexing."""

import os

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db.models import LegalChunk
from app.db.vector_store import (
    EMBEDDING_DIMENSIONS,
    MAX_SEARCH_LIMIT,
    add_legal_chunk,
    search_legal_chunks,
)

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
    if "legal_chunks" not in inspect(engine).get_table_names():
        pytest.fail(
            "Database table 'legal_chunks' does not exist; run alembic upgrade head",
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


def make_embedding(*, first: float, second: float = 0.0) -> list[float]:
    return [first, second] + [0.0] * (EMBEDDING_DIMENSIONS - 2)


def make_chunk(name: str) -> LegalChunk:
    return LegalChunk(source_type="law", source_name=name, text=f"Text from {name}")


def test_store_and_search_legal_chunks_by_cosine_distance(db_session: Session) -> None:
    query = make_embedding(first=1.0)
    nearest = add_legal_chunk(db_session, make_chunk("nearest"), query)
    middle = add_legal_chunk(
        db_session, make_chunk("middle"), make_embedding(first=0.8, second=0.6)
    )
    farthest = add_legal_chunk(
        db_session, make_chunk("farthest"), make_embedding(first=-1.0)
    )
    db_session.add(make_chunk("without embedding"))
    db_session.flush()

    results = search_legal_chunks(db_session, query, limit=2)

    assert [chunk.id for chunk, _distance in results] == [nearest.id, middle.id]
    assert results[0][1] == pytest.approx(0.0)
    assert results[1][1] == pytest.approx(0.2)
    assert farthest.id not in {chunk.id for chunk, _distance in results}


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, MAX_SEARCH_LIMIT + 1])
def test_search_rejects_invalid_limit_without_querying_database(
    db_session: Session, limit
) -> None:
    with pytest.raises(ValueError, match="integer from 1"):
        search_legal_chunks(db_session, make_embedding(first=1.0), limit=limit)


def test_cosine_hnsw_index_is_installed_with_matching_operator_class(test_engine):
    with test_engine.connect() as connection:
        definition = connection.scalar(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'legal_chunks' "
                "AND indexname = 'ix_legal_chunks_embedding_hnsw_cosine'"
            )
        )

    assert definition is not None
    normalized = definition.lower()
    assert "using hnsw" in normalized
    assert "vector_cosine_ops" in normalized
    assert "where (embedding is not null)" in normalized


def test_migration_head_includes_vector_index(test_engine):
    with test_engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))

    assert revision == "9a0c317c9f11"
