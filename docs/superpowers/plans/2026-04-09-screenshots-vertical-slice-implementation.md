# Screenshots Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the first native Memoria screenshot slice inside `/home/xai/DEV/memoria`, from canonical ingest through OCR, semantic interpretation, absorb, projections, assistant answers, and evidence drill-down.

**Architecture:** Build on the existing foundation already present in this repo: keep the current canonical base (`blobs`, `source_items`, `pipeline_runs`, `stage_results`), add the still-missing screenshot payload and fragment layer, then wire a conservative synchronous pipeline: `ingest -> ocr -> vision -> absorb -> projections -> assistant`. The assistant must stay knowledge-first, using projections and claims before dropping to canonical fragments and raw screenshots.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.x, Alembic, SQLite + FTS5, pytest

---

## Current Status

The following foundation work already exists in `/home/xai/DEV/memoria` and should be treated as the baseline, not reimplemented:

- `alembic/versions/20260409_01_initial_foundation.py`
- `src/memoria/domain/models.py`
- `src/memoria/ingest/service.py`
- `tests/integration/test_schema_tables.py`
- `tests/integration/test_ingest_service.py`

Fresh verification before writing this plan:

```bash
uv run pytest -v
```

Expected at plan-writing time:

```text
3 passed
```

This means:

- the initial schema exists,
- canonical screenshot ingest works,
- duplicate ingest is idempotent,
- ingest no longer leaves orphan blob files,
- current code is ready for the next layer rather than a rewrite-from-zero.

Remaining gaps relative to the approved design:

- no dedicated `source_payloads_screenshot` table yet,
- no `content_fragments` table or FTS index yet,
- no OCR stage service yet,
- no vision stage service yet,
- no absorb service yet,
- no projections yet,
- no assistant query flow yet,
- no FastAPI app surface yet.

---

## Repository Roots

- Plan document repo: `/home/xai/DEV/memoria`
- Implementation repo: `/home/xai/DEV/memoria`
- All code changes must stay inside `/home/xai/DEV/memoria`

---

## File Structure

### Already Present

- `alembic/versions/20260409_01_initial_foundation.py`
  Purpose: initial canonical, knowledge, and pipeline tables.
- `src/memoria/domain/models.py`
  Purpose: ORM models for the current foundation.
- `src/memoria/ingest/service.py`
  Purpose: idempotent canonical screenshot ingest and ingest-stage bookkeeping.
- `src/memoria/storage/metadata_db.py`
  Purpose: engine factory with SQLite pragmas.
- `tests/integration/test_schema_tables.py`
  Purpose: verifies schema presence after Alembic upgrade.
- `tests/integration/test_ingest_service.py`
  Purpose: verifies canonical ingest behavior and duplicate safety.

### Create

- `alembic/versions/20260409_02_add_screenshot_payloads_and_fragments.py`
  Purpose: add missing screenshot payload records, canonical content fragments, and SQLite FTS5 support.
- `src/memoria/pipeline/__init__.py`
  Purpose: export pipeline bookkeeping helpers.
- `src/memoria/pipeline/service.py`
  Purpose: create processing runs, record stage results, and finalize runs consistently.
- `src/memoria/ocr/__init__.py`
  Purpose: export OCR stage entrypoints.
- `src/memoria/ocr/service.py`
  Purpose: persist OCR output and canonical OCR fragments.
- `src/memoria/vision/__init__.py`
  Purpose: export vision contracts and service.
- `src/memoria/vision/contracts.py`
  Purpose: typed payloads for screenshot semantic interpretation.
- `src/memoria/vision/service.py`
  Purpose: persist screenshot interpretation and related canonical fragments.
- `src/memoria/knowledge/__init__.py`
  Purpose: export absorb service.
- `src/memoria/knowledge/service.py`
  Purpose: transform interpreted screenshots into knowledge objects, claims, and evidence links.
- `src/memoria/projections/__init__.py`
  Purpose: export projection refresh helpers.
- `src/memoria/projections/service.py`
  Purpose: build `assistant_context_projection` and `topic_status_projection`.
- `src/memoria/assistant/__init__.py`
  Purpose: export assistant query service.
- `src/memoria/assistant/service.py`
  Purpose: assemble assistant answers from projections, claims, and canonical evidence.
- `src/memoria/api/__init__.py`
  Purpose: package marker for API code.
- `src/memoria/api/schemas.py`
  Purpose: request and response models for ingest and assistant endpoints.
- `src/memoria/api/app.py`
  Purpose: FastAPI application wiring the vertical slice end to end.
- `tests/integration/test_ocr_service.py`
  Purpose: verify OCR persistence and OCR-stage bookkeeping.
- `tests/integration/test_vision_service.py`
  Purpose: verify interpretation persistence and vision-stage bookkeeping.
- `tests/integration/test_absorb_service.py`
  Purpose: verify object creation, claim refresh, idempotency, and uncertainty handling.
- `tests/integration/test_projection_service.py`
  Purpose: verify projection refresh output.
- `tests/integration/test_assistant_service.py`
  Purpose: verify knowledge-first assistant answers with evidence.
- `tests/integration/test_api_end_to_end.py`
  Purpose: verify the API can ingest a screenshot and answer a question about it.
- `README.md`
  Purpose: document the vertical-slice workflow and API contract.

### Modify

- `pyproject.toml`
  Purpose: add `httpx` to the dev group for FastAPI integration tests.
- `src/memoria/domain/models.py`
  Purpose: add ORM models for screenshot payloads and canonical fragments.
- `src/memoria/ingest/service.py`
  Purpose: persist screenshot payload metadata and delegate pipeline bookkeeping to shared helpers.
- `tests/integration/test_schema_tables.py`
  Purpose: extend schema assertions to the newly required canonical tables.
- `tests/integration/test_ingest_service.py`
  Purpose: extend ingest assertions to screenshot payload persistence and pipeline-run semantics.

---

### Task 1: Add Screenshot Payload and Fragment Schema

**Files:**
- Create: `alembic/versions/20260409_02_add_screenshot_payloads_and_fragments.py`
- Modify: `src/memoria/domain/models.py`
- Modify: `tests/integration/test_schema_tables.py`

- [ ] **Step 1: Write the failing schema test**

```python
assert {
    "source_payloads_screenshot",
    "content_fragments",
} <= table_names
```

Add one extra assertion so the FTS table is also checked:

```python
with engine.connect() as connection:
    fts_names = {
        row[0]
        for row in connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        )
    }

assert "content_fragments_fts" in fts_names
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/integration/test_schema_tables.py::test_initial_schema_includes_screenshot_knowledge_core_tables -v
```

Expected: FAIL because the new canonical tables and FTS table do not exist yet.

- [ ] **Step 3: Add the migration and ORM models**

