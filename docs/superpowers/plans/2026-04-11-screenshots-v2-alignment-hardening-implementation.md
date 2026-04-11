# Screenshots V2 Alignment And Live-Import Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining screenshot `v2` API and product gaps, while adding rebuild safety around live imports and performing all implementation work from a dedicated git worktree.

**Architecture:** Keep the existing write path (`ingest -> OCR -> vision -> absorb -> projections/map`) intact. Add the missing `v2` behavior through read-side services and routers: knowledge object views, map point drill-down, and filtered hybrid search. Add explicit admin guards so rebuild-style commands do not run by default while screenshot pipeline runs are still active.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.x, Alembic, SQLite + FTS5 + sqlite-vec, pytest

---

## Current Status

Fresh verification before writing this plan:

```bash
uv run pytest -v
```

Observed at plan-writing time:

```text
88 passed in 4.23s
```

Important operational context:

- the live screenshot import may still be running on another environment;
- implementation must happen in a dedicated worktree and against a separate development database;
- this plan assumes **no schema migration is required**;
- if implementation reveals a schema change is necessary, stop and revise rollout before touching the live environment.

---

## Repository Roots

- Plan document repo: `/home/xai/DEV/memoria`
- Worktree to create for implementation: `../memoria-screenshots-v2`
- All code changes in this plan happen inside the new worktree, not the current checkout

---

## File Structure

### Already Present

- `src/memoria/api/app.py`
  Purpose: current FastAPI application wiring screenshot, search, and map routers.
- `src/memoria/api/map.py`
  Purpose: cluster-oriented semantic map API and simple HTML shell.
- `src/memoria/api/search.py`
  Purpose: current `GET /search/hybrid`.
- `src/memoria/api/schemas.py`
  Purpose: shared API request and response models.
- `src/memoria/admin/cli.py`
  Purpose: admin CLI for import, reconcile, diagnose, and rebuild flows.
- `src/memoria/admin/service.py`
  Purpose: admin service logic for import, rebuild, and reconcile.
- `src/memoria/map/service.py`
  Purpose: semantic map rebuild and cluster read logic.
- `src/memoria/search/service.py`
  Purpose: hybrid search ranking across lexical, semantic, and knowledge channels.
- `src/memoria/screenshots/read/service.py`
  Purpose: screenshot list/detail/blob/search read layer.
- `tests/integration/_screenshot_read_helpers.py`
  Purpose: reusable screenshot dataset seeding for read/search/map tests.

### Create

- `src/memoria/screenshots/read/filters.py`
  Purpose: shared screenshot read filter contract and SQLAlchemy clause helpers reused by search, map, and knowledge read flows.
- `src/memoria/knowledge/read/__init__.py`
  Purpose: export knowledge read services.
- `src/memoria/knowledge/read/contracts.py`
  Purpose: typed topic/thread read models and evidence summaries.
- `src/memoria/knowledge/read/service.py`
  Purpose: build topic and thread views from existing knowledge, projection, and canonical tables.
- `src/memoria/api/knowledge.py`
  Purpose: knowledge topic/thread API router.
- `tests/unit/test_screenshot_read_filters.py`
  Purpose: unit coverage for shared filter normalization and clause generation.
- `tests/integration/test_knowledge_read_service.py`
  Purpose: service-level verification for topic/thread read-model assembly.
- `tests/integration/test_knowledge_api.py`
  Purpose: API-level verification for topic/thread endpoints.

### Modify

- `src/memoria/api/app.py`
  Purpose: register the knowledge router.
- `src/memoria/api/map.py`
  Purpose: add `GET /map/semantic/{source_item_id}` and update the HTML shell to load point detail.
- `src/memoria/api/search.py`
  Purpose: accept and pass filter parameters into hybrid search.
- `src/memoria/api/schemas.py`
  Purpose: add response models for knowledge views and semantic map point detail.
- `src/memoria/admin/cli.py`
  Purpose: add `--force` to rebuild-style commands and pass it through.
- `src/memoria/admin/service.py`
  Purpose: guard rebuilds against active screenshot pipeline runs unless forced.
- `src/memoria/map/service.py`
  Purpose: expose semantic map point detail read logic.
- `src/memoria/search/service.py`
  Purpose: apply shared screenshot filters to hybrid search inputs and channels.
- `tests/integration/_screenshot_read_helpers.py`
  Purpose: seed stable timestamps and refresh projections for knowledge-oriented read tests.
- `tests/integration/test_admin_service.py`
  Purpose: verify rebuild guard and force override behavior.
- `tests/integration/test_hybrid_search_api.py`
  Purpose: verify filter-aware hybrid search.
- `tests/integration/test_semantic_map_api.py`
  Purpose: verify point detail API and updated map HTML shell behavior.

---

### Task 1: Create The Dedicated Worktree And Verify The Baseline

