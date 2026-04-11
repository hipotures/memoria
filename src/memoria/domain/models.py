from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy import func
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column


class Base(DeclarativeBase):
    pass


class Blob(Base):
    __tablename__ = "blobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    media_type: Mapped[str] = mapped_column(String(128))
    byte_size: Mapped[int] = mapped_column(Integer)
    storage_kind: Mapped[str] = mapped_column(String(32), default="local")
    storage_uri: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)


class SourceItem(Base):
    __tablename__ = "source_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    source_family: Mapped[str] = mapped_column(String(32), index=True)
    connector_instance_id: Mapped[str] = mapped_column(String(128))
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dedup_key: Mapped[str] = mapped_column(String(255), unique=True)
    mode: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    source_observed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)
    raw_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    blob_id: Mapped[int] = mapped_column(ForeignKey("blobs.id", ondelete="CASCADE"), index=True)


class SourcePayloadScreenshot(Base):
    __tablename__ = "source_payloads_screenshot"

    source_item_id: Mapped[int] = mapped_column(
        ForeignKey("source_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(128))
    file_extension: Mapped[str] = mapped_column(String(16))
    metadata_json: Mapped[str] = mapped_column(Text, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)


class ContentFragment(Base):
    __tablename__ = "content_fragments"
    __table_args__ = (
        UniqueConstraint(
            "source_item_id",
            "fragment_type",
            "fragment_ref",
            name="uq_content_fragments_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_item_id: Mapped[int] = mapped_column(
        ForeignKey("source_items.id", ondelete="CASCADE"),
        index=True,
    )
    fragment_type: Mapped[str] = mapped_column(String(64), index=True)
    fragment_ref: Mapped[str] = mapped_column(String(255))
    fragment_text: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)


class AssetOcrText(Base):
    __tablename__ = "asset_ocr_texts"

    source_item_id: Mapped[int] = mapped_column(
        ForeignKey("source_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    engine_name: Mapped[str] = mapped_column(String(64))
    text_content: Mapped[str] = mapped_column(Text)
    language_hint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    block_map_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AssetInterpretation(Base):
    __tablename__ = "asset_interpretations"

    source_item_id: Mapped[int] = mapped_column(
        ForeignKey("source_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    screen_category: Mapped[str] = mapped_column(String(64))
    semantic_summary: Mapped[str] = mapped_column(Text)
    app_hint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    topic_candidates_json: Mapped[str] = mapped_column(Text)
    task_candidates_json: Mapped[str] = mapped_column(Text)
    person_candidates_json: Mapped[str] = mapped_column(Text)
    entity_mentions_json: Mapped[str] = mapped_column(Text, default="[]")
    searchable_labels_json: Mapped[str] = mapped_column(Text, default="[]")
    cluster_hints_json: Mapped[str] = mapped_column(Text, default="[]")
    confidence_json: Mapped[str] = mapped_column(Text)
    raw_model_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_items.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    object_ref: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    embedding_type: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(128))
    content_text: Mapped[str] = mapped_column(Text)
    dimension: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class KnowledgeObject(Base):
    __tablename__ = "knowledge_objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    object_type: Mapped[str] = mapped_column(String(32), index=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)


class KnowledgeClaim(Base):
    __tablename__ = "knowledge_claims"
    __table_args__ = (
        UniqueConstraint(
            "claim_type",
            "subject_ref",
            "predicate",
            "object_ref_or_value",
            name="uq_knowledge_claim_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_type: Mapped[str] = mapped_column(String(32))
    subject_ref: Mapped[str] = mapped_column(String(255), index=True)
    predicate: Mapped[str] = mapped_column(String(64))
    object_ref_or_value: Mapped[str] = mapped_column(String(512))
    asserted_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    status: Mapped[str] = mapped_column(String(32))
    confidence_score: Mapped[float] = mapped_column(Float)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)
    evidence_set_id: Mapped[str] = mapped_column(String(64))


class KnowledgeEvidenceLink(Base):
    __tablename__ = "knowledge_evidence_links"
    __table_args__ = (
        UniqueConstraint(
            "claim_id",
            "source_item_id",
            "fragment_type",
            "fragment_ref",
            name="uq_knowledge_evidence_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_claims.id", ondelete="CASCADE"),
        index=True,
    )
    source_item_id: Mapped[int] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"))
    fragment_type: Mapped[str] = mapped_column(String(64))
    fragment_ref: Mapped[str] = mapped_column(String(255))
    interpretation_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    support_role: Mapped[str] = mapped_column(String(32), default="primary")


class Projection(Base):
    __tablename__ = "projections"
    __table_args__ = (
        UniqueConstraint("object_ref", "projection_type", name="uq_projection_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    object_ref: Mapped[str] = mapped_column(String(255))
    projection_type: Mapped[str] = mapped_column(String(64))
    content_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)


class SemanticMapRun(Base):
    __tablename__ = "semantic_map_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    map_key: Mapped[str] = mapped_column(String(64), index=True)
    source_family: Mapped[str] = mapped_column(String(32), index=True)
    source_count: Mapped[int] = mapped_column(Integer)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)


class SemanticCluster(Base):
    __tablename__ = "semantic_clusters"
    __table_args__ = (
        UniqueConstraint("map_run_id", "cluster_key", name="uq_semantic_cluster_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    map_run_id: Mapped[int] = mapped_column(
        ForeignKey("semantic_map_runs.id", ondelete="CASCADE"),
        index=True,
    )
    cluster_key: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(255))
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    centroid_x: Mapped[float] = mapped_column(Float, default=0.0)
    centroid_y: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SemanticMapPoint(Base):
    __tablename__ = "semantic_map_points"
    __table_args__ = (
        UniqueConstraint(
            "map_run_id",
            "source_item_id",
            name="uq_semantic_map_point_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    map_run_id: Mapped[int] = mapped_column(
        ForeignKey("semantic_map_runs.id", ondelete="CASCADE"),
        index=True,
    )
    source_item_id: Mapped[int] = mapped_column(
        ForeignKey("source_items.id", ondelete="CASCADE"),
        index=True,
    )
    cluster_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    x: Mapped[float] = mapped_column(Float, default=0.0)
    y: Mapped[float] = mapped_column(Float, default=0.0)
    score_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_item_id: Mapped[int] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"), index=True)
    pipeline_name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    run_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)


class StageResult(Base):
    __tablename__ = "stage_results"
    __table_args__ = (
        UniqueConstraint("pipeline_run_id", "stage_name", "attempt", name="uq_stage_attempt"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        index=True,
    )
    stage_name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