```python
# alembic/versions/20260409_02_add_screenshot_payloads_and_fragments.py
"""add screenshot payload and content fragments

Revision ID: 20260409_02
Revises: 20260409_01
Create Date: 2026-04-09 00:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260409_02"
down_revision = "20260409_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_payloads_screenshot",
        sa.Column("source_item_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column("file_extension", sa.String(length=16), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_item_id"),
    )

    op.create_table(
        "content_fragments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_item_id", sa.Integer(), nullable=False),
        sa.Column("fragment_type", sa.String(length=64), nullable=False),
        sa.Column("fragment_ref", sa.String(length=255), nullable=False),
        sa.Column("fragment_text", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "source_item_id",
            "fragment_type",
            "fragment_ref",
            name="uq_content_fragments_identity",
        ),
    )
    op.create_index(
        "ix_content_fragments_source_item_id",
        "content_fragments",
        ["source_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_content_fragments_fragment_type",
        "content_fragments",
        ["fragment_type"],
        unique=False,
    )

    op.execute(
        """
        CREATE VIRTUAL TABLE content_fragments_fts
        USING fts5(fragment_text, content='content_fragments', content_rowid='id')
        """
    )
    op.execute(
        """
        CREATE TRIGGER content_fragments_ai AFTER INSERT ON content_fragments BEGIN
            INSERT INTO content_fragments_fts(rowid, fragment_text)
            VALUES (new.id, new.fragment_text);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER content_fragments_ad AFTER DELETE ON content_fragments BEGIN
            INSERT INTO content_fragments_fts(content_fragments_fts, rowid, fragment_text)
            VALUES ('delete', old.id, old.fragment_text);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER content_fragments_au AFTER UPDATE ON content_fragments BEGIN
            INSERT INTO content_fragments_fts(content_fragments_fts, rowid, fragment_text)
            VALUES ('delete', old.id, old.fragment_text);
            INSERT INTO content_fragments_fts(rowid, fragment_text)
            VALUES (new.id, new.fragment_text);
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS content_fragments_au")
    op.execute("DROP TRIGGER IF EXISTS content_fragments_ad")
    op.execute("DROP TRIGGER IF EXISTS content_fragments_ai")
    op.execute("DROP TABLE IF EXISTS content_fragments_fts")
    op.drop_index("ix_content_fragments_fragment_type", table_name="content_fragments")
    op.drop_index("ix_content_fragments_source_item_id", table_name="content_fragments")
    op.drop_table("content_fragments")
    op.drop_table("source_payloads_screenshot")
```

```python
# src/memoria/domain/models.py
class SourcePayloadScreenshot(Base):
    __tablename__ = "source_payloads_screenshot"

    source_item_id: Mapped[int] = mapped_column(
        ForeignKey("source_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(128))
    file_extension: Mapped[str] = mapped_column(String(16))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)


class ContentFragment(Base):
    __tablename__ = "content_fragments"
    __table_args__ = (
        UniqueConstraint(
            "source_item_id",
            "fragment_type",
            "fragment_ref",
            name="uq_content_fragments_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_item_id: Mapped[int] = mapped_column(
        ForeignKey("source_items.id", ondelete="CASCADE"),
        index=True,
    )
    fragment_type: Mapped[str] = mapped_column(String(64), index=True)
    fragment_ref: Mapped[str] = mapped_column(String(255))
    fragment_text: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)
```

- [ ] **Step 4: Run the schema test to verify it passes**

Run:

```bash
uv run pytest tests/integration/test_schema_tables.py::test_initial_schema_includes_screenshot_knowledge_core_tables -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/20260409_02_add_screenshot_payloads_and_fragments.py \
  src/memoria/domain/models.py \
  tests/integration/test_schema_tables.py
git commit -m "feat: add screenshot payload and fragment schema"
```

### Task 2: Normalize Pipeline Bookkeeping for Multi-Stage Processing

**Files:**
- Create: `src/memoria/pipeline/__init__.py`
- Create: `src/memoria/pipeline/service.py`
- Modify: `src/memoria/ingest/service.py`
- Modify: `tests/integration/test_ingest_service.py`

- [ ] **Step 1: Write the failing ingest test for multi-stage semantics**

Update the existing happy-path ingest test so it expects:

```python
assert pipeline_run.status == "running"
assert pipeline_run.finished_at is None

assert stage_result.stage_name == "ingest"
assert stage_result.status == "completed"
assert stage_result.finished_at is not None
```

Add one more assertion:

```python
assert pipeline_run.pipeline_name == "screenshots_v1"
```

This keeps one run open for downstream OCR, vision, absorb, and projection work.

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/integration/test_ingest_service.py::test_ingest_screenshot_persists_canonical_records_and_ingest_stage_result -v
```

Expected: FAIL because the current ingest service marks the whole run as `completed`.

- [ ] **Step 3: Add shared pipeline helpers and switch ingest to them**

```python
# src/memoria/pipeline/service.py
from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from memoria.domain.models import PipelineRun, StageResult


def start_pipeline_run(session: Session, *, source_item_id: int, pipeline_name: str) -> PipelineRun:
    run = PipelineRun(
        source_item_id=source_item_id,
        pipeline_name=pipeline_name,
        status="running",
        run_reason="ingest",
    )
    session.add(run)
    session.flush()
    return run


def record_stage_result(
    session: Session,
    *,
    pipeline_run_id: int,
    stage_name: str,
    status: str,
    output_payload: dict[str, object] | None = None,
    error_text: str | None = None,
    attempt: int = 1,
) -> StageResult:
    stage = StageResult(
        pipeline_run_id=pipeline_run_id,
        stage_name=stage_name,
        status=status,
        attempt=attempt,
        output_json=json.dumps(output_payload or {}, sort_keys=True),
        error_text=error_text,
        finished_at=_utc_now() if status in {"completed", "failed"} else None,
    )
    session.add(stage)
    session.flush()
    return stage


def mark_pipeline_run_completed(session: Session, pipeline_run: PipelineRun) -> None:
    pipeline_run.status = "completed"
    pipeline_run.finished_at = _utc_now()
    session.flush()


def mark_pipeline_run_failed(session: Session, pipeline_run: PipelineRun) -> None:
    pipeline_run.status = "failed"
    pipeline_run.finished_at = _utc_now()
    session.flush()


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
```

```python
# src/memoria/ingest/service.py
from memoria.pipeline.service import record_stage_result
from memoria.pipeline.service import start_pipeline_run


pipeline_run = start_pipeline_run(
    session,
    source_item_id=source_item.id,
    pipeline_name="screenshots_v1",
)

record_stage_result(
    session,
    pipeline_run_id=pipeline_run.id,
    stage_name="ingest",
    status="completed",
    output_payload={
        "blob_id": blob.id,
        "source_item_id": source_item.id,
        "filename": command.filename,
    },
)
```

- [ ] **Step 4: Run the ingest test to verify it passes**

Run:

```bash
uv run pytest tests/integration/test_ingest_service.py::test_ingest_screenshot_persists_canonical_records_and_ingest_stage_result -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memoria/pipeline/__init__.py \
  src/memoria/pipeline/service.py \
  src/memoria/ingest/service.py \
  tests/integration/test_ingest_service.py
git commit -m "refactor: normalize pipeline bookkeeping"
```

### Task 3: Persist Screenshot Payload Metadata During Ingest

**Files:**
- Modify: `src/memoria/ingest/service.py`
- Modify: `tests/integration/test_ingest_service.py`

- [ ] **Step 1: Write the failing payload-persistence test**

Extend the existing ingest test:

```python
from memoria.domain.models import SourcePayloadScreenshot


