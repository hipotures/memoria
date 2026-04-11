"""add atlas projection tables

Revision ID: 20260411_04
Revises: 20260410_03
Create Date: 2026-04-11 18:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260411_04"
down_revision = "20260410_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "atlas_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("atlas_key", sa.String(length=120), nullable=False),
        sa.Column("source_family", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="completed"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_snapshot_id", sa.String(length=120), nullable=True),
        sa.Column("corpus_hash", sa.String(length=120), nullable=True),
        sa.Column("embedding_type", sa.String(length=120), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("embedding_version", sa.String(length=120), nullable=False),
        sa.Column("clustering_method", sa.String(length=120), nullable=False),
        sa.Column("clustering_params_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("random_seed", sa.Integer(), nullable=False, server_default="42"),
        sa.Column(
            "layout_version",
            sa.String(length=120),
            nullable=False,
            server_default="atlas-world-v1",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_atlas_runs_atlas_key", "atlas_runs", ["atlas_key"], unique=False)
    op.create_index("ix_atlas_runs_source_family", "atlas_runs", ["source_family"], unique=False)
    op.create_index("ix_atlas_runs_status", "atlas_runs", ["status"], unique=False)

    op.create_table(
        "atlas_regions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("atlas_run_id", sa.Integer(), nullable=False),
        sa.Column("region_key", sa.String(length=160), nullable=False),
        sa.Column("parent_region_key", sa.String(length=160), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("x", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("y", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("label_x", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("label_y", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("region_shape_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("top_labels_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("top_apps_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("top_people_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("top_entities_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("time_start", sa.DateTime(), nullable=True),
        sa.Column("time_end", sa.DateTime(), nullable=True),
        sa.Column("representatives_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("bridge_neighbors_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("cohesion_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.ForeignKeyConstraint(["atlas_run_id"], ["atlas_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["atlas_run_id", "parent_region_key"],
            ["atlas_regions.atlas_run_id", "atlas_regions.region_key"],
            name="fk_atlas_regions_parent_region",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("atlas_run_id", "region_key", name="uq_atlas_region_identity"),
    )
    op.create_index("ix_atlas_regions_atlas_run_id", "atlas_regions", ["atlas_run_id"], unique=False)
    op.create_index("ix_atlas_regions_parent_region_key", "atlas_regions", ["parent_region_key"], unique=False)
    op.create_index("ix_atlas_regions_region_key", "atlas_regions", ["region_key"], unique=False)

    op.create_table(
        "atlas_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("atlas_run_id", sa.Integer(), nullable=False),
        sa.Column("source_item_id", sa.Integer(), nullable=False),
        sa.Column("region_key", sa.String(length=160), nullable=False),
        sa.Column("subregion_key", sa.String(length=160), nullable=True),
        sa.Column("x", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("y", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("semantic_summary", sa.Text(), nullable=True),
        sa.Column("app_hint", sa.String(length=120), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("object_refs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("is_representative", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("representative_rank", sa.Integer(), nullable=True),
        sa.Column("is_bridge", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("bridge_type", sa.String(length=64), nullable=True),
        sa.Column("secondary_region_key", sa.String(length=160), nullable=True),
        sa.Column("bridge_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("screenshot_detail_url", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["atlas_run_id"], ["atlas_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["atlas_run_id", "region_key"],
            ["atlas_regions.atlas_run_id", "atlas_regions.region_key"],
            name="fk_atlas_items_region",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["atlas_run_id", "subregion_key"],
            ["atlas_regions.atlas_run_id", "atlas_regions.region_key"],
            name="fk_atlas_items_subregion",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("atlas_run_id", "source_item_id", name="uq_atlas_item_identity"),
    )
    op.create_index("ix_atlas_items_atlas_run_id", "atlas_items", ["atlas_run_id"], unique=False)
    op.create_index("ix_atlas_items_region_key", "atlas_items", ["region_key"], unique=False)
    op.create_index("ix_atlas_items_source_item_id", "atlas_items", ["source_item_id"], unique=False)
    op.create_index("ix_atlas_items_subregion_key", "atlas_items", ["subregion_key"], unique=False)

    op.create_table(
        "atlas_edges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("atlas_run_id", sa.Integer(), nullable=False),
        sa.Column("source_region_key", sa.String(length=160), nullable=False),
        sa.Column("target_region_key", sa.String(length=160), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("edge_type", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["atlas_run_id"], ["atlas_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["atlas_run_id", "source_region_key"],
            ["atlas_regions.atlas_run_id", "atlas_regions.region_key"],
            name="fk_atlas_edges_source_region",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["atlas_run_id", "target_region_key"],
            ["atlas_regions.atlas_run_id", "atlas_regions.region_key"],
            name="fk_atlas_edges_target_region",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "atlas_run_id",
            "source_region_key",
            "target_region_key",
            "edge_type",
            name="uq_atlas_edge_identity",
        ),
    )
    op.create_index("ix_atlas_edges_atlas_run_id", "atlas_edges", ["atlas_run_id"], unique=False)
    op.create_index(
        "ix_atlas_edges_source_region_key",
        "atlas_edges",
        ["source_region_key"],
        unique=False,
    )
    op.create_index(
        "ix_atlas_edges_target_region_key",
        "atlas_edges",
        ["target_region_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_atlas_edges_target_region_key", table_name="atlas_edges")
    op.drop_index("ix_atlas_edges_source_region_key", table_name="atlas_edges")
    op.drop_index("ix_atlas_edges_atlas_run_id", table_name="atlas_edges")
    op.drop_table("atlas_edges")
    op.drop_index("ix_atlas_items_subregion_key", table_name="atlas_items")
    op.drop_index("ix_atlas_items_source_item_id", table_name="atlas_items")
    op.drop_index("ix_atlas_items_region_key", table_name="atlas_items")
    op.drop_index("ix_atlas_items_atlas_run_id", table_name="atlas_items")
    op.drop_table("atlas_items")
    op.drop_index("ix_atlas_regions_region_key", table_name="atlas_regions")
    op.drop_index("ix_atlas_regions_parent_region_key", table_name="atlas_regions")
    op.drop_index("ix_atlas_regions_atlas_run_id", table_name="atlas_regions")
    op.drop_table("atlas_regions")
    op.drop_index("ix_atlas_runs_status", table_name="atlas_runs")
    op.drop_index("ix_atlas_runs_source_family", table_name="atlas_runs")
    op.drop_index("ix_atlas_runs_atlas_key", table_name="atlas_runs")
    op.drop_table("atlas_runs")
