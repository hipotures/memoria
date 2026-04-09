from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import KnowledgeClaim
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import KnowledgeObject
from memoria.domain.models import StageResult
from memoria.ingest.service import IngestScreenshotCommand
from memoria.ingest.service import ingest_screenshot
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas


def test_absorb_creates_topic_thread_task_claims_and_evidence(tmp_path):
    try:
        from memoria.knowledge.service import absorb_interpreted_screenshot
        from memoria.vision.contracts import CandidateRef
        from memoria.vision.contracts import VisionInterpretation
        from memoria.vision.service import RunVisionStageCommand
        from memoria.vision.service import run_vision_stage
    except ImportError as exc:
        pytest.fail(f"absorb service not implemented yet: {exc}")

    engine = _create_engine(tmp_path, "absorb.db")

    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-absorb.png",
                media_type="image/png",
                content=b"fake screenshot bytes for absorb",
                connector_instance_id="manual-upload",
                external_id="capture-absorb",
                blob_dir=tmp_path / "blobs",
            ),
        )
        session.commit()

    with Session(engine) as session:
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                interpretation=VisionInterpretation(
                    screen_category="chat",
                    semantic_summary=(
                        "Telegram chat about a Berlin trip with Alice and booking train tickets."
                    ),
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
                    confidence={"screen_category": 0.91, "semantic_summary": 0.85},
                ),
            ),
        )
        session.commit()

    with Session(engine) as session:
        touched_refs = absorb_interpreted_screenshot(
            session,
            pipeline_run_id=ingest_result.pipeline_run_id,
            source_item_id=ingest_result.source_item_id,
        )
        session.commit()

    with Session(engine) as session:
        objects = session.scalars(select(KnowledgeObject)).all()
        claims = session.scalars(select(KnowledgeClaim)).all()
        evidence_links = session.scalars(select(KnowledgeEvidenceLink)).all()
        stage_results = session.scalars(
            select(StageResult)
            .where(
                StageResult.pipeline_run_id == ingest_result.pipeline_run_id,
                StageResult.stage_name == "absorb",
            )
            .order_by(StageResult.attempt.asc())
        ).all()

    object_refs = {row.slug for row in objects}
    claim_signatures = {
        (row.claim_type, row.subject_ref, row.predicate, row.object_ref_or_value)
        for row in claims
    }

    assert {"thread", "topic", "task", "person"} == {row.object_type for row in objects}
    assert {
        "thread:telegram-trip-to-berlin",
        "topic:trip-to-berlin",
        "task:book-train",
        "person:alice",
    } <= object_refs
    assert (
        "membership",
        "thread:telegram-trip-to-berlin",
        "belongs_to_topic",
        "topic:trip-to-berlin",
    ) in claim_signatures
    assert ("task_status", "task:book-train", "status", "open") in claim_signatures
    assert (
        "person_hint",
        "thread:telegram-trip-to-berlin",
        "involves_person",
        "person:alice",
    ) in claim_signatures
    assert len(evidence_links) >= 3
    assert all(link.fragment_type == "interpretation" for link in evidence_links)
    assert all(link.fragment_ref == "summary" for link in evidence_links)
    assert all(link.support_role == "primary" for link in evidence_links)
    assert [stage_result.attempt for stage_result in stage_results] == [1]
    assert all(stage_result.status == "completed" for stage_result in stage_results)
    assert "topic:trip-to-berlin" in touched_refs


def test_absorb_is_idempotent_for_same_interpreted_packet(tmp_path):
    from memoria.knowledge.service import absorb_interpreted_screenshot
    from memoria.vision.contracts import CandidateRef
    from memoria.vision.contracts import VisionInterpretation
    from memoria.vision.service import RunVisionStageCommand
    from memoria.vision.service import run_vision_stage

    engine = _create_engine(tmp_path, "absorb-idempotent.db")

    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-absorb-idempotent.png",
                media_type="image/png",
                content=b"fake screenshot bytes for absorb idempotency",
                connector_instance_id="manual-upload",
                external_id="capture-absorb-idempotent",
                blob_dir=tmp_path / "blobs",
            ),
        )
        session.commit()

    with Session(engine) as session:
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                interpretation=VisionInterpretation(
                    screen_category="chat",
                    semantic_summary=(
                        "Telegram chat about a Berlin trip with Alice and booking train tickets."
                    ),
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
                    confidence={"screen_category": 0.91, "semantic_summary": 0.85},
                ),
            ),
        )
        session.commit()

    with Session(engine) as session:
        first_refs = absorb_interpreted_screenshot(
            session,
            pipeline_run_id=ingest_result.pipeline_run_id,
            source_item_id=ingest_result.source_item_id,
        )
        session.commit()

    with Session(engine) as session:
        second_refs = absorb_interpreted_screenshot(
            session,
            pipeline_run_id=ingest_result.pipeline_run_id,
            source_item_id=ingest_result.source_item_id,
        )
        session.commit()

    with Session(engine) as session:
        object_count = session.scalar(select(func.count()).select_from(KnowledgeObject))
        claim_count = session.scalar(select(func.count()).select_from(KnowledgeClaim))
        evidence_count = session.scalar(select(func.count()).select_from(KnowledgeEvidenceLink))
        stage_results = session.scalars(
            select(StageResult)
            .where(
                StageResult.pipeline_run_id == ingest_result.pipeline_run_id,
                StageResult.stage_name == "absorb",
            )
            .order_by(StageResult.attempt.asc())
        ).all()

    assert second_refs == first_refs
    assert object_count == 4
    assert claim_count == 3
    assert evidence_count == 3
    assert [stage_result.attempt for stage_result in stage_results] == [1, 2]
    assert all(stage_result.status == "completed" for stage_result in stage_results)