**Files:**
- Verify only: current checkout and `../memoria-screenshots-v2`

- [ ] **Step 1: Create the worktree on a dedicated branch**

Run:

```bash
git worktree add ../memoria-screenshots-v2 -b feat/screenshots-v2-alignment main
```

Expected: a new worktree is created at `../memoria-screenshots-v2` and checked out on `feat/screenshots-v2-alignment`.

- [ ] **Step 2: Enter the worktree and confirm it is isolated**

Run:

```bash
cd ../memoria-screenshots-v2
git status --short
```

Expected:

```text
[no output]
```

- [ ] **Step 3: Create a dedicated development database path**

Run:

```bash
mkdir -p var
printf '%s\n' "MEMORIA_DATABASE_URL=sqlite:///$PWD/var/screenshots-v2.db" > .env.local
```

Expected: `.env.local` exists in the worktree and points at a database path under the worktree `var/` directory.

- [ ] **Step 4: Run the baseline suite from the worktree**

Run:

```bash
uv run pytest -v
```

Expected:

```text
88 passed
```

- [ ] **Step 5: Confirm that no implementation happens on `main`**

Run:

```bash
git rev-parse --abbrev-ref HEAD
```

Expected:

```text
feat/screenshots-v2-alignment
```

---

### Task 2: Add Shared Screenshot Filters And Upgrade Test Fixtures

**Files:**
- Create: `src/memoria/screenshots/read/filters.py`
- Create: `tests/unit/test_screenshot_read_filters.py`
- Modify: `tests/integration/_screenshot_read_helpers.py`

- [ ] **Step 1: Write the failing unit test for shared filters**

```python
# tests/unit/test_screenshot_read_filters.py
from datetime import datetime

from memoria.screenshots.read.filters import ScreenshotReadFilters


def test_screenshot_read_filters_drop_empty_values_and_keep_explicit_bounds() -> None:
    filters = ScreenshotReadFilters(
        connector_instance_id="manual-upload",
        app_hint="telegram",
        screen_category="chat",
        has_knowledge=True,
        observed_from=datetime(2026, 4, 2, 0, 0, 0),
        observed_to=datetime(2026, 4, 4, 23, 59, 59),
    )

    assert filters.connector_instance_id == "manual-upload"
    assert filters.app_hint == "telegram"
    assert filters.screen_category == "chat"
    assert filters.has_knowledge is True
    assert filters.observed_from == datetime(2026, 4, 2, 0, 0, 0)
    assert filters.observed_to == datetime(2026, 4, 4, 23, 59, 59)
    assert filters.has_any() is True
```

- [ ] **Step 2: Run the new unit test and verify it fails**

Run:

```bash
uv run pytest tests/unit/test_screenshot_read_filters.py::test_screenshot_read_filters_drop_empty_values_and_keep_explicit_bounds -v
```

Expected: FAIL with `ModuleNotFoundError` for `memoria.screenshots.read.filters`.

- [ ] **Step 3: Implement the shared filter contract and clause helpers**

```python
# src/memoria/screenshots/read/filters.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists

from memoria.domain.models import AssetInterpretation
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import SourceItem


@dataclass(frozen=True, slots=True)
class ScreenshotReadFilters:
    connector_instance_id: str | None = None
    app_hint: str | None = None
    screen_category: str | None = None
    has_knowledge: bool | None = None
    observed_from: datetime | None = None
    observed_to: datetime | None = None

    def has_any(self) -> bool:
        return any(
            value is not None
            for value in (
                self.connector_instance_id,
                self.app_hint,
                self.screen_category,
                self.has_knowledge,
                self.observed_from,
                self.observed_to,
            )
        )


def build_screenshot_filter_clauses(filters: ScreenshotReadFilters) -> list[object]:
    clauses: list[object] = []
    if filters.connector_instance_id is not None:
        clauses.append(SourceItem.connector_instance_id == filters.connector_instance_id)
    if filters.app_hint is not None:
        clauses.append(AssetInterpretation.app_hint == filters.app_hint)
    if filters.screen_category is not None:
        clauses.append(AssetInterpretation.screen_category == filters.screen_category)
    if filters.observed_from is not None:
        clauses.append(SourceItem.source_observed_at >= filters.observed_from)
    if filters.observed_to is not None:
        clauses.append(SourceItem.source_observed_at <= filters.observed_to)
    if filters.has_knowledge is True:
        clauses.append(
            exists(
                KnowledgeEvidenceLink.source_item_id
            ).where(KnowledgeEvidenceLink.source_item_id == SourceItem.id)
        )
    if filters.has_knowledge is False:
        clauses.append(
            ~exists(
                KnowledgeEvidenceLink.source_item_id
            ).where(KnowledgeEvidenceLink.source_item_id == SourceItem.id)
        )
    return clauses
```

