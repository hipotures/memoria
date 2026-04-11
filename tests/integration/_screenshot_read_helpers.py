from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import Blob
from memoria.domain.models import KnowledgeClaim
from memoria.domain.models import PipelineRun
from memoria.domain.models import Projection
from memoria.domain.models import SourceItem
from memoria.domain.models import StageResult
from memoria.ingest.service import IngestScreenshotCommand
from memoria.ingest.service import ingest_screenshot
from memoria.knowledge.service import absorb_interpreted_screenshot
from memoria.pipeline import mark_pipeline_run_completed
from memoria.projections.service import refresh_assistant_context_projection
from memoria.projections.service import refresh_topic_status_projection
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas
from memoria.vision.contracts import CandidateRef
from memoria.vision.contracts import EntityMention
from memoria.vision.contracts import VisionInterpretation
from memoria.vision.service import RunVisionStageCommand
from memoria.vision.service import run_vision_stage
from memoria.ocr.service import RunOcrStageCommand
from memoria.ocr.service import run_ocr_stage


CANONICAL_ONLY_SOURCE_TIME = datetime(2026, 4, 1, 9, 5, 0)
OCR_ONLY_SOURCE_TIME = datetime(2026, 4, 2, 9, 5, 0)
INTERPRETATION_ONLY_SOURCE_TIME = datetime(2026, 4, 3, 9, 5, 0)
KNOWLEDGE_BACKED_SOURCE_TIME = datetime(2026, 4, 4, 9, 5, 0)


@dataclass(frozen=True, slots=True)
class SeededScreenshotDataset:
    canonical_only_source_item_id: int
    canonical_only_bytes: bytes
    ocr_only_source_item_id: int
    ocr_only_bytes: bytes
    interpretation_only_source_item_id: int
    interpretation_only_bytes: bytes
    knowledge_backed_source_item_id: int
    knowledge_backed_bytes: bytes


def create_test_engine(tmp_path: Path, database_name: str):
    database_path = tmp_path / database_name
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")
    return create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")


def create_test_client(tmp_path: Path, database_name: str):
    from memoria.api.app import create_app

    engine = create_test_engine(tmp_path, database_name)
    app = create_app(
        database_url=f"sqlite:///{tmp_path / database_name}",
        blob_dir=tmp_path / "blobs",
        ocr_engine=_UnusedOcrEngine(),
        vision_engine=_UnusedVisionEngine(),
    )
    return TestClient(app), engine


def seed_screenshot_dataset(engine, tmp_path: Path) -> SeededScreenshotDataset:
    canonical_only_bytes = b"canonical only screenshot bytes"
    ocr_only_bytes = b"ocr only screenshot bytes"
    interpretation_only_bytes = b"interpretation only screenshot bytes"
    knowledge_backed_bytes = b"knowledge backed screenshot bytes"

    canonical_only_source_item_id = _seed_canonical_only(
        engine,
        tmp_path,
        filename="capture-canonical-only.png",
        external_id="capture-canonical-only",
        content=canonical_only_bytes,
        connector_instance_id="manual-upload",
    )
    ocr_only_source_item_id = _seed_ocr_only(
        engine,
        tmp_path,
        filename="capture-ocr-only.png",
        external_id="capture-ocr-only",
        content=ocr_only_bytes,
        ocr_text="Reminder: submit expenses to Finance before Friday.",
        connector_instance_id="mobile-sync",
    )
    interpretation_only_source_item_id = _seed_interpretation_only(
        engine,
        tmp_path,
        filename="capture-interpretation-only.png",
        external_id="capture-interpretation-only",
        content=interpretation_only_bytes,
        ocr_text="Alice: book train tickets for Berlin",
        connector_instance_id="desktop-sync",
    )
    knowledge_backed_source_item_id = _seed_knowledge_backed(
        engine,
        tmp_path,
        filename="capture-knowledge-backed.png",
        external_id="capture-knowledge-backed",
        content=knowledge_backed_bytes,
        ocr_text="Alice: book train tickets for Berlin",
        connector_instance_id="manual-upload",
    )

    return SeededScreenshotDataset(
        canonical_only_source_item_id=canonical_only_source_item_id,
        canonical_only_bytes=canonical_only_bytes,
        ocr_only_source_item_id=ocr_only_source_item_id,
        ocr_only_bytes=ocr_only_bytes,
        interpretation_only_source_item_id=interpretation_only_source_item_id,
        interpretation_only_bytes=interpretation_only_bytes,
        knowledge_backed_source_item_id=knowledge_backed_source_item_id,
        knowledge_backed_bytes=knowledge_backed_bytes,
    )


def blob_path_for_source_item(engine, *, source_item_id: int) -> Path:
    with Session(engine) as session:
        source_item = session.get(SourceItem, source_item_id)
        assert source_item is not None
        blob = session.get(Blob, source_item.blob_id)
        assert blob is not None
        return Path(blob.storage_uri)


def read_only_row_counts(engine) -> dict[str, int]:
    with Session(engine) as session:
        return {
            "pipeline_runs": int(session.scalar(select(func.count()).select_from(PipelineRun)) or 0),
            "stage_results": int(session.scalar(select(func.count()).select_from(StageResult)) or 0),
            "knowledge_claims": int(session.scalar(select(func.count()).select_from(KnowledgeClaim)) or 0),
            "projections": int(session.scalar(select(func.count()).select_from(Projection)) or 0),
        }


