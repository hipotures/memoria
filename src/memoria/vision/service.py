from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetInterpretation
from memoria.domain.models import ContentFragment
from memoria.domain.models import Embedding
from memoria.domain.models import PipelineRun
from memoria.domain.models import StageResult
from memoria.domain.models import SourcePayloadScreenshot
from memoria.pipeline import mark_pipeline_run_failed
from memoria.pipeline import record_stage_result
from memoria.search.embeddings import EMBEDDING_DIMENSION
from memoria.search.embeddings import EMBEDDING_MODEL_NAME
from memoria.search.embeddings import build_embedding_text_for_screenshot
from memoria.search.embeddings import embed_text
from memoria.search.embeddings import upsert_embedding
from memoria.vision.contracts import VisionInterpretation
from memoria.vision.engines import VisionEngine
from memoria.vision.engines import extract_app_hint_from_filename
from memoria.vision.mapper import map_vision_analysis_to_interpretation


@dataclass(slots=True)
class RunVisionStageCommand:
    pipeline_run_id: int
    source_item_id: int
    interpretation: VisionInterpretation


@dataclass(slots=True)
class ExecuteVisionStageCommand:
    pipeline_run_id: int
    source_item_id: int
    image_bytes: bytes
    media_type: str
    ocr_text: str
    language_hint: str
    original_filename: str


