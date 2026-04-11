from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetInterpretation
from memoria.domain.models import AssetOcrText
from memoria.domain.models import PipelineRun
from memoria.domain.models import SourceItem
from memoria.domain.models import StageResult
from memoria.ingest.service import IngestScreenshotCommand
from memoria.ingest.service import ingest_screenshot
from memoria.knowledge.service import absorb_interpreted_screenshot
from memoria.map.service import rebuild_semantic_map
from memoria.ocr.engines import OcrEngine
from memoria.ocr.service import ExecuteOcrStageCommand
from memoria.ocr.service import RunOcrStageCommand
from memoria.ocr.service import execute_ocr_stage
from memoria.ocr.service import run_ocr_stage
from memoria.pipeline import mark_pipeline_run_completed
from memoria.projections.service import refresh_assistant_context_projection
from memoria.projections.service import refresh_topic_status_projection
from memoria.runtime_settings import RuntimeSettings
from memoria.storage.blob_store import load_blob_bytes_for_source_item
from memoria.storage.blob_store import load_original_filename_for_source_item
from memoria.vision.contracts import VisionInterpretation
from memoria.vision.engines import VisionEngine
from memoria.vision.mapper import should_absorb_interpretation
from memoria.vision.service import ExecuteVisionStageCommand
from memoria.vision.service import execute_vision_stage


@dataclass(slots=True)
class ProcessScreenshotCommand:
    filename: str
    media_type: str
    content: bytes
    connector_instance_id: str
    external_id: str | None = None
    source_created_at: datetime | None = None
    source_observed_at: datetime | None = None
    blob_dir: Path = Path("var/blobs")
    mode: str = "absorb"
    ocr_text: str | None = None
    rebuild_semantic_map: bool = True


@dataclass(slots=True)
class ProcessScreenshotResult:
    source_item_id: int
    pipeline_run_id: int
    is_duplicate: bool


def ingest_and_process_screenshot(
    session: Session,
    *,
    command: ProcessScreenshotCommand,
    settings: RuntimeSettings,
    ocr_engine: OcrEngine,
    vision_engine: VisionEngine,
) -> ProcessScreenshotResult:
    ingest_result = ingest_screenshot(
        session,
        IngestScreenshotCommand(
            filename=command.filename,
            media_type=command.media_type,
            content=command.content,
            connector_instance_id=command.connector_instance_id,
            external_id=command.external_id,
            source_created_at=command.source_created_at,
            source_observed_at=command.source_observed_at,
            blob_dir=command.blob_dir,
            mode=command.mode,
        ),
    )
    pipeline_run = session.get(PipelineRun, ingest_result.pipeline_run_id)
    assert pipeline_run is not None

    if pipeline_run.status == "completed":
        return ProcessScreenshotResult(
            source_item_id=ingest_result.source_item_id,
            pipeline_run_id=ingest_result.pipeline_run_id,
            is_duplicate=ingest_result.is_duplicate,
        )

    if _has_completed_absorb_stage(session, pipeline_run_id=ingest_result.pipeline_run_id):
        mark_pipeline_run_completed(session, pipeline_run)
    else:
        _process_screenshot_pipeline(
            session,
            source_item_id=ingest_result.source_item_id,
            pipeline_run_id=ingest_result.pipeline_run_id,
            settings=settings,
            ocr_engine=ocr_engine,
            vision_engine=vision_engine,
            ocr_text=command.ocr_text,
            rebuild_semantic_map_after=command.rebuild_semantic_map,
        )

    return ProcessScreenshotResult(
        source_item_id=ingest_result.source_item_id,
        pipeline_run_id=ingest_result.pipeline_run_id,
        is_duplicate=ingest_result.is_duplicate,
    )


