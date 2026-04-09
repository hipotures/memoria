"""add screenshot payload and content fragments

Revision ID: 20260409_02
Revises: 20260409_01
Create Date: 2026-04-09 00:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260409_02"
down_revision = "20260409_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_payloads_screenshot",
        sa.Column("source_item_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column("file_extension", sa.String(length=16), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_item_id"),
    )

    op.create_table(
        "content_fragments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_item_id", sa.Integer(), nullable=False),
        sa.Column("fragment_type", sa.String(length=64), nullable=False),
        sa.Column("fragment_ref", sa.String(length=255), nullable=False),
        sa.Column("fragment_text", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "source_item_id",
            "fragment_type",
            "fragment_ref",
            name="uq_content_fragments_identity",
        ),
    )
    op.create_index(
        "ix_content_fragments_source_item_id",
        "content_fragments",
        ["source_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_content_fragments_fragment_type",
        "content_fragments",
        ["fragment_type"],
        unique=False,
    )

    op.execute(
        """
        CREATE VIRTUAL TABLE content_fragments_fts
        USING fts5(fragment_text, content='content_fragments', content_rowid='id')
        """
    )
    op.execute(
        """
        CREATE TRIGGER content_fragments_ai AFTER INSERT ON content_fragments BEGIN
            INSERT INTO content_fragments_fts(rowid, fragment_text)
            VALUES (new.id, new.fragment_text);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER content_fragments_ad AFTER DELETE ON content_fragments BEGIN
            INSERT INTO content_fragments_fts(content_fragments_fts, rowid, fragment_text)
            VALUES ('delete', old.id, old.fragment_text);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER content_fragments_au AFTER UPDATE ON content_fragments BEGIN
            INSERT INTO content_fragments_fts(content_fragments_fts, rowid, fragment_text)
            VALUES ('delete', old.id, old.fragment_text);
            INSERT INTO content_fragments_fts(rowid, fragment_text)
            VALUES (new.id, new.fragment_text);
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS content_fragments_au")
    op.execute("DROP TRIGGER IF EXISTS content_fragments_ad")
    op.execute("DROP TRIGGER IF EXISTS content_fragments_ai")
    op.execute("DROP TABLE IF EXISTS content_fragments_fts")
    op.drop_index("ix_content_fragments_fragment_type", table_name="content_fragments")
    op.drop_index("ix_content_fragments_source_item_id", table_name="content_fragments")
    op.drop_table("content_fragments")
    op.drop_table("source_payloads_screenshot")