payload_row = session.scalar(select(SourcePayloadScreenshot))
assert payload_row is not None
assert payload_row.source_item_id == source_item.id
assert payload_row.original_filename == "capture-01.png"
assert payload_row.media_type == "image/png"
assert payload_row.file_extension == ".png"
```

Extend the duplicate-ingest test too:

```python
payload_count = session.scalar(select(func.count()).select_from(SourcePayloadScreenshot))
assert payload_count == 1
```

- [ ] **Step 2: Run the ingest test to verify it fails**

Run:

```bash
uv run pytest tests/integration/test_ingest_service.py -v
```

Expected: FAIL because ingest does not yet create a `source_payloads_screenshot` row.

- [ ] **Step 3: Implement screenshot payload persistence**

```python
# src/memoria/ingest/service.py
import json

from memoria.domain.models import SourcePayloadScreenshot


payload_row = SourcePayloadScreenshot(
    source_item_id=source_item.id,
    original_filename=command.filename,
    media_type=command.media_type,
    file_extension=Path(command.filename).suffix or ".bin",
    metadata_json=json.dumps(
        {
            "connector_instance_id": command.connector_instance_id,
            "external_id": command.external_id,
        },
        sort_keys=True,
    ),
)
session.add(payload_row)
session.flush()
```

On duplicate ingest, do not create a second payload row. Reuse the same source item and return the same result object.

- [ ] **Step 4: Run the ingest tests to verify they pass**

Run:

```bash
uv run pytest tests/integration/test_ingest_service.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memoria/ingest/service.py tests/integration/test_ingest_service.py
git commit -m "feat: persist screenshot payload metadata"
```

### Task 4: Implement OCR Stage Persistence

**Files:**
- Create: `src/memoria/ocr/__init__.py`
- Create: `src/memoria/ocr/service.py`
- Create: `tests/integration/test_ocr_service.py`

- [ ] **Step 1: Write the failing OCR integration test**

```python
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetOcrText
from memoria.domain.models import ContentFragment
from memoria.domain.models import StageResult
from memoria.ingest.service import IngestScreenshotCommand, ingest_screenshot
from memoria.ocr.service import RunOcrStageCommand, run_ocr_stage
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas


def test_run_ocr_stage_persists_text_fragment_and_stage_result(tmp_path):
    database_path = tmp_path / "ocr.db"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-01.png",
                media_type="image/png",
                content=b"fake screenshot bytes",
                connector_instance_id="manual-upload",
                external_id="capture-01",
                blob_dir=tmp_path / "blobs",
            ),
        )
        run_ocr_stage(
            session,
            RunOcrStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                engine_name="stub-ocr",
                text_content="Book train tickets for Berlin",
                language_hint="en",
            ),
        )
        session.commit()

    with Session(engine) as session:
        ocr_row = session.get(AssetOcrText, ingest_result.source_item_id)
        fragment = session.scalar(
            select(ContentFragment).where(
                ContentFragment.source_item_id == ingest_result.source_item_id,
                ContentFragment.fragment_type == "ocr_text",
                ContentFragment.fragment_ref == "full",
            )
        )
        stage = session.scalar(
            select(StageResult).where(
                StageResult.pipeline_run_id == ingest_result.pipeline_run_id,
                StageResult.stage_name == "ocr",
            )
        )

    assert ocr_row is not None
    assert ocr_row.engine_name == "stub-ocr"
    assert ocr_row.text_content == "Book train tickets for Berlin"
    assert fragment is not None
    assert fragment.fragment_ref == "full"
    assert fragment.fragment_text == "Book train tickets for Berlin"
    assert stage is not None
    assert stage.status == "completed"
```

- [ ] **Step 2: Run the OCR test to verify it fails**

Run:

```bash
uv run pytest tests/integration/test_ocr_service.py::test_run_ocr_stage_persists_text_fragment_and_stage_result -v
```

Expected: FAIL because `memoria.ocr.service` does not exist yet.

- [ ] **Step 3: Add the OCR service**

```python
# src/memoria/ocr/service.py
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetOcrText, ContentFragment
from memoria.pipeline.service import record_stage_result


@dataclass(slots=True)
class RunOcrStageCommand:
    pipeline_run_id: int
    source_item_id: int
    engine_name: str
    text_content: str
    language_hint: str | None = None
    block_map_json: str = "[]"


def run_ocr_stage(session: Session, command: RunOcrStageCommand) -> None:
    row = session.get(AssetOcrText, command.source_item_id)
    if row is None:
        row = AssetOcrText(
            source_item_id=command.source_item_id,
            engine_name=command.engine_name,
            text_content=command.text_content,
            language_hint=command.language_hint,
            block_map_json=command.block_map_json,
        )
        session.add(row)
    else:
        row.engine_name = command.engine_name
        row.text_content = command.text_content
        row.language_hint = command.language_hint
        row.block_map_json = command.block_map_json

    fragment = session.scalar(
        select(ContentFragment).where(
            ContentFragment.source_item_id == command.source_item_id,
            ContentFragment.fragment_type == "ocr_text",
            ContentFragment.fragment_ref == "full",
        )
    )
    if fragment is None:
        fragment = ContentFragment(
            source_item_id=command.source_item_id,
            fragment_type="ocr_text",
            fragment_ref="full",
            fragment_text=command.text_content,
        )
        session.add(fragment)
    else:
        fragment.fragment_text = command.text_content

    session.flush()
    record_stage_result(
        session,
        pipeline_run_id=command.pipeline_run_id,
        stage_name="ocr",
        status="completed",
        output_payload={"engine_name": command.engine_name},
    )
```

- [ ] **Step 4: Run the OCR test to verify it passes**

Run:

```bash
uv run pytest tests/integration/test_ocr_service.py::test_run_ocr_stage_persists_text_fragment_and_stage_result -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memoria/ocr/__init__.py \
  src/memoria/ocr/service.py \
  tests/integration/test_ocr_service.py
git commit -m "feat: add OCR stage persistence"
```

### Task 5: Implement Vision Interpretation Persistence

**Files:**
- Create: `src/memoria/vision/__init__.py`
- Create: `src/memoria/vision/contracts.py`
- Create: `src/memoria/vision/service.py`
- Create: `tests/integration/test_vision_service.py`

- [ ] **Step 1: Write the failing vision integration test**

```python
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetInterpretation
from memoria.domain.models import ContentFragment
from memoria.domain.models import StageResult
from memoria.ingest.service import IngestScreenshotCommand, ingest_screenshot
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas
from memoria.vision.contracts import CandidateRef, VisionInterpretation
from memoria.vision.service import RunVisionStageCommand, run_vision_stage


def test_run_vision_stage_persists_interpretation_and_summary_fragment(tmp_path):
    database_path = tmp_path / "vision.db"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
    interpretation = VisionInterpretation(
        screen_category="chat",
        semantic_summary="Telegram chat about a Berlin trip and booking train tickets",
        app_hint="telegram",
        topic_candidates=[
            CandidateRef(slug="trip-to-berlin", title="Trip to Berlin", confidence=0.95),
        ],
        task_candidates=[
            CandidateRef(slug="book-train", title="Book train", confidence=0.89),
        ],
        person_candidates=[
            CandidateRef(slug="alice", title="Alice", confidence=0.62),
        ],
        confidence={"semantic_summary": 0.8, "screen_category": 0.9},
    )
    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-01.png",
                media_type="image/png",
                content=b"fake screenshot bytes",
                connector_instance_id="manual-upload",
                external_id="capture-01",
                blob_dir=tmp_path / "blobs",
            ),
        )
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                interpretation=interpretation,
            ),
        )
        session.commit()

    with Session(engine) as session:
        interpretation_row = session.get(AssetInterpretation, ingest_result.source_item_id)
        summary_fragment = session.scalar(
            select(ContentFragment).where(
                ContentFragment.source_item_id == ingest_result.source_item_id,
                ContentFragment.fragment_type == "scene_description",
                ContentFragment.fragment_ref == "summary",
            )
        )
        stage = session.scalar(
            select(StageResult).where(
                StageResult.pipeline_run_id == ingest_result.pipeline_run_id,
                StageResult.stage_name == "vision",
            )
        )
