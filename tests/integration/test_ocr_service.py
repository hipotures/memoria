from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetOcrText
from memoria.domain.models import ContentFragment
from memoria.domain.models import PipelineRun
from memoria.domain.models import StageResult
from memoria.ingest.service import IngestScreenshotCommand
from memoria.ingest.service import ingest_screenshot
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas


def test_run_ocr_stage_persists_text_fragment_and_stage_result(tmp_path):
    try:
        from memoria.ocr.service import RunOcrStageCommand
        from memoria.ocr.service import run_ocr_stage
    except ImportError as exc:
        pytest.fail(f"ocr service not implemented yet: {exc}")

    database_path = tmp_path / "ocr.db"
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
                filename="capture-ocr.png",
                media_type="image/png",
                content=b"fake screenshot bytes for ocr",
                connector_instance_id="manual-upload",
                external_id="capture-ocr",
                blob_dir=blob_dir,
            ),
        )
        session.commit()

    with Session(engine) as session:
        run_ocr_stage(
            session,
            RunOcrStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                engine_name="tesseract",
                text_content="Visible OCR text",
            ),
        )
        session.commit()

    with Session(engine) as session:
        ocr_text = session.get(AssetOcrText, ingest_result.source_item_id)
        content_fragment = session.scalar(
            select(ContentFragment).where(
                ContentFragment.source_item_id == ingest_result.source_item_id,
                ContentFragment.fragment_type == "ocr_text",
                ContentFragment.fragment_ref == "full",
            )
        )
        stage_result = session.scalar(
            select(StageResult).where(
                StageResult.pipeline_run_id == ingest_result.pipeline_run_id,
                StageResult.stage_name == "ocr",
                StageResult.status == "completed",
            )
        )

    assert ocr_text is not None
    assert ocr_text.engine_name == "tesseract"
    assert ocr_text.text_content == "Visible OCR text"

    assert content_fragment is not None
    assert content_fragment.source_item_id == ingest_result.source_item_id
    assert content_fragment.fragment_type == "ocr_text"
    assert content_fragment.fragment_ref == "full"
    assert content_fragment.fragment_text == "Visible OCR text"

    assert stage_result is not None
    assert stage_result.pipeline_run_id == ingest_result.pipeline_run_id
    assert stage_result.stage_name == "ocr"
    assert stage_result.status == "completed"


def test_run_ocr_stage_is_replay_safe_and_tracks_attempts(tmp_path):
    from memoria.ocr.service import RunOcrStageCommand
    from memoria.ocr.service import run_ocr_stage

    database_path = tmp_path / "ocr-replay.db"
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
                filename="capture-ocr-replay.png",
                media_type="image/png",
                content=b"fake screenshot bytes for ocr replay",
                connector_instance_id="manual-upload",
                external_id="capture-ocr-replay",
                blob_dir=blob_dir,
            ),
        )
        session.commit()

    with Session(engine) as session:
        run_ocr_stage(
            session,
            RunOcrStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                engine_name="tesseract",
                text_content="First OCR text",
            ),
        )
        session.commit()

    with Session(engine) as session:
        run_ocr_stage(
            session,
            RunOcrStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                engine_name="tesseract",
                text_content="Updated OCR text",
            ),
        )
        session.commit()

    with Session(engine) as session:
        ocr_text = session.get(AssetOcrText, ingest_result.source_item_id)
        content_fragment = session.scalar(
            select(ContentFragment).where(
                ContentFragment.source_item_id == ingest_result.source_item_id,
                ContentFragment.fragment_type == "ocr_text",
                ContentFragment.fragment_ref == "full",
            )
        )
        stage_results = session.scalars(
            select(StageResult)
            .where(
                StageResult.pipeline_run_id == ingest_result.pipeline_run_id,
                StageResult.stage_name == "ocr",
            )
            .order_by(StageResult.attempt.asc())
        ).all()

    assert ocr_text is not None
    assert ocr_text.text_content == "Updated OCR text"

    assert content_fragment is not None
    assert content_fragment.fragment_text == "Updated OCR text"

    assert len(stage_results) == 2
    assert [stage_result.attempt for stage_result in stage_results] == [1, 2]
    assert all(stage_result.status == "completed" for stage_result in stage_results)


