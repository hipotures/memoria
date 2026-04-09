from __future__ import annotations

import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetInterpretation
from memoria.domain.models import ContentFragment
from memoria.domain.models import PipelineRun
from memoria.domain.models import StageResult
from memoria.ingest.service import IngestScreenshotCommand
from memoria.ingest.service import ingest_screenshot
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas


def test_run_vision_stage_persists_interpretation_and_summary_fragment(tmp_path):
    try:
        from memoria.vision.contracts import CandidateRef
        from memoria.vision.contracts import VisionInterpretation
        from memoria.vision.service import RunVisionStageCommand
        from memoria.vision.service import run_vision_stage
    except ImportError as exc:
        pytest.fail(f"vision service not implemented yet: {exc}")

    database_path = tmp_path / "vision.db"
    blob_dir = tmp_path / "blobs"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"

    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")

    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-vision.png",
                media_type="image/png",
                content=b"fake screenshot bytes for vision",
                connector_instance_id="manual-upload",
                external_id="capture-vision",
                blob_dir=blob_dir,
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
                    semantic_summary="Telegram chat about shipping Task 5 this afternoon.",
                    app_hint="telegram",
                    topic_candidates=[
                        CandidateRef(slug="task-5", title="Task 5", confidence=0.98)
                    ],
                    task_candidates=[
                        CandidateRef(
                            slug="ship-vision-persistence",
                            title="Ship vision persistence",
                            confidence=0.96,
                        )
                    ],
                    person_candidates=[
                        CandidateRef(slug="alex", title="Alex", confidence=0.72)
                    ],
                    confidence={"screen_category": 0.99, "app_hint": 0.97},
                ),
            ),
        )
        session.commit()

    with Session(engine) as session:
        interpretation_row = session.get(AssetInterpretation, ingest_result.source_item_id)
        summary_fragment = session.scalar(
            select(ContentFragment).where(
                ContentFragment.source_item_id == ingest_result.source_item_id,
                ContentFragment.fragment_type == "scene_description",
                ContentFragment.fragment_ref == "summary",
            )
        )
        app_fragment = session.scalar(
            select(ContentFragment).where(
                ContentFragment.source_item_id == ingest_result.source_item_id,
                ContentFragment.fragment_type == "app_hint",
                ContentFragment.fragment_ref == "detected_app",
            )
        )
        stage = session.scalar(
            select(StageResult).where(
                StageResult.pipeline_run_id == ingest_result.pipeline_run_id,
                StageResult.stage_name == "vision",
            )
        )

    assert interpretation_row is not None
    assert interpretation_row.screen_category == "chat"
    assert interpretation_row.app_hint == "telegram"
    assert json.loads(interpretation_row.topic_candidates_json) == [
        {"confidence": 0.98, "slug": "task-5", "title": "Task 5"}
    ]
    assert json.loads(interpretation_row.task_candidates_json) == [
        {
            "confidence": 0.96,
            "slug": "ship-vision-persistence",
            "title": "Ship vision persistence",
        }
    ]
    assert json.loads(interpretation_row.person_candidates_json) == [
        {"confidence": 0.72, "slug": "alex", "title": "Alex"}
    ]
    assert json.loads(interpretation_row.confidence_json) == {
        "app_hint": 0.97,
        "screen_category": 0.99,
    }

    assert summary_fragment is not None
    assert summary_fragment.fragment_type == "scene_description"
    assert summary_fragment.fragment_ref == "summary"
    assert summary_fragment.fragment_text.startswith("Telegram chat")

    assert app_fragment is not None
    assert app_fragment.fragment_type == "app_hint"
    assert app_fragment.fragment_ref == "detected_app"
    assert app_fragment.fragment_text == "telegram"

    assert stage is not None
    assert stage.status == "completed"