class VisionStageExecutionError(RuntimeError):
    pass


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
            entity_mentions_json=_serialize_mentions(payload.entity_mentions),
            searchable_labels_json=json.dumps(payload.searchable_labels, sort_keys=True),
            cluster_hints_json=json.dumps(payload.cluster_hints, sort_keys=True),
            confidence_json=json.dumps(payload.confidence, sort_keys=True),
            raw_model_payload_json=json.dumps(payload.raw_model_payload, sort_keys=True),
        )
        session.add(interpretation_row)
    else:
        interpretation_row.screen_category = payload.screen_category
        interpretation_row.semantic_summary = payload.semantic_summary
        interpretation_row.app_hint = payload.app_hint
        interpretation_row.topic_candidates_json = _serialize_candidates(payload.topic_candidates)
        interpretation_row.task_candidates_json = _serialize_candidates(payload.task_candidates)
        interpretation_row.person_candidates_json = _serialize_candidates(payload.person_candidates)
        interpretation_row.entity_mentions_json = _serialize_mentions(payload.entity_mentions)
        interpretation_row.searchable_labels_json = json.dumps(payload.searchable_labels, sort_keys=True)
        interpretation_row.cluster_hints_json = json.dumps(payload.cluster_hints, sort_keys=True)
        interpretation_row.confidence_json = json.dumps(payload.confidence, sort_keys=True)
        interpretation_row.raw_model_payload_json = json.dumps(payload.raw_model_payload, sort_keys=True)
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

    _replace_string_fragments(
        session,
        source_item_id=command.source_item_id,
        fragment_type="searchable_label",
        values=payload.searchable_labels,
    )
    _replace_string_fragments(
        session,
        source_item_id=command.source_item_id,
        fragment_type="cluster_hint",
        values=payload.cluster_hints,
    )
    _replace_entity_fragments(
        session,
        source_item_id=command.source_item_id,
        interpretation=payload,
    )

    ocr_row_text = session.scalar(
        select(ContentFragment.fragment_text).where(
            ContentFragment.source_item_id == command.source_item_id,
            ContentFragment.fragment_type == "ocr_text",
            ContentFragment.fragment_ref == "full_text",
        )
    ) or ""
    screenshot_payload = session.get(SourcePayloadScreenshot, command.source_item_id)
    if screenshot_payload is not None:
        embedding_text = build_embedding_text_for_screenshot(
            filename=screenshot_payload.original_filename,
            screen_category=payload.screen_category,
            semantic_summary=payload.semantic_summary,
            app_hint=payload.app_hint,
            searchable_labels=payload.searchable_labels,
            cluster_hints=payload.cluster_hints,
            entity_mentions=[mention.text for mention in payload.entity_mentions],
            ocr_text=ocr_row_text,
        )
        upsert_embedding(
            session,
            source_item_id=command.source_item_id,
            embedding_type="screenshot_semantic_text",
            model_name=EMBEDDING_MODEL_NAME,
            content_text=embedding_text,
            vector=embed_text(embedding_text),
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


def execute_vision_stage(
    session: Session,
    command: ExecuteVisionStageCommand,
    *,
    engine: VisionEngine,
) -> VisionInterpretation:
    pipeline_run = session.get(PipelineRun, command.pipeline_run_id)
    if pipeline_run is None or pipeline_run.source_item_id != command.source_item_id:
        raise ValueError("pipeline_run_id does not belong to source_item_id")

    try:
        analysis = engine.analyze(
            image_bytes=command.image_bytes,
            media_type=command.media_type,
            language_hint=command.language_hint,
            app_hint_from_filename=extract_app_hint_from_filename(command.original_filename),
            ocr_text=command.ocr_text,
        )
        interpretation = map_vision_analysis_to_interpretation(
            analysis=analysis,
            ocr_text=command.ocr_text,
            original_filename=command.original_filename,
        )
    except Exception as exc:
        _record_failed_vision_stage(
            session,
            pipeline_run_id=command.pipeline_run_id,
            error_text=str(exc),
        )
        mark_pipeline_run_failed(session, pipeline_run)
        raise VisionStageExecutionError(str(exc)) from exc

    run_vision_stage(
        session,
        RunVisionStageCommand(
            pipeline_run_id=command.pipeline_run_id,
            source_item_id=command.source_item_id,
            interpretation=interpretation,
        ),
    )
    return interpretation


def _serialize_candidates(candidates: list[object]) -> str:
    return json.dumps([asdict(candidate) for candidate in candidates], sort_keys=True)


def _serialize_mentions(mentions: list[object]) -> str:
    return json.dumps([asdict(mention) for mention in mentions], sort_keys=True)


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


def _replace_string_fragments(
    session: Session,
    *,
    source_item_id: int,
    fragment_type: str,
    values: list[str],
) -> None:
    existing_fragments = session.scalars(
        select(ContentFragment).where(
            ContentFragment.source_item_id == source_item_id,
            ContentFragment.fragment_type == fragment_type,
        )
    ).all()
    existing_by_ref = {fragment.fragment_ref: fragment for fragment in existing_fragments}
    desired_refs = {f"{fragment_type}:{index}" for index, _ in enumerate(values)}

    for fragment_ref, fragment in existing_by_ref.items():
        if fragment_ref not in desired_refs:
            session.delete(fragment)

    for index, value in enumerate(values):
        _upsert_fragment(
            session,
            source_item_id=source_item_id,
            fragment_type=fragment_type,
            fragment_ref=f"{fragment_type}:{index}",
            fragment_text=value,
        )


def _replace_entity_fragments(
    session: Session,
    *,
    source_item_id: int,
    interpretation: VisionInterpretation,
) -> None:
    existing_fragments = session.scalars(
        select(ContentFragment).where(
            ContentFragment.source_item_id == source_item_id,
            ContentFragment.fragment_type == "entity_mention",
        )
    ).all()
    existing_by_ref = {fragment.fragment_ref: fragment for fragment in existing_fragments}
    desired_refs = {
        f"{mention.type}:{mention.text.lower()}"
        for mention in interpretation.entity_mentions
    }

    for fragment_ref, fragment in existing_by_ref.items():
        if fragment_ref not in desired_refs:
            session.delete(fragment)

    for mention in interpretation.entity_mentions:
        _upsert_fragment(
            session,
            source_item_id=source_item_id,
            fragment_type="entity_mention",
            fragment_ref=f"{mention.type}:{mention.text.lower()}",
            fragment_text=mention.text,
        )


def _record_failed_vision_stage(
    session: Session,
    *,
    pipeline_run_id: int,
    error_text: str,
) -> None:
    next_attempt = session.scalar(
        select(func.coalesce(func.max(StageResult.attempt), 0) + 1).where(
            StageResult.pipeline_run_id == pipeline_run_id,
            StageResult.stage_name == "vision",
        )
    )
    assert next_attempt is not None
    record_stage_result(
        session,
        pipeline_run_id=pipeline_run_id,
        stage_name="vision",
        status="failed",
        error_text=error_text,
        attempt=next_attempt,
    )