- [ ] **Step 4: Upgrade the shared integration fixture dataset with stable observed times and refreshed projections**

```python
# tests/integration/_screenshot_read_helpers.py
from datetime import datetime

from memoria.projections.service import refresh_assistant_context_projection
from memoria.projections.service import refresh_topic_status_projection


def _seed_knowledge_backed(
    engine,
    tmp_path: Path,
    *,
    filename: str,
    external_id: str,
    content: bytes,
    ocr_text: str,
    connector_instance_id: str,
) -> int:
    with Session(engine) as session:
        ingest_result = ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename=filename,
                media_type="image/png",
                content=content,
                connector_instance_id=connector_instance_id,
                external_id=external_id,
                blob_dir=tmp_path / "blobs",
                source_created_at=datetime(2026, 4, 4, 9, 0, 0),
                source_observed_at=datetime(2026, 4, 4, 9, 5, 0),
            ),
        )
        run_ocr_stage(
            session,
            RunOcrStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                engine_name="manual-override",
                text_content=ocr_text,
            ),
        )
        run_vision_stage(
            session,
            RunVisionStageCommand(
                pipeline_run_id=ingest_result.pipeline_run_id,
                source_item_id=ingest_result.source_item_id,
                interpretation=_berlin_interpretation(),
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
        pipeline_run = session.get(PipelineRun, ingest_result.pipeline_run_id)
        assert pipeline_run is not None
        mark_pipeline_run_completed(session, pipeline_run)
        session.commit()
        return ingest_result.source_item_id
```

Use these exact timestamps:

- canonical-only: `2026-04-01T09:05:00`
- ocr-only: `2026-04-02T09:05:00`
- interpretation-only: `2026-04-03T09:05:00`
- knowledge-backed: `2026-04-04T09:05:00`

Set both `source_created_at` and `source_observed_at` explicitly in each helper so later filter tests can target exact windows deterministically.

- [ ] **Step 5: Run the new unit test and the existing read helper consumers**

Run:

```bash
uv run pytest tests/unit/test_screenshot_read_filters.py -v
uv run pytest tests/integration/test_screenshot_read_api.py tests/integration/test_screenshot_read_service.py -v
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 6: Commit the filter contract and fixture upgrade**

```bash
git add src/memoria/screenshots/read/filters.py \
  tests/unit/test_screenshot_read_filters.py \
  tests/integration/_screenshot_read_helpers.py
