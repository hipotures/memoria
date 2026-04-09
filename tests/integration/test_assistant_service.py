from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from memoria.ingest.service import IngestScreenshotCommand
from memoria.ingest.service import ingest_screenshot
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas


def test_assistant_answers_from_projections_and_returns_evidence(tmp_path):
    try:
        from memoria.assistant.service import answer_question
    except ImportError as exc:
        pytest.fail(f"assistant service not implemented yet: {exc}")

    engine = _create_engine(tmp_path, "assistant.db")
    _seed_berlin_knowledge(engine, tmp_path)

    with Session(engine) as session:
        result = answer_question(session, "What is going on lately with the Berlin trip?")

    assert "Berlin" in result.answer_text
    assert "book train" in result.answer_text.lower()
    assert result.answer_source == "knowledge"
    assert "topic:trip-to-berlin" in result.object_refs
    assert len(result.evidence) >= 1


def test_assistant_prefers_answerable_topic_projection_over_shallow_object_projection(tmp_path):
    from memoria.assistant.service import answer_question

    engine = _create_engine(tmp_path, "assistant-ranking.db")
    _seed_berlin_knowledge(engine, tmp_path)

    with Session(engine) as session:
        result = answer_question(session, "What is the status of book train?")

    assert result.answer_source == "knowledge"
    assert "topic:trip-to-berlin" in result.object_refs
    assert len(result.evidence) >= 1
    assert "book train" in result.answer_text.lower()
    assert "open" in result.answer_text.lower()


def test_assistant_falls_back_to_canonical_fragments_when_knowledge_is_missing(tmp_path):
    from memoria.assistant.service import answer_question

    engine = _create_engine(tmp_path, "assistant-canonical.db")
    _seed_vision_only(engine, tmp_path)

    with Session(engine) as session:
        result = answer_question(session, "What is going on with the Berlin trip?")

    assert result.answer_source == "canonical"
    assert "Berlin" in result.answer_text
    assert len(result.evidence) >= 1
    assert any(evidence.fragment_type == "scene_description" for evidence in result.evidence)


@pytest.mark.parametrize(
    "question",
    [
        "",
        "   ",
        "?!...",
        "What is going on?",
        "What's going on?",
        "Who's involved?",
        "What's up?",
    ],
)
def test_assistant_returns_no_match_for_blank_punctuation_or_stopword_only_questions(
    tmp_path,
    question,
):
    from memoria.assistant.service import answer_question

    engine = _create_engine(tmp_path, "assistant-empty-query.db")
    _seed_berlin_knowledge(engine, tmp_path)

    with Session(engine) as session:
        result = answer_question(session, question)

    assert result.answer_text == "I do not have matching knowledge for that question yet."
    assert result.answer_source == "no_match"
    assert "berlin" not in result.answer_text.lower()
    assert result.evidence == []
    assert result.object_refs == []


def _seed_berlin_knowledge(engine, tmp_path) -> None:
    from memoria.knowledge.service import absorb_interpreted_screenshot
    from memoria.projections.service import refresh_assistant_context_projection
    from memoria.projections.service import refresh_topic_status_projection

    ingest_result = _seed_vision_only(engine, tmp_path)

    with Session(engine) as session:
        touched_refs = absorb_interpreted_screenshot(
            session,
            pipeline_run_id=ingest_result.pipeline_run_id,
            source_item_id=ingest_result.source_item_id,
        )
        for object_ref in touched_refs:
            refresh_assistant_context_projection(session, object_ref=object_ref)
            if object_ref.startswith("topic:"):
                refresh_topic_status_projection(session, object_ref=object_ref)
        session.commit()


def _seed_vision_only(engine, tmp_path):
    from memoria.vision.contracts import CandidateRef
    from memoria.vision.contracts import VisionInterpretation
    from memoria.vision.service import RunVisionStageCommand
    from memoria.vision.service import run_vision_stage

    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-assistant.png",
                media_type="image/png",
                content=b"fake screenshot bytes for assistant answering",
                connector_instance_id="manual-upload",
                external_id="capture-assistant",
                blob_dir=tmp_path / "blobs",
            ),
        )
        session.commit()

    with Session(engine) as session:
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                interpretation=VisionInterpretation(
                    screen_category="chat",
                    semantic_summary=(
                        "Telegram chat about a Berlin trip with Alice and booking train tickets."
                    ),
                    app_hint="telegram",
                    topic_candidates=[
                        CandidateRef(
                            slug="trip-to-berlin",
                            title="Trip to Berlin",
                            confidence=0.95,
                        )
                    ],
                    task_candidates=[
                        CandidateRef(
                            slug="book-train",
                            title="Book train",
                            confidence=0.89,
                        )
                    ],
                    person_candidates=[
                        CandidateRef(
                            slug="alice",
                            title="Alice",
                            confidence=0.62,
                        )
                    ],
                    confidence={"screen_category": 0.91, "semantic_summary": 0.85},
                ),
            ),
        )
        session.commit()

    return ingest_result


def _create_engine(tmp_path, database_name: str):
    database_path = tmp_path / database_name
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")
    return create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
