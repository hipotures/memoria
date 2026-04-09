from __future__ import annotations

from base64 import b64encode
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import PipelineRun
from memoria.domain.models import SourceItem
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas


def test_api_can_ingest_and_answer_status_question(tmp_path):
    try:
        from memoria.api.app import create_app
    except ImportError as exc:
        pytest.fail(f"api app not implemented yet: {exc}")

    from fastapi.testclient import TestClient

    database_path = tmp_path / "api.db"
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    app = create_app(database_url=f"sqlite:///{database_path}", blob_dir=tmp_path / "blobs")
    client = TestClient(app)

    ingest_response = client.post(
        "/ingest",
        json={
            "filename": "capture-01.png",
            "media_type": "image/png",
            "connector_instance_id": "manual-upload",
            "content_base64": b64encode(b"fake screenshot bytes").decode("ascii"),
            "ocr_text": "Alice: book train tickets for Berlin",
        },
    )

    assert ingest_response.status_code == 201

    assistant_response = client.post(
        "/assistant/query",
        json={"question": "What is going on lately with the Berlin trip?"},
    )

    assert assistant_response.status_code == 200

    payload = assistant_response.json()
    assert payload["answer_source"] == "knowledge"
    assert "Berlin" in payload["answer_text"]
    assert payload["evidence"]

    with Session(_create_engine_for_existing_db(tmp_path, "api.db")) as session:
        pipeline_run = session.scalar(
            select(PipelineRun)
            .where(PipelineRun.source_item_id == ingest_response.json()["source_item_id"])
            .order_by(PipelineRun.id.desc())
        )

    assert pipeline_run is not None
    assert pipeline_run.status == "completed"
    assert pipeline_run.finished_at is not None


def test_api_duplicate_ingest_with_same_bytes_stays_idempotent(tmp_path):
    client, engine = _create_test_client(tmp_path)
    duplicate_bytes = b"same screenshot bytes"

    first_ingest_response = client.post(
        "/ingest",
        json={
            "filename": "capture-berlin.png",
            "media_type": "image/png",
            "connector_instance_id": "manual-upload",
            "content_base64": b64encode(duplicate_bytes).decode("ascii"),
            "ocr_text": "Alice: book train tickets for Berlin",
        },
    )

    assert first_ingest_response.status_code == 201

    second_ingest_response = client.post(
        "/ingest",
        json={
            "filename": "capture-finance.png",
            "media_type": "image/png",
            "connector_instance_id": "manual-upload",
            "content_base64": b64encode(duplicate_bytes).decode("ascii"),
            "ocr_text": "Alice: book train tickets for Finance",
        },
    )

    assert second_ingest_response.status_code == 201
    assert second_ingest_response.json()["source_item_id"] == first_ingest_response.json()["source_item_id"]

    with Session(engine) as session:
        pipeline_runs = session.scalars(
            select(PipelineRun)
            .where(PipelineRun.source_item_id == first_ingest_response.json()["source_item_id"])
            .order_by(PipelineRun.id.asc())
        ).all()

    assert len(pipeline_runs) == 1
    assert pipeline_runs[0].status == "completed"
    assert pipeline_runs[0].finished_at is not None

    berlin_response = client.post(
        "/assistant/query",
        json={"question": "What is going on lately with the Berlin trip?"},
    )

    assert berlin_response.status_code == 200

    berlin_payload = berlin_response.json()
    assert berlin_payload["answer_source"] == "knowledge"
    assert "Berlin" in berlin_payload["answer_text"]
    assert "Finance" not in berlin_payload["answer_text"]

    finance_response = client.post(
        "/assistant/query",
        json={"question": "What is going on lately with Finance?"},
    )

    assert finance_response.status_code == 200

    finance_payload = finance_response.json()
    assert finance_payload["answer_source"] == "no_match"
    assert finance_payload["object_refs"] == []
    assert finance_payload["answer_text"] == "I do not have matching knowledge for that question yet."
    assert finance_payload["evidence"] == []


def test_api_ingest_without_ocr_keeps_pipeline_run_running(tmp_path):
    client, engine = _create_test_client(tmp_path)

    ingest_response = client.post(
        "/ingest",
        json={
            "filename": "capture-ingest-only.png",
            "media_type": "image/png",
            "connector_instance_id": "manual-upload",
            "content_base64": b64encode(b"ingest only bytes").decode("ascii"),
        },
    )

    assert ingest_response.status_code == 201

    with Session(engine) as session:
        pipeline_run = session.scalar(
            select(PipelineRun)
            .where(PipelineRun.source_item_id == ingest_response.json()["source_item_id"])
            .order_by(PipelineRun.id.desc())
        )

    assert pipeline_run is not None
    assert pipeline_run.status == "running"
    assert pipeline_run.finished_at is None


def test_api_does_not_fabricate_travel_knowledge_from_finance_ticket_reminder(tmp_path):
    client, _ = _create_test_client(tmp_path)

    ingest_response = client.post(
        "/ingest",
        json={
            "filename": "capture-finance-reminder.png",
            "media_type": "image/png",
            "connector_instance_id": "manual-upload",
            "content_base64": b64encode(b"finance reminder screenshot").decode("ascii"),
            "ocr_text": "Reminder: submit tickets for Finance",
        },
    )

    assert ingest_response.status_code == 201

    assistant_response = client.post(
        "/assistant/query",
        json={"question": "What is going on lately with Finance?"},
    )

    assert assistant_response.status_code == 200

    payload = assistant_response.json()
    assert payload["answer_source"] in {"canonical", "no_match"}
    assert payload["answer_source"] != "knowledge"
    assert "trip-to-finance" not in payload["object_refs"]
    assert "Trip to Finance" not in payload["answer_text"]

    if payload["answer_source"] == "canonical":
        assert "submit tickets for Finance" in payload["answer_text"]
        assert payload["evidence"]
    else:
        assert payload["answer_text"] == "I do not have matching knowledge for that question yet."
        assert payload["evidence"] == []


