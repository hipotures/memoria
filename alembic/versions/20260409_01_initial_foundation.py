"""initial screenshot vertical slice foundation

Revision ID: 20260409_01
Revises:
Create Date: 2026-04-09 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260409_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("storage_kind", sa.String(length=32), nullable=False, server_default="local"),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_blobs_sha256", "blobs", ["sha256"], unique=True)

    op.create_table(
        "source_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_family", sa.String(length=32), nullable=False),
        sa.Column("connector_instance_id", sa.String(length=128), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("dedup_key", sa.String(length=255), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_created_at", sa.DateTime(), nullable=True),
        sa.Column("source_observed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("raw_ref", sa.Text(), nullable=True),
        sa.Column("blob_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["blob_id"], ["blobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("dedup_key", name="uq_source_items_dedup_key"),
    )
    op.create_index("ix_source_items_blob_id", "source_items", ["blob_id"], unique=False)
    op.create_index("ix_source_items_source_family", "source_items", ["source_family"], unique=False)
    op.create_index("ix_source_items_source_type", "source_items", ["source_type"], unique=False)

    op.create_table(
        "asset_ocr_texts",
        sa.Column("source_item_id", sa.Integer(), nullable=False),
        sa.Column("engine_name", sa.String(length=64), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("language_hint", sa.String(length=16), nullable=True),
        sa.Column("block_map_json", sa.Text(), nullable=False, server_default="[]"),
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
        sa.PrimaryKeyConstraint("source_item_id"),
    )

    op.create_table(
        "asset_interpretations",
        sa.Column("source_item_id", sa.Integer(), nullable=False),
        sa.Column("screen_category", sa.String(length=64), nullable=False),
        sa.Column("semantic_summary", sa.Text(), nullable=False),
        sa.Column("app_hint", sa.String(length=64), nullable=True),
        sa.Column("topic_candidates_json", sa.Text(), nullable=False),
        sa.Column("task_candidates_json", sa.Text(), nullable=False),
        sa.Column("person_candidates_json", sa.Text(), nullable=False),
        sa.Column("confidence_json", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("source_item_id"),
    )

    op.create_table(
        "knowledge_objects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_confirmed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("slug", name="uq_knowledge_objects_slug"),
    )
    op.create_index(
        "ix_knowledge_objects_object_type",
        "knowledge_objects",
        ["object_type"],
        unique=False,
    )

    op.create_table(
        "knowledge_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("claim_type", sa.String(length=32), nullable=False),
        sa.Column("subject_ref", sa.String(length=255), nullable=False),
        sa.Column("predicate", sa.String(length=64), nullable=False),
        sa.Column("object_ref_or_value", sa.String(length=512), nullable=False),
        sa.Column(
            "asserted_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_confirmed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("evidence_set_id", sa.String(length=64), nullable=False),
        sa.UniqueConstraint(
            "claim_type",
            "subject_ref",
            "predicate",
            "object_ref_or_value",
            name="uq_knowledge_claim_identity",
        ),
    )
    op.create_index(
        "ix_knowledge_claims_subject_ref",
        "knowledge_claims",
        ["subject_ref"],
        unique=False,
    )

    op.create_table(
        "knowledge_evidence_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("claim_id", sa.Integer(), nullable=False),
        sa.Column("source_item_id", sa.Integer(), nullable=False),
        sa.Column("fragment_type", sa.String(length=64), nullable=False),
        sa.Column("fragment_ref", sa.String(length=255), nullable=False),
        sa.Column("interpretation_ref", sa.String(length=255), nullable=True),
        sa.Column("support_role", sa.String(length=32), nullable=False, server_default="primary"),
        sa.ForeignKeyConstraint(["claim_id"], ["knowledge_claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "claim_id",
            "source_item_id",
            "fragment_type",
            "fragment_ref",
            name="uq_knowledge_evidence_identity",
        ),
    )
    op.create_index(
        "ix_knowledge_evidence_links_claim_id",
        "knowledge_evidence_links",
        ["claim_id"],
        unique=False,
    )

    op.create_table(
        "projections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("object_ref", sa.String(length=255), nullable=False),
        sa.Column("projection_type", sa.String(length=64), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("object_ref", "projection_type", name="uq_projection_identity"),
    )

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_item_id", sa.Integer(), nullable=False),
        sa.Column("pipeline_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("run_reason", sa.String(length=64), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_pipeline_runs_source_item_id", "pipeline_runs", ["source_item_id"], unique=False)

    op.create_table(
        "stage_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=False),
        sa.Column("stage_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("output_json", sa.Text(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("pipeline_run_id", "stage_name", "attempt", name="uq_stage_attempt"),
    )
    op.create_index("ix_stage_results_pipeline_run_id", "stage_results", ["pipeline_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_stage_results_pipeline_run_id", table_name="stage_results")
    op.drop_table("stage_results")
    op.drop_index("ix_pipeline_runs_source_item_id", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
    op.drop_table("projections")
    op.drop_index(
        "ix_knowledge_evidence_links_claim_id",
        table_name="knowledge_evidence_links",
    )
    op.drop_table("knowledge_evidence_links")
    op.drop_index("ix_knowledge_claims_subject_ref", table_name="knowledge_claims")
    op.drop_table("knowledge_claims")
    op.drop_index("ix_knowledge_objects_object_type", table_name="knowledge_objects")
    op.drop_table("knowledge_objects")
    op.drop_table("asset_interpretations")
    op.drop_table("asset_ocr_texts")
    op.drop_index("ix_source_items_source_type", table_name="source_items")
    op.drop_index("ix_source_items_source_family", table_name="source_items")
    op.drop_index("ix_source_items_blob_id", table_name="source_items")
    op.drop_table("source_items")
    op.drop_index("ix_blobs_sha256", table_name="blobs")
    op.drop_table("blobs")
