"""Opt-in AURA-62 PostgreSQL migration and atomic-claim integration tests.

Set AURA62_POSTGRES_TEST_URL to a disposable database whose name ends in
``_aura62_test``. Each test creates and drops its own randomly named schema.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.memory import Memory
from app.models.memory_enrichment import MemoryEnrichment
from app.models.memory_enrichment_attempt import MemoryEnrichmentAttempt
from app.repositories.memory_enrichment_repository import MemoryEnrichmentRepository

API_ROOT = Path(__file__).parents[1]
PRE_USAGE_REVISION = "b59a14d6e320"


@pytest.fixture
def postgres_schema(monkeypatch):
    raw_url = os.getenv("AURA62_POSTGRES_TEST_URL")
    if not raw_url:
        pytest.skip("Set AURA62_POSTGRES_TEST_URL to a disposable PostgreSQL test DB.")
    base_url = make_url(raw_url)
    if base_url.get_backend_name() != "postgresql":
        pytest.fail("AURA62_POSTGRES_TEST_URL must use PostgreSQL.")
    if not base_url.database or not base_url.database.endswith("_aura62_test"):
        pytest.fail("PostgreSQL test DB name must end with _aura62_test.")

    schema = f"aura62_{uuid4().hex}"
    admin_engine = create_engine(base_url)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    scoped_url = base_url.set(
        query={**base_url.query, "options": f"-csearch_path={schema}"}
    )
    monkeypatch.setenv("DATABASE_URL", scoped_url.render_as_string(hide_password=False))
    try:
        yield scoped_url, schema
    finally:
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


def test_postgres_usage_migration_contract_and_downgrade(postgres_schema):
    scoped_url, schema = postgres_schema
    config = Config(str(API_ROOT / "alembic.ini"))
    command.upgrade(config, PRE_USAGE_REVISION)
    engine = create_engine(scoped_url)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO memories "
                "(id,title,content,category,is_favorite,user_id,created_at,updated_at) "
                "VALUES ('memory-legacy','Legacy','Keep this text','work',false,"
                "'user-1',:now,:now)"
            ),
            {"now": now},
        )
        connection.execute(
            text(
                "INSERT INTO memory_enrichments "
                "(memory_id,tags,entities,schema_version,prompt_version,model,"
                "source_content_hash,created_at,updated_at) VALUES "
                "('memory-legacy','[]'::jsonb,'[]'::jsonb,'1.0.0','1.4.0',"
                "'gpt-5-mini','source-hash',:now,:now)"
            ),
            {"now": now},
        )

    command.upgrade(config, "head")
    inspector = inspect(engine)
    assert "memory_enrichment_attempts" in inspector.get_table_names(schema=schema)
    assert "generation_id" in {
        column["name"]
        for column in inspector.get_columns("memory_enrichments", schema=schema)
    }
    with engine.begin() as connection:
        generation = connection.scalar(
            text(
                "SELECT generation_id FROM memory_enrichments "
                "WHERE memory_id='memory-legacy'"
            )
        )
        assert generation
        indexes = {
            item["name"]
            for item in inspector.get_indexes(
                "memory_enrichment_attempts", schema=schema
            )
        }
        assert "ix_memory_enrichment_attempts_memory_id" in indexes
        assert "ix_memory_enrichment_attempts_generation_id" in indexes
        foreign_keys = inspector.get_foreign_keys(
            "memory_enrichment_attempts", schema=schema
        )
        assert any(
            fk["constrained_columns"] == ["memory_id"]
            and fk["options"].get("ondelete") == "SET NULL"
            for fk in foreign_keys
        )
        insert_attempt = text(
            "INSERT INTO memory_enrichment_attempts "
            "(id,memory_id,generation_id,attempt_number,requested_model,schema_version,"
            "prompt_version,source_content_hash,pricing_version,"
            "started_at,recorded_at) "
            "VALUES (:id,'memory-legacy',:generation,1,'gpt-5-mini','1.0.0','1.4.0',"
            "'source-hash','pricing-v1',:now,:now)"
        )
    with engine.begin() as connection:
        connection.execute(
            insert_attempt,
            {"id": str(uuid4()), "generation": generation, "now": now},
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as duplicate_connection:
            duplicate_connection.execute(
                insert_attempt,
                {"id": str(uuid4()), "generation": generation, "now": now},
            )
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM memories WHERE id='memory-legacy'"))
        retained = connection.execute(
            text("SELECT memory_id FROM memory_enrichment_attempts")
        ).scalar_one()
        assert retained is None

    command.downgrade(config, PRE_USAGE_REVISION)
    inspector = inspect(engine)
    assert "memory_enrichment_attempts" not in inspector.get_table_names(schema=schema)
    assert "generation_id" not in {
        column["name"]
        for column in inspector.get_columns("memory_enrichments", schema=schema)
    }
    engine.dispose()


def test_postgres_concurrent_workers_claim_one_job(postgres_schema):
    scoped_url, _schema = postgres_schema
    engine = create_engine(scoped_url, pool_size=4, max_overflow=0)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        memory = Memory(
            title="Atomic claim",
            content="Original content remains unchanged.",
            category="work",
            is_favorite=False,
            user_id="user-1",
        )
        session.add(memory)
        session.flush()
        memory_id = memory.id
        repository = MemoryEnrichmentRepository(session)
        repository.create_or_reset_pending(
            memory_id,
            memory.content,
            schema_version="1.0.0",
            prompt_version="1.4.0",
            model="gpt-5-mini",
        )
        session.commit()

    gate = Barrier(2)

    def claim_job():
        with Session(engine) as session:
            gate.wait(timeout=5)
            return MemoryEnrichmentRepository(session).claim(memory_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _index: claim_job(), range(2)))

    assert sum(claim is not None for claim in claims) == 1
    with Session(engine) as session:
        assert (
            session.get(Memory, memory_id).content
            == "Original content remains unchanged."
        )
        assert (
            session.query(MemoryEnrichmentAttempt)
            .filter_by(memory_id=memory_id)
            .count()
            == 1
        )
        assert session.get(MemoryEnrichment, memory_id).status == "processing"
    engine.dispose()