git commit -m "test: add shared screenshot filter contract"
```

---

### Task 3: Add Filter-Aware Hybrid Search

**Files:**
- Modify: `src/memoria/api/search.py`
- Modify: `src/memoria/search/service.py`
- Modify: `tests/integration/test_hybrid_search_api.py`

- [ ] **Step 1: Write the failing hybrid search filter integration test**

```python
# tests/integration/test_hybrid_search_api.py
def test_hybrid_search_applies_connector_app_category_time_and_knowledge_filters(tmp_path):
    client, engine = create_test_client(tmp_path, "hybrid-search-filtered.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    response = client.get(
        "/search/hybrid",
        params={
            "q": "Berlin train telegram",
            "connector_instance_id": "manual-upload",
            "app_hint": "telegram",
            "screen_category": "chat",
            "has_knowledge": "true",
            "observed_from": "2026-04-03T00:00:00",
            "observed_to": "2026-04-03T23:59:59",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["source_item_id"] for item in payload["items"]] == [
        seeded.knowledge_backed_source_item_id,
    ]
```

- [ ] **Step 2: Run the filtered hybrid search test and verify it fails**

Run:

```bash
uv run pytest tests/integration/test_hybrid_search_api.py::test_hybrid_search_applies_connector_app_category_time_and_knowledge_filters -v
```

Expected: FAIL because the endpoint does not yet accept or apply those query parameters.

- [ ] **Step 3: Extend the API and service to accept and apply shared filters**

```python
# src/memoria/api/search.py
from datetime import datetime

from memoria.screenshots.read.filters import ScreenshotReadFilters


@router.get("/search/hybrid", response_model=HybridSearchResponse)
def get_hybrid_search(
    q: str = Query(...),
    limit: int = Query(20, ge=0),
    offset: int = Query(0, ge=0),
    connector_instance_id: str | None = None,
    app_hint: str | None = None,
    screen_category: str | None = None,
    has_knowledge: bool | None = None,
    observed_from: datetime | None = None,
    observed_to: datetime | None = None,
) -> dict[str, object]:
    filters = ScreenshotReadFilters(
        connector_instance_id=connector_instance_id,
        app_hint=app_hint,
        screen_category=screen_category,
        has_knowledge=has_knowledge,
        observed_from=observed_from,
        observed_to=observed_to,
    )
    with Session(engine) as session:
        result = hybrid_search_screenshots(
            session,
            query=q,
            limit=limit,
            offset=offset,
            filters=filters,
        )
    return asdict(result)
```

```python
# src/memoria/search/service.py
from memoria.screenshots.read.filters import ScreenshotReadFilters
from memoria.screenshots.read.filters import build_screenshot_filter_clauses


def hybrid_search_screenshots(
    session: Session,
    *,
    query: str,
    limit: int = 20,
    offset: int = 0,
    filters: ScreenshotReadFilters | None = None,
) -> HybridSearchResult:
    resolved_filters = filters or ScreenshotReadFilters()
    allowed_source_ids = _filtered_source_item_ids(session, filters=resolved_filters)
    lexical = [
        item
        for item in search_screenshots(
            session,
            query=query,
            limit=max(limit * 5, 20),
            offset=0,
        ).items
        if not allowed_source_ids or item.source_item_id in allowed_source_ids
    ]
    semantic = _filtered_semantic_matches(
        session,
        query=query,
        filters=resolved_filters,
        limit=max(limit * 5, 20),
    )
    knowledge_ids = _knowledge_source_matches(
        session,
        query=query,
        filters=resolved_filters,
        limit=max(limit * 5, 20),
    )
```

Apply the shared clauses to the semantic and knowledge channels, and reject any lexical hit whose `source_item_id` falls outside the filter set.

- [ ] **Step 4: Run hybrid search tests**

Run:

```bash
uv run pytest tests/integration/test_hybrid_search_api.py -v
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 5: Commit the hybrid search filter support**

```bash
git add src/memoria/api/search.py \
  src/memoria/search/service.py \
  tests/integration/test_hybrid_search_api.py
git commit -m "feat: add filtered hybrid screenshot search"
```

---

### Task 4: Add Knowledge Read Services For Topics And Threads

**Files:**
- Create: `src/memoria/knowledge/read/__init__.py`
- Create: `src/memoria/knowledge/read/contracts.py`
- Create: `src/memoria/knowledge/read/service.py`
- Create: `tests/integration/test_knowledge_read_service.py`

- [ ] **Step 1: Write the failing topic/thread read service tests**

```python
# tests/integration/test_knowledge_read_service.py
def test_get_topic_view_returns_threads_tasks_people_and_recent_screenshots(tmp_path):
    engine = create_test_engine(tmp_path, "knowledge-read-topic.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    from memoria.knowledge.read.service import get_topic_view

    with Session(engine) as session:
        result = get_topic_view(session, slug="trip-to-berlin")

    assert result is not None
    assert result.topic.object_ref == "topic:trip-to-berlin"
    assert "thread:telegram-trip-to-berlin" in result.thread_refs
    assert any(task.status_value == "open" for task in result.task_statuses)
    assert any(person.object_ref == "person:alice" for person in result.people)
    assert result.recent_screenshots[0].source_item_id == seeded.knowledge_backed_source_item_id


def test_get_thread_view_returns_parent_topic_people_and_recent_screenshots(tmp_path):
    engine = create_test_engine(tmp_path, "knowledge-read-thread.db")
    seeded = seed_screenshot_dataset(engine, tmp_path)

    from memoria.knowledge.read.service import get_thread_view

    with Session(engine) as session:
        result = get_thread_view(session, slug="telegram-trip-to-berlin")

    assert result is not None
    assert result.thread.object_ref == "thread:telegram-trip-to-berlin"
    assert result.topic_ref == "topic:trip-to-berlin"
    assert any(person.object_ref == "person:alice" for person in result.people)
    assert result.recent_screenshots[0].source_item_id == seeded.knowledge_backed_source_item_id
```

- [ ] **Step 2: Run the new knowledge read service tests and verify they fail**

Run:

```bash
uv run pytest tests/integration/test_knowledge_read_service.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `memoria.knowledge.read.service`.

- [ ] **Step 3: Implement typed knowledge read contracts and services**

```python
# src/memoria/knowledge/read/contracts.py
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class KnowledgeObjectSummary:
    object_ref: str
    object_type: str
    title: str
    status: str
    confidence_score: float


@dataclass(frozen=True, slots=True)
class KnowledgeTaskStatusSummary:
    task_ref: str
    task_title: str | None
    status_value: str
    claim_status: str


@dataclass(frozen=True, slots=True)
class KnowledgeScreenshotSummary:
    source_item_id: int
    filename: str
    semantic_summary: str | None
    app_hint: str | None
    observed_at: datetime | None
    object_refs: list[str]
```

```python
# src/memoria/knowledge/read/service.py
def get_topic_view(session: Session, *, slug: str) -> TopicReadModel | None:
    topic_ref = f"topic:{slug}"
    topic_object = _get_object(session, topic_ref)
    if topic_object is None:
        return None
    assistant_projection = _load_projection(session, topic_ref, "assistant_context_projection")
    topic_projection = _load_projection(session, topic_ref, "topic_status_projection")
    return TopicReadModel(
        topic=_object_summary(topic_object),
        thread_refs=_extract_thread_refs(assistant_projection, topic_projection),
        task_statuses=_extract_task_statuses(topic_projection),
        people=_extract_people(session, assistant_projection, topic_projection),
        recent_screenshots=_recent_screenshots_for_refs(session, [topic_ref]),
        evidence=_recent_evidence_for_refs(session, [topic_ref]),
    )


def get_thread_view(session: Session, *, slug: str) -> ThreadReadModel | None:
    thread_ref = f"thread:{slug}"
    thread_object = _get_object(session, thread_ref)
    if thread_object is None:
        return None
    topic_ref = _parent_topic_ref_for_thread(session, thread_ref)
    return ThreadReadModel(
        thread=_object_summary(thread_object),
        topic_ref=topic_ref,
        people=_people_for_thread(session, thread_ref),
        claims=_claims_for_thread(session, thread_ref),
        recent_screenshots=_recent_screenshots_for_refs(session, [thread_ref]),
        evidence=_recent_evidence_for_refs(session, [thread_ref]),
    )
```

- [ ] **Step 4: Run the new service tests**

Run:

```bash
uv run pytest tests/integration/test_knowledge_read_service.py -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit the knowledge read service**

```bash
git add src/memoria/knowledge/read/__init__.py \
  src/memoria/knowledge/read/contracts.py \
  src/memoria/knowledge/read/service.py \
  tests/integration/test_knowledge_read_service.py
git commit -m "feat: add knowledge topic and thread read services"
```

---

### Task 5: Add Knowledge API Endpoints

**Files:**
- Create: `src/memoria/api/knowledge.py`
- Modify: `src/memoria/api/app.py`
- Modify: `src/memoria/api/schemas.py`
- Create: `tests/integration/test_knowledge_api.py`

- [ ] **Step 1: Write the failing knowledge API tests**

```python
# tests/integration/test_knowledge_api.py
def test_get_topic_endpoint_returns_semantic_topic_view(tmp_path):
    client, engine = create_test_client(tmp_path, "knowledge-api-topic.db")
    seed_screenshot_dataset(engine, tmp_path)

    response = client.get("/knowledge/topics/trip-to-berlin")

    assert response.status_code == 200
    payload = response.json()
    assert payload["topic"]["object_ref"] == "topic:trip-to-berlin"
    assert "thread:telegram-trip-to-berlin" in payload["thread_refs"]


def test_get_thread_endpoint_returns_semantic_thread_view(tmp_path):
    client, engine = create_test_client(tmp_path, "knowledge-api-thread.db")
    seed_screenshot_dataset(engine, tmp_path)

    response = client.get("/knowledge/threads/telegram-trip-to-berlin")

    assert response.status_code == 200
    payload = response.json()
    assert payload["thread"]["object_ref"] == "thread:telegram-trip-to-berlin"
    assert payload["topic_ref"] == "topic:trip-to-berlin"
```

- [ ] **Step 2: Run the knowledge API tests and verify they fail**

Run:

```bash
uv run pytest tests/integration/test_knowledge_api.py -v
```

Expected: FAIL with `404 Not Found` because the knowledge router is not registered.

- [ ] **Step 3: Add schemas, router, and app wiring**

```python
# src/memoria/api/knowledge.py
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from memoria.knowledge.read.service import get_thread_view
from memoria.knowledge.read.service import get_topic_view


@router.get("/knowledge/topics/{slug}", response_model=KnowledgeTopicResponse)
def get_topic(slug: str) -> dict[str, object]:
    with Session(engine) as session:
        result = get_topic_view(session, slug=slug)
    if result is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return asdict(result)
```

```python
# src/memoria/api/app.py
from memoria.api.knowledge import create_knowledge_router

app.include_router(create_knowledge_router(engine=engine))
```

```python
# src/memoria/api/schemas.py
class KnowledgeObjectSummaryResponse(BaseModel):
    object_ref: str
    object_type: str
    title: str
    status: str
    confidence_score: float


class KnowledgeTaskStatusResponse(BaseModel):
    task_ref: str
    task_title: str | None
    status_value: str
    claim_status: str


class KnowledgeScreenshotSummaryResponse(BaseModel):
    source_item_id: int
    filename: str
    semantic_summary: str | None
    app_hint: str | None
    observed_at: datetime | None
    object_refs: list[str]


class KnowledgeTopicResponse(BaseModel):
    topic: KnowledgeObjectSummaryResponse
    thread_refs: list[str]
    task_statuses: list[KnowledgeTaskStatusResponse]
    people: list[KnowledgeObjectSummaryResponse]
    recent_screenshots: list[KnowledgeScreenshotSummaryResponse]
    evidence: list[dict[str, object]]


class KnowledgeThreadResponse(BaseModel):
    thread: KnowledgeObjectSummaryResponse
    topic_ref: str | None
    people: list[KnowledgeObjectSummaryResponse]
    claims: list[dict[str, object]]
    recent_screenshots: list[KnowledgeScreenshotSummaryResponse]
    evidence: list[dict[str, object]]
```

- [ ] **Step 4: Run the knowledge API tests**

Run:

```bash
uv run pytest tests/integration/test_knowledge_api.py tests/integration/test_knowledge_read_service.py -v
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 5: Commit the knowledge API surface**

```bash
git add src/memoria/api/knowledge.py \
  src/memoria/api/app.py \
  src/memoria/api/schemas.py \
  tests/integration/test_knowledge_api.py
git commit -m "feat: add knowledge topic and thread api"
```

---

### Task 6: Add Semantic Map Point Detail API

**Files:**
- Modify: `src/memoria/map/service.py`
- Modify: `src/memoria/api/map.py`
- Modify: `src/memoria/api/schemas.py`
- Modify: `tests/integration/test_semantic_map_api.py`

- [ ] **Step 1: Write the failing semantic map point detail test**

```python
# tests/integration/test_semantic_map_api.py
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
```

- [ ] **Step 2: Run the point detail test and verify it fails**

Run:

```bash
uv run pytest tests/integration/test_semantic_map_api.py::test_semantic_map_point_endpoint_returns_point_detail_and_object_refs -v
```

Expected: FAIL with `404 Not Found`.

- [ ] **Step 3: Implement point detail in the map service and router**

```python
# src/memoria/map/service.py
@dataclass(frozen=True, slots=True)
class SemanticMapPointDetail:
    source_item_id: int
    x: float
    y: float
    cluster_key: str | None
    semantic_summary: str | None
    app_hint: str | None
    created_at: datetime | None
    observed_at: datetime | None
    object_refs: list[str]
    evidence: list[dict[str, object]]
    screenshot_detail_url: str


def get_semantic_map_point(session: Session, *, source_item_id: int) -> SemanticMapPointDetail | None:
    latest_map_run_id = session.scalar(
        select(SemanticMapRun.id)
        .where(SemanticMapRun.map_key == "screenshots_semantic_v1")
        .order_by(SemanticMapRun.id.desc())
    )
    if latest_map_run_id is None:
        return None
    point = session.scalar(
        select(SemanticMapPoint).where(
            SemanticMapPoint.map_run_id == latest_map_run_id,
            SemanticMapPoint.source_item_id == source_item_id,
        )
    )
    if point is None:
        return None
    source_item = session.get(SourceItem, source_item_id)
    payload = session.get(SourcePayloadScreenshot, source_item_id)
    interpretation = session.get(AssetInterpretation, source_item_id)
    evidence_links = session.scalars(
        select(KnowledgeEvidenceLink)
        .where(KnowledgeEvidenceLink.source_item_id == source_item_id)
        .order_by(KnowledgeEvidenceLink.id.asc())
    ).all()
    return SemanticMapPointDetail(
        source_item_id=source_item_id,
        x=point.x,
        y=point.y,
        cluster_key=point.cluster_key,
        semantic_summary=None if interpretation is None else interpretation.semantic_summary,
        app_hint=None if interpretation is None else interpretation.app_hint,
        created_at=None if source_item is None else source_item.source_created_at,
        observed_at=None if source_item is None else source_item.source_observed_at,
        object_refs=_load_object_refs(session, source_item_id=source_item_id),
        evidence=[
            {
                "claim_id": link.claim_id,
                "fragment_type": link.fragment_type,
                "fragment_ref": link.fragment_ref,
            }
            for link in evidence_links
        ],
        screenshot_detail_url=f"/screenshots/{source_item_id}",
    )
```

```python
# src/memoria/api/map.py
@router.get("/map/semantic/{source_item_id}", response_model=SemanticMapPointDetailResponse)
def get_semantic_map_point_endpoint(source_item_id: int) -> dict[str, object]:
    with Session(engine) as session:
        result = get_semantic_map_point(session, source_item_id=source_item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="semantic map point not found")
    return asdict(result)
```

- [ ] **Step 4: Run the semantic map API tests**

Run:

```bash
uv run pytest tests/integration/test_semantic_map_api.py -v
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 5: Commit the semantic map point detail endpoint**

```bash
git add src/memoria/map/service.py \
  src/memoria/api/map.py \
  src/memoria/api/schemas.py \
  tests/integration/test_semantic_map_api.py
git commit -m "feat: add semantic map point detail api"
```

---

### Task 7: Update The Map HTML Shell To Drill Down From A Point

**Files:**
- Modify: `src/memoria/api/map.py`
- Modify: `tests/integration/test_semantic_map_api.py`

- [ ] **Step 1: Add the failing HTML shell test**

```python
# tests/integration/test_semantic_map_api.py
def test_semantic_map_page_contains_point_detail_loader(tmp_path):
    client, engine = create_test_client(tmp_path, "semantic-map-page-point-loader.db")
    seed_screenshot_dataset(engine, tmp_path)

    response = client.get("/map")

    assert response.status_code == 200
    assert "loadPoint" in response.text
    assert "/map/semantic/${sourceItemId}" in response.text
    assert "/screenshots/${sourceItemId}" in response.text
```

- [ ] **Step 2: Run the HTML shell test and verify it fails**

Run:

```bash
uv run pytest tests/integration/test_semantic_map_api.py::test_semantic_map_page_contains_point_detail_loader -v
```

Expected: FAIL because the current HTML shell does not contain point-detail loader code.

- [ ] **Step 3: Update the map shell JavaScript to fetch point detail and render screenshot/knowledge links**

```html
<script>
  async function loadPoint(sourceItemId) {
    const point = await fetchJson(`/map/semantic/${sourceItemId}`);
    const detailNode = document.getElementById('cluster-detail');
    detailNode.innerHTML = `
      <h2>${point.semantic_summary || 'Screenshot detail'}</h2>
      <div class="muted">${point.app_hint || 'unknown app'} · cluster ${point.cluster_key || 'none'}</div>
      <p><a href="${point.screenshot_detail_url}">Open screenshot detail</a></p>
      <ul>${point.object_refs.map(ref => `<li>${ref}</li>`).join('')}</ul>
    `;
  }

  async function loadCluster(clusterKey) {
    const [detail, items] = await Promise.all([
      fetchJson(`/map/semantic/clusters/${clusterKey}`),
      fetchJson(`/map/semantic/clusters/${clusterKey}/items`),
    ]);
    detailNode.innerHTML = `
      <h2>${detail.title}</h2>
      <div class="muted">${detail.item_count} items · ${detail.top_labels.join(', ')}</div>
      <ul>${items.items.map(item => `<li><button type="button" onclick="loadPoint(${item.source_item_id})">${item.filename}</button></li>`).join('')}</ul>
    `;
  }
</script>
```

- [ ] **Step 4: Run the map shell and API tests**

Run:

```bash
uv run pytest tests/integration/test_semantic_map_api.py -v
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 5: Commit the map UI drill-down update**

```bash
git add src/memoria/api/map.py \
  tests/integration/test_semantic_map_api.py
git commit -m "feat: add map point drill-down ui"
```

---

### Task 8: Guard Rebuild Operations Against Active Imports

**Files:**
- Modify: `src/memoria/admin/service.py`
- Modify: `src/memoria/admin/cli.py`
- Modify: `tests/integration/test_admin_service.py`

- [ ] **Step 1: Write the failing admin safety tests**

```python
# tests/integration/test_admin_service.py
def test_rebuild_screenshot_derived_data_rejects_active_running_pipelines(tmp_path):
    from memoria.admin.service import rebuild_screenshot_derived_data

    engine = _create_engine(tmp_path, "admin-rebuild-guard.db")
    blob_dir = tmp_path / "blobs"

    with Session(engine) as session:
        ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-running.png",
                media_type="image/png",
                content=b"running pipeline bytes",
                connector_instance_id="manual-upload",
                external_id="capture-running",
                blob_dir=blob_dir,
            ),
        )
        session.commit()

    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="active screenshot pipeline runs"):
            rebuild_screenshot_derived_data(session)


