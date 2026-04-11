from __future__ import annotations

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

