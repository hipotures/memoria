from datetime import datetime
from typing import Any

from pydantic import BaseModel


class IngestScreenshotRequest(BaseModel):
    filename: str
    media_type: str
    connector_instance_id: str
    content_base64: str
    external_id: str | None = None
    ocr_text: str | None = None


class AssistantQueryRequest(BaseModel):
    question: str


class ScreenshotListItemResponse(BaseModel):
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


class ScreenshotListResponse(BaseModel):
    items: list[ScreenshotListItemResponse]
    limit: int
    offset: int


class ScreenshotBlobMetadataResponse(BaseModel):
    media_type: str
    byte_size: int
    download_url: str


class ScreenshotOcrResponse(BaseModel):
    engine_name: str
    text_content: str
    language_hint: str | None
    block_map: list[Any]
    created_at: datetime
    updated_at: datetime


class ScreenshotInterpretationResponse(BaseModel):
    screen_category: str
    semantic_summary: str
    app_hint: str | None
    topic_candidates: list[dict[str, Any]]
    task_candidates: list[dict[str, Any]]
    person_candidates: list[dict[str, Any]]
    confidence: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ScreenshotContentFragmentResponse(BaseModel):
    fragment_type: str
    fragment_ref: str
    fragment_text: str
    created_at: datetime


class ScreenshotKnowledgeClaimResponse(BaseModel):
    claim_id: int
    claim_type: str
    subject_ref: str
    predicate: str
    object_ref_or_value: str
    status: str
    confidence_score: float
    observed_at: datetime


class ScreenshotKnowledgeResponse(BaseModel):
    object_refs: list[str]
    claims: list[ScreenshotKnowledgeClaimResponse]


class ScreenshotStageResultResponse(BaseModel):
    stage_name: str
    status: str
    attempt: int
    output_payload: dict[str, Any] | None
    error_text: str | None
    started_at: datetime
    finished_at: datetime | None


class ScreenshotPipelineResponse(BaseModel):
    pipeline_run_id: int
    pipeline_name: str
    status: str
    run_reason: str | None
    started_at: datetime
    finished_at: datetime | None
    stage_results: list[ScreenshotStageResultResponse]


class ScreenshotDetailResponse(BaseModel):
    source_item_id: int
    filename: str
    media_type: str
    connector_instance_id: str
    external_id: str | None
    created_at: datetime | None
    observed_at: datetime | None
    ingested_at: datetime
    blob: ScreenshotBlobMetadataResponse
    ocr: ScreenshotOcrResponse | None
    interpretation: ScreenshotInterpretationResponse | None
    content_fragments: list[ScreenshotContentFragmentResponse]
    knowledge: ScreenshotKnowledgeResponse
    pipeline: ScreenshotPipelineResponse | None


class ScreenshotSearchHitResponse(BaseModel):
    source_item_id: int
    filename: str
    match_source: str
    match_fragment_ref: str
    match_text: str
    semantic_summary: str | None
    app_hint: str | None
    object_refs: list[str]


class ScreenshotSearchResponse(BaseModel):
    query: str
    items: list[ScreenshotSearchHitResponse]
    limit: int
    offset: int
