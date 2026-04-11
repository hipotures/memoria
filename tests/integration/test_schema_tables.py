from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas


def test_initial_schema_includes_screenshot_knowledge_core_tables(tmp_path):
    database_path = tmp_path / "schema.db"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"

    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    asset_interpretation_columns = {
        column["name"] for column in inspector.get_columns("asset_interpretations")
    }
    with engine.connect() as connection:
        sqlite_master = connection.exec_driver_sql(
            "SELECT name, type FROM sqlite_master WHERE name = 'content_fragments_fts'"
        ).fetchall()

    assert {
        "blobs",
        "source_items",
        "source_payloads_screenshot",
        "content_fragments",
        "asset_ocr_texts",
        "asset_interpretations",
        "embeddings",
        "knowledge_objects",
        "knowledge_claims",
        "knowledge_evidence_links",
        "projections",
        "semantic_clusters",
        "semantic_map_points",
        "semantic_map_runs",
        "pipeline_runs",
        "stage_results",
    } <= table_names
    assert sqlite_master == [("content_fragments_fts", "table")]
    assert {
        "cluster_hints_json",
        "entity_mentions_json",
        "raw_model_payload_json",
        "searchable_labels_json",
    } <= asset_interpretation_columns
