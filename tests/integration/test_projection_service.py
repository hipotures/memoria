from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import Projection
from memoria.ingest.service import IngestScreenshotCommand
from memoria.ingest.service import ingest_screenshot
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas


def test_projection_refresh_builds_assistant_and_topic_views(tmp_path):
    try:
        from memoria.knowledge.service import absorb_interpreted_screenshot
        from memoria.projections.service import refresh_assistant_context_projection
        from memoria.projections.service import refresh_topic_status_projection
        from memoria.vision.contracts import CandidateRef
        from memoria.vision.contracts import VisionInterpretation
        from memoria.vision.service import RunVisionStageCommand
        from memoria.vision.service import run_vision_stage
    except ImportError as exc:
        pytest.fail(f"projection service not implemented yet: {exc}")

    engine = _create_engine(tmp_path, "projection.db")

    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-projection.png",
                media_type="image/png",
                content=b"fake screenshot bytes for projection refresh",
                connector_instance_id="manual-upload",
                external_id="capture-projection",
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
        absorb_interpreted_screenshot(
            session,
            pipeline_run_id=ingest_result.pipeline_run_id,
            source_item_id=ingest_result.source_item_id,
        )
        refresh_assistant_context_projection(
            session,
            object_ref="topic:trip-to-berlin",
        )
        refresh_topic_status_projection(
            session,
            object_ref="topic:trip-to-berlin",
        )
        session.commit()

    with Session(engine) as session:
        projections = session.scalars(
            select(Projection).where(Projection.object_ref == "topic:trip-to-berlin")
        ).all()

    assert {projection.projection_type for projection in projections} == {
        "assistant_context_projection",
        "topic_status_projection",
    }


def _create_engine(tmp_path, database_name: str):
    database_path = tmp_path / database_name
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")
    return create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