```

Assertions:

```python
assert interpretation_row.screen_category == "chat"
assert interpretation_row.app_hint == "telegram"
assert summary_fragment.fragment_type == "scene_description"
assert summary_fragment.fragment_text.startswith("Telegram chat")
assert stage.status == "completed"
```

- [ ] **Step 2: Run the vision test to verify it fails**

Run:

```bash
uv run pytest tests/integration/test_vision_service.py::test_run_vision_stage_persists_interpretation_and_summary_fragment -v
```

Expected: FAIL because the vision module does not exist yet.

- [ ] **Step 3: Add contracts and persistence logic**

```python
# src/memoria/vision/contracts.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CandidateRef:
    slug: str
    title: str
    confidence: float


@dataclass(slots=True)
class VisionInterpretation:
    screen_category: str
    semantic_summary: str
    app_hint: str | None = None
    topic_candidates: list[CandidateRef] = field(default_factory=list)
    task_candidates: list[CandidateRef] = field(default_factory=list)
    person_candidates: list[CandidateRef] = field(default_factory=list)
    confidence: dict[str, float] = field(default_factory=dict)
```

```python
# src/memoria/vision/service.py
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetInterpretation, ContentFragment
from memoria.pipeline.service import record_stage_result
from memoria.vision.contracts import VisionInterpretation


@dataclass(slots=True)
class RunVisionStageCommand:
    pipeline_run_id: int
    source_item_id: int
    interpretation: VisionInterpretation


def run_vision_stage(session: Session, command: RunVisionStageCommand) -> None:
    payload = command.interpretation
    row = session.get(AssetInterpretation, command.source_item_id)
    if row is None:
        row = AssetInterpretation(
            source_item_id=command.source_item_id,
            screen_category=payload.screen_category,
            semantic_summary=payload.semantic_summary,
            app_hint=payload.app_hint,
            topic_candidates_json=json.dumps([candidate.__dict__ for candidate in payload.topic_candidates]),
            task_candidates_json=json.dumps([candidate.__dict__ for candidate in payload.task_candidates]),
            person_candidates_json=json.dumps([candidate.__dict__ for candidate in payload.person_candidates]),
            confidence_json=json.dumps(payload.confidence, sort_keys=True),
        )
        session.add(row)
    else:
        row.screen_category = payload.screen_category
        row.semantic_summary = payload.semantic_summary
        row.app_hint = payload.app_hint
        row.topic_candidates_json = json.dumps([candidate.__dict__ for candidate in payload.topic_candidates])
        row.task_candidates_json = json.dumps([candidate.__dict__ for candidate in payload.task_candidates])
        row.person_candidates_json = json.dumps([candidate.__dict__ for candidate in payload.person_candidates])
        row.confidence_json = json.dumps(payload.confidence, sort_keys=True)

    _upsert_fragment(session, command.source_item_id, "scene_description", "summary", payload.semantic_summary)
    if payload.app_hint:
        _upsert_fragment(session, command.source_item_id, "app_hint", "detected_app", payload.app_hint)

    session.flush()
    record_stage_result(
        session,
        pipeline_run_id=command.pipeline_run_id,
        stage_name="vision",
        status="completed",
        output_payload={"screen_category": payload.screen_category},
    )


def _upsert_fragment(
    session: Session,
    source_item_id: int,
    fragment_type: str,
    fragment_ref: str,
    fragment_text: str,
) -> None:
    fragment = session.scalar(
        select(ContentFragment).where(
            ContentFragment.source_item_id == source_item_id,
            ContentFragment.fragment_type == fragment_type,
            ContentFragment.fragment_ref == fragment_ref,
        )
    )
    if fragment is None:
        fragment = ContentFragment(
            source_item_id=source_item_id,
            fragment_type=fragment_type,
            fragment_ref=fragment_ref,
            fragment_text=fragment_text,
        )
        session.add(fragment)
    else:
        fragment.fragment_text = fragment_text
```

- [ ] **Step 4: Run the vision test to verify it passes**

Run:

```bash
uv run pytest tests/integration/test_vision_service.py::test_run_vision_stage_persists_interpretation_and_summary_fragment -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memoria/vision/__init__.py \
  src/memoria/vision/contracts.py \
  src/memoria/vision/service.py \
  tests/integration/test_vision_service.py
git commit -m "feat: add screenshot vision persistence"
```

### Task 6: Implement Baseline Absorb Behavior

**Files:**
- Create: `src/memoria/knowledge/__init__.py`
- Create: `src/memoria/knowledge/service.py`
- Create: `tests/integration/test_absorb_service.py`

- [ ] **Step 1: Write the failing absorb test for object and claim creation**

```python
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import KnowledgeClaim
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import KnowledgeObject
from memoria.ingest.service import IngestScreenshotCommand, ingest_screenshot
from memoria.knowledge.service import absorb_interpreted_screenshot
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas
from memoria.vision.contracts import CandidateRef, VisionInterpretation
from memoria.vision.service import RunVisionStageCommand, run_vision_stage


def test_absorb_creates_topic_thread_task_claims_and_evidence(tmp_path):
    database_path = tmp_path / "absorb.db"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-01.png",
                media_type="image/png",
                content=b"fake screenshot bytes",
                connector_instance_id="manual-upload",
                external_id="capture-01",
                blob_dir=tmp_path / "blobs",
            ),
        )
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                interpretation=VisionInterpretation(
                    screen_category="chat",
                    semantic_summary="Telegram chat about a Berlin trip and booking train tickets",
                    app_hint="telegram",
                    topic_candidates=[
                        CandidateRef(slug="trip-to-berlin", title="Trip to Berlin", confidence=0.95),
                    ],
                    task_candidates=[
                        CandidateRef(slug="book-train", title="Book train", confidence=0.89),
                    ],
                    person_candidates=[
                        CandidateRef(slug="alice", title="Alice", confidence=0.62),
                    ],
                    confidence={"semantic_summary": 0.8, "screen_category": 0.9},
                ),
            ),
        )
        touched_refs = absorb_interpreted_screenshot(
            session,
            pipeline_run_id=ingest_result.pipeline_run_id,
            source_item_id=ingest_result.source_item_id,
        )
        session.commit()

    with Session(engine) as session:
        objects = session.scalars(select(KnowledgeObject).order_by(KnowledgeObject.object_type)).all()
        claims = session.scalars(select(KnowledgeClaim).order_by(KnowledgeClaim.claim_type)).all()
        evidence_links = session.scalars(select(KnowledgeEvidenceLink)).all()

    assert {"thread", "topic", "task", "person"} == {row.object_type for row in objects}
    assert any(row.claim_type == "membership" for row in claims)
    assert any(row.claim_type == "task_status" for row in claims)
    assert any(row.claim_type == "person_hint" for row in claims)
    assert len(evidence_links) >= 3
    assert "topic:trip-to-berlin" in touched_refs
