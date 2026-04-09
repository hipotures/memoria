from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetOcrText
from memoria.domain.models import ContentFragment
from memoria.domain.models import PipelineRun
from memoria.domain.models import StageResult
from memoria.ocr.engines import OcrEngine
from memoria.ocr.engines import OcrEngineResult
from memoria.pipeline import mark_pipeline_run_failed
from memoria.pipeline import record_stage_result


@dataclass(slots=True)
class RunOcrStageCommand:
    pipeline_run_id: int
    source_item_id: int
    engine_name: str
    text_content: str
    language_hint: str | None = None
    block_map_json: str = "[]"


@dataclass(slots=True)
class ExecuteOcrStageCommand:
    pipeline_run_id: int
    source_item_id: int
    image_bytes: bytes
    media_type: str
    language_hint: str | None = None


class OcrStageExecutionError(RuntimeError):
    pass


def run_ocr_stage(session: Session, command: RunOcrStageCommand) -> None:
    pipeline_run = session.get(PipelineRun, command.pipeline_run_id)
    if pipeline_run is None or pipeline_run.source_item_id != command.source_item_id:
        raise ValueError("pipeline_run_id does not belong to source_item_id")

    asset_ocr_text = session.get(AssetOcrText, command.source_item_id)
    if asset_ocr_text is None:
        asset_ocr_text = AssetOcrText(
            source_item_id=command.source_item_id,
            engine_name=command.engine_name,
            text_content=command.text_content,
            language_hint=command.language_hint,
            block_map_json=command.block_map_json,
        )
        session.add(asset_ocr_text)
    else:
        asset_ocr_text.engine_name = command.engine_name
        asset_ocr_text.text_content = command.text_content
        asset_ocr_text.language_hint = command.language_hint
        asset_ocr_text.block_map_json = command.block_map_json
        session.add(asset_ocr_text)

    content_fragment = session.scalar(
        select(ContentFragment).where(
            ContentFragment.source_item_id == command.source_item_id,
            ContentFragment.fragment_type == "ocr_text",
            ContentFragment.fragment_ref == "full",
        )
    )
    if content_fragment is None:
        content_fragment = ContentFragment(
            source_item_id=command.source_item_id,
            fragment_type="ocr_text",
            fragment_ref="full",
            fragment_text=command.text_content,
            metadata_json="{}",
        )
        session.add(content_fragment)
    else:
        content_fragment.fragment_text = command.text_content
        session.add(content_fragment)

    session.flush()

    next_attempt = session.scalar(
        select(func.coalesce(func.max(StageResult.attempt), 0) + 1).where(
            StageResult.pipeline_run_id == command.pipeline_run_id,
            StageResult.stage_name == "ocr",
        )
    )
    assert next_attempt is not None

    record_stage_result(
        session,
        pipeline_run_id=command.pipeline_run_id,
        stage_name="ocr",
        status="completed",
        output_payload={"engine_name": command.engine_name},
        attempt=next_attempt,
    )


def execute_ocr_stage(
    session: Session,
    command: ExecuteOcrStageCommand,
    *,
    engine: OcrEngine,
) -> OcrEngineResult:
    pipeline_run = session.get(PipelineRun, command.pipeline_run_id)
    if pipeline_run is None or pipeline_run.source_item_id != command.source_item_id:
        raise ValueError("pipeline_run_id does not belong to source_item_id")

    try:
        result = engine.extract_text(
            image_bytes=command.image_bytes,
            media_type=command.media_type,
            language_hint=command.language_hint,
        )
    except Exception as exc:
        _record_failed_ocr_stage(
            session,
            pipeline_run_id=command.pipeline_run_id,
            error_text=str(exc),
        )
        mark_pipeline_run_failed(session, pipeline_run)
        raise OcrStageExecutionError(str(exc)) from exc

    run_ocr_stage(
        session,
        RunOcrStageCommand(
            pipeline_run_id=command.pipeline_run_id,
            source_item_id=command.source_item_id,
            engine_name=result.engine_name,
            text_content=result.text_content,
            language_hint=result.language_hint,
            block_map_json=result.block_map_json,
        ),
    )
    return result


def _record_failed_ocr_stage(
    session: Session,
    *,
    pipeline_run_id: int,
    error_text: str,
) -> None:
    next_attempt = session.scalar(
        select(func.coalesce(func.max(StageResult.attempt), 0) + 1).where(
            StageResult.pipeline_run_id == pipeline_run_id,
            StageResult.stage_name == "ocr",
        )
    )
    assert next_attempt is not None
    record_stage_result(
        session,
        pipeline_run_id=pipeline_run_id,
        stage_name="ocr",
        status="failed",
        error_text=error_text,
        attempt=next_attempt,
    )
