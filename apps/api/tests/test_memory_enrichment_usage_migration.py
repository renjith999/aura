import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "c6b7e24a901d_memory_enrichment_usage.py"
)


def load_migration():
    spec = importlib.util.spec_from_file_location(
        "memory_enrichment_usage_migration", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_usage_migration_backfills_generations_and_downgrades(monkeypatch):
    migration = load_migration()
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE memories (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE memory_enrichments ("
                "memory_id VARCHAR(36) PRIMARY KEY, "
                "FOREIGN KEY(memory_id) REFERENCES memories(id))"
            )
        )
        connection.execute(text("INSERT INTO memories (id) VALUES ('m-1'), ('m-2')"))
        connection.execute(
            text("INSERT INTO memory_enrichments (memory_id) VALUES ('m-1'), ('m-2')")
        )
        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(migration, "op", operations)

        migration.upgrade()
        generations = (
            connection.execute(
                text("SELECT generation_id FROM memory_enrichments ORDER BY memory_id")
            )
            .scalars()
            .all()
        )
        assert len(generations) == 2
        assert all(generations)
        assert len(set(generations)) == 2
        assert "memory_enrichment_attempts" in inspect(connection).get_table_names()

        migration.downgrade()
        assert "memory_enrichment_attempts" not in inspect(connection).get_table_names()
        assert "generation_id" not in {
            column["name"]
            for column in inspect(connection).get_columns("memory_enrichments")
        }
    engine.dispose()
