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


def test_semantic_map_point_endpoint_returns_point_detail_and_object_refs(tmp_path):
    client, engine = create_test_client(tmp_path, "semantic-map-point.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    from memoria.map.service import rebuild_semantic_map

    with Session(engine) as session:
        rebuild_semantic_map(session, source_family="screenshot")
        session.commit()

    response = client.get(f"/map/semantic/{seeded.knowledge_backed_source_item_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_item_id"] == seeded.knowledge_backed_source_item_id
    assert payload["cluster_key"]
    assert "topic:trip-to-berlin" in payload["object_refs"]
    assert payload["screenshot_detail_url"] == f"/screenshots/{seeded.knowledge_backed_source_item_id}"


def test_semantic_map_point_endpoint_returns_404_for_points_missing_from_latest_run(tmp_path):
    client, engine = create_test_client(tmp_path, "semantic-map-point-404.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    from memoria.domain.models import SemanticMapRun
    from memoria.map.service import rebuild_semantic_map

    with Session(engine) as session:
        rebuild_semantic_map(session, source_family="screenshot")
        session.add(
            SemanticMapRun(
                map_key="screenshots_semantic_v1",
                source_family="screenshot",
                source_count=0,
                config_json="{}",
            )
        )
        session.commit()

    response = client.get(f"/map/semantic/{seeded.knowledge_backed_source_item_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "semantic map point not found"


def test_semantic_map_page_returns_html_shell(tmp_path):
    client, engine = create_test_client(tmp_path, "semantic-map-page.db")
    seed_screenshot_dataset(engine, tmp_path)

    response = client.get("/map")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "/map/semantic" in response.text


def test_semantic_map_page_includes_point_detail_loader_and_panel_copy(tmp_path):
    client, engine = create_test_client(tmp_path, "semantic-map-point-shell.db")
    seed_screenshot_dataset(engine, tmp_path)

    response = client.get("/map")

    assert response.status_code == 200
    assert "loadPoint(sourceItemId)" in response.text
    assert "Semantic summary" in response.text
    assert "App hint" in response.text
    assert "Screenshot detail" in response.text
    assert "Object refs" in response.text
