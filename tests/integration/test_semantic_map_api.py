from __future__ import annotations

from sqlalchemy.orm import Session

from tests.integration._screenshot_read_helpers import create_test_client
from tests.integration._screenshot_read_helpers import seed_screenshot_dataset


def test_semantic_map_endpoints_return_clusters_and_cluster_items(tmp_path):
    client, engine = create_test_client(tmp_path, "semantic-map-api.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    from memoria.map.service import rebuild_semantic_map

    with Session(engine) as session:
        rebuild_semantic_map(session, source_family="screenshot")
        session.commit()

    response = client.get("/map/semantic")

    assert response.status_code == 200
    payload = response.json()
    assert payload["clusters"]
    cluster_key = payload["clusters"][0]["cluster_key"]

    detail_response = client.get(f"/map/semantic/clusters/{cluster_key}")
    items_response = client.get(f"/map/semantic/clusters/{cluster_key}/items")

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["cluster_key"] == cluster_key
    assert detail_payload["item_count"] >= 1

    assert items_response.status_code == 200
    items_payload = items_response.json()
    assert items_payload["cluster_key"] == cluster_key
    assert items_payload["items"]
    assert any(
        item["source_item_id"] == seeded.knowledge_backed_source_item_id
        for item in items_payload["items"]
    )


def test_semantic_map_page_returns_html_shell(tmp_path):
    client, engine = create_test_client(tmp_path, "semantic-map-page.db")
    seed_screenshot_dataset(engine, tmp_path)

    response = client.get("/map")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "/map/semantic" in response.text