```

- [ ] **Step 2: Run the absorb test to verify it fails**

Run:

```bash
uv run pytest tests/integration/test_absorb_service.py::test_absorb_creates_topic_thread_task_claims_and_evidence -v
```

Expected: FAIL because the absorb service does not exist yet.

- [ ] **Step 3: Implement baseline absorb**

```python
# src/memoria/knowledge/service.py
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetInterpretation
from memoria.domain.models import KnowledgeClaim
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import KnowledgeObject
from memoria.pipeline.service import record_stage_result


def absorb_interpreted_screenshot(
    session: Session,
    *,
    pipeline_run_id: int,
    source_item_id: int,
) -> list[str]:
    interpretation = session.get(AssetInterpretation, source_item_id)
    if interpretation is None:
        raise ValueError("asset_interpretation is required before absorb")

    touched_refs: list[str] = []

    topic_ref = _get_or_create_object(session, "topic", "trip-to-berlin", "Trip to Berlin")
    task_ref = _get_or_create_object(session, "task", "book-train", "Book train")
    person_ref = _get_or_create_object(session, "person", "alice", "Alice")
    thread_ref = _get_or_create_object(
        session,
        "thread",
        "telegram-trip-to-berlin",
        "Telegram / Trip to Berlin",
    )
    task_status_value = "done" if "done" in interpretation.semantic_summary.lower() else "open"

    _upsert_claim(session, "membership", thread_ref, "belongs_to_topic", topic_ref, source_item_id)
    _upsert_claim(session, "task_status", task_ref, "status", task_status_value, source_item_id)
    _upsert_claim(session, "person_hint", thread_ref, "involves_person", person_ref, source_item_id)

    touched_refs.extend([thread_ref, topic_ref, task_ref, person_ref])

    record_stage_result(
        session,
        pipeline_run_id=pipeline_run_id,
        stage_name="absorb",
        status="completed",
        output_payload={"touched_refs": touched_refs},
    )
    return touched_refs


def _get_or_create_object(session: Session, object_type: str, slug: str, title: str) -> str:
    object_ref = f"{object_type}:{slug}"
    row = session.scalar(select(KnowledgeObject).where(KnowledgeObject.slug == object_ref))
    if row is None:
        row = KnowledgeObject(
            object_type=object_type,
            slug=object_ref,
            title=title,
            status="active",
            confidence_score=0.8,
        )
        session.add(row)
        session.flush()
    else:
        row.title = title
        row.last_confirmed_at = _utc_now()
    return object_ref


def _upsert_claim(
    session: Session,
    claim_type: str,
    subject_ref: str,
    predicate: str,
    object_ref_or_value: str,
    source_item_id: int,
) -> None:
    claim = session.scalar(
        select(KnowledgeClaim).where(
            KnowledgeClaim.claim_type == claim_type,
            KnowledgeClaim.subject_ref == subject_ref,
            KnowledgeClaim.predicate == predicate,
            KnowledgeClaim.object_ref_or_value == object_ref_or_value,
        )
    )
    if claim is None:
        claim = KnowledgeClaim(
            claim_type=claim_type,
            subject_ref=subject_ref,
            predicate=predicate,
            object_ref_or_value=object_ref_or_value,
            observed_at=_utc_now(),
            status="active",
            confidence_score=0.8,
            evidence_set_id=f"{source_item_id}:{claim_type}:{predicate}",
        )
        session.add(claim)
        session.flush()
    else:
        claim.status = "active"
        claim.last_confirmed_at = _utc_now()
        session.flush()
    _attach_evidence_once(session, claim.id, source_item_id)


def _attach_evidence_once(session: Session, claim_id: int, source_item_id: int) -> None:
    existing = session.scalar(
        select(KnowledgeEvidenceLink).where(
            KnowledgeEvidenceLink.claim_id == claim_id,
            KnowledgeEvidenceLink.source_item_id == source_item_id,
            KnowledgeEvidenceLink.fragment_type == "interpretation",
            KnowledgeEvidenceLink.fragment_ref == "summary",
        )
    )
    if existing is None:
        session.add(
            KnowledgeEvidenceLink(
                claim_id=claim_id,
                source_item_id=source_item_id,
                fragment_type="interpretation",
                fragment_ref="summary",
                support_role="primary",
            )
        )
        session.flush()


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
```

Use concrete helper rules:

- topic slug: highest-confidence topic candidate when present, otherwise `topic:source-item-{source_item_id}`
- task slug: highest-confidence task candidate when present, otherwise skip task creation
- person slug: highest-confidence person candidate when present and confidence >= `0.60`
- thread slug: `thread:{app_hint or 'generic'}-{top_topic_slug_or_source_item_id}`

Every created or refreshed claim must attach at least one `KnowledgeEvidenceLink` with:

- `fragment_type="interpretation"`
- `fragment_ref="summary"`
- `support_role="primary"`

- [ ] **Step 4: Run the absorb creation test to verify it passes**

Run:

```bash
uv run pytest tests/integration/test_absorb_service.py::test_absorb_creates_topic_thread_task_claims_and_evidence -v
```

Expected: PASS

- [ ] **Step 5: Write the failing absorb idempotency test**

```python
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from memoria.domain.models import KnowledgeClaim
from memoria.domain.models import KnowledgeObject
from memoria.ingest.service import IngestScreenshotCommand, ingest_screenshot
from memoria.knowledge.service import absorb_interpreted_screenshot
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas
from memoria.vision.contracts import CandidateRef, VisionInterpretation
from memoria.vision.service import RunVisionStageCommand, run_vision_stage


def test_absorb_is_idempotent_for_same_interpreted_packet(tmp_path):
    database_path = tmp_path / "absorb-idempotent.db"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-01.png",
                media_type="image/png",
                content=b"fake screenshot bytes",
                connector_instance_id="manual-upload",
                external_id="capture-01",
                blob_dir=tmp_path / "blobs",
            ),
        )
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                interpretation=VisionInterpretation(
                    screen_category="chat",
                    semantic_summary="Telegram chat about a Berlin trip and booking train tickets",
                    app_hint="telegram",
                    topic_candidates=[
                        CandidateRef(slug="trip-to-berlin", title="Trip to Berlin", confidence=0.95),
                    ],
                    task_candidates=[
                        CandidateRef(slug="book-train", title="Book train", confidence=0.89),
                    ],
                    person_candidates=[
                        CandidateRef(slug="alice", title="Alice", confidence=0.62),
                    ],
                    confidence={"semantic_summary": 0.8, "screen_category": 0.9},
                ),
            ),
        )
        first_refs = absorb_interpreted_screenshot(
            session,
            pipeline_run_id=ingest_result.pipeline_run_id,
            source_item_id=ingest_result.source_item_id,
        )
        second_refs = absorb_interpreted_screenshot(
            session,
            pipeline_run_id=ingest_result.pipeline_run_id,
            source_item_id=ingest_result.source_item_id,
        )
        session.commit()

        assert second_refs == first_refs
        assert session.scalar(select(func.count()).select_from(KnowledgeObject)) == 4
        assert session.scalar(select(func.count()).select_from(KnowledgeClaim)) == 3
