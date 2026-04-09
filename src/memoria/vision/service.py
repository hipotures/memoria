from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetInterpretation
from memoria.domain.models import ContentFragment
from memoria.domain.models import PipelineRun
from memoria.domain.models import StageResult
from memoria.pipeline import record_stage_result
from memoria.vision.contracts import VisionInterpretation


@dataclass(slots=True)
class RunVisionStageCommand:
    pipeline_run_id: int
    source_item_id: int
    interpretation: VisionInterpretation


def run_vision_stage(session: Session, command: RunVisionStageCommand) -> None:
    pipeline_run = session.get(PipelineRun, command.pipeline_run_id)
    if pipeline_run is None or pipeline_run.source_item_id != command.source_item_id:
        raise ValueError("pipeline_run_id does not belong to source_item_id")

    payload = command.interpretation
    interpretation_row = session.get(AssetInterpretation, command.source_item_id)
    if interpretation_row is None:
        interpretation_row = AssetInterpretation(
            source_item_id=command.source_item_id,
            screen_category=payload.screen_category,
            semantic_summary=payload.semantic_summary,
            app_hint=payload.app_hint,
            topic_candidates_json=_serialize_candidates(payload.topic_candidates),
            task_candidates_json=_serialize_candidates(payload.task_candidates),
            person_candidates_json=_serialize_candidates(payload.person_candidates),
            confidence_json=json.dumps(payload.confidence, sort_keys=True),
        )
        session.add(interpretation_row)
    else:
        interpretation_row.screen_category = payload.screen_category
        interpretation_row.semantic_summary = payload.semantic_summary
        interpretation_row.app_hint = payload.app_hint
        interpretation_row.topic_candidates_json = _serialize_candidates(payload.topic_candidates)
        interpretation_row.task_candidates_json = _serialize_candidates(payload.task_candidates)
        interpretation_row.person_candidates_json = _serialize_candidates(payload.person_candidates)
        interpretation_row.confidence_json = json.dumps(payload.confidence, sort_keys=True)
        session.add(interpretation_row)

    _upsert_fragment(
        session,
        source_item_id=command.source_item_id,
        fragment_type="scene_description",
        fragment_ref="summary",
        fragment_text=payload.semantic_summary,
    )

    if payload.app_hint:
        _upsert_fragment(
            session,
            source_item_id=command.source_item_id,
            fragment_type="app_hint",
            fragment_ref="detected_app",
            fragment_text=payload.app_hint,
        )
    else:
        _delete_fragment(
            session,
            source_item_id=command.source_item_id,
            fragment_type="app_hint",
            fragment_ref="detected_app",
        )

    session.flush()

    next_attempt = session.scalar(
        select(func.coalesce(func.max(StageResult.attempt), 0) + 1).where(
            StageResult.pipeline_run_id == command.pipeline_run_id,
            StageResult.stage_name == "vision",
        )
    )
    assert next_attempt is not None

    record_stage_result(
        session,
        pipeline_run_id=command.pipeline_run_id,
        stage_name="vision",
        status="completed",
        output_payload={"screen_category": payload.screen_category},
        attempt=next_attempt,
    )


def _serialize_candidates(candidates: list[object]) -> str:
    return json.dumps([asdict(candidate) for candidate in candidates], sort_keys=True)


def _upsert_fragment(
    session: Session,
    *,
    source_item_id: int,
    fragment_type: str,
    fragment_ref: str,
    fragment_text: str,
) -> None:
    fragment = session.scalar(
        select(ContentFragment).where(
            ContentFragment.source_item_id == source_item_id,
            ContentFragment.fragment_type == fragment_type,
            ContentFragment.fragment_ref == fragment_ref,
        )
    )
    if fragment is None:
        fragment = ContentFragment(
            source_item_id=source_item_id,
            fragment_type=fragment_type,
            fragment_ref=fragment_ref,
            fragment_text=fragment_text,
            metadata_json="{}",
        )
        session.add(fragment)
        return

    fragment.fragment_text = fragment_text
    session.add(fragment)


def _delete_fragment(
    session: Session,
    *,
    source_item_id: int,
    fragment_type: str,
    fragment_ref: str,
) -> None:
    fragment = session.scalar(
        select(ContentFragment).where(
            ContentFragment.source_item_id == source_item_id,
            ContentFragment.fragment_type == fragment_type,
            ContentFragment.fragment_ref == fragment_ref,
        )
    )
    if fragment is not None:
        session.delete(fragment)
