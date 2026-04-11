from __future__ import annotations

import json
import re
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import Blob
from memoria.domain.models import PipelineRun
from memoria.domain.models import SourceItem
from memoria.domain.models import SourcePayloadScreenshot
from memoria.pipeline import record_stage_result
from memoria.pipeline import start_pipeline_run


@dataclass(slots=True)
class IngestScreenshotCommand:
    filename: str
    media_type: str
    content: bytes
    connector_instance_id: str
    external_id: str | None = None
    source_created_at: datetime | None = None
    source_observed_at: datetime | None = None
    blob_dir: Path = Path("var/blobs")
    mode: str = "absorb"


@dataclass(slots=True)
class IngestScreenshotResult:
    blob_id: int
    source_item_id: int
    pipeline_run_id: int
    dedup_key: str
    storage_uri: str
    is_duplicate: bool = field(compare=False)


def ingest_screenshot(session: Session, command: IngestScreenshotCommand) -> IngestScreenshotResult:
    resolved_created_at, resolved_observed_at = _resolve_source_times(command)
    digest = sha256(command.content).hexdigest()
    dedup_key = f"screenshot:{digest}"
    existing_source_item = session.scalar(
        select(SourceItem).where(SourceItem.dedup_key == dedup_key)
    )

    if existing_source_item is not None:
        existing_pipeline_run = session.scalar(
            select(PipelineRun)
            .where(PipelineRun.source_item_id == existing_source_item.id)
            .order_by(PipelineRun.id.desc())
        )
        blob = session.get(Blob, existing_source_item.blob_id)
        assert blob is not None
        assert existing_pipeline_run is not None
        return IngestScreenshotResult(
            blob_id=blob.id,
            source_item_id=existing_source_item.id,
            pipeline_run_id=existing_pipeline_run.id,
            dedup_key=existing_source_item.dedup_key,
            storage_uri=blob.storage_uri,
            is_duplicate=True,
        )

    blob = session.scalar(select(Blob).where(Blob.sha256 == digest))
    if blob is None:
        storage_uri = _persist_blob(command.blob_dir, digest, command.filename, command.content)
        blob = Blob(
            sha256=digest,
            media_type=command.media_type,
            byte_size=len(command.content),
            storage_kind="local",
            storage_uri=str(storage_uri),
        )
        session.add(blob)
        session.flush()
    else:
        storage_uri = Path(blob.storage_uri)

    source_item = SourceItem(
        source_type="screenshot",
        source_family="screenshot",
        connector_instance_id=command.connector_instance_id,
        external_id=command.external_id,
        dedup_key=dedup_key,
        mode=command.mode,
        status="ingested",
        source_created_at=resolved_created_at,
        source_observed_at=resolved_observed_at,
        raw_ref=command.filename,
        blob_id=blob.id,
    )
    session.add(source_item)
    session.flush()

    session.add(
        SourcePayloadScreenshot(
            source_item_id=source_item.id,
            original_filename=command.filename,
            media_type=command.media_type,
            file_extension=Path(command.filename).suffix or ".bin",
            metadata_json=json.dumps(
                {
                    "connector_instance_id": command.connector_instance_id,
                    "external_id": command.external_id,
                },
                sort_keys=True,
            ),
        )
    )

    pipeline_run = start_pipeline_run(
        session,
        source_item_id=source_item.id,
        pipeline_name="screenshots_v1",
    )
    record_stage_result(
        session,
        pipeline_run_id=pipeline_run.id,
        stage_name="ingest",
        status="completed",
        output_payload={
            "blob_id": blob.id,
            "source_item_id": source_item.id,
            "filename": command.filename,
        },
    )

    return IngestScreenshotResult(
        blob_id=blob.id,
        source_item_id=source_item.id,
        pipeline_run_id=pipeline_run.id,
        dedup_key=source_item.dedup_key,
        storage_uri=str(storage_uri),
        is_duplicate=False,
    )


def _persist_blob(blob_dir: Path, digest: str, filename: str, content: bytes) -> Path:
    suffix = Path(filename).suffix or ".bin"
    blob_path = blob_dir / digest[:2] / f"{digest}{suffix}"
    blob_path.parent.mkdir(parents=True, exist_ok=True)

    if not blob_path.exists():
        blob_path.write_bytes(content)

    return blob_path.resolve()


_SCREENSHOT_FILENAME_TIMESTAMP_RE = re.compile(
    r"^Screenshot_(?P<date>\d{8})_(?P<time>\d{6})(?:_.+)?$"
)


def _resolve_source_times(command: IngestScreenshotCommand) -> tuple[datetime, datetime]:
    parsed_timestamp = _parse_screenshot_timestamp_from_filename(command.filename)
    created_at = command.source_created_at or parsed_timestamp or _utc_now()
    observed_at = command.source_observed_at or command.source_created_at or parsed_timestamp or created_at
    return created_at, observed_at


def _parse_screenshot_timestamp_from_filename(filename: str) -> datetime | None:
    match = _SCREENSHOT_FILENAME_TIMESTAMP_RE.match(Path(filename).stem)
    if match is None:
        return None

    return datetime.strptime(
        f"{match.group('date')}{match.group('time')}",
        "%Y%m%d%H%M%S",
    )


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
