from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.api.schemas import AssistantQueryRequest
from memoria.api.schemas import IngestScreenshotRequest
from memoria.assistant.service import answer_question
from memoria.domain.models import AssetInterpretation
from memoria.domain.models import AssetOcrText
from memoria.domain.models import PipelineRun
from memoria.domain.models import StageResult
from memoria.ingest.service import IngestScreenshotCommand
from memoria.ingest.service import ingest_screenshot
from memoria.knowledge.service import absorb_interpreted_screenshot
from memoria.ocr.service import RunOcrStageCommand
from memoria.ocr.service import run_ocr_stage
from memoria.pipeline import mark_pipeline_run_completed
from memoria.projections.service import refresh_assistant_context_projection
from memoria.projections.service import refresh_topic_status_projection
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas
from memoria.vision.contracts import CandidateRef
from memoria.vision.contracts import VisionInterpretation
from memoria.vision.service import RunVisionStageCommand
from memoria.vision.service import run_vision_stage

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_LEADING_SPEAKER_RE = re.compile(r"^\s*([A-Z][A-Za-z0-9_-]*)\s*:")
_TRIP_LOCATION_RE = re.compile(
    r"\b(?:for|to)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)"
)
_TRAVEL_SIGNAL_RE = re.compile(r"\b(?:trip|travel|train|flight|hotel)\b")
_AMBIGUOUS_TRIP_LOCATION_TOKENS = {
    "finance",
    "monday",
    "reimbursement",
    "support",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}


def create_app(*, database_url: str, blob_dir: Path) -> FastAPI:
    engine = create_engine_with_sqlite_pragmas(database_url)
    app = FastAPI()

    @app.post("/ingest", status_code=201)
    def ingest_endpoint(payload: IngestScreenshotRequest) -> dict[str, int | str]:
        content = _decode_content_base64(payload.content_base64)

        with Session(engine) as session:
            ingest_result = ingest_screenshot(
                session,
                IngestScreenshotCommand(
                    filename=payload.filename,
                    media_type=payload.media_type,
                    content=content,
                    connector_instance_id=payload.connector_instance_id,
                    external_id=payload.external_id,
                    blob_dir=blob_dir,
                ),
            )
            pipeline_run = session.get(PipelineRun, ingest_result.pipeline_run_id)
            assert pipeline_run is not None

            if payload.ocr_text and not _has_existing_stub_derivatives(
                session,
                source_item_id=ingest_result.source_item_id,
            ):
                interpretation = _build_stub_interpretation(payload.ocr_text)
                run_ocr_stage(
                    session,
                    RunOcrStageCommand(
                        pipeline_run_id=ingest_result.pipeline_run_id,
                        source_item_id=ingest_result.source_item_id,
                        engine_name="api-stub-ocr",
                        text_content=payload.ocr_text,
                    ),
                )
                run_vision_stage(
                    session,
                    RunVisionStageCommand(
                        pipeline_run_id=ingest_result.pipeline_run_id,
                        source_item_id=ingest_result.source_item_id,
                        interpretation=interpretation,
                    ),
                )
                if _should_absorb_stub_interpretation(interpretation):
                    touched_refs = absorb_interpreted_screenshot(
                        session,
                        pipeline_run_id=ingest_result.pipeline_run_id,
                        source_item_id=ingest_result.source_item_id,
                    )
                    for object_ref in touched_refs:
                        refresh_assistant_context_projection(session, object_ref=object_ref)
                        if object_ref.startswith("topic:"):
                            refresh_topic_status_projection(session, object_ref=object_ref)
                    if pipeline_run.status != "completed":
                        mark_pipeline_run_completed(session, pipeline_run)
            elif _has_completed_absorb_stage(
                session,
                pipeline_run_id=ingest_result.pipeline_run_id,
            ) and pipeline_run.status != "completed":
                mark_pipeline_run_completed(session, pipeline_run)

            session.commit()
            return {"source_item_id": ingest_result.source_item_id}

    @app.post("/assistant/query")
    def assistant_query_endpoint(payload: AssistantQueryRequest) -> dict[str, object]:
        with Session(engine) as session:
            answer = answer_question(session, payload.question)
            return {
                "answer_text": answer.answer_text,
                "answer_source": answer.answer_source,
                "object_refs": answer.object_refs,
                "evidence": [
                    {
                        "source_item_id": evidence.source_item_id,
                        "fragment_type": evidence.fragment_type,
                        "fragment_ref": evidence.fragment_ref,
                        "support_role": evidence.support_role,
                        "claim_id": evidence.claim_id,
                    }
                    for evidence in answer.evidence
                ],
            }

    return app


