from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from tests.integration._screenshot_read_helpers import create_test_engine
from tests.integration._screenshot_read_helpers import seed_screenshot_dataset


def test_get_topic_view_returns_threads_tasks_people_and_recent_screenshots(tmp_path):
    engine = create_test_engine(tmp_path, "knowledge-read-topic.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    try:
        from memoria.knowledge.read.service import get_topic_view
    except ImportError as exc:
        pytest.fail(f"knowledge read service not implemented yet: {exc}")

    with Session(engine) as session:
        result = get_topic_view(session, slug="trip-to-berlin")

    assert result is not None
    assert result.topic.object_ref == "topic:trip-to-berlin"
    assert result.topic.object_type == "topic"
    assert "thread:telegram-trip-to-berlin" in result.thread_refs
    assert any(task.status_value == "open" for task in result.task_statuses)
    assert any(person.object_ref == "person:alice" for person in result.people)
    assert result.recent_screenshots[0].source_item_id == seeded.knowledge_backed_source_item_id
    assert result.evidence


def test_get_thread_view_returns_parent_topic_people_and_recent_screenshots(tmp_path):
    engine = create_test_engine(tmp_path, "knowledge-read-thread.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    try:
        from memoria.knowledge.read.service import get_thread_view
    except ImportError as exc:
        pytest.fail(f"knowledge read service not implemented yet: {exc}")

    with Session(engine) as session:
        result = get_thread_view(session, slug="telegram-trip-to-berlin")

    assert result is not None
    assert result.thread.object_ref == "thread:telegram-trip-to-berlin"
    assert result.thread.object_type == "thread"
    assert result.topic_ref == "topic:trip-to-berlin"
    assert any(person.object_ref == "person:alice" for person in result.people)
    assert result.recent_screenshots[0].source_item_id == seeded.knowledge_backed_source_item_id
    assert result.evidence
