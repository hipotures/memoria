from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy.orm import Session

from memoria.domain.models import Blob
from memoria.domain.models import PipelineRun
from memoria.domain.models import SourceItem
from memoria.domain.models import SourcePayloadScreenshot
from memoria.domain.models import StageResult
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas


def test_ingest_screenshot_persists_canonical_records_and_ingest_stage_result(tmp_path):
    try:
        from memoria.ingest.service import IngestScreenshotCommand
        from memoria.ingest.service import ingest_screenshot
    except ImportError as exc:
        pytest.fail(f"ingest service not implemented yet: {exc}")

    database_path = tmp_path / "ingest.db"
    blob_dir = tmp_path / "blobs"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"

    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
    created_at = datetime(2026, 4, 9, 10, 30, 0)
    observed_at = datetime(2026, 4, 9, 10, 31, 0)
    payload = b"fake screenshot bytes"

    with Session(engine) as session:
        result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-01.png",
                media_type="image/png",
                content=payload,
                connector_instance_id="manual-upload",
                external_id="capture-01",
                source_created_at=created_at,
                source_observed_at=observed_at,
                blob_dir=blob_dir,
            ),
        )
        session.commit()

    with Session(engine) as session:
        blob = session.scalar(select(Blob))
        source_item = session.scalar(select(SourceItem))
        payload_row = session.scalar(select(SourcePayloadScreenshot))
        pipeline_run = session.scalar(select(PipelineRun))
        stage_result = session.scalar(select(StageResult))

    assert blob is not None
    assert source_item is not None
    assert payload_row is not None
    assert pipeline_run is not None
    assert stage_result is not None

    assert Path(blob.storage_uri).exists()
    assert Path(blob.storage_uri).read_bytes() == payload

    assert result.blob_id == blob.id
    assert result.source_item_id == source_item.id
    assert result.pipeline_run_id == pipeline_run.id

    assert source_item.source_type == "screenshot"
    assert source_item.source_family == "screenshot"
    assert source_item.connector_instance_id == "manual-upload"
    assert source_item.external_id == "capture-01"
    assert source_item.mode == "absorb"
    assert source_item.status == "ingested"
    assert source_item.source_created_at == created_at
    assert source_item.source_observed_at == observed_at
    assert source_item.blob_id == blob.id

    assert payload_row.source_item_id == source_item.id
    assert payload_row.original_filename == "capture-01.png"
    assert payload_row.media_type == "image/png"
    assert payload_row.file_extension == ".png"

    assert pipeline_run.source_item_id == source_item.id
    assert pipeline_run.pipeline_name == "screenshots_v1"
    assert pipeline_run.status == "running"
    assert pipeline_run.run_reason == "ingest"
    assert pipeline_run.finished_at is None

    assert stage_result.pipeline_run_id == pipeline_run.id
    assert stage_result.stage_name == "ingest"
    assert stage_result.status == "completed"
    assert stage_result.finished_at is not None


def test_ingest_screenshot_is_idempotent_for_duplicate_content_without_orphan_blob_files(tmp_path):
    try:
        from memoria.ingest.service import IngestScreenshotCommand
        from memoria.ingest.service import ingest_screenshot
    except ImportError as exc:
        pytest.fail(f"ingest service not implemented yet: {exc}")

    database_path = tmp_path / "ingest.db"
    blob_dir = tmp_path / "blobs"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"

    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
    payload = b"same screenshot bytes"

    with Session(engine) as session:
        first = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-01.png",
                media_type="image/png",
                content=payload,
                connector_instance_id="manual-upload",
                external_id="capture-01",
                blob_dir=blob_dir,
            ),
        )
        session.commit()

    with Session(engine) as session:
        second = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-01.jpg",
                media_type="image/jpeg",
                content=payload,
                connector_instance_id="manual-upload",
                external_id="capture-01-duplicate",
                blob_dir=blob_dir,
            ),
        )
        session.commit()

    with Session(engine) as session:
        blob_count = session.scalar(select(func.count()).select_from(Blob))
        source_item_count = session.scalar(select(func.count()).select_from(SourceItem))
        payload_count = session.scalar(select(func.count()).select_from(SourcePayloadScreenshot))
        pipeline_run_count = session.scalar(select(func.count()).select_from(PipelineRun))
        stage_result_count = session.scalar(select(func.count()).select_from(StageResult))

    written_files = sorted(path for path in blob_dir.rglob("*") if path.is_file())

    assert second == first
    assert blob_count == 1
    assert source_item_count == 1
    assert payload_count == 1
    assert pipeline_run_count == 1
    assert stage_result_count == 1
    assert len(written_files) == 1
    assert written_files[0].read_bytes() == payload
