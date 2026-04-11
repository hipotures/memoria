from __future__ import annotations

from tests.integration._screenshot_read_helpers import KNOWLEDGE_BACKED_SOURCE_TIME
from tests.integration._screenshot_read_helpers import create_test_client
from tests.integration._screenshot_read_helpers import seed_screenshot_dataset


def test_hybrid_search_shared_filters_remain_scoped_to_screenshot_search(tmp_path):
    client, engine = create_test_client(tmp_path, "api-ingest-search.db")
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
