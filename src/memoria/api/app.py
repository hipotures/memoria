from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException
from sqlalchemy.orm import Session

from memoria.api.knowledge import create_knowledge_router
from memoria.api.map import create_map_router
from memoria.api.schemas import AssistantQueryRequest
from memoria.api.schemas import IngestScreenshotRequest
from memoria.api.screenshots import create_screenshot_router
from memoria.api.search import create_search_router
from memoria.assistant.service import answer_question
from memoria.domain.models import AssetInterpretation
from memoria.ocr.engines import OcrEngine
from memoria.ocr.service import OcrStageExecutionError
from memoria.runtime_engines import create_ocr_engine
from memoria.runtime_engines import create_vision_engine
from memoria.runtime_settings import RuntimeSettings
from memoria.runtime_settings import load_runtime_settings_from_env
from memoria.screenshots.pipeline import ProcessScreenshotCommand
from memoria.screenshots.pipeline import ingest_and_process_screenshot
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas
from memoria.vision.contracts import CandidateRef
from memoria.vision.contracts import EntityMention
from memoria.vision.contracts import VisionInterpretation
from memoria.vision.engines import VisionEngine
from memoria.vision.service import VisionStageExecutionError


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
    resolved_ocr_engine = ocr_engine or create_ocr_engine(settings)
    resolved_vision_engine = vision_engine or create_vision_engine(settings)
    app = FastAPI()
    app.include_router(create_knowledge_router(engine=engine))
    app.include_router(create_screenshot_router(engine=engine))
    app.include_router(create_search_router(engine=engine))
    app.include_router(create_map_router(engine=engine))

    @app.post("/ingest", status_code=201)
    def ingest_endpoint(payload: IngestScreenshotRequest) -> dict[str, int | str]:
        content = _decode_content_base64(payload.content_base64)

        with Session(engine) as session:
            try:
                result = ingest_and_process_screenshot(
                    session,
                    command=ProcessScreenshotCommand(
                        filename=payload.filename,
                        media_type=payload.media_type,
                        content=content,
                        connector_instance_id=payload.connector_instance_id,
                        external_id=payload.external_id,
                        source_created_at=payload.source_created_at,
                        source_observed_at=payload.source_observed_at,
                        blob_dir=blob_dir,
                        mode=payload.mode,
                        ocr_text=payload.ocr_text,
                    ),
                    settings=settings,
                    ocr_engine=resolved_ocr_engine,
                    vision_engine=resolved_vision_engine,
                )
            except (OcrStageExecutionError, VisionStageExecutionError) as exc:
                session.commit()
                raise HTTPException(status_code=500, detail=str(exc)) from exc

            session.commit()
            return {"source_item_id": result.source_item_id}

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
        entity_mentions=[
            EntityMention(**mention)
            for mention in json.loads(interpretation_row.entity_mentions_json or "[]")
        ],
        searchable_labels=json.loads(interpretation_row.searchable_labels_json or "[]"),
        cluster_hints=json.loads(interpretation_row.cluster_hints_json or "[]"),
        confidence=json.loads(interpretation_row.confidence_json),
        raw_model_payload=json.loads(interpretation_row.raw_model_payload_json or "{}"),
    )


def _decode_content_base64(content_base64: str) -> bytes:
    try:
        return base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="content_base64 must be valid base64") from exc
