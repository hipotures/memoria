from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetOcrText
from memoria.domain.models import ContentFragment
from memoria.domain.models import PipelineRun
from memoria.domain.models import StageResult
from memoria.pipeline import record_stage_result


@dataclass(slots=True)
class RunOcrStageCommand:
    pipeline_run_id: int
    source_item_id: int
    engine_name: str
    text_content: str
    language_hint: str | None = None
    block_map_json: str = "[]"


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