def _seed_canonical_only(
    engine,
    tmp_path: Path,
    *,
    filename: str,
    external_id: str,
    content: bytes,
    connector_instance_id: str,
) -> int:
    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename=filename,
                media_type="image/png",
                content=content,
                connector_instance_id=connector_instance_id,
                external_id=external_id,
                blob_dir=tmp_path / "blobs",
                source_created_at=CANONICAL_ONLY_SOURCE_TIME,
                source_observed_at=CANONICAL_ONLY_SOURCE_TIME,
            ),
        )
        session.commit()
        return ingest_result.source_item_id


def _seed_ocr_only(
    engine,
    tmp_path: Path,
    *,
    filename: str,
    external_id: str,
    content: bytes,
    ocr_text: str,
    connector_instance_id: str,
) -> int:
    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename=filename,
                media_type="image/png",
                content=content,
                connector_instance_id=connector_instance_id,
                external_id=external_id,
                blob_dir=tmp_path / "blobs",
                source_created_at=OCR_ONLY_SOURCE_TIME,
                source_observed_at=OCR_ONLY_SOURCE_TIME,
            ),
        )
        run_ocr_stage(
            session,
            RunOcrStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                engine_name="manual-override",
                text_content=ocr_text,
            ),
        )
        session.commit()
        return ingest_result.source_item_id


def _seed_interpretation_only(
    engine,
    tmp_path: Path,
    *,
    filename: str,
    external_id: str,
    content: bytes,
    ocr_text: str,
    connector_instance_id: str,
) -> int:
    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename=filename,
                media_type="image/png",
                content=content,
                connector_instance_id=connector_instance_id,
                external_id=external_id,
                blob_dir=tmp_path / "blobs",
                source_created_at=INTERPRETATION_ONLY_SOURCE_TIME,
                source_observed_at=INTERPRETATION_ONLY_SOURCE_TIME,
            ),
        )
        run_ocr_stage(
            session,
            RunOcrStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                engine_name="manual-override",
                text_content=ocr_text,
            ),
        )
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                interpretation=_berlin_interpretation(),
            ),
        )
        session.commit()
        return ingest_result.source_item_id


def _seed_knowledge_backed(
    engine,
    tmp_path: Path,
    *,
    filename: str,
    external_id: str,
    content: bytes,
    ocr_text: str,
    connector_instance_id: str,
) -> int:
    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename=filename,
                media_type="image/png",
                content=content,
                connector_instance_id=connector_instance_id,
                external_id=external_id,
                blob_dir=tmp_path / "blobs",
                source_created_at=KNOWLEDGE_BACKED_SOURCE_TIME,
                source_observed_at=KNOWLEDGE_BACKED_SOURCE_TIME,
            ),
        )
        run_ocr_stage(
            session,
            RunOcrStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                engine_name="manual-override",
                text_content=ocr_text,
            ),
        )
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                interpretation=_berlin_interpretation(),
            ),
        )
        touched_refs = absorb_interpreted_screenshot(
            session,
            pipeline_run_id=ingest_result.pipeline_run_id,
            source_item_id=ingest_result.source_item_id,
        )
        assert touched_refs
        for object_ref in touched_refs:
            refresh_assistant_context_projection(session, object_ref=object_ref)
            if object_ref.startswith("topic:"):
                refresh_topic_status_projection(session, object_ref=object_ref)
        pipeline_run = session.get(PipelineRun, ingest_result.pipeline_run_id)
        assert pipeline_run is not None
        mark_pipeline_run_completed(session, pipeline_run)
        session.commit()
        return ingest_result.source_item_id


def _berlin_interpretation() -> VisionInterpretation:
    return VisionInterpretation(
        screen_category="chat",
        semantic_summary="Telegram chat about a Berlin trip with Alice and booking train tickets.",
        app_hint="telegram",
        topic_candidates=[
            CandidateRef(
                slug="trip-to-berlin",
                title="Trip to Berlin",
                confidence=0.95,
            )
        ],
        task_candidates=[
            CandidateRef(
                slug="book-train",
                title="Book train",
                confidence=0.89,
            )
        ],
        person_candidates=[
            CandidateRef(
                slug="alice",
                title="Alice",
                confidence=0.62,
            )
        ],
        entity_mentions=[
            EntityMention(
                type="person",
                text="Alice",
                confidence=0.62,
            )
        ],
        searchable_labels=["berlin", "telegram", "train tickets"],
        cluster_hints=["travel planning", "telegram chat"],
        confidence={"screen_category": 0.91, "semantic_summary": 0.85},
        raw_model_payload={
            "screen_category": "chat",
            "semantic_summary": "Telegram chat about a Berlin trip with Alice and booking train tickets.",
        },
    )


class _UnusedOcrEngine:
    def extract_text(self, *, image_bytes: bytes, media_type: str, language_hint: str | None = None):
        raise AssertionError("read API tests should not invoke OCR")


class _UnusedVisionEngine:
    def analyze(
        self,
        *,
        image_bytes: bytes,
        media_type: str,
        language_hint: str,
        app_hint_from_filename: str,
        ocr_text: str,
    ):
        raise AssertionError("read API tests should not invoke vision")