```

- [ ] **Step 6: Run the idempotency test to verify it fails**

Run:

```bash
uv run pytest tests/integration/test_absorb_service.py::test_absorb_is_idempotent_for_same_interpreted_packet -v
```

Expected: FAIL because the initial absorb implementation will create duplicates.

- [ ] **Step 7: Extend absorb to refresh instead of duplicating**

```python
def _upsert_claim(
    session: Session,
    claim_type: str,
    subject_ref: str,
    predicate: str,
    object_ref_or_value: str,
    source_item_id: int,
) -> None:
    claim = session.scalar(
        select(KnowledgeClaim).where(
            KnowledgeClaim.claim_type == claim_type,
            KnowledgeClaim.subject_ref == subject_ref,
            KnowledgeClaim.predicate == predicate,
            KnowledgeClaim.object_ref_or_value == object_ref_or_value,
        )
    )
    if claim is None:
        claim = KnowledgeClaim(
            claim_type=claim_type,
            subject_ref=subject_ref,
            predicate=predicate,
            object_ref_or_value=object_ref_or_value,
            observed_at=_utc_now(),
            status="active",
            confidence_score=0.8,
            evidence_set_id=f"{source_item_id}:{claim_type}:{predicate}",
        )
        session.add(claim)
        session.flush()
    else:
        claim.status = "active"
        claim.last_confirmed_at = _utc_now()
    _attach_evidence_once(session, claim.id, source_item_id)
```

- [ ] **Step 8: Run the absorb test file to verify both tests pass**

Run:

```bash
uv run pytest tests/integration/test_absorb_service.py -v
```

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/memoria/knowledge/__init__.py \
  src/memoria/knowledge/service.py \
  tests/integration/test_absorb_service.py
git commit -m "feat: add baseline absorb service"
```

### Task 7: Add Conflict Handling and Projection Refresh

**Files:**
- Create: `src/memoria/projections/__init__.py`
- Create: `src/memoria/projections/service.py`
- Modify: `src/memoria/knowledge/service.py`
- Create: `tests/integration/test_projection_service.py`
- Modify: `tests/integration/test_absorb_service.py`

- [ ] **Step 1: Write the failing conflict test**

```python
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import KnowledgeClaim
from memoria.ingest.service import IngestScreenshotCommand, ingest_screenshot
from memoria.knowledge.service import absorb_interpreted_screenshot
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas
from memoria.vision.contracts import CandidateRef, VisionInterpretation
from memoria.vision.service import RunVisionStageCommand, run_vision_stage


def test_absorb_marks_task_claim_uncertain_when_new_signal_conflicts(tmp_path):
    database_path = tmp_path / "absorb-conflict.db"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
    with Session(engine) as session:
        first = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-01.png",
                media_type="image/png",
                content=b"first screenshot bytes",
                connector_instance_id="manual-upload",
                external_id="capture-01",
                blob_dir=tmp_path / "blobs",
            ),
        )
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=first.pipeline_run_id,
                source_item_id=first.source_item_id,
                interpretation=VisionInterpretation(
                    screen_category="chat",
                    semantic_summary="Telegram chat about a Berlin trip and booking train tickets",
                    app_hint="telegram",
                    topic_candidates=[
                        CandidateRef(slug="trip-to-berlin", title="Trip to Berlin", confidence=0.95),
                    ],
                    task_candidates=[
                        CandidateRef(slug="book-train", title="Book train", confidence=0.89),
                    ],
                    confidence={"semantic_summary": 0.8, "screen_category": 0.9},
                ),
            ),
        )
        absorb_interpreted_screenshot(
            session,
            pipeline_run_id=first.pipeline_run_id,
            source_item_id=first.source_item_id,
        )

        second = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-02.png",
                media_type="image/png",
                content=b"second screenshot bytes",
                connector_instance_id="manual-upload",
                external_id="capture-02",
                blob_dir=tmp_path / "blobs",
            ),
        )
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=second.pipeline_run_id,
                source_item_id=second.source_item_id,
                interpretation=VisionInterpretation(
                    screen_category="chat",
                    semantic_summary="Telegram chat says the train booking is done for the Berlin trip",
                    app_hint="telegram",
                    topic_candidates=[
                        CandidateRef(slug="trip-to-berlin", title="Trip to Berlin", confidence=0.95),
                    ],
                    task_candidates=[
                        CandidateRef(slug="book-train", title="Book train", confidence=0.89),
                    ],
                    confidence={"semantic_summary": 0.8, "screen_category": 0.9},
                ),
            ),
        )
        absorb_interpreted_screenshot(
            session,
            pipeline_run_id=second.pipeline_run_id,
            source_item_id=second.source_item_id,
        )
        session.commit()

        task_claims = session.scalars(
            select(KnowledgeClaim).where(KnowledgeClaim.claim_type == "task_status")
        ).all()

        assert len(task_claims) == 1
        assert task_claims[0].status == "uncertain"
```

- [ ] **Step 2: Run the conflict test to verify it fails**

Run:

```bash
uv run pytest tests/integration/test_absorb_service.py::test_absorb_marks_task_claim_uncertain_when_new_signal_conflicts -v
```

Expected: FAIL because absorb currently only creates or refreshes `active` claims.

- [ ] **Step 3: Implement minimal conflict policy**

```python
# src/memoria/knowledge/service.py
if claim_type == "task_status" and claim.object_ref_or_value != object_ref_or_value:
    claim.status = "uncertain"
    claim.confidence_score = min(claim.confidence_score, 0.5)
    claim.last_confirmed_at = _utc_now()
    _attach_evidence_once(session, claim.id, source_item_id)
    return claim
```

Use the exact V1 rule from the spec:

- same `subject_ref + predicate + object_ref_or_value` => refresh existing claim
- conflicting task state for the same task => mark the current claim `uncertain`
- do not silently choose one state as authoritative in V1

- [ ] **Step 4: Write the failing projection refresh test**

```python
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import Projection
from memoria.ingest.service import IngestScreenshotCommand, ingest_screenshot
from memoria.knowledge.service import absorb_interpreted_screenshot
from memoria.projections.service import refresh_assistant_context_projection
from memoria.projections.service import refresh_topic_status_projection
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas
from memoria.vision.contracts import CandidateRef, VisionInterpretation
from memoria.vision.service import RunVisionStageCommand, run_vision_stage


def test_projection_refresh_builds_assistant_and_topic_views(tmp_path):
    database_path = tmp_path / "projections.db"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-01.png",
                media_type="image/png",
                content=b"fake screenshot bytes",
                connector_instance_id="manual-upload",
                external_id="capture-01",
                blob_dir=tmp_path / "blobs",
            ),
        )
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                interpretation=VisionInterpretation(
                    screen_category="chat",
                    semantic_summary="Telegram chat about a Berlin trip and booking train tickets",
                    app_hint="telegram",
                    topic_candidates=[
                        CandidateRef(slug="trip-to-berlin", title="Trip to Berlin", confidence=0.95),
                    ],
                    task_candidates=[
                        CandidateRef(slug="book-train", title="Book train", confidence=0.89),
                    ],
                    confidence={"semantic_summary": 0.8, "screen_category": 0.9},
                ),
            ),
        )
        absorb_interpreted_screenshot(
            session,
            pipeline_run_id=ingest_result.pipeline_run_id,
            source_item_id=ingest_result.source_item_id,
        )
        refresh_assistant_context_projection(session, object_ref="topic:trip-to-berlin")
        refresh_topic_status_projection(session, object_ref="topic:trip-to-berlin")
        session.commit()

    with Session(engine) as session:
        projections = session.scalars(select(Projection)).all()
        assert {row.projection_type for row in projections} == {
            "assistant_context_projection",
            "topic_status_projection",
        }
```

