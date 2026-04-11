from __future__ import annotations

import json
import mimetypes
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from memoria.domain.models import AssetInterpretation
from memoria.domain.models import PipelineRun
from memoria.domain.models import SourceItem
from memoria.domain.models import SourcePayloadScreenshot
from memoria.domain.models import StageResult
from memoria.knowledge.service import absorb_interpreted_screenshot
from memoria.map.service import rebuild_semantic_map
from memoria.ocr.engines import OcrEngine
from memoria.ocr.service import OcrStageExecutionError
from memoria.pipeline import mark_pipeline_run_completed
from memoria.pipeline import mark_pipeline_run_failed
from memoria.projections.service import refresh_assistant_context_projection
from memoria.projections.service import refresh_topic_status_projection
from memoria.runtime_settings import RuntimeSettings
from memoria.screenshots.pipeline import ProcessScreenshotCommand
from memoria.screenshots.pipeline import ingest_and_process_screenshot
from memoria.vision.engines import VisionEngine
from memoria.vision.mapper import should_absorb_interpretation
from memoria.vision.service import VisionStageExecutionError

DEFAULT_SCREENSHOT_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")


@dataclass(slots=True)
class ImportScreenshotsCommand:
    input_dir: Path
    blob_dir: Path = Path("var/blobs")
    connector_instance_id: str = "filesystem-import"
    mode: str = "absorb"
    recursive: bool = False
    extensions: tuple[str, ...] = DEFAULT_SCREENSHOT_EXTENSIONS


@dataclass(slots=True)
class ImportedScreenshotRecord:
    path: Path
    status: str
    source_item_id: int | None = None
    pipeline_run_id: int | None = None
    error: str | None = None


@dataclass(slots=True)
class ImportScreenshotsResult:
    discovered_count: int = 0
    imported_count: int = 0
    deduped_count: int = 0
    failed_count: int = 0
    failures: list[dict[str, str]] | None = None
    semantic_map_rebuilt: bool = False

    def __post_init__(self) -> None:
        if self.failures is None:
            self.failures = []

    def to_payload(self) -> dict[str, object]:
        return {
            "deduped_count": self.deduped_count,
            "discovered_count": self.discovered_count,
            "failed_count": self.failed_count,
            "failures": self.failures,
            "imported_count": self.imported_count,
            "semantic_map_rebuilt": self.semantic_map_rebuilt,
        }


def discover_screenshot_files(
    *,
    input_dir: Path,
    recursive: bool,
    extensions: tuple[str, ...] = DEFAULT_SCREENSHOT_EXTENSIONS,
) -> list[Path]:
    if not input_dir.exists():
        raise FileNotFoundError(f"input directory does not exist: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"input path is not a directory: {input_dir}")

    normalized_extensions = {
        extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        for extension in extensions
    }
    iterator = input_dir.rglob("*") if recursive else input_dir.glob("*")
    return sorted(
        (
            path
            for path in iterator
            if path.is_file() and path.suffix.lower() in normalized_extensions
        ),
        key=lambda path: path.relative_to(input_dir).as_posix(),
    )


def import_screenshots_from_directory(
    *,
    engine: Engine,
    command: ImportScreenshotsCommand,
    settings: RuntimeSettings,
    ocr_engine: OcrEngine,
    vision_engine: VisionEngine,
    paths: list[Path] | None = None,
    on_item_processed: Callable[[ImportedScreenshotRecord], None] | None = None,
) -> ImportScreenshotsResult:
    discovered_paths = paths
    if discovered_paths is None:
        discovered_paths = discover_screenshot_files(
            input_dir=command.input_dir,
            recursive=command.recursive,
            extensions=command.extensions,
        )
    result = ImportScreenshotsResult(discovered_count=len(discovered_paths))

    for path in discovered_paths:
        relative_path = path.relative_to(command.input_dir)
        with Session(engine) as session:
            try:
                process_result = ingest_and_process_screenshot(
                    session,
                    command=ProcessScreenshotCommand(
                        filename=relative_path.as_posix(),
                        media_type=_guess_media_type(path),
                        content=path.read_bytes(),
                        connector_instance_id=command.connector_instance_id,
                        external_id=relative_path.as_posix(),
                        blob_dir=command.blob_dir,
                        mode=command.mode,
                        rebuild_semantic_map=False,
                    ),
                    settings=settings,
                    ocr_engine=ocr_engine,
                    vision_engine=vision_engine,
                )
            except (OcrStageExecutionError, VisionStageExecutionError) as exc:
                session.commit()
                result.failed_count += 1
                result.failures.append({"error": str(exc), "path": relative_path.as_posix()})
                if on_item_processed is not None:
                    on_item_processed(
                        ImportedScreenshotRecord(
                            path=relative_path,
                            status="failed",
                            error=str(exc),
                        )
                    )
                continue
            except Exception as exc:
                session.rollback()
                result.failed_count += 1
                result.failures.append({"error": str(exc), "path": relative_path.as_posix()})
                if on_item_processed is not None:
                    on_item_processed(
                        ImportedScreenshotRecord(
                            path=relative_path,
                            status="failed",
                            error=str(exc),
                        )
                    )
                continue

            session.commit()
            status = "deduped" if process_result.is_duplicate else "imported"
            if process_result.is_duplicate:
                result.deduped_count += 1
            else:
                result.imported_count += 1
            if on_item_processed is not None:
                on_item_processed(
                    ImportedScreenshotRecord(
                        path=relative_path,
                        status=status,
                        source_item_id=process_result.source_item_id,
                        pipeline_run_id=process_result.pipeline_run_id,
                    )
                )

    if result.imported_count > 0:
        with Session(engine) as session:
            rebuild_semantic_map(session, source_family="screenshot")
            reconcile_pipeline_runs(session)
            session.commit()
        result.semantic_map_rebuilt = True

    return result


def diagnose_vision_failure(session: Session, *, source_item_id: int) -> dict[str, object] | None:
    source_item = session.get(SourceItem, source_item_id)
    payload = session.get(SourcePayloadScreenshot, source_item_id)
    if source_item is None or payload is None:
        return None

    pipeline_run = session.scalar(
        select(PipelineRun)
        .where(PipelineRun.source_item_id == source_item_id)
        .order_by(PipelineRun.id.desc())
    )
    if pipeline_run is None:
        return None

    failed_stage = session.scalar(
        select(StageResult)
        .where(
            StageResult.pipeline_run_id == pipeline_run.id,
            StageResult.stage_name == "vision",
            StageResult.status == "failed",
        )
        .order_by(StageResult.attempt.desc())
    )
    if failed_stage is None:
        return None

    return {
        "source_item_id": source_item_id,
        "filename": payload.original_filename,
        "pipeline_run_id": pipeline_run.id,
        "stage_error": failed_stage.error_text,
        "diagnosis": _diagnose_vision_error_text(failed_stage.error_text or ""),
    }


def reconcile_pipeline_runs(session: Session) -> dict[str, int]:
    completed = 0
    failed = 0

    running_runs = session.scalars(
        select(PipelineRun).where(PipelineRun.status == "running").order_by(PipelineRun.id.asc())
    ).all()
    for pipeline_run in running_runs:
        stages = session.scalars(
            select(StageResult)
            .where(StageResult.pipeline_run_id == pipeline_run.id)
            .order_by(StageResult.id.asc())
        ).all()
        if not stages:
            continue
        if any(stage.status == "failed" for stage in stages):
            mark_pipeline_run_failed(session, pipeline_run)
            failed += 1
            continue
        if all(stage.status == "completed" for stage in stages):
            mark_pipeline_run_completed(session, pipeline_run)
            completed += 1

    return {"completed": completed, "failed": failed}


def count_running_screenshot_pipeline_runs(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(PipelineRun)
            .join(SourceItem, SourceItem.id == PipelineRun.source_item_id)
            .where(PipelineRun.status == "running", SourceItem.source_family == "screenshot")
        )
        or 0
    )