def test_rebuild_screenshot_derived_data_force_bypasses_running_pipeline_guard(tmp_path):
    from memoria.admin.service import rebuild_screenshot_derived_data

    engine = _create_engine(tmp_path, "admin-rebuild-force.db")
    blob_dir = tmp_path / "blobs"

    with Session(engine) as session:
        ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="capture-running-force.png",
                media_type="image/png",
                content=b"running pipeline bytes",
                connector_instance_id="manual-upload",
                external_id="capture-running-force",
                blob_dir=blob_dir,
            ),
        )
        session.commit()

    with Session(engine) as session:
        payload = rebuild_screenshot_derived_data(session, force=True)

    assert payload["absorbed"] == 0
```

- [ ] **Step 2: Run the admin safety tests and verify they fail**

Run:

```bash
uv run pytest tests/integration/test_admin_service.py::test_rebuild_screenshot_derived_data_rejects_active_running_pipelines tests/integration/test_admin_service.py::test_rebuild_screenshot_derived_data_force_bypasses_running_pipeline_guard -v
```

Expected: FAIL because `rebuild_screenshot_derived_data()` does not yet guard active imports or accept `force`.

- [ ] **Step 3: Implement the running-pipeline guard and CLI flag**

```python
# src/memoria/admin/service.py
def count_running_screenshot_pipeline_runs(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(PipelineRun)
            .join(SourceItem, SourceItem.id == PipelineRun.source_item_id)
            .where(
                PipelineRun.status == "running",
                SourceItem.source_family == "screenshot",
            )
        )
        or 0
    )