def test_absorb_marks_task_claim_uncertain_when_new_signal_conflicts(tmp_path):
    from memoria.knowledge.service import absorb_interpreted_screenshot
    from memoria.vision.contracts import CandidateRef
    from memoria.vision.contracts import VisionInterpretation
    from memoria.vision.service import RunVisionStageCommand
    from memoria.vision.service import run_vision_stage

    engine = _create_engine(tmp_path, "absorb-conflict.db")

    with Session(engine) as session:
        first_ingest = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-open.png",
                media_type="image/png",
                content=b"first screenshot bytes",
                connector_instance_id="manual-upload",
                external_id="capture-open",
                blob_dir=tmp_path / "blobs",
            ),
        )
        second_ingest = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-done.png",
                media_type="image/png",
                content=b"second screenshot bytes",
                connector_instance_id="manual-upload",
                external_id="capture-done",
                blob_dir=tmp_path / "blobs",
            ),
        )
        session.commit()

    with Session(engine) as session:
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=first_ingest.pipeline_run_id,
                source_item_id=first_ingest.source_item_id,
                interpretation=VisionInterpretation(
                    screen_category="chat",
                    semantic_summary="Telegram chat about a Berlin trip and booking train tickets.",
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
                    person_candidates=[],
                    confidence={"screen_category": 0.91, "semantic_summary": 0.85},
                ),
            ),
        )
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=second_ingest.pipeline_run_id,
                source_item_id=second_ingest.source_item_id,
                interpretation=VisionInterpretation(
                    screen_category="chat",
                    semantic_summary=(
                        "Telegram chat about a Berlin trip and booking train tickets completed."
                    ),
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
                    person_candidates=[],
                    confidence={"screen_category": 0.93, "semantic_summary": 0.88},
                ),
            ),
        )
        session.commit()

    with Session(engine) as session:
        absorb_interpreted_screenshot(
            session,
            pipeline_run_id=first_ingest.pipeline_run_id,
            source_item_id=first_ingest.source_item_id,
        )
        absorb_interpreted_screenshot(
            session,
            pipeline_run_id=second_ingest.pipeline_run_id,
            source_item_id=second_ingest.source_item_id,
        )
        session.commit()

    with Session(engine) as session:
        task_claims = session.scalars(
            select(KnowledgeClaim).where(
                KnowledgeClaim.claim_type == "task_status",
                KnowledgeClaim.subject_ref == "task:book-train",
                KnowledgeClaim.predicate == "status",
            )
        ).all()

    assert len(task_claims) == 1
    assert task_claims[0].status == "uncertain"


@pytest.mark.parametrize(
    ("semantic_summary", "expected_status"),
    [
        (
            "Telegram chat about a Berlin trip and booking train tickets not done yet.",
            "open",
        ),
        (
            "Telegram chat about a Berlin trip and booking train tickets not completed.",
            "open",
        ),
        (
            "Telegram chat about a Berlin trip and booking train tickets not shipped.",
            "open",
        ),
        (
            "Telegram chat about a Berlin trip and booking train tickets unshipped.",
            "open",
        ),
        (
            "Telegram chat about a Berlin trip and booking train tickets still open.",
            "open",
        ),
        (
            "Telegram chat about a Berlin trip and booking train tickets pending.",
            "open",
        ),
        (
            "Telegram chat about a Berlin trip and booking train tickets completed.",
            "done",
        ),
    ],
)
def test_absorb_infers_task_status_from_negated_and_positive_completion_phrases(
    tmp_path,
    semantic_summary,
    expected_status,
):
    from memoria.knowledge.service import absorb_interpreted_screenshot
    from memoria.vision.contracts import CandidateRef
    from memoria.vision.contracts import VisionInterpretation
    from memoria.vision.service import RunVisionStageCommand
    from memoria.vision.service import run_vision_stage

    engine = _create_engine(tmp_path, "absorb-negation.db")

    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-negation.png",
                media_type="image/png",
                content=semantic_summary.encode("utf-8"),
                connector_instance_id="manual-upload",
                external_id="capture-negation",
                blob_dir=tmp_path / "blobs",
            ),
        )
        session.commit()

    with Session(engine) as session:
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                interpretation=VisionInterpretation(
                    screen_category="chat",
                    semantic_summary=semantic_summary,
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
                    person_candidates=[],
                    confidence={"screen_category": 0.91, "semantic_summary": 0.85},
                ),
            ),
        )
        session.commit()

    with Session(engine) as session:
        absorb_interpreted_screenshot(
            session,
            pipeline_run_id=ingest_result.pipeline_run_id,
            source_item_id=ingest_result.source_item_id,
        )
        session.commit()

    with Session(engine) as session:
        task_claim = session.scalar(
            select(KnowledgeClaim).where(
                KnowledgeClaim.claim_type == "task_status",
                KnowledgeClaim.subject_ref == "task:book-train",
                KnowledgeClaim.predicate == "status",
            )
        )

    assert task_claim is not None
    assert task_claim.object_ref_or_value == expected_status


def _create_engine(tmp_path, database_name: str):
    database_path = tmp_path / database_name
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")
    return create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
