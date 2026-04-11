from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn
from rich.progress import MofNCompleteColumn
from rich.progress import Progress
from rich.progress import SpinnerColumn
from rich.progress import TaskProgressColumn
from rich.progress import TextColumn
from rich.progress import TimeElapsedColumn
from sqlalchemy.orm import Session

from memoria.admin.service import DEFAULT_SCREENSHOT_EXTENSIONS
from memoria.admin.service import ImportScreenshotsCommand
from memoria.admin.service import diagnose_vision_failure
from memoria.admin.service import discover_screenshot_files
from memoria.admin.service import import_screenshots_from_directory
from memoria.admin.service import rebuild_screenshot_derived_data
from memoria.admin.service import reconcile_pipeline_runs
from memoria.runtime_engines import create_ocr_engine
from memoria.runtime_engines import create_vision_engine
from memoria.runtime_settings import load_runtime_settings_from_env
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="memoria-admin")
    parser.add_argument("--database-url", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    diagnose_parser = subparsers.add_parser("diagnose-vision-failure")
    diagnose_parser.add_argument("--source-item-id", required=True, type=int)

    subparsers.add_parser("reconcile-pipeline-runs")
    subparsers.add_parser("rebuild-screenshot-derived-data")

    import_parser = subparsers.add_parser("import-screenshots")
    import_parser.add_argument("--input-dir", required=True, type=Path)
    import_parser.add_argument("--blob-dir", type=Path, default=Path("var/blobs"))
    import_parser.add_argument("--connector-instance-id", default="filesystem-import")
    import_parser.add_argument("--mode", choices=["absorb", "index_only"], default="absorb")
    import_parser.add_argument("--recursive", action="store_true")
    import_parser.add_argument("--extensions", nargs="*", default=None)

    args = parser.parse_args(argv)
    engine = create_engine_with_sqlite_pragmas(args.database_url)

    if args.command == "import-screenshots":
        settings = load_runtime_settings_from_env()
        ocr_engine = create_ocr_engine(settings)
        vision_engine = create_vision_engine(settings)
        extensions = tuple(args.extensions) if args.extensions else DEFAULT_SCREENSHOT_EXTENSIONS
        command = ImportScreenshotsCommand(
            input_dir=args.input_dir,
            blob_dir=args.blob_dir,
            connector_instance_id=args.connector_instance_id,
            mode=args.mode,
            recursive=args.recursive,
            extensions=extensions,
        )
        discovered_paths = discover_screenshot_files(
            input_dir=command.input_dir,
            recursive=command.recursive,
            extensions=command.extensions,
        )
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=Console(stderr=True),
            expand=False,
        )
        with progress:
            task_id = progress.add_task("starting import".ljust(25), total=len(discovered_paths))
            result = import_screenshots_from_directory(
                engine=engine,
                command=command,
                settings=settings,
                ocr_engine=ocr_engine,
                vision_engine=vision_engine,
                paths=discovered_paths,
                on_item_processed=lambda record: progress.update(
                    task_id,
                    advance=1,
                    description=_progress_description(record.path),
                ),
            )
        payload = result.to_payload()
    else:
        with Session(engine) as session:
            if args.command == "diagnose-vision-failure":
                payload = diagnose_vision_failure(session, source_item_id=args.source_item_id)
            elif args.command == "reconcile-pipeline-runs":
                payload = reconcile_pipeline_runs(session)
                session.commit()
            else:
                payload = rebuild_screenshot_derived_data(session)
                session.commit()

    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


def _progress_description(path: Path) -> str:
    return f"importing {path.as_posix()}"[:25].ljust(25)


if __name__ == "__main__":
    raise SystemExit(main())
