from __future__ import annotations

from tests.integration._screenshot_read_helpers import KNOWLEDGE_BACKED_SOURCE_TIME
from tests.integration._screenshot_read_helpers import create_test_client
from tests.integration._screenshot_read_helpers import seed_screenshot_dataset


def test_hybrid_search_returns_combined_matches_for_screenshot_dataset(tmp_path):
    client, engine = create_test_client(tmp_path, "hybrid-search-api.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    response = client.get("/search/hybrid", params={"q": "Berlin train telegram", "limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "Berlin train telegram"
    assert payload["items"]
    assert payload["items"][0]["source_item_id"] in {
        seeded.knowledge_backed_source_item_id,
        seeded.interpretation_only_source_item_id,
    }
    assert any("semantic" in item["match_sources"] for item in payload["items"])
    assert any("lexical" in item["match_sources"] for item in payload["items"])


def test_hybrid_search_applies_shared_filters(tmp_path):
    client, engine = create_test_client(tmp_path, "hybrid-search-api.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    response = client.get(
        "/search/hybrid",
        params={
            "q": "Berlin train telegram",
            "limit": 10,
            "connector_instance_id": "manual-upload",
            "app_hint": "telegram",
            "screen_category": "chat",
            "has_knowledge": "true",
            "observed_from": KNOWLEDGE_BACKED_SOURCE_TIME.isoformat(),
            "observed_to": KNOWLEDGE_BACKED_SOURCE_TIME.isoformat(),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["source_item_id"] for item in payload["items"]] == [
        seeded.knowledge_backed_source_item_id
    ]
