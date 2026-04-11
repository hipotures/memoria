from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas


def _column_names(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _unique_constraint_columns(inspector, table_name: str) -> set[tuple[str, ...]]:
    return {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table_name)
    }


def _foreign_key_signatures(inspector, table_name: str) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(foreign_key["constrained_columns"]),
            foreign_key["referred_table"],
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys(table_name)
    }


def test_initial_schema_includes_screenshot_knowledge_core_tables(tmp_path):
    database_path = tmp_path / "schema.db"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"

    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    asset_interpretation_columns = _column_names(inspector, "asset_interpretations")
    atlas_run_columns = _column_names(inspector, "atlas_runs")
    atlas_region_columns = _column_names(inspector, "atlas_regions")
    atlas_item_columns = _column_names(inspector, "atlas_items")
    atlas_edge_columns = _column_names(inspector, "atlas_edges")
    atlas_region_unique_constraints = _unique_constraint_columns(inspector, "atlas_regions")
    atlas_item_unique_constraints = _unique_constraint_columns(inspector, "atlas_items")
    atlas_edge_unique_constraints = _unique_constraint_columns(inspector, "atlas_edges")
    atlas_region_foreign_keys = _foreign_key_signatures(inspector, "atlas_regions")
    atlas_item_foreign_keys = _foreign_key_signatures(inspector, "atlas_items")
    atlas_edge_foreign_keys = _foreign_key_signatures(inspector, "atlas_edges")
    with engine.connect() as connection:
        sqlite_master = connection.exec_driver_sql(
            "SELECT name, type FROM sqlite_master WHERE name = 'content_fragments_fts'"
        ).fetchall()

    assert {
        "atlas_edges",
        "atlas_items",
        "atlas_regions",
        "atlas_runs",
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
    assert {
        "atlas_key",
        "clustering_method",
        "clustering_params_json",
        "completed_at",
        "corpus_hash",
        "created_at",
        "embedding_model",
        "embedding_type",
        "embedding_version",
        "layout_version",
        "published_at",
        "random_seed",
        "source_count",
        "source_family",
        "source_snapshot_id",
        "status",
    } <= atlas_run_columns
    assert {
        "atlas_run_id",
        "bridge_neighbors_json",
        "cohesion_score",
        "item_count",
        "label_x",
        "label_y",
        "level",
        "parent_region_key",
        "region_key",
        "region_shape_json",
        "representatives_json",
        "time_end",
        "time_start",
        "title",
        "top_apps_json",
        "top_entities_json",
        "top_labels_json",
        "top_people_json",
        "x",
        "y",
    } <= atlas_region_columns
    assert {
        "app_hint",
        "atlas_run_id",
        "bridge_score",
        "bridge_type",
        "is_bridge",
        "is_representative",
        "object_refs_json",
        "observed_at",
        "region_key",
        "representative_rank",
        "screenshot_detail_url",
        "secondary_region_key",
        "semantic_summary",
        "source_item_id",
        "subregion_key",
        "x",
        "y",
    } <= atlas_item_columns
    assert {
        "atlas_run_id",
        "edge_type",
        "source_region_key",
        "target_region_key",
        "weight",
    } <= atlas_edge_columns
    assert ("atlas_run_id", "region_key") in atlas_region_unique_constraints
    assert ("atlas_run_id", "source_item_id") in atlas_item_unique_constraints
    assert (
        "atlas_run_id",
        "source_region_key",
        "target_region_key",
        "edge_type",
    ) in atlas_edge_unique_constraints
    assert (
        ("atlas_run_id",),
        "atlas_runs",
        ("id",),
    ) in atlas_region_foreign_keys
    assert (
        ("atlas_run_id", "parent_region_key"),
        "atlas_regions",
        ("atlas_run_id", "region_key"),
    ) in atlas_region_foreign_keys
    assert (
        ("atlas_run_id",),
        "atlas_runs",
        ("id",),
    ) in atlas_item_foreign_keys
    assert (
        ("source_item_id",),
        "source_items",
        ("id",),
    ) in atlas_item_foreign_keys
    assert (
        ("atlas_run_id", "region_key"),
        "atlas_regions",
        ("atlas_run_id", "region_key"),
    ) in atlas_item_foreign_keys
    assert (
        ("atlas_run_id", "subregion_key"),
        "atlas_regions",
        ("atlas_run_id", "region_key"),
    ) in atlas_item_foreign_keys
    assert (
        ("atlas_run_id", "secondary_region_key"),
        "atlas_regions",
        ("atlas_run_id", "region_key"),
    ) in atlas_item_foreign_keys
    assert (
        ("atlas_run_id",),
        "atlas_runs",
        ("id",),
    ) in atlas_edge_foreign_keys
    assert (
        ("atlas_run_id", "source_region_key"),
        "atlas_regions",
        ("atlas_run_id", "region_key"),
    ) in atlas_edge_foreign_keys
    assert (
        ("atlas_run_id", "target_region_key"),
        "atlas_regions",
        ("atlas_run_id", "region_key"),
    ) in atlas_edge_foreign_keys
