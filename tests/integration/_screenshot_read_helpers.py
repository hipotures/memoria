from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
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
ATLAS_SOURCE_START_TIME = datetime(2026, 4, 5, 9, 5, 0)


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


@dataclass(frozen=True, slots=True)
class SeededAtlasDataset:
    source_item_ids: list[int]
    travel_source_item_ids: list[int]
    finance_source_item_ids: list[int]
    semantic_map_run_id: int
    atlas_run_id: int | None = None

    @property
    def total_source_items(self) -> int:
        return len(self.source_item_ids)


@dataclass(frozen=True, slots=True)
class _AtlasSeedSpec:
    filename: str
    external_id: str
    connector_instance_id: str
    source_time: datetime
    content: bytes
    ocr_text: str
    interpretation: VisionInterpretation
    absorb: bool


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


def seed_atlas_dataset(
    engine,
    tmp_path: Path,
    *,
    rebuild_atlas: bool = False,
) -> SeededAtlasDataset:
    travel_specs = [
        _AtlasSeedSpec(
            filename="atlas-travel-01-telegram.png",
            external_id="atlas-travel-01",
            connector_instance_id="atlas-seed",
            source_time=ATLAS_SOURCE_START_TIME,
            content=b"atlas travel 01",
            ocr_text="Telegram thread about Berlin train tickets, hotel check-in, and Alice.",
            interpretation=_atlas_interpretation(
                screen_category="chat",
                semantic_summary="Telegram chat about Berlin train tickets, hotel check-in, and coordinating with Alice.",
                app_hint="telegram",
                topic_slug="trip-to-berlin",
                topic_title="Trip to Berlin",
                task_slug="book-train",
                task_title="Book train tickets",
                person_slug="alice",
                person_title="Alice",
                searchable_labels=["berlin", "travel", "train tickets"],
                cluster_hints=["travel planning", "berlin trip"],
                entity_mentions=["Alice"],
            ),
            absorb=True,
        ),
        _AtlasSeedSpec(
            filename="atlas-travel-02-telegram.png",
            external_id="atlas-travel-02",
            connector_instance_id="atlas-seed",
            source_time=ATLAS_SOURCE_START_TIME + timedelta(minutes=5),
            content=b"atlas travel 02",
            ocr_text="Berlin museum pass, train seats, and weekend itinerary planning.",
            interpretation=_atlas_interpretation(
                screen_category="chat",
                semantic_summary="Telegram planning notes for Berlin museum passes, train seats, and a weekend itinerary.",
                app_hint="telegram",
                topic_slug="trip-to-berlin",
                topic_title="Trip to Berlin",
                task_slug="confirm-itinerary",
                task_title="Confirm itinerary",
                person_slug="alice",
                person_title="Alice",
                searchable_labels=["berlin", "museum pass", "weekend"],
                cluster_hints=["travel planning", "itinerary"],
                entity_mentions=["Alice"],
            ),
            absorb=False,
        ),
        _AtlasSeedSpec(
            filename="atlas-travel-03-whatsapp.png",
            external_id="atlas-travel-03",
            connector_instance_id="atlas-seed",
            source_time=ATLAS_SOURCE_START_TIME + timedelta(minutes=10),
            content=b"atlas travel 03",
            ocr_text="WhatsApp reminder to confirm hostel reservation and train platform for Berlin.",
            interpretation=_atlas_interpretation(
                screen_category="chat",
                semantic_summary="WhatsApp reminder to confirm the Berlin hostel reservation and train platform details.",
                app_hint="whatsapp",
                topic_slug="trip-to-berlin",
                topic_title="Trip to Berlin",
                task_slug="confirm-hostel",
                task_title="Confirm hostel reservation",
                person_slug="alice",
                person_title="Alice",
                searchable_labels=["berlin", "hostel", "platform"],
                cluster_hints=["travel planning", "lodging"],
                entity_mentions=["Alice"],
            ),
            absorb=True,
        ),
        _AtlasSeedSpec(
            filename="atlas-travel-04-maps.png",
            external_id="atlas-travel-04",
            connector_instance_id="atlas-seed",
            source_time=ATLAS_SOURCE_START_TIME + timedelta(minutes=15),
            content=b"atlas travel 04",
            ocr_text="Berlin station directions, luggage storage, and route to the hotel.",
            interpretation=_atlas_interpretation(
                screen_category="map",
                semantic_summary="Maps screenshot with Berlin station directions, luggage storage options, and the route to the hotel.",
                app_hint="maps",
                topic_slug="trip-to-berlin",
                topic_title="Trip to Berlin",
                task_slug="plan-arrival",
                task_title="Plan station arrival",
                person_slug="alice",
                person_title="Alice",
                searchable_labels=["berlin", "station", "hotel"],
                cluster_hints=["travel planning", "arrival logistics"],
                entity_mentions=["Berlin"],
            ),
            absorb=False,
        ),
        _AtlasSeedSpec(
            filename="atlas-travel-05-email.png",
            external_id="atlas-travel-05",
            connector_instance_id="atlas-seed",
            source_time=ATLAS_SOURCE_START_TIME + timedelta(minutes=20),
            content=b"atlas travel 05",
            ocr_text="Email with Berlin weekend itinerary, museum bookings, and departure details.",
            interpretation=_atlas_interpretation(
                screen_category="email",
                semantic_summary="Email with a Berlin weekend itinerary, museum bookings, and departure details for the train trip.",
                app_hint="gmail",
                topic_slug="trip-to-berlin",
                topic_title="Trip to Berlin",
                task_slug="review-bookings",
                task_title="Review bookings",
                person_slug="alice",
                person_title="Alice",
                searchable_labels=["berlin", "museum", "departure"],
                cluster_hints=["travel planning", "bookings"],
                entity_mentions=["Alice"],
            ),
            absorb=True,
        ),
        _AtlasSeedSpec(
            filename="atlas-travel-06-calendar.png",
            external_id="atlas-travel-06",
            connector_instance_id="atlas-seed",
            source_time=ATLAS_SOURCE_START_TIME + timedelta(minutes=25),
            content=b"atlas travel 06",
            ocr_text="Calendar reminder for Berlin departure, packing list, and passport check.",
            interpretation=_atlas_interpretation(
                screen_category="calendar",
                semantic_summary="Calendar reminder for Berlin departure, a packing list, and a passport check before the train ride.",
                app_hint="calendar",
                topic_slug="trip-to-berlin",
                topic_title="Trip to Berlin",
                task_slug="pack-bags",
                task_title="Pack bags",
                person_slug="alice",
                person_title="Alice",
                searchable_labels=["berlin", "packing", "passport"],
                cluster_hints=["travel planning", "checklist"],
                entity_mentions=["Alice"],
            ),
            absorb=False,
        ),
        _AtlasSeedSpec(
            filename="atlas-travel-07-booking.png",
            external_id="atlas-travel-07",
            connector_instance_id="atlas-seed",
            source_time=ATLAS_SOURCE_START_TIME + timedelta(minutes=30),
            content=b"atlas travel 07",
            ocr_text="Booking confirmation for Berlin rail tickets, seat numbers, and hotel dates.",
            interpretation=_atlas_interpretation(
                screen_category="document",
                semantic_summary="Booking confirmation for Berlin rail tickets, seat numbers, and hotel stay dates.",
                app_hint="browser",
                topic_slug="trip-to-berlin",
                topic_title="Trip to Berlin",
                task_slug="verify-seats",
                task_title="Verify seats",
                person_slug="alice",
                person_title="Alice",
                searchable_labels=["berlin", "rail", "hotel dates"],
                cluster_hints=["travel planning", "tickets"],
                entity_mentions=["Alice"],
            ),
            absorb=True,
        ),
        _AtlasSeedSpec(
            filename="atlas-travel-08-notes.png",
            external_id="atlas-travel-08",
            connector_instance_id="atlas-seed",
            source_time=ATLAS_SOURCE_START_TIME + timedelta(minutes=35),
            content=b"atlas travel 08",
            ocr_text="Notes app packing checklist for Berlin, chargers, headphones, and snack stop.",
            interpretation=_atlas_interpretation(
                screen_category="notes",
                semantic_summary="Notes app packing checklist for Berlin with chargers, headphones, snacks, and station timing.",
                app_hint="notes",
                topic_slug="trip-to-berlin",
                topic_title="Trip to Berlin",
                task_slug="final-checklist",
                task_title="Review final checklist",
                person_slug="alice",
                person_title="Alice",
                searchable_labels=["berlin", "checklist", "station"],
                cluster_hints=["travel planning", "packing"],
                entity_mentions=["Alice"],
            ),
            absorb=False,
        ),
    ]
    finance_specs = [
        _AtlasSeedSpec(
            filename="atlas-finance-01-slack.png",
            external_id="atlas-finance-01",
            connector_instance_id="atlas-seed",
            source_time=ATLAS_SOURCE_START_TIME + timedelta(hours=1),
            content=b"atlas finance 01",
            ocr_text="Slack thread about April budget close, vendor invoices, and finance approvals.",
            interpretation=_atlas_interpretation(
                screen_category="chat",
                semantic_summary="Slack thread about the April budget close, vendor invoices, and finance approvals.",
                app_hint="slack",
                topic_slug="month-end-close",
                topic_title="Month-end close",
                task_slug="approve-invoices",
                task_title="Approve invoices",
                person_slug="morgan",
                person_title="Morgan",
                searchable_labels=["budget", "finance", "invoices"],
                cluster_hints=["finance ops", "month end"],
                entity_mentions=["Morgan"],
            ),
            absorb=True,
        ),
        _AtlasSeedSpec(
            filename="atlas-finance-02-sheet.png",
            external_id="atlas-finance-02",
            connector_instance_id="atlas-seed",
            source_time=ATLAS_SOURCE_START_TIME + timedelta(hours=1, minutes=5),
            content=b"atlas finance 02",
            ocr_text="Spreadsheet with budget variance, cost centers, and vendor invoice totals.",
            interpretation=_atlas_interpretation(
                screen_category="spreadsheet",
                semantic_summary="Spreadsheet showing budget variance, cost centers, and vendor invoice totals for finance review.",
                app_hint="sheets",
                topic_slug="month-end-close",
                topic_title="Month-end close",
                task_slug="check-variance",
                task_title="Check budget variance",
                person_slug="morgan",
                person_title="Morgan",
                searchable_labels=["budget variance", "finance", "spreadsheet"],
                cluster_hints=["finance ops", "budget review"],
                entity_mentions=["Morgan"],
            ),
            absorb=False,
        ),
        _AtlasSeedSpec(
            filename="atlas-finance-03-email.png",
            external_id="atlas-finance-03",
            connector_instance_id="atlas-seed",
            source_time=ATLAS_SOURCE_START_TIME + timedelta(hours=1, minutes=10),
            content=b"atlas finance 03",
            ocr_text="Email reminder to send expense report and invoice totals to finance before noon.",
            interpretation=_atlas_interpretation(
                screen_category="email",
                semantic_summary="Email reminder to send the expense report and invoice totals to finance before noon.",
                app_hint="gmail",
                topic_slug="month-end-close",
                topic_title="Month-end close",
                task_slug="send-expense-report",
                task_title="Send expense report",
                person_slug="morgan",
                person_title="Morgan",
                searchable_labels=["expense report", "finance", "invoice totals"],
                cluster_hints=["finance ops", "reporting"],
                entity_mentions=["Morgan"],
            ),
            absorb=True,
        ),
    ]

    travel_source_item_ids = [
        _seed_completed_interpreted_screenshot(engine, tmp_path, spec=spec)
        for spec in travel_specs
    ]
    finance_source_item_ids = [
        _seed_completed_interpreted_screenshot(engine, tmp_path, spec=spec)
        for spec in finance_specs
    ]

    atlas_run_id: int | None = None
    with Session(engine) as session:
        from memoria.map.service import rebuild_semantic_map

        rebuild_semantic_map(session, source_family="screenshot")
        session.commit()

    with Session(engine) as session:
        from memoria.domain.models import SemanticMapRun

        semantic_map_run_id = session.scalar(select(SemanticMapRun.id).order_by(SemanticMapRun.id.desc()))
        assert semantic_map_run_id is not None
        if rebuild_atlas:
            from memoria.atlas.projection import rebuild_screenshot_atlas

            atlas_result = rebuild_screenshot_atlas(session, force=True)
            atlas_run_id = int(atlas_result["atlas_run_id"])
        session.commit()

    return SeededAtlasDataset(
        source_item_ids=travel_source_item_ids + finance_source_item_ids,
        travel_source_item_ids=travel_source_item_ids,
        finance_source_item_ids=finance_source_item_ids,
        semantic_map_run_id=semantic_map_run_id,
        atlas_run_id=atlas_run_id,
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


def _seed_completed_interpreted_screenshot(
    engine,
    tmp_path: Path,
    *,
    spec: _AtlasSeedSpec,
) -> int:
    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename=spec.filename,
                media_type="image/png",
                content=spec.content,
                connector_instance_id=spec.connector_instance_id,
                external_id=spec.external_id,
                blob_dir=tmp_path / "blobs",
                source_created_at=spec.source_time,
                source_observed_at=spec.source_time,
            ),
        )
        run_ocr_stage(
            session,
            RunOcrStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                engine_name="manual-override",
                text_content=spec.ocr_text,
            ),
        )
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                interpretation=spec.interpretation,
            ),
        )
        if spec.absorb:
            touched_refs = absorb_interpreted_screenshot(
                session,
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
            )
            for object_ref in touched_refs:
                refresh_assistant_context_projection(session, object_ref=object_ref)
                if object_ref.startswith("topic:"):
                    refresh_topic_status_projection(session, object_ref=object_ref)
        pipeline_run = session.get(PipelineRun, ingest_result.pipeline_run_id)
        assert pipeline_run is not None
        mark_pipeline_run_completed(session, pipeline_run)
        session.commit()
        return ingest_result.source_item_id


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