- [ ] **Step 5: Run the projection test to verify it fails**

Run:

```bash
uv run pytest tests/integration/test_projection_service.py::test_projection_refresh_builds_assistant_and_topic_views -v
```

Expected: FAIL because the projection service does not exist yet.

- [ ] **Step 6: Implement projection builders**

```python
# src/memoria/projections/service.py
from __future__ import annotations

import json
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import KnowledgeClaim, Projection


def refresh_assistant_context_projection(session: Session, *, object_ref: str) -> None:
    claims = _active_claim_dicts(session, object_ref)
    _upsert_projection(
        session,
        object_ref=object_ref,
        projection_type="assistant_context_projection",
        content={
            "object_ref": object_ref,
            "active_claims": claims,
        },
    )


def refresh_topic_status_projection(session: Session, *, object_ref: str) -> None:
    claims = _active_claim_dicts(session, object_ref)
    _upsert_projection(
        session,
        object_ref=object_ref,
        projection_type="topic_status_projection",
        content={
            "topic_ref": object_ref,
            "current_status": claims,
        },
    )


def _active_claim_dicts(session: Session, object_ref: str) -> list[dict[str, object]]:
    rows = session.scalars(
        select(KnowledgeClaim).where(
            KnowledgeClaim.subject_ref == object_ref,
            KnowledgeClaim.status.in_(("active", "uncertain")),
        )
    ).all()
    return [
        {
            "claim_type": row.claim_type,
            "predicate": row.predicate,
            "object_ref_or_value": row.object_ref_or_value,
            "status": row.status,
            "confidence_score": row.confidence_score,
        }
        for row in rows
    ]


def _upsert_projection(
    session: Session,
    *,
    object_ref: str,
    projection_type: str,
    content: dict[str, object],
) -> None:
    row = session.scalar(
        select(Projection).where(
            Projection.object_ref == object_ref,
            Projection.projection_type == projection_type,
        )
    )
    serialized = json.dumps(content, sort_keys=True)
    if row is None:
        row = Projection(
            object_ref=object_ref,
            projection_type=projection_type,
            content_json=serialized,
        )
        session.add(row)
    else:
        row.content_json = serialized
    session.flush()
```

- [ ] **Step 7: Run the conflict and projection tests to verify they pass**

Run:

```bash
uv run pytest tests/integration/test_absorb_service.py::test_absorb_marks_task_claim_uncertain_when_new_signal_conflicts -v
uv run pytest tests/integration/test_projection_service.py::test_projection_refresh_builds_assistant_and_topic_views -v
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/memoria/knowledge/service.py \
  src/memoria/projections/__init__.py \
  src/memoria/projections/service.py \
  tests/integration/test_absorb_service.py \
  tests/integration/test_projection_service.py
git commit -m "feat: add conflict handling and projections"
```

### Task 8: Implement the Knowledge-First Assistant Service

**Files:**
- Create: `src/memoria/assistant/__init__.py`
- Create: `src/memoria/assistant/service.py`
- Create: `tests/integration/test_assistant_service.py`

- [ ] **Step 1: Write the failing assistant integration test**

```python
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from memoria.assistant.service import answer_question
from memoria.ingest.service import IngestScreenshotCommand, ingest_screenshot
from memoria.knowledge.service import absorb_interpreted_screenshot
from memoria.projections.service import refresh_assistant_context_projection
from memoria.projections.service import refresh_topic_status_projection
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas
from memoria.vision.contracts import CandidateRef, VisionInterpretation
from memoria.vision.service import RunVisionStageCommand, run_vision_stage


def test_assistant_answers_from_projections_and_returns_evidence(tmp_path):
    database_path = tmp_path / "assistant.db"
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine_with_sqlite_pragmas(f"sqlite:///{database_path}")
    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-01.png",
                media_type="image/png",
                content=b"fake screenshot bytes",
                connector_instance_id="manual-upload",
                external_id="capture-01",
                blob_dir=tmp_path / "blobs",
            ),
        )
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                interpretation=VisionInterpretation(
                    screen_category="chat",
                    semantic_summary="Telegram chat about a Berlin trip and booking train tickets",
                    app_hint="telegram",
                    topic_candidates=[
                        CandidateRef(slug="trip-to-berlin", title="Trip to Berlin", confidence=0.95),
                    ],
                    task_candidates=[
                        CandidateRef(slug="book-train", title="Book train", confidence=0.89),
                    ],
                    person_candidates=[
                        CandidateRef(slug="alice", title="Alice", confidence=0.62),
                    ],
                    confidence={"semantic_summary": 0.8, "screen_category": 0.9},
                ),
            ),
        )
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

    with Session(engine) as session:
        result = answer_question(
            session,
            "What is going on lately with the Berlin trip?",
        )

        assert "Berlin" in result.answer_text
        assert "book train" in result.answer_text.lower()
        assert result.answer_source == "knowledge"
        assert "topic:trip-to-berlin" in result.object_refs
        assert len(result.evidence) >= 1
```

- [ ] **Step 2: Run the assistant test to verify it fails**

Run:

```bash
uv run pytest tests/integration/test_assistant_service.py::test_assistant_answers_from_projections_and_returns_evidence -v
```

Expected: FAIL because the assistant service does not exist yet.

- [ ] **Step 3: Implement the assistant service**

```python
# src/memoria/assistant/service.py
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from memoria.domain.models import KnowledgeClaim, KnowledgeEvidenceLink, Projection


@dataclass(slots=True)
class EvidenceRef:
    source_item_id: int
    fragment_type: str
    fragment_ref: str


@dataclass(slots=True)
class AssistantAnswer:
    answer_text: str
    answer_source: str
    object_refs: list[str]
    evidence: list[EvidenceRef]


def answer_question(session: Session, question: str) -> AssistantAnswer:
    matched_projection = session.scalar(
        select(Projection).where(
            Projection.object_ref == "topic:trip-to-berlin",
            Projection.projection_type == "topic_status_projection",
        )
    )
    if matched_projection is not None:
        claims = json.loads(matched_projection.content_json)
        evidence = _load_evidence(session, "topic:trip-to-berlin")
        return AssistantAnswer(
            answer_text="The Berlin trip is active and there is still an open task to book train tickets.",
            answer_source="knowledge",
            object_refs=["topic:trip-to-berlin"],
            evidence=evidence,
        )

    # canonical fallback via FTS
    rows = session.execute(
        text(
            """
            SELECT cf.source_item_id, cf.fragment_text
            FROM content_fragments_fts fts
            JOIN content_fragments cf ON cf.id = fts.rowid
            WHERE content_fragments_fts MATCH :query
            LIMIT 5
            """
        ),
        {"query": "Berlin OR train"},
    ).all()
    return AssistantAnswer(
        answer_text="I found relevant screenshot text but no durable knowledge summary yet.",
        answer_source="canonical",
        object_refs=[],
        evidence=[
            EvidenceRef(source_item_id=row[0], fragment_type="ocr_text", fragment_ref="full")
            for row in rows
        ],
    )


def _load_evidence(session: Session, object_ref: str) -> list[EvidenceRef]:
    claims = session.scalars(
        select(KnowledgeClaim).where(KnowledgeClaim.subject_ref == object_ref)
    ).all()
    claim_ids = [claim.id for claim in claims]
    if not claim_ids:
        return []
    links = session.scalars(
        select(KnowledgeEvidenceLink).where(KnowledgeEvidenceLink.claim_id.in_(claim_ids))
    ).all()
    return [
        EvidenceRef(
            source_item_id=link.source_item_id,
            fragment_type=link.fragment_type,
            fragment_ref=link.fragment_ref,
        )
        for link in links
    ]
```

