from __future__ import annotations

from tests.integration._screenshot_read_helpers import create_test_client
from tests.integration._screenshot_read_helpers import blob_path_for_source_item
from tests.integration._screenshot_read_helpers import read_only_row_counts
from tests.integration._screenshot_read_helpers import seed_screenshot_dataset


def test_get_screenshot_blob_returns_image_bytes_without_side_effects(tmp_path):
    client, engine = create_test_client(tmp_path, "screenshot-read-api.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)
    before_counts = read_only_row_counts(engine)

    response = client.get(f"/screenshots/{seeded.knowledge_backed_source_item_id}/blob")

    after_counts = read_only_row_counts(engine)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == seeded.knowledge_backed_bytes
    assert after_counts == before_counts


def test_get_screenshot_blob_returns_404_for_missing_backing_file(tmp_path):
    client, engine = create_test_client(tmp_path, "screenshot-read-api-missing-blob.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)
    blob_path_for_source_item(
        engine,
        source_item_id=seeded.knowledge_backed_source_item_id,
    ).unlink()

    response = client.get(f"/screenshots/{seeded.knowledge_backed_source_item_id}/blob")

    assert response.status_code == 404


def test_get_screenshot_detail_returns_partial_and_knowledge_backed_views_without_side_effects(tmp_path):
    client, engine = create_test_client(tmp_path, "screenshot-read-api-detail.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)
    before_counts = read_only_row_counts(engine)

    canonical_response = client.get(f"/screenshots/{seeded.canonical_only_source_item_id}")
    knowledge_response = client.get(f"/screenshots/{seeded.knowledge_backed_source_item_id}")

    after_counts = read_only_row_counts(engine)

    assert canonical_response.status_code == 200
    canonical_payload = canonical_response.json()
    assert canonical_payload["source_item_id"] == seeded.canonical_only_source_item_id
    assert canonical_payload["ocr"] is None
    assert canonical_payload["interpretation"] is None
    assert canonical_payload["knowledge"]["object_refs"] == []

    assert knowledge_response.status_code == 200
    knowledge_payload = knowledge_response.json()
    assert knowledge_payload["source_item_id"] == seeded.knowledge_backed_source_item_id
    assert knowledge_payload["interpretation"]["app_hint"] == "telegram"
    assert "topic:trip-to-berlin" in knowledge_payload["knowledge"]["object_refs"]
    assert knowledge_payload["blob"]["download_url"] == (
        f"/screenshots/{seeded.knowledge_backed_source_item_id}/blob"
    )
    assert after_counts == before_counts


def test_get_screenshots_returns_filtered_list_payload(tmp_path):
    client, engine = create_test_client(tmp_path, "screenshot-read-api-list.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)
    before_counts = read_only_row_counts(engine)

    response = client.get(
        "/screenshots",
        params={"connector_instance_id": "manual-upload", "has_knowledge": "true"},
    )

    after_counts = read_only_row_counts(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 20
    assert payload["offset"] == 0
    assert [item["source_item_id"] for item in payload["items"]] == [
        seeded.knowledge_backed_source_item_id,
    ]
    assert after_counts == before_counts


def test_get_screenshots_search_returns_screenshot_centric_hits_without_side_effects(tmp_path):
    client, engine = create_test_client(tmp_path, "screenshot-read-api-search.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)
    before_counts = read_only_row_counts(engine)

    response = client.get("/screenshots/search", params={"q": "Berlin"})

    after_counts = read_only_row_counts(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "Berlin"
    assert [item["source_item_id"] for item in payload["items"]] == [
        seeded.interpretation_only_source_item_id,
        seeded.knowledge_backed_source_item_id,
    ]
    assert all(item["match_source"] == "ocr_text" for item in payload["items"])
    assert after_counts == before_counts
