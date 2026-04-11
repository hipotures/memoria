from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ScreenshotListItem:
    source_item_id: int
    filename: str
    media_type: str
    created_at: datetime | None
    observed_at: datetime | None
    ingested_at: datetime
    connector_instance_id: str
    pipeline_status: str | None
    blob_available: bool
    ocr_excerpt: str | None
    semantic_summary: str | None
    screen_category: str | None
    app_hint: str | None
    object_refs: list[str]


@dataclass(frozen=True, slots=True)
class ScreenshotListResult:
    items: list[ScreenshotListItem]
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class ScreenshotContentFragment:
    fragment_type: str
    fragment_ref: str
    fragment_text: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ScreenshotKnowledgeClaim:
    claim_id: int
    claim_type: str
    subject_ref: str
    predicate: str
    object_ref_or_value: str
    status: str
    confidence_score: float
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class ScreenshotKnowledgeSummary:
    object_refs: list[str]
    claims: list[ScreenshotKnowledgeClaim]


@dataclass(frozen=True, slots=True)
class ScreenshotOcrPayload:
    engine_name: str
    text_content: str
    language_hint: str | None
    block_map: list[Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ScreenshotInterpretationPayload:
    screen_category: str
    semantic_summary: str
    app_hint: str | None
    topic_candidates: list[dict[str, Any]]
    task_candidates: list[dict[str, Any]]
    person_candidates: list[dict[str, Any]]
    entity_mentions: list[dict[str, Any]]
    searchable_labels: list[str]
    cluster_hints: list[str]
    confidence: dict[str, Any]
    raw_model_payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ScreenshotStageResult:
    stage_name: str
    status: str
    attempt: int
    output_payload: dict[str, Any] | None
    error_text: str | None
    started_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class ScreenshotPipelineRun:
    pipeline_run_id: int
    pipeline_name: str
    status: str
    run_reason: str | None
    started_at: datetime
    finished_at: datetime | None
    stage_results: list[ScreenshotStageResult]


@dataclass(frozen=True, slots=True)
class ScreenshotBlobMetadata:
    media_type: str
    byte_size: int
    download_url: str


@dataclass(frozen=True, slots=True)
class ScreenshotDetail:
    source_item_id: int
    filename: str
    media_type: str
    connector_instance_id: str
    external_id: str | None
    created_at: datetime | None
    observed_at: datetime | None
    ingested_at: datetime
    blob: ScreenshotBlobMetadata
    ocr: ScreenshotOcrPayload | None
    interpretation: ScreenshotInterpretationPayload | None
    content_fragments: list[ScreenshotContentFragment]
    knowledge: ScreenshotKnowledgeSummary
    pipeline: ScreenshotPipelineRun | None


@dataclass(frozen=True, slots=True)
class ScreenshotSearchHit:
    source_item_id: int
    filename: str
    match_source: str
    match_fragment_ref: str
    match_text: str
    semantic_summary: str | None
    app_hint: str | None
    object_refs: list[str]


@dataclass(frozen=True, slots=True)
class ScreenshotSearchResult:
    query: str
    items: list[ScreenshotSearchHit]
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class ScreenshotBlobResult:
    content: bytes
    media_type: str
