"""add interpretation extras embeddings and semantic map tables

Revision ID: 20260410_03
Revises: 20260409_02
Create Date: 2026-04-10 15:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260410_03"
down_revision = "20260409_02"
branch_labels = None
depends_on = None

_EMBEDDING_DIMENSION = 96


def upgrade() -> None:
    op.add_column(
        "asset_interpretations",
        sa.Column("entity_mentions_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "asset_interpretations",
        sa.Column("searchable_labels_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "asset_interpretations",
        sa.Column("cluster_hints_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "asset_interpretations",
        sa.Column("raw_model_payload_json", sa.Text(), nullable=False, server_default="{}"),
    )

    op.create_table(
        "embeddings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_item_id", sa.Integer(), nullable=True),
        sa.Column("object_ref", sa.String(length=255), nullable=True),
        sa.Column("embedding_type", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_embeddings_source_item_id", "embeddings", ["source_item_id"], unique=False)
    op.create_index("ix_embeddings_object_ref", "embeddings", ["object_ref"], unique=False)

    op.create_table(
        "semantic_map_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("map_key", sa.String(length=64), nullable=False),
        sa.Column("source_family", sa.String(length=32), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_semantic_map_runs_map_key", "semantic_map_runs", ["map_key"], unique=False)
    op.create_index(
        "ix_semantic_map_runs_source_family",
        "semantic_map_runs",
        ["source_family"],
        unique=False,
    )

    op.create_table(
        "semantic_clusters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("map_run_id", sa.Integer(), nullable=False),
        sa.Column("cluster_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("centroid_x", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("centroid_y", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["map_run_id"], ["semantic_map_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("map_run_id", "cluster_key", name="uq_semantic_cluster_identity"),
    )
    op.create_index("ix_semantic_clusters_map_run_id", "semantic_clusters", ["map_run_id"], unique=False)

    op.create_table(
        "semantic_map_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("map_run_id", sa.Integer(), nullable=False),
        sa.Column("source_item_id", sa.Integer(), nullable=False),
        sa.Column("cluster_key", sa.String(length=128), nullable=True),
        sa.Column("x", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("y", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("score_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["map_run_id"], ["semantic_map_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("map_run_id", "source_item_id", name="uq_semantic_map_point_identity"),
    )
    op.create_index("ix_semantic_map_points_map_run_id", "semantic_map_points", ["map_run_id"], unique=False)
    op.create_index(
        "ix_semantic_map_points_source_item_id",
        "semantic_map_points",
        ["source_item_id"],
        unique=False,
    )

    op.execute(
        f"""
        CREATE VIRTUAL TABLE embedding_vec_items
        USING vec0(
            embedding_id integer primary key,
            embedding float[{_EMBEDDING_DIMENSION}]
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS embedding_vec_items")
    op.drop_index("ix_semantic_map_points_source_item_id", table_name="semantic_map_points")
    op.drop_index("ix_semantic_map_points_map_run_id", table_name="semantic_map_points")
    op.drop_table("semantic_map_points")
    op.drop_index("ix_semantic_clusters_map_run_id", table_name="semantic_clusters")
    op.drop_table("semantic_clusters")
    op.drop_index("ix_semantic_map_runs_source_family", table_name="semantic_map_runs")
    op.drop_index("ix_semantic_map_runs_map_key", table_name="semantic_map_runs")
    op.drop_table("semantic_map_runs")
    op.drop_index("ix_embeddings_object_ref", table_name="embeddings")
    op.drop_index("ix_embeddings_source_item_id", table_name="embeddings")
    op.drop_table("embeddings")
    op.drop_column("asset_interpretations", "raw_model_payload_json")
    op.drop_column("asset_interpretations", "cluster_hints_json")
    op.drop_column("asset_interpretations", "searchable_labels_json")
    op.drop_column("asset_interpretations", "entity_mentions_json")
