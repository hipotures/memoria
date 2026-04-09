from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from memoria.domain.models import Blob
from memoria.domain.models import SourceItem
from memoria.domain.models import SourcePayloadScreenshot


def load_blob_bytes_for_source_item(session: Session, *, source_item_id: int) -> tuple[bytes, str]:
    source_item = session.get(SourceItem, source_item_id)
    if source_item is None:
        raise ValueError("source_item_id does not exist")

    blob = session.get(Blob, source_item.blob_id)
    if blob is None:
        raise ValueError("blob missing for source_item")
    if blob.storage_kind != "local":
        raise RuntimeError(f"unsupported blob storage kind: {blob.storage_kind}")

    path = Path(blob.storage_uri)
    return path.read_bytes(), blob.media_type


def load_original_filename_for_source_item(session: Session, *, source_item_id: int) -> str:
    payload = session.get(SourcePayloadScreenshot, source_item_id)
    if payload is None:
        raise ValueError("screenshot payload missing for source_item")
    return payload.original_filename