def _build_stub_interpretation(ocr_text: str) -> VisionInterpretation:
    lower_text = ocr_text.lower()
    has_travel_signal = _TRAVEL_SIGNAL_RE.search(lower_text) is not None
    topic_candidates: list[CandidateRef] = []
    task_candidates: list[CandidateRef] = []
    person_candidates: list[CandidateRef] = []

    trip_match = _TRIP_LOCATION_RE.search(ocr_text) if has_travel_signal else None
    if trip_match is not None:
        location_title = trip_match.group(1).strip()
        if _is_plausible_trip_location(location_title):
            topic_candidates.append(
                CandidateRef(
                    slug=f"trip-to-{_slugify(location_title)}",
                    title=f"Trip to {location_title}",
                    confidence=0.95,
                )
            )

    if "book train" in lower_text or "train ticket" in lower_text:
        task_candidates.append(
            CandidateRef(
                slug="book-train",
                title="Book train",
                confidence=0.89,
            )
        )

    speaker_match = _LEADING_SPEAKER_RE.match(ocr_text)
    if speaker_match is not None and (topic_candidates or task_candidates):
        person_title = speaker_match.group(1).strip()
        person_candidates.append(
            CandidateRef(
                slug=_slugify(person_title),
                title=person_title,
                confidence=0.62,
            )
        )

    has_chat_signal = speaker_match is not None and (topic_candidates or task_candidates)
    return VisionInterpretation(
        screen_category="chat" if has_chat_signal else "generic",
        semantic_summary=ocr_text,
        app_hint="telegram" if has_chat_signal else None,
        topic_candidates=topic_candidates,
        task_candidates=task_candidates,
        person_candidates=person_candidates,
        confidence={
            "screen_category": 0.70 if has_chat_signal else 0.25,
            "semantic_summary": 0.55,
        },
    )


def _slugify(value: str) -> str:
    slug = _NON_ALNUM_RE.sub("-", value.strip().lower()).strip("-")
    return slug or "unknown"


def _decode_content_base64(content_base64: str) -> bytes:
    try:
        return base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="content_base64 must be valid base64") from exc


def _should_absorb_stub_interpretation(interpretation: VisionInterpretation) -> bool:
    return bool(interpretation.topic_candidates and interpretation.task_candidates)


def _has_existing_stub_derivatives(session: Session, *, source_item_id: int) -> bool:
    return (
        session.get(AssetOcrText, source_item_id) is not None
        or session.get(AssetInterpretation, source_item_id) is not None
    )


def _has_completed_absorb_stage(session: Session, *, pipeline_run_id: int) -> bool:
    stage_result = session.scalar(
        select(StageResult)
        .where(
            StageResult.pipeline_run_id == pipeline_run_id,
            StageResult.stage_name == "absorb",
            StageResult.status == "completed",
        )
        .order_by(StageResult.attempt.desc())
    )
    return stage_result is not None


def _is_plausible_trip_location(location_title: str) -> bool:
    normalized_tokens = {token.lower() for token in location_title.strip().split()}
    return not normalized_tokens.intersection(_AMBIGUOUS_TRIP_LOCATION_TOKENS)
