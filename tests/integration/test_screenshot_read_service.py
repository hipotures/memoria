from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from tests.integration._screenshot_read_helpers import create_test_engine
from tests.integration._screenshot_read_helpers import blob_path_for_source_item
from tests.integration._screenshot_read_helpers import seed_screenshot_dataset


def test_screenshot_read_service_exposes_contract(tmp_path):
    try:
        from memoria.screenshots.read.service import get_screenshot_detail
        from memoria.screenshots.read.service import list_screenshots
        from memoria.screenshots.read.service import open_screenshot_blob
        from memoria.screenshots.read.service import search_screenshots
    except ImportError as exc:
        pytest.fail(f"screenshot read service not implemented yet: {exc}")

    assert callable(list_screenshots)
    assert callable(get_screenshot_detail)
    assert callable(search_screenshots)
    assert callable(open_screenshot_blob)


def test_open_screenshot_blob_returns_bytes_and_media_type(tmp_path):
    try:
        from memoria.screenshots.read.service import open_screenshot_blob
    except ImportError as exc:
        pytest.fail(f"screenshot read service not implemented yet: {exc}")

    engine = create_test_engine(tmp_path, "screenshot-read-service.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    with Session(engine) as session:
        result = open_screenshot_blob(
            session,
            source_item_id=seeded.knowledge_backed_source_item_id,
        )

    assert result is not None
    assert result.media_type == "image/png"
    assert result.content == seeded.knowledge_backed_bytes


def test_open_screenshot_blob_returns_none_when_backing_file_is_missing(tmp_path):
    from memoria.screenshots.read.service import open_screenshot_blob

    engine = create_test_engine(tmp_path, "screenshot-read-service-missing-blob.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)
    blob_path_for_source_item(
        engine,
        source_item_id=seeded.knowledge_backed_source_item_id,
    ).unlink()

    with Session(engine) as session:
        result = open_screenshot_blob(
            session,
            source_item_id=seeded.knowledge_backed_source_item_id,
        )

    assert result is None


def test_get_screenshot_detail_returns_partial_state_for_canonical_only_input(tmp_path):
    from memoria.screenshots.read.service import get_screenshot_detail

    engine = create_test_engine(tmp_path, "screenshot-read-detail-canonical.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    with Session(engine) as session:
        result = get_screenshot_detail(
            session,
            source_item_id=seeded.canonical_only_source_item_id,
        )

    assert result is not None
    assert result.source_item_id == seeded.canonical_only_source_item_id
    assert result.filename == "capture-canonical-only.png"
    assert result.media_type == "image/png"
    assert result.blob.download_url == f"/screenshots/{seeded.canonical_only_source_item_id}/blob"
    assert result.ocr is None
    assert result.interpretation is None
    assert result.knowledge.object_refs == []
    assert result.knowledge.claims == []
    assert result.pipeline is not None
    assert result.pipeline.status == "running"
    assert [stage.stage_name for stage in result.pipeline.stage_results] == ["ingest"]


def test_get_screenshot_detail_returns_knowledge_backed_metadata(tmp_path):
    from memoria.screenshots.read.service import get_screenshot_detail

    engine = create_test_engine(tmp_path, "screenshot-read-detail-knowledge.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    with Session(engine) as session:
        result = get_screenshot_detail(
            session,
            source_item_id=seeded.knowledge_backed_source_item_id,
        )

    assert result is not None
    assert result.source_item_id == seeded.knowledge_backed_source_item_id
    assert result.ocr is not None
    assert "Alice: book train tickets for Berlin" in result.ocr.text_content
    assert result.interpretation is not None
    assert result.interpretation.app_hint == "telegram"
    assert result.interpretation.screen_category == "chat"
    assert "topic:trip-to-berlin" in result.knowledge.object_refs
    assert {claim.claim_type for claim in result.knowledge.claims} == {
        "membership",
        "person_hint",
        "task_status",
    }
    assert result.pipeline is not None
    assert result.pipeline.status == "completed"
    assert [stage.stage_name for stage in result.pipeline.stage_results] == [
        "ingest",
        "ocr",
        "vision",
        "absorb",
    ]
    assert {fragment.fragment_type for fragment in result.content_fragments} == {
        "ocr_text",
        "scene_description",
        "app_hint",
        "entity_mention",
        "searchable_label",
        "cluster_hint",
    }


def test_list_screenshots_returns_recent_rows_with_filters_and_object_refs(tmp_path):
    from memoria.screenshots.read.service import list_screenshots

    engine = create_test_engine(tmp_path, "screenshot-read-list.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    with Session(engine) as session:
        result = list_screenshots(session, limit=10, offset=0)
        manual_only = list_screenshots(
            session,
            connector_instance_id="manual-upload",
            limit=10,
            offset=0,
        )
        knowledge_only = list_screenshots(
            session,
            has_knowledge=True,
            limit=10,
            offset=0,
        )
        berlin_filtered = list_screenshots(session, q="Berlin", limit=10, offset=0)
        paged = list_screenshots(session, limit=2, offset=1)

    assert [item.source_item_id for item in result.items] == [
        seeded.knowledge_backed_source_item_id,
        seeded.interpretation_only_source_item_id,
        seeded.ocr_only_source_item_id,
        seeded.canonical_only_source_item_id,
    ]
    assert [item.source_item_id for item in manual_only.items] == [
        seeded.knowledge_backed_source_item_id,
        seeded.canonical_only_source_item_id,
    ]
    assert [item.source_item_id for item in knowledge_only.items] == [
        seeded.knowledge_backed_source_item_id,
    ]
    assert [item.source_item_id for item in berlin_filtered.items] == [
        seeded.knowledge_backed_source_item_id,
        seeded.interpretation_only_source_item_id,
    ]
    assert [item.source_item_id for item in paged.items] == [
        seeded.interpretation_only_source_item_id,
        seeded.ocr_only_source_item_id,
    ]
    assert result.items[0].pipeline_status == "completed"
    assert result.items[-1].pipeline_status == "running"
    assert result.items[0].blob_available is True
    assert result.items[0].object_refs == [
        "person:alice",
        "task:book-train",
        "thread:telegram-trip-to-berlin",
        "topic:trip-to-berlin",
    ]
    assert "Finance" in result.items[2].ocr_excerpt


def test_search_screenshots_returns_semantic_label_hits_and_deduplicates_per_source_item(tmp_path, monkeypatch):
    from memoria.screenshots.read import service as screenshot_read_service

    engine = create_test_engine(tmp_path, "screenshot-read-search.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    with Session(engine) as session:
        berlin_result = screenshot_read_service.search_screenshots(
            session,
            query="Berlin",
            limit=10,
            offset=0,
        )

    assert [item.source_item_id for item in berlin_result.items] == [
        seeded.interpretation_only_source_item_id,
        seeded.knowledge_backed_source_item_id,
    ]
    assert all(item.match_source == "searchable_label" for item in berlin_result.items)
    assert all(item.match_text == "berlin" for item in berlin_result.items)

    monkeypatch.setattr(
        screenshot_read_service,
        "_search_screenshot_candidates_via_fts",
        lambda session, *, query, limit, offset: [],
    )

    with Session(engine) as session:
        fallback_result = screenshot_read_service.search_screenshots(
            session,
            query="Finance",
            limit=10,
            offset=0,
        )

    assert [item.source_item_id for item in fallback_result.items] == [
        seeded.ocr_only_source_item_id,
    ]
    assert fallback_result.items[0].match_source == "ocr_text"
    assert "Finance" in fallback_result.items[0].match_text