def rebuild_screenshot_derived_data(session: Session, *, force: bool = False) -> dict[str, int]:
    active_runs = count_running_screenshot_pipeline_runs(session)
    if active_runs > 0 and not force:
        raise RuntimeError(f"active screenshot pipeline runs: {active_runs}")

    absorbed = 0
    projections = 0
    interpretation_rows = session.scalars(
        select(AssetInterpretation).order_by(AssetInterpretation.source_item_id.asc())
    ).all()
    for interpretation_row in interpretation_rows:
        source_item = session.get(SourceItem, interpretation_row.source_item_id)
        pipeline_run = session.scalar(
            select(PipelineRun)
            .where(PipelineRun.source_item_id == interpretation_row.source_item_id)
            .order_by(PipelineRun.id.desc())
        )
        if source_item is None or pipeline_run is None:
            continue
        interpretation = _interpretation_dict(interpretation_row)
        if source_item.mode == "absorb" and should_absorb_interpretation(interpretation):
            touched_refs = absorb_interpreted_screenshot(
                session,
                pipeline_run_id=pipeline_run.id,
                source_item_id=source_item.id,
            )
            absorbed += 1
            for object_ref in touched_refs:
                refresh_assistant_context_projection(session, object_ref=object_ref)
                projections += 1
                if object_ref.startswith("topic:"):
                    refresh_topic_status_projection(session, object_ref=object_ref)
                    projections += 1

    rebuild_semantic_map(session, source_family="screenshot")
    reconcile_pipeline_runs(session)
    return {"absorbed": absorbed, "projections_refreshed": projections}


def _diagnose_vision_error_text(error_text: str) -> str:
    lowered = error_text.strip().lower()
    if "category item is not an object" in lowered:
        return (
            "legacy category payload mismatch: the model returned category items in a shape the old "
            "parser could not coerce, so vision failed before structured interpretation or absorb."
        )
    if "no json object found" in lowered or "empty response body" in lowered:
        return "model response was not valid JSON; raw payload capture and soft-failure handling should be inspected."
    return "vision stage failed; inspect raw payload, parser coercion, and model response schema."


def _interpretation_dict(interpretation_row: AssetInterpretation):
    from memoria.api.app import _interpretation_from_row

    return _interpretation_from_row(interpretation_row)


def _guess_media_type(path: Path) -> str:
    guessed_type, _ = mimetypes.guess_type(path.name)
    if guessed_type:
        return guessed_type
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        return "image/jpeg"
    return "image/png"