def rebuild_screenshot_derived_data(session: Session, *, force: bool = False) -> dict[str, int]:
    running_count = count_running_screenshot_pipeline_runs(session)
    if running_count and not force:
        raise RuntimeError(f"active screenshot pipeline runs: {running_count}")
    absorbed = 0
    projections = 0
    interpretation_rows = session.scalars(
        select(AssetInterpretation).order_by(AssetInterpretation.source_item_id.asc())
    ).all()
    for interpretation_row in interpretation_rows:
        source_item = session.get(SourceItem, interpretation_row.source_item_id)
        pipeline_run = session.scalar(
            select(PipelineRun)
            .where(PipelineRun.source_item_id == interpretation_row.source_item_id)
            .order_by(PipelineRun.id.desc())
        )
        if source_item is None or pipeline_run is None:
            continue
        interpretation = _interpretation_dict(interpretation_row)
        if source_item.mode == "absorb" and should_absorb_interpretation(interpretation):
            touched_refs = absorb_interpreted_screenshot(
                session,
                pipeline_run_id=pipeline_run.id,
                source_item_id=source_item.id,
            )
            absorbed += 1
            for object_ref in touched_refs:
                refresh_assistant_context_projection(session, object_ref=object_ref)
                projections += 1
                if object_ref.startswith("topic:"):
                    refresh_topic_status_projection(session, object_ref=object_ref)
                    projections += 1
    rebuild_semantic_map(session, source_family="screenshot")
    reconcile_pipeline_runs(session)
    return {"absorbed": absorbed, "projections_refreshed": projections}