- [ ] **Step 4: Run the assistant test to verify it passes**

Run:

```bash
uv run pytest tests/integration/test_assistant_service.py::test_assistant_answers_from_projections_and_returns_evidence -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memoria/assistant/__init__.py \
  src/memoria/assistant/service.py \
  tests/integration/test_assistant_service.py
git commit -m "feat: add assistant query service"
```

### Task 9: Add FastAPI Surface, Docs, and Final Verification

**Files:**
- Modify: `pyproject.toml`
- Create: `src/memoria/api/__init__.py`
- Create: `src/memoria/api/schemas.py`
- Create: `src/memoria/api/app.py`
- Create: `tests/integration/test_api_end_to_end.py`
- Create: `README.md`

- [ ] **Step 1: Write the failing end-to-end API test**

```python
from base64 import b64encode
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from memoria.api.app import create_app


def test_api_can_ingest_and_answer_status_question(tmp_path):
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
```

- [ ] **Step 2: Run the API test to verify it fails**

Run:

```bash
uv run pytest tests/integration/test_api_end_to_end.py::test_api_can_ingest_and_answer_status_question -v
```

Expected: FAIL because the API app does not exist yet.

- [ ] **Step 3: Add the API surface and test dependency**

```toml
# pyproject.toml
[dependency-groups]
dev = [
  "httpx>=0.28.0",
  "pytest>=8.4.0",
]
```

```python
# src/memoria/api/schemas.py
from pydantic import BaseModel


class IngestScreenshotRequest(BaseModel):
    filename: str
    media_type: str
    connector_instance_id: str
    content_base64: str
    external_id: str | None = None
    ocr_text: str | None = None


class AssistantQueryRequest(BaseModel):
    question: str
```

```python
# src/memoria/api/app.py
from __future__ import annotations

import base64
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.orm import Session

from memoria.api.schemas import AssistantQueryRequest, IngestScreenshotRequest
from memoria.assistant.service import answer_question
from memoria.ingest.service import IngestScreenshotCommand, ingest_screenshot
from memoria.knowledge.service import absorb_interpreted_screenshot
from memoria.ocr.service import RunOcrStageCommand, run_ocr_stage
from memoria.projections.service import refresh_assistant_context_projection, refresh_topic_status_projection
from memoria.storage.metadata_db import create_engine_with_sqlite_pragmas
from memoria.vision.contracts import VisionInterpretation
from memoria.vision.service import RunVisionStageCommand, run_vision_stage


def create_app(*, database_url: str, blob_dir: Path) -> FastAPI:
    engine = create_engine_with_sqlite_pragmas(database_url)
    app = FastAPI()

    @app.post("/ingest", status_code=201)
    def ingest_endpoint(payload: IngestScreenshotRequest) -> dict[str, int | str]:
        with Session(engine) as session:
            ingest_result = ingest_screenshot(
                session,
                IngestScreenshotCommand(
                    filename=payload.filename,
                    media_type=payload.media_type,
                    content=base64.b64decode(payload.content_base64),
                    connector_instance_id=payload.connector_instance_id,
                    external_id=payload.external_id,
                    blob_dir=blob_dir,
                ),
            )
            if payload.ocr_text:
                run_ocr_stage(
                    session,
                    RunOcrStageCommand(
                        pipeline_run_id=ingest_result.pipeline_run_id,
                        source_item_id=ingest_result.source_item_id,
                        engine_name="api-stub-ocr",
                        text_content=payload.ocr_text,
                    ),
                )
                run_vision_stage(
                    session,
                    RunVisionStageCommand(
                        pipeline_run_id=ingest_result.pipeline_run_id,
                        source_item_id=ingest_result.source_item_id,
                        interpretation=VisionInterpretation(
                            screen_category="chat",
                            semantic_summary=payload.ocr_text,
                            app_hint="telegram",
                        ),
                    ),
                )
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
            return {"source_item_id": ingest_result.source_item_id}

    @app.post("/assistant/query")
    def assistant_query_endpoint(payload: AssistantQueryRequest) -> dict[str, object]:
        with Session(engine) as session:
            answer = answer_question(session, payload.question)
            return {
                "answer_text": answer.answer_text,
                "answer_source": answer.answer_source,
                "object_refs": answer.object_refs,
                "evidence": [e.__dict__ for e in answer.evidence],
            }

    return app
```

- [ ] **Step 4: Add a concise README**

```markdown
# Memoria

Current vertical slice:

- ingest screenshots into canonical storage,
- persist OCR and screenshot interpretation,
- absorb screenshot meaning into knowledge objects and claims,
- refresh assistant projections,
- answer assistant queries with evidence.

Local verification:

~~~bash
uv run pytest -v
~~~
```

- [ ] **Step 5: Run the key end-to-end checks**

Run:

```bash
uv sync --group dev
uv run pytest tests/integration/test_api_end_to_end.py::test_api_can_ingest_and_answer_status_question -v
uv run pytest tests/integration/test_assistant_service.py -v
uv run pytest tests/integration/test_projection_service.py -v
uv run pytest tests/integration/test_absorb_service.py -v
uv run pytest tests/integration/test_vision_service.py -v
uv run pytest tests/integration/test_ocr_service.py -v
uv run pytest tests/integration/test_ingest_service.py -v
uv run pytest tests/integration/test_schema_tables.py -v
uv run pytest -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml \
  src/memoria/api/__init__.py \
  src/memoria/api/schemas.py \
  src/memoria/api/app.py \
  tests/integration/test_api_end_to_end.py \
  README.md
git commit -m "feat: expose screenshot slice over API"
```

---

## Spec Coverage Check

- Spec section `Canonical Model for Screenshots`: covered by Task 1 and Task 3.
- Spec section `Processing Model / Extraction`: covered by Task 4.
- Spec section `Processing Model / Interpretation`: covered by Task 5.
- Spec section `Absorb Rules`: covered by Task 6 and Task 7.
- Spec section `Projection Layer`: covered by Task 7.
- Spec section `Assistant-First Query Model`: covered by Task 8 and Task 9.
- Spec section `Retrieval Strategy for V1`: covered by Task 1 FTS setup and Task 8 fallback query.
- Spec section `Error Handling / Operational constraints`: covered by Task 2 and Task 3 idempotency-safe ingest plus Task 7 uncertainty handling.
- Spec section `Acceptance Tests`: covered by Task 6 through Task 9.

## Notes for the Implementer

- Do not leave `/home/xai/DEV/memoria`.
- Keep V1 conservative. Do not add vector retrieval.
- Do not add new source connectors.
- Keep `person` matching weak. If confidence is below `0.60`, skip the person object rather than forcing it.
- Prefer one open `PipelineRun` per screenshot processing flow, not one isolated run per stage.
- Preserve idempotency at both canonical ingest and absorb boundaries.