def test_api_does_not_fabricate_trip_topic_from_train_booking_for_finance(tmp_path):
    client, _ = _create_test_client(tmp_path)

    ingest_response = client.post(
        "/ingest",
        json={
            "filename": "capture-finance-train.png",
            "media_type": "image/png",
            "connector_instance_id": "manual-upload",
            "content_base64": b64encode(b"finance train screenshot").decode("ascii"),
            "ocr_text": "Alice: book train tickets for Finance",
        },
    )

    assert ingest_response.status_code == 201

    assistant_response = client.post(
        "/assistant/query",
        json={"question": "What is going on lately with Finance?"},
    )

    assert assistant_response.status_code == 200

    payload = assistant_response.json()
    assert payload["answer_source"] in {"canonical", "no_match"}
    assert payload["answer_source"] != "knowledge"
    assert "trip-to-finance" not in payload["object_refs"]
    assert "Trip to Finance" not in payload["answer_text"]

    if payload["answer_source"] == "canonical":
        assert "book train tickets for Finance" in payload["answer_text"]
        assert payload["evidence"]
    else:
        assert payload["answer_text"] == "I do not have matching knowledge for that question yet."
        assert payload["evidence"] == []


@pytest.mark.parametrize(
    ("ocr_text", "question", "unexpected_object_ref", "unexpected_topic_title"),
    [
        (
            "Alice: book train tickets for Support",
            "What is going on lately with Support?",
            "trip-to-support",
            "Trip to Support",
        ),
        (
            "Alice: book train tickets for Monday",
            "What is going on lately with Monday?",
            "trip-to-monday",
            "Trip to Monday",
        ),
        (
            "Alice: book train tickets to Reimbursement",
            "What is going on lately with Reimbursement?",
            "trip-to-reimbursement",
            "Trip to Reimbursement",
        ),
    ],
)
def test_api_does_not_fabricate_trip_topics_from_non_destination_train_booking_tokens(
    tmp_path,
    ocr_text,
    question,
    unexpected_object_ref,
    unexpected_topic_title,
):
    client, _ = _create_test_client(tmp_path)

    ingest_response = client.post(
        "/ingest",
        json={
            "filename": "capture-train-booking.png",
            "media_type": "image/png",
            "connector_instance_id": "manual-upload",
            "content_base64": b64encode(b"non destination train screenshot").decode("ascii"),
            "ocr_text": ocr_text,
        },
    )

    assert ingest_response.status_code == 201

    assistant_response = client.post(
        "/assistant/query",
        json={"question": question},
    )

    assert assistant_response.status_code == 200

    payload = assistant_response.json()
    assert payload["answer_source"] in {"canonical", "no_match"}
    assert payload["answer_source"] != "knowledge"
    assert unexpected_object_ref not in payload["object_refs"]
    assert unexpected_topic_title not in payload["answer_text"]

    if payload["answer_source"] == "canonical":
        assert ocr_text in payload["answer_text"]
        assert payload["evidence"]
    else:
        assert payload["answer_text"] == "I do not have matching knowledge for that question yet."
        assert payload["evidence"] == []


def test_api_rejects_invalid_base64_with_client_error_and_no_ingest(tmp_path):
    client, engine = _create_test_client(tmp_path)

    response = client.post(
        "/ingest",
        json={
            "filename": "capture-invalid.png",
            "media_type": "image/png",
            "connector_instance_id": "manual-upload",
            "content_base64": "%%%",
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "content_base64 must be valid base64"}

    with Session(engine) as session:
        source_item_count = session.scalar(select(func.count()).select_from(SourceItem))
        pipeline_run_count = session.scalar(select(func.count()).select_from(PipelineRun))

    assert source_item_count == 0
    assert pipeline_run_count == 0


def test_api_keeps_generic_ocr_canonical_only_instead_of_fabricating_knowledge(tmp_path):
    client, _ = _create_test_client(tmp_path)

    ingest_response = client.post(
        "/ingest",
        json={
            "filename": "capture-reminder.png",
            "media_type": "image/png",
            "connector_instance_id": "manual-upload",
            "content_base64": b64encode(b"generic reminder screenshot").decode("ascii"),
            "ocr_text": "Reminder: submit receipts to Finance",
        },
    )

    assert ingest_response.status_code == 201

    assistant_response = client.post(
        "/assistant/query",
        json={"question": "What reminder mentions Finance?"},
    )

    assert assistant_response.status_code == 200

    payload = assistant_response.json()
    assert payload["answer_source"] in {"canonical", "no_match"}
    assert payload["answer_source"] != "knowledge"
    assert payload["object_refs"] == []

    if payload["answer_source"] == "canonical":
        assert "submit receipts to Finance" in payload["answer_text"]
        assert payload["evidence"]
    else:
        assert payload["answer_text"] == "I do not have matching knowledge for that question yet."
        assert payload["evidence"] == []


def _create_test_client(tmp_path):
    from fastapi.testclient import TestClient

    try:
        from memoria.api.app import create_app
    except ImportError as exc:
        pytest.fail(f"api app not implemented yet: {exc}")

    database_path = tmp_path / "api.db"
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    app = create_app(database_url=f"sqlite:///{database_path}", blob_dir=tmp_path / "blobs")
    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
    return TestClient(app), engine


def _create_engine_for_existing_db(tmp_path, database_name: str):
    database_path = tmp_path / database_name
    return create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