def _atlas_interpretation(
    *,
    screen_category: str,
    semantic_summary: str,
    app_hint: str,
    topic_slug: str,
    topic_title: str,
    task_slug: str,
    task_title: str,
    person_slug: str,
    person_title: str,
    searchable_labels: list[str],
    cluster_hints: list[str],
    entity_mentions: list[str],
) -> VisionInterpretation:
    return VisionInterpretation(
        screen_category=screen_category,
        semantic_summary=semantic_summary,
        app_hint=app_hint,
        topic_candidates=[
            CandidateRef(
                slug=topic_slug,
                title=topic_title,
                confidence=0.95,
            )
        ],
        task_candidates=[
            CandidateRef(
                slug=task_slug,
                title=task_title,
                confidence=0.88,
            )
        ],
        person_candidates=[
            CandidateRef(
                slug=person_slug,
                title=person_title,
                confidence=0.71,
            )
        ],
        entity_mentions=[
            EntityMention(
                type="person" if mention == person_title else "topic",
                text=mention,
                confidence=0.72,
            )
            for mention in entity_mentions
        ],
        searchable_labels=searchable_labels,
        cluster_hints=cluster_hints,
        confidence={"screen_category": 0.92, "semantic_summary": 0.87},
        raw_model_payload={
            "screen_category": screen_category,
            "semantic_summary": semantic_summary,
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
