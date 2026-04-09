from __future__ import annotations

import base64
import binascii
import json
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
from memoria.ocr.engines import OcrEngine
from memoria.ocr.engines import PaddleOcrEngine
from memoria.ocr.service import ExecuteOcrStageCommand
from memoria.ocr.service import OcrStageExecutionError
from memoria.ocr.service import RunOcrStageCommand
from memoria.ocr.service import execute_ocr_stage
from memoria.ocr.service import run_ocr_stage
from memoria.pipeline import mark_pipeline_run_completed
from memoria.projections.service import refresh_assistant_context_projection
from memoria.projections.service import refresh_topic_status_projection
from memoria.runtime_settings import RuntimeSettings
from memoria.runtime_settings import load_runtime_settings_from_env
from memoria.storage.blob_store import load_blob_bytes_for_source_item
from memoria.storage.blob_store import load_original_filename_for_source_item
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas
from memoria.vision.contracts import CandidateRef
from memoria.vision.contracts import VisionInterpretation
from memoria.vision.engines import OllamaVisionEngine
from memoria.vision.engines import OpenAICompatibleVisionEngine
from memoria.vision.engines import VisionEngine
from memoria.vision.mapper import should_absorb_interpretation
from memoria.vision.service import ExecuteVisionStageCommand
from memoria.vision.service import VisionStageExecutionError
from memoria.vision.service import execute_vision_stage


def create_app(
    *,
    database_url: str | None = None,
    blob_dir: Path,
    runtime_settings: RuntimeSettings | None = None,
    ocr_engine: OcrEngine | None = None,
    vision_engine: VisionEngine | None = None,
) -> FastAPI:
    settings = runtime_settings or load_runtime_settings_from_env()
    resolved_database_url = database_url or settings.database_url
    engine = create_engine_with_sqlite_pragmas(resolved_database_url)
    resolved_ocr_engine = ocr_engine or _create_ocr_engine(settings)
    resolved_vision_engine = vision_engine or _create_vision_engine(settings)
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

            try:
                if _has_completed_absorb_stage(
                    session,
                    pipeline_run_id=ingest_result.pipeline_run_id,
                ):
                    if pipeline_run.status != "completed":
                        mark_pipeline_run_completed(session, pipeline_run)
                else:
                    _process_screenshot_pipeline(
                        session,
                        source_item_id=ingest_result.source_item_id,
                        pipeline_run_id=ingest_result.pipeline_run_id,
                        payload=payload,
                        settings=settings,
                        ocr_engine=resolved_ocr_engine,
                        vision_engine=resolved_vision_engine,
                    )
            except (OcrStageExecutionError, VisionStageExecutionError) as exc:
                session.commit()
                raise HTTPException(status_code=500, detail=str(exc)) from exc

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


def _process_screenshot_pipeline(
    session: Session,
    *,
    source_item_id: int,
    pipeline_run_id: int,
    payload: IngestScreenshotRequest,
    settings: RuntimeSettings,
    ocr_engine: OcrEngine,
    vision_engine: VisionEngine,
) -> None:
    pipeline_run = session.get(PipelineRun, pipeline_run_id)
    assert pipeline_run is not None

    image_bytes, media_type = load_blob_bytes_for_source_item(session, source_item_id=source_item_id)
    original_filename = load_original_filename_for_source_item(
        session,
        source_item_id=source_item_id,
    )

    ocr_text = _ensure_ocr_text(
        session,
        pipeline_run_id=pipeline_run_id,
        source_item_id=source_item_id,
        payload=payload,
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
        ocr_text=ocr_text,
    )

    if should_absorb_interpretation(interpretation):
        touched_refs = absorb_interpreted_screenshot(
            session,
            pipeline_run_id=pipeline_run_id,
            source_item_id=source_item_id,
        )
        for object_ref in touched_refs:
            refresh_assistant_context_projection(session, object_ref=object_ref)
            if object_ref.startswith("topic:"):
                refresh_topic_status_projection(session, object_ref=object_ref)
    if pipeline_run.status != "completed":
        mark_pipeline_run_completed(session, pipeline_run)


def _ensure_ocr_text(
    session: Session,
    *,
    pipeline_run_id: int,
    source_item_id: int,
    payload: IngestScreenshotRequest,
    settings: RuntimeSettings,
    ocr_engine: OcrEngine,
    image_bytes: bytes,
    media_type: str,
) -> str:
    ocr_row = session.get(AssetOcrText, source_item_id)
    if ocr_row is not None:
        return ocr_row.text_content

    if payload.ocr_text is not None:
        run_ocr_stage(
            session,
            RunOcrStageCommand(
                pipeline_run_id=pipeline_run_id,
                source_item_id=source_item_id,
                engine_name="manual_override",
                text_content=payload.ocr_text,
                language_hint=settings.ocr_language_hint,
            ),
        )
        return payload.ocr_text

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


def _interpretation_from_row(interpretation_row: AssetInterpretation) -> VisionInterpretation:
    return VisionInterpretation(
        screen_category=interpretation_row.screen_category,
        semantic_summary=interpretation_row.semantic_summary,
        app_hint=interpretation_row.app_hint,
        topic_candidates=[
            CandidateRef(**candidate)
            for candidate in json.loads(interpretation_row.topic_candidates_json)
        ],
        task_candidates=[
            CandidateRef(**candidate)
            for candidate in json.loads(interpretation_row.task_candidates_json)
        ],
        person_candidates=[
            CandidateRef(**candidate)
            for candidate in json.loads(interpretation_row.person_candidates_json)
        ],
        confidence=json.loads(interpretation_row.confidence_json),
    )


def _decode_content_base64(content_base64: str) -> bytes:
    try:
        return base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="content_base64 must be valid base64") from exc


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


def _create_ocr_engine(settings: RuntimeSettings) -> OcrEngine:
    if settings.ocr_engine == "paddleocr":
        return PaddleOcrEngine(
            lang=settings.paddle_lang,
            use_angle_cls=settings.paddle_use_angle_cls,
            use_gpu=settings.paddle_use_gpu,
        )
    raise ValueError(f"unsupported OCR engine: {settings.ocr_engine}")


def _create_vision_engine(settings: RuntimeSettings) -> VisionEngine:
    if settings.vision_engine == "ollama":
        return OllamaVisionEngine(
            api_base_url=settings.vision_api_base_url,
            model=settings.vision_model,
            temperature=settings.vision_temperature,
            timeout_seconds=settings.vision_timeout_seconds,
            max_output_tokens=settings.vision_max_output_tokens,
            keep_alive=settings.ollama_keep_alive,
            think=settings.ollama_think,
            seed=settings.seed,
        )
    if settings.vision_engine in {"vllm", "llamacpp"}:
        return OpenAICompatibleVisionEngine(
            engine_name=settings.vision_engine,
            api_base_url=settings.vision_api_base_url,
            model=settings.vision_model,
            temperature=settings.vision_temperature,
            timeout_seconds=settings.vision_timeout_seconds,
            max_output_tokens=settings.vision_max_output_tokens,
            seed=settings.seed,
        )
    raise ValueError(f"unsupported vision engine: {settings.vision_engine}")