def test_run_ocr_stage_rejects_mismatched_pipeline_run_and_source_item(tmp_path):
    from memoria.ocr.service import RunOcrStageCommand
    from memoria.ocr.service import run_ocr_stage

    database_path = tmp_path / "ocr-mismatch.db"
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
                filename="capture-ocr-mismatch-1.png",
                media_type="image/png",
                content=b"fake screenshot bytes one",
                connector_instance_id="manual-upload",
                external_id="capture-ocr-mismatch-1",
                blob_dir=blob_dir,
            ),
        )
        second_ingest = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-ocr-mismatch-2.png",
                media_type="image/png",
                content=b"fake screenshot bytes two",
                connector_instance_id="manual-upload",
                external_id="capture-ocr-mismatch-2",
                blob_dir=blob_dir,
            ),
        )
        session.commit()

    with Session(engine) as session:
        with pytest.raises(ValueError):
            run_ocr_stage(
                session,
                RunOcrStageCommand(
                    pipeline_run_id=first_ingest.pipeline_run_id,
                    source_item_id=second_ingest.source_item_id,
                    engine_name="tesseract",
                    text_content="Mismatched OCR text",
                ),
            )
        session.rollback()

    with Session(engine) as session:
        ocr_rows = session.scalar(select(func.count()).select_from(AssetOcrText))
        fragment_rows = session.scalar(
            select(func.count()).select_from(ContentFragment).where(
                ContentFragment.fragment_type == "ocr_text"
            )
        )
        stage_results = session.scalar(
            select(func.count()).select_from(StageResult).where(StageResult.stage_name == "ocr")
        )

    assert ocr_rows == 0
    assert fragment_rows == 0
    assert stage_results == 0


def test_execute_ocr_stage_runs_engine_and_persists_result(tmp_path):
    from memoria.ocr.engines import OcrEngineResult
    from memoria.ocr.service import ExecuteOcrStageCommand
    from memoria.ocr.service import execute_ocr_stage

    database_path = tmp_path / "ocr-exec.db"
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
                filename="capture-ocr-exec.png",
                media_type="image/png",
                content=b"fake screenshot bytes for ocr execution",
                connector_instance_id="manual-upload",
                external_id="capture-ocr-exec",
                blob_dir=blob_dir,
            ),
        )
        session.commit()

    class _FakeOcrEngine:
        def extract_text(self, *, image_bytes: bytes, media_type: str, language_hint: str | None = None):
            return OcrEngineResult(
                engine_name="fake-paddleocr",
                text_content="Visible OCR text from engine",
                language_hint=language_hint,
                block_map_json="[]",
            )

    with Session(engine) as session:
        result = execute_ocr_stage(
            session,
            ExecuteOcrStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                image_bytes=b"image bytes",
                media_type="image/png",
            ),
            engine=_FakeOcrEngine(),
        )
        session.commit()

    assert result.engine_name == "fake-paddleocr"

    with Session(engine) as session:
        ocr_text = session.get(AssetOcrText, ingest_result.source_item_id)

    assert ocr_text is not None
    assert ocr_text.engine_name == "fake-paddleocr"
    assert ocr_text.text_content == "Visible OCR text from engine"


def test_execute_ocr_stage_marks_pipeline_failed_when_engine_raises(tmp_path):
    from memoria.ocr.service import ExecuteOcrStageCommand
    from memoria.ocr.service import OcrStageExecutionError
    from memoria.ocr.service import execute_ocr_stage

    database_path = tmp_path / "ocr-failed.db"
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
                filename="capture-ocr-failed.png",
                media_type="image/png",
                content=b"fake screenshot bytes for ocr failure",
                connector_instance_id="manual-upload",
                external_id="capture-ocr-failed",
                blob_dir=blob_dir,
            ),
        )
        session.commit()

    class _ExplodingOcrEngine:
        def extract_text(self, *, image_bytes: bytes, media_type: str, language_hint: str | None = None):
            raise RuntimeError("ocr exploded")

    with Session(engine) as session:
        with pytest.raises(OcrStageExecutionError, match="ocr exploded"):
            execute_ocr_stage(
                session,
                ExecuteOcrStageCommand(
                    pipeline_run_id=ingest_result.pipeline_run_id,
                    source_item_id=ingest_result.source_item_id,
                    image_bytes=b"image bytes",
                    media_type="image/png",
                ),
                engine=_ExplodingOcrEngine(),
            )
        session.commit()

    with Session(engine) as session:
        pipeline_run = session.get(PipelineRun, ingest_result.pipeline_run_id)
        stage_result = session.scalar(
            select(StageResult).where(
                StageResult.pipeline_run_id == ingest_result.pipeline_run_id,
                StageResult.stage_name == "ocr",
                StageResult.status == "failed",
            )
        )

    assert pipeline_run is not None
    assert pipeline_run.status == "failed"
    assert pipeline_run.finished_at is not None
    assert stage_result is not None
    assert stage_result.error_text == "ocr exploded"
