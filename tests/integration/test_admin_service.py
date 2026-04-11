from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session
import pytest

from memoria.domain.models import PipelineRun
from memoria.ingest.service import IngestScreenshotCommand
from memoria.ingest.service import ingest_screenshot
from memoria.ocr.service import RunOcrStageCommand
from memoria.ocr.service import run_ocr_stage
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas
from memoria.vision.contracts import VisionInterpretation
from memoria.vision.service import RunVisionStageCommand
from memoria.vision.service import VisionStageExecutionError
from memoria.vision.service import execute_vision_stage
from memoria.vision.service import run_vision_stage
from memoria.vision.service import ExecuteVisionStageCommand


def test_rebuild_screenshot_derived_data_refuses_active_screenshot_runs(tmp_path):
    from memoria.admin.service import rebuild_screenshot_derived_data

    engine = _create_engine(tmp_path, "admin-rebuild-guard.db")
    blob_dir = tmp_path / "blobs"

    with Session(engine) as session:
        ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="Screenshot_20240411_101500_ChatGPT.png",
                media_type="image/png",
                content=b"active screenshot run",
                connector_instance_id="manual-upload",
                external_id="active-screenshot-run",
                blob_dir=blob_dir,
            ),
        )
        session.commit()

    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="active screenshot pipeline runs: 1"):
            rebuild_screenshot_derived_data(session)


def test_rebuild_screenshot_derived_data_force_bypasses_active_screenshot_runs(tmp_path):
    from memoria.admin.service import rebuild_screenshot_derived_data

    engine = _create_engine(tmp_path, "admin-rebuild-force.db")
    blob_dir = tmp_path / "blobs"

    with Session(engine) as session:
        ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="Screenshot_20240411_101500_ChatGPT.png",
                media_type="image/png",
                content=b"active screenshot run",
                connector_instance_id="manual-upload",
                external_id="active-screenshot-run",
                blob_dir=blob_dir,
            ),
        )
        session.commit()

    with Session(engine) as session:
        result = rebuild_screenshot_derived_data(session, force=True)

    assert result == {"absorbed": 0, "projections_refreshed": 0}


def test_admin_cli_rebuild_screenshot_derived_data_command_accepts_force_flag(
    tmp_path, monkeypatch, capsys
):
    from memoria.admin import cli

    _create_engine(tmp_path, "admin-rebuild-cli.db")

    received = {}

    def _fake_rebuild(session, *, force=False):
        received["force"] = force
        return {"absorbed": 0, "projections_refreshed": 0}

    monkeypatch.setattr(cli, "rebuild_screenshot_derived_data", _fake_rebuild)

    exit_code = cli.main(
        [
            "--database-url",
            f"sqlite:///{tmp_path / 'admin-rebuild-cli.db'}",
            "rebuild-screenshot-derived-data",
            "--force",
        ]
    )

    assert exit_code == 0
    assert received["force"] is True
    stdout = capsys.readouterr().out
    assert '"absorbed": 0' in stdout


def test_diagnose_vision_failure_reports_known_parser_mismatch(tmp_path):
    from memoria.admin.service import diagnose_vision_failure

    engine = _create_engine(tmp_path, "admin-diagnose.db")
    blob_dir = tmp_path / "blobs"

    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="Screenshot_20230204_201912_TikTok.jpg",
                media_type="image/jpeg",
                content=b"failed vision screenshot",
                connector_instance_id="manual-upload",
                external_id="tiktok-live",
                blob_dir=blob_dir,
            ),
        )
        run_ocr_stage(
            session,
            RunOcrStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                engine_name="manual-override",
                text_content="LIVE TikTok Q&A screenshot",
            ),
        )
        with Session(engine) as inner_session:
            pass
        session.commit()

    class _FailingVisionEngine:
        def analyze(self, **_kwargs):
            raise ValueError("category item is not an object")

    with Session(engine) as session:
        try:
            execute_vision_stage(
                session,
                ExecuteVisionStageCommand(
                    pipeline_run_id=ingest_result.pipeline_run_id,
                    source_item_id=ingest_result.source_item_id,
                    image_bytes=b"img",
                    media_type="image/jpeg",
                    ocr_text="LIVE TikTok Q&A screenshot",
                    language_hint="pl,en",
                    original_filename="Screenshot_20230204_201912_TikTok.jpg",
                ),
                engine=_FailingVisionEngine(),
            )
        except VisionStageExecutionError:
            session.commit()

    with Session(engine) as session:
        diagnosis = diagnose_vision_failure(session, source_item_id=ingest_result.source_item_id)

    assert diagnosis is not None
    assert diagnosis["filename"] == "Screenshot_20230204_201912_TikTok.jpg"
    assert diagnosis["stage_error"] == "category item is not an object"
    assert "legacy category payload mismatch" in diagnosis["diagnosis"]


def test_reconcile_pipeline_runs_marks_completed_after_manual_stage_execution(tmp_path):
    from memoria.admin.service import reconcile_pipeline_runs

    engine = _create_engine(tmp_path, "admin-reconcile.db")
    blob_dir = tmp_path / "blobs"

    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-admin-reconcile.png",
                media_type="image/png",
                content=b"reconcile screenshot bytes",
                connector_instance_id="manual-upload",
                external_id="capture-admin-reconcile",
                blob_dir=blob_dir,
            ),
        )
        run_ocr_stage(
            session,
            RunOcrStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                engine_name="manual-override",
                text_content="Telegram thread about Berlin tickets",
            ),
        )
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                interpretation=VisionInterpretation(
                    screen_category="chat",
                    semantic_summary="Telegram thread about Berlin tickets",
                    app_hint="telegram",
                    searchable_labels=["telegram", "berlin"],
                    cluster_hints=["travel", "chat"],
                ),
            ),
        )
        session.commit()

    with Session(engine) as session:
        reconciled = reconcile_pipeline_runs(session)
        session.commit()

    with Session(engine) as session:
        pipeline_run = session.scalar(select(PipelineRun))

    assert reconciled["completed"] == 1
    assert pipeline_run is not None
    assert pipeline_run.status == "completed"
    assert pipeline_run.finished_at is not None


def _create_engine(tmp_path, database_name: str):
    database_path = tmp_path / database_name
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")
    return create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