```

```python
# src/memoria/admin/cli.py
diagnose_parser = subparsers.add_parser("diagnose-vision-failure")
diagnose_parser.add_argument("--source-item-id", required=True, type=int)
subparsers.add_parser("reconcile-pipeline-runs")
rebuild_parser = subparsers.add_parser("rebuild-screenshot-derived-data")
rebuild_parser.add_argument("--force", action="store_true")

elif args.command == "reconcile-pipeline-runs":
    payload = reconcile_pipeline_runs(session)
    session.commit()
else:
    payload = rebuild_screenshot_derived_data(session, force=args.force)
    session.commit()
```

- [ ] **Step 4: Run the admin tests**

Run:

```bash
uv run pytest tests/integration/test_admin_service.py -v
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 5: Commit the rebuild safety guard**

```bash
git add src/memoria/admin/service.py \
  src/memoria/admin/cli.py \
  tests/integration/test_admin_service.py
git commit -m "feat: guard rebuilds during active screenshot imports"
```

---

### Task 9: Run Focused Verification And The Full Regression Suite

**Files:**
- Verify only: current worktree changes

- [ ] **Step 1: Run the focused new and modified test groups**

Run:

```bash
uv run pytest \
  tests/unit/test_screenshot_read_filters.py \
  tests/integration/test_hybrid_search_api.py \
  tests/integration/test_knowledge_read_service.py \
  tests/integration/test_knowledge_api.py \
  tests/integration/test_semantic_map_api.py \
  tests/integration/test_admin_service.py -v
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 2: Run the full regression suite**

Run:

```bash
uv run pytest -v
```

Expected:

```text
all tests pass
```

- [ ] **Step 3: Confirm the worktree is clean after the last task commit**

Run:

```bash
git status --short
```

Expected:

```text
[no output]
```

- [ ] **Step 4: Record the rollout rule before merging**

Add this note to the PR description or merge checklist:

```text
No schema migration is included in this change set.
Deploy only after confirming rebuild-style admin commands are not being run against the live database during active imports.
```

This step does not change repository files. It exists to make the operational constraint explicit at merge time.

---

## Self-Review

### Spec Coverage

- Missing `v2` knowledge endpoints: covered by Tasks 4 and 5.
- Missing `GET /map/semantic/{source_item_id}`: covered by Task 6.
- Map drill-down from UI: covered by Task 7.
- Filter-aware hybrid search: covered by Tasks 2 and 3.
- Live-import rebuild safety: covered by Task 8.
- Separate worktree requirement: covered by Task 1 and enforced throughout the plan.

### Placeholder Scan

- No `TBD`, `TODO`, or deferred implementation notes appear inside executable tasks.
- The plan does not rely on “similar to Task N” references for code steps.

### Type Consistency

- Shared filter contract is named `ScreenshotReadFilters` consistently across Tasks 2 and 3.
- Topic/thread read service naming is consistent between contracts, service functions, and API wiring.
- Semantic map point detail naming is consistent between service, API, and tests.
