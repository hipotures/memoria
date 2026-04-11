from __future__ import annotations

import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import PipelineRun
from memoria.domain.models import SemanticMapPoint
from memoria.domain.models import SourceItem
from memoria.runtime_settings import RuntimeSettings
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas
from memoria.vision.engines import VisionEngineResult


def test_import_screenshots_from_directory_imports_recursive_tree_and_counts_duplicates(tmp_path):
    try:
        from memoria.admin.service import ImportScreenshotsCommand
        from memoria.admin.service import import_screenshots_from_directory
    except ImportError as exc:
        pytest.fail(f"admin screenshot import service not implemented yet: {exc}")

    engine = _create_test_engine(tmp_path, "import.db")
    input_dir = tmp_path / "screens"
    nested_dir = input_dir / "nested"
    nested_dir.mkdir(parents=True)

    (input_dir / "Screenshot_20260331_121849_ChatGPT.jpg").write_bytes(b"screen-one")
    (nested_dir / "Screenshot_20260401_091500_Instagram.jpg").write_bytes(b"screen-two")
    (nested_dir / "Screenshot_20260401_091500_Instagram-copy.jpg").write_bytes(b"screen-two")
    (input_dir / "notes.txt").write_text("ignore me", encoding="utf-8")

    result = import_screenshots_from_directory(
        engine=engine,
        command=ImportScreenshotsCommand(
            input_dir=input_dir,
            blob_dir=tmp_path / "blobs",
            recursive=True,
        ),
        settings=RuntimeSettings(database_url=f"sqlite:///{tmp_path / 'import.db'}"),
        ocr_engine=_FakeOcrEngine(),
        vision_engine=_FakeVisionEngine(),
    )

    assert result.discovered_count == 3
    assert result.imported_count == 2
    assert result.deduped_count == 1
    assert result.failed_count == 0
    assert result.failures == []

    with Session(engine) as session:
        source_item_count = session.scalar(select(func.count()).select_from(SourceItem))
        pipeline_run_count = session.scalar(select(func.count()).select_from(PipelineRun))
        completed_pipeline_count = session.scalar(
            select(func.count()).select_from(PipelineRun).where(PipelineRun.status == "completed")
        )
        semantic_map_point_count = session.scalar(select(func.count()).select_from(SemanticMapPoint))

    assert source_item_count == 2
    assert pipeline_run_count == 2
    assert completed_pipeline_count == 2
    assert semantic_map_point_count == 2


def test_admin_cli_import_screenshots_command_prints_json_summary(tmp_path, monkeypatch, capsys):
    try:
        from memoria.admin import cli
    except ImportError as exc:
        pytest.fail(f"admin CLI not implemented yet: {exc}")

    _create_test_engine(tmp_path, "cli.db")
    input_dir = tmp_path / "screens"
    input_dir.mkdir()
    (input_dir / "Screenshot_20260331_121849_ChatGPT.jpg").write_bytes(b"screen-one")

    monkeypatch.setattr(cli, "create_ocr_engine", lambda settings: _FakeOcrEngine())
    monkeypatch.setattr(cli, "create_vision_engine", lambda settings: _FakeVisionEngine())

    exit_code = cli.main(
        [
            "--database-url",
            f"sqlite:///{tmp_path / 'cli.db'}",
            "import-screenshots",
            "--input-dir",
            str(input_dir),
            "--blob-dir",
            str(tmp_path / "blobs"),
        ]
    )

    assert exit_code == 0

    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert payload["discovered_count"] == 1
    assert payload["imported_count"] == 1
    assert payload["deduped_count"] == 0
    assert payload["failed_count"] == 0


def _create_test_engine(tmp_path, database_name: str):
    database_path = tmp_path / database_name
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")
    return create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")


class _FakeOcrEngine:
    def extract_text(self, *, image_bytes: bytes, media_type: str, language_hint: str | None = None):
        from memoria.ocr.engines import OcrEngineResult

        return OcrEngineResult(
            engine_name="fake-paddleocr",
            text_content="Alice: book train tickets for Berlin",
            language_hint=language_hint,
            block_map_json="[]",
        )


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
            screen_category="chat",
            semantic_summary=ocr_text,
            app_hint=app_hint_from_filename.lower() or "chatgpt",
            topic_candidates=[{"slug": "trip-to-berlin", "title": "Trip to Berlin", "confidence": 0.95}],
            task_candidates=[{"slug": "book-train", "title": "Book train", "confidence": 0.89}],
            person_candidates=[{"slug": "alice", "title": "Alice", "confidence": 0.62}],
            searchable_labels=["berlin", "train", "chat"],
            cluster_hints=["travel", "chat"],
            confidence={
                "screen_category": 0.9,
                "topic_candidates": 0.95,
                "task_candidates": 0.89,
                "person_candidates": 0.62,
            },
            raw_model_payload={"semantic_summary": ocr_text},
        )