def test_run_vision_stage_is_replay_safe_and_tracks_attempts(tmp_path):
    from memoria.vision.contracts import VisionInterpretation
    from memoria.vision.service import RunVisionStageCommand
    from memoria.vision.service import run_vision_stage

    database_path = tmp_path / "vision-replay.db"
    blob_dir = tmp_path / "blobs"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"

    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")

    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-vision-replay.png",
                media_type="image/png",
                content=b"fake screenshot bytes for vision replay",
                connector_instance_id="manual-upload",
                external_id="capture-vision-replay",
                blob_dir=blob_dir,
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
                    semantic_summary="Telegram chat about a first summary.",
                    app_hint="telegram",
                ),
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
                    semantic_summary="Telegram chat about an updated summary.",
                    app_hint=None,
                ),
            ),
        )
        session.commit()

    with Session(engine) as session:
        interpretation_row = session.get(AssetInterpretation, ingest_result.source_item_id)
        summary_fragment = session.scalar(
            select(ContentFragment).where(
                ContentFragment.source_item_id == ingest_result.source_item_id,
                ContentFragment.fragment_type == "scene_description",
                ContentFragment.fragment_ref == "summary",
            )
        )
        app_fragment = session.scalar(
            select(ContentFragment).where(
                ContentFragment.source_item_id == ingest_result.source_item_id,
                ContentFragment.fragment_type == "app_hint",
                ContentFragment.fragment_ref == "detected_app",
            )
        )
        stage_results = session.scalars(
            select(StageResult)
            .where(
                StageResult.pipeline_run_id == ingest_result.pipeline_run_id,
                StageResult.stage_name == "vision",
            )
            .order_by(StageResult.attempt.asc())
        ).all()

    assert interpretation_row is not None
    assert interpretation_row.semantic_summary == "Telegram chat about an updated summary."
    assert interpretation_row.app_hint is None

    assert summary_fragment is not None
    assert summary_fragment.fragment_text == "Telegram chat about an updated summary."
    assert app_fragment is None

    assert len(stage_results) == 2
    assert [stage_result.attempt for stage_result in stage_results] == [1, 2]
    assert all(stage_result.status == "completed" for stage_result in stage_results)


def test_run_vision_stage_rejects_mismatched_pipeline_run_and_source_item(tmp_path):
    from memoria.vision.contracts import VisionInterpretation
    from memoria.vision.service import RunVisionStageCommand
    from memoria.vision.service import run_vision_stage

    database_path = tmp_path / "vision-mismatch.db"
    blob_dir = tmp_path / "blobs"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"

    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")

    with Session(engine) as session:
        first_ingest = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-vision-mismatch-1.png",
                media_type="image/png",
                content=b"fake screenshot bytes one",
                connector_instance_id="manual-upload",
                external_id="capture-vision-mismatch-1",
                blob_dir=blob_dir,
            ),
        )
        second_ingest = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-vision-mismatch-2.png",
                media_type="image/png",
                content=b"fake screenshot bytes two",
                connector_instance_id="manual-upload",
                external_id="capture-vision-mismatch-2",
                blob_dir=blob_dir,
            ),
        )
        session.commit()

    with Session(engine) as session:
        with pytest.raises(ValueError):
            run_vision_stage(
                session,
                RunVisionStageCommand(
                    pipeline_run_id=first_ingest.pipeline_run_id,
                    source_item_id=second_ingest.source_item_id,
                    interpretation=VisionInterpretation(
                        screen_category="chat",
                        semantic_summary="Telegram chat mismatch.",
                        app_hint="telegram",
                    ),
                ),
            )
        session.rollback()

    with Session(engine) as session:
        interpretation_rows = session.scalar(select(func.count()).select_from(AssetInterpretation))
        fragment_rows = session.scalar(
            select(func.count()).select_from(ContentFragment).where(
                ContentFragment.fragment_type.in_(["scene_description", "app_hint"])
            )
        )
        stage_results = session.scalar(
            select(func.count()).select_from(StageResult).where(StageResult.stage_name == "vision")
        )

    assert interpretation_rows == 0
    assert fragment_rows == 0
    assert stage_results == 0


