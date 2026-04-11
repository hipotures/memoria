from __future__ import annotations

from tests.integration._screenshot_read_helpers import create_test_client
from tests.integration._screenshot_read_helpers import seed_screenshot_dataset


def test_get_topic_view_returns_task_4_read_model_payload(tmp_path):
    client, engine = create_test_client(tmp_path, "knowledge-api-topic.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    response = client.get("/knowledge/topics/trip-to-berlin")

    assert response.status_code == 200
    payload = response.json()
    assert payload["topic"]["object_ref"] == "topic:trip-to-berlin"
    assert payload["topic"]["object_type"] == "topic"
    assert "thread:telegram-trip-to-berlin" in payload["thread_refs"]
    assert payload["recent_screenshots"][0]["source_item_id"] == seeded.knowledge_backed_source_item_id
    assert payload["evidence"]


def test_get_thread_view_returns_task_4_read_model_payload(tmp_path):
    client, engine = create_test_client(tmp_path, "knowledge-api-thread.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    response = client.get("/knowledge/threads/telegram-trip-to-berlin")

    assert response.status_code == 200
    payload = response.json()
    assert payload["thread"]["object_ref"] == "thread:telegram-trip-to-berlin"
    assert payload["thread"]["object_type"] == "thread"
    assert payload["topic_ref"] == "topic:trip-to-berlin"
    assert any(person["object_ref"] == "person:alice" for person in payload["people"])
    assert payload["recent_screenshots"][0]["source_item_id"] == seeded.knowledge_backed_source_item_id
    assert payload["evidence"]


def test_get_topic_view_returns_404_for_missing_slug(tmp_path):
    client, _engine = create_test_client(tmp_path, "knowledge-api-topic-missing.db")

    response = client.get("/knowledge/topics/missing-topic")

    assert response.status_code == 404


def test_get_thread_view_returns_404_for_missing_slug(tmp_path):
    client, _engine = create_test_client(tmp_path, "knowledge-api-thread-missing.db")

    response = client.get("/knowledge/threads/missing-thread")

    assert response.status_code == 404