def _process_screenshot_pipeline(
    session: Session,
    *,
    source_item_id: int,
    pipeline_run_id: int,
    settings: RuntimeSettings,
    ocr_engine: OcrEngine,
    vision_engine: VisionEngine,
    ocr_text: str | None,
    rebuild_semantic_map_after: bool,
) -> None:
    pipeline_run = session.get(PipelineRun, pipeline_run_id)
    assert pipeline_run is not None
    source_item = session.get(SourceItem, source_item_id)
    assert source_item is not None

    image_bytes, media_type = load_blob_bytes_for_source_item(session, source_item_id=source_item_id)
    original_filename = load_original_filename_for_source_item(
        session,
        source_item_id=source_item_id,
    )

    resolved_ocr_text = _ensure_ocr_text(
        session,
        pipeline_run_id=pipeline_run_id,
        source_item_id=source_item_id,
        ocr_text=ocr_text,
        settings=settings,
        ocr_engine=ocr_engine,
        image_bytes=image_bytes,
        media_type=media_type,
    )
    interpretation = _ensure_vision_interpretation(
        session,
        pipeline_run_id=pipeline_run_id,
        source_item_id=source_item_id,
        settings=settings,
        vision_engine=vision_engine,
        image_bytes=image_bytes,
        media_type=media_type,
        original_filename=original_filename,
        ocr_text=resolved_ocr_text,
    )

    if source_item.mode == "absorb" and should_absorb_interpretation(interpretation):
        touched_refs = absorb_interpreted_screenshot(
            session,
            pipeline_run_id=pipeline_run_id,
            source_item_id=source_item_id,
        )
        for object_ref in touched_refs:
            refresh_assistant_context_projection(session, object_ref=object_ref)
            if object_ref.startswith("topic:"):
                refresh_topic_status_projection(session, object_ref=object_ref)
    if rebuild_semantic_map_after:
        rebuild_semantic_map(session, source_family="screenshot")
    if pipeline_run.status != "completed":
        mark_pipeline_run_completed(session, pipeline_run)


def _ensure_ocr_text(
    session: Session,
    *,
    pipeline_run_id: int,
    source_item_id: int,
    ocr_text: str | None,
    settings: RuntimeSettings,
    ocr_engine: OcrEngine,
    image_bytes: bytes,
    media_type: str,
) -> str:
    ocr_row = session.get(AssetOcrText, source_item_id)
    if ocr_row is not None:
        return ocr_row.text_content

    if ocr_text is not None:
        run_ocr_stage(
            session,
            RunOcrStageCommand(
                pipeline_run_id=pipeline_run_id,
                source_item_id=source_item_id,
                engine_name="manual_override",
                text_content=ocr_text,
                language_hint=settings.ocr_language_hint,
            ),
        )
        return ocr_text

    result = execute_ocr_stage(
        session,
        ExecuteOcrStageCommand(
            pipeline_run_id=pipeline_run_id,
            source_item_id=source_item_id,
            image_bytes=image_bytes,
            media_type=media_type,
            language_hint=settings.ocr_language_hint,
        ),
        engine=ocr_engine,
    )
    return result.text_content


def _ensure_vision_interpretation(
    session: Session,
    *,
    pipeline_run_id: int,
    source_item_id: int,
    settings: RuntimeSettings,
    vision_engine: VisionEngine,
    image_bytes: bytes,
    media_type: str,
    original_filename: str,
    ocr_text: str,
) -> VisionInterpretation:
    interpretation_row = session.get(AssetInterpretation, source_item_id)
    if interpretation_row is not None:
        from memoria.api.app import _interpretation_from_row

        return _interpretation_from_row(interpretation_row)

    return execute_vision_stage(
        session,
        ExecuteVisionStageCommand(
            pipeline_run_id=pipeline_run_id,
            source_item_id=source_item_id,
            image_bytes=image_bytes,
            media_type=media_type,
            ocr_text=ocr_text,
            language_hint=settings.vision_language_hint,
            original_filename=original_filename,
        ),
        engine=vision_engine,
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