def test_execute_vision_stage_runs_engine_and_persists_interpretation(tmp_path):
    from memoria.ocr.service import RunOcrStageCommand
    from memoria.ocr.service import run_ocr_stage
    from memoria.vision.engines import CategoryLabel
    from memoria.vision.engines import VisionEngineResult
    from memoria.vision.service import ExecuteVisionStageCommand
    from memoria.vision.service import execute_vision_stage

    database_path = tmp_path / "vision-exec.db"
    blob_dir = tmp_path / "blobs"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"

    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")

    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="Screenshot_20260409_120000_Telegram.png",
                media_type="image/png",
                content=b"fake screenshot bytes for vision execution",
                connector_instance_id="manual-upload",
                external_id="capture-vision-exec",
                blob_dir=blob_dir,
            ),
        )
        run_ocr_stage(
            session,
            RunOcrStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                engine_name="manual_override",
                text_content="Alice: book train tickets for Berlin",
            ),
        )
        session.commit()

    class _FakeVisionEngine:
        def analyze(
            self,
            *,
            image_bytes: bytes,
            media_type: str,
            language_hint: str,
            app_hint_from_filename: str,
            ocr_text: str,
        ):
            return VisionEngineResult(
                engine_name="fake-vision",
                summary_pl=ocr_text,
                summary_en=ocr_text,
                categories=[
                    CategoryLabel(pl="chat", en="chat"),
                    CategoryLabel(pl="travel", en="travel"),
                    CategoryLabel(pl="task", en="task"),
                    CategoryLabel(pl="reminder", en="reminder"),
                    CategoryLabel(pl="assistant", en="assistant"),
                ],
                app_hint="telegram",
            )

    with Session(engine) as session:
        interpretation = execute_vision_stage(
            session,
            ExecuteVisionStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                image_bytes=b"image bytes",
                media_type="image/png",
                ocr_text="Alice: book train tickets for Berlin",
                language_hint="pl,en",
                original_filename="Screenshot_20260409_120000_Telegram.png",
            ),
            engine=_FakeVisionEngine(),
        )
        session.commit()

    assert interpretation.app_hint == "telegram"
    assert interpretation.topic_candidates[0].slug == "trip-to-berlin"

    with Session(engine) as session:
        interpretation_row = session.get(AssetInterpretation, ingest_result.source_item_id)

    assert interpretation_row is not None
    assert interpretation_row.screen_category == "chat"
    assert interpretation_row.app_hint == "telegram"


def test_execute_vision_stage_marks_pipeline_failed_when_engine_raises(tmp_path):
    from memoria.ocr.service import RunOcrStageCommand
    from memoria.ocr.service import run_ocr_stage
    from memoria.vision.service import ExecuteVisionStageCommand
    from memoria.vision.service import VisionStageExecutionError
    from memoria.vision.service import execute_vision_stage

    database_path = tmp_path / "vision-failed.db"
    blob_dir = tmp_path / "blobs"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"

    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")

    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-vision-failed.png",
                media_type="image/png",
                content=b"fake screenshot bytes for vision failure",
                connector_instance_id="manual-upload",
                external_id="capture-vision-failed",
                blob_dir=blob_dir,
            ),
        )
        run_ocr_stage(
            session,
            RunOcrStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                engine_name="manual_override",
                text_content="Alice: book train tickets for Berlin",
            ),
        )
        session.commit()

    class _ExplodingVisionEngine:
        def analyze(
            self,
            *,
            image_bytes: bytes,
            media_type: str,
            language_hint: str,
            app_hint_from_filename: str,
            ocr_text: str,
        ):
            raise RuntimeError("vision exploded")

    with Session(engine) as session:
        with pytest.raises(VisionStageExecutionError, match="vision exploded"):
            execute_vision_stage(
                session,
                ExecuteVisionStageCommand(
                    pipeline_run_id=ingest_result.pipeline_run_id,
                    source_item_id=ingest_result.source_item_id,
                    image_bytes=b"image bytes",
                    media_type="image/png",
                    ocr_text="Alice: book train tickets for Berlin",
                    language_hint="pl,en",
                    original_filename="capture-vision-failed.png",
                ),
                engine=_ExplodingVisionEngine(),
            )
        session.commit()

    with Session(engine) as session:
        pipeline_run = session.get(PipelineRun, ingest_result.pipeline_run_id)
        stage_result = session.scalar(
            select(StageResult).where(
                StageResult.pipeline_run_id == ingest_result.pipeline_run_id,
                StageResult.stage_name == "vision",
                StageResult.status == "failed",
            )
        )

    assert pipeline_run is not None
    assert pipeline_run.status == "failed"
    assert pipeline_run.finished_at is not None
    assert stage_result is not None
    assert stage_result.error_text == "vision exploded"
