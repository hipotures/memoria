# Semantic Atlas Cluster Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first screenshot semantic atlas product: a backend atlas projection with dedicated atlas tables and read APIs, plus a React + TypeScript + PixiJS atlas/workbench UI with semantic zoom across region, subregion, and evidence levels.

**Architecture:** Keep the current screenshot ingest, OCR, vision, absorb, and semantic map write paths intact. Add a new atlas projection layer under `src/memoria/atlas/`, persist it in dedicated `atlas_*` tables, expose read-only atlas APIs through FastAPI, and mount a separately built Vite frontend that consumes those atlas endpoints. Atlas structure is computed on the backend from the latest semantic map and screenshot semantic embeddings; the browser only renders and navigates the projection.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.x, Alembic, SQLite, pytest, React, TypeScript, Vite, PixiJS v8, TanStack Virtual, Vitest, helper-only d3 modules

---

## Current Status

Fresh verification before writing this plan:

```bash
uv run pytest -v
```

Observed at plan-writing time:

```text
104 passed in 4.85s
```

Important implementation context:

- this feature **does require a schema migration** because atlas projection tables do not exist yet;
- the repository has no existing React/Vite frontend workspace;
- the current semantic map already exists and will be used as the structural input for atlas MVP;
- atlas rebuilds must not run by default while screenshot pipeline runs are active.

---

## Repository Roots

- Plan document repo: `/home/xai/DEV/memoria`
- Worktree for implementation: `/home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas`
- Frontend workspace to create inside the worktree: `frontend/atlas`
- Atlas development database inside the worktree: `var/semantic-atlas.db`

---

## File Structure

### Already Present

- `src/memoria/api/app.py`
  Purpose: FastAPI application wiring and router registration.
- `src/memoria/api/schemas.py`
  Purpose: existing API response models.
- `src/memoria/admin/cli.py`
  Purpose: admin entrypoint for imports and rebuilds.
- `src/memoria/admin/service.py`
  Purpose: import and rebuild orchestration with active-run guards.
- `src/memoria/domain/models.py`
  Purpose: SQLAlchemy metadata model definitions.
- `src/memoria/map/service.py`
  Purpose: current semantic map rebuild and read logic.
- `src/memoria/search/embeddings.py`
  Purpose: current screenshot semantic embedding basis (`hashed-text-v1`, 96d).
- `src/memoria/screenshots/read/filters.py`
  Purpose: shared screenshot-oriented filter contract for backend read surfaces.
- `tests/integration/_screenshot_read_helpers.py`
  Purpose: reusable screenshot dataset seeding helpers.
- `tests/integration/test_admin_service.py`
  Purpose: rebuild and CLI guard verification.
- `tests/integration/test_schema_tables.py`
  Purpose: alembic-upgraded schema verification.

### Create

- `alembic/versions/20260411_04_add_atlas_projection_tables.py`
  Purpose: create atlas run, region, item, and edge tables.
- `src/memoria/atlas/__init__.py`
  Purpose: export atlas rebuild and read functions.
- `src/memoria/atlas/contracts.py`
  Purpose: typed atlas filters, projection records, and read-service contracts.
- `src/memoria/atlas/projection.py`
  Purpose: atlas rebuild logic, region matching, subregioning, representatives, bridges, and shapes.
- `src/memoria/atlas/service.py`
  Purpose: read APIs over atlas runs, overview, region detail, and evidence slices.
- `src/memoria/api/atlas.py`
  Purpose: atlas JSON endpoints plus built frontend page route.
- `tests/unit/test_atlas_projection_helpers.py`
  Purpose: unit coverage for region identity reuse, representative ranking, and bridge classification.
- `tests/integration/test_atlas_projection.py`
  Purpose: atlas rebuild and persisted projection verification.
- `tests/integration/test_atlas_api.py`
  Purpose: atlas API and atlas page route verification.
- `frontend/atlas/package.json`
  Purpose: frontend workspace dependencies and scripts.
- `frontend/atlas/tsconfig.json`
  Purpose: TypeScript compiler settings.
- `frontend/atlas/vite.config.ts`
  Purpose: Vite frontend build configuration.
- `frontend/atlas/index.html`
  Purpose: Vite HTML entrypoint.
- `frontend/atlas/src/main.tsx`
  Purpose: React application bootstrap.
- `frontend/atlas/src/App.tsx`
  Purpose: atlas page composition and top-level state wiring.
- `frontend/atlas/src/styles.css`
  Purpose: atlas UI visual system and layout styling.
- `frontend/atlas/src/api/contracts.ts`
  Purpose: frontend atlas response typings.
- `frontend/atlas/src/api/client.ts`
  Purpose: fetch wrappers for atlas endpoints.
- `frontend/atlas/src/state/atlasReducer.ts`
  Purpose: pure selection and drill-down state machine.
- `frontend/atlas/src/state/atlasReducer.test.ts`
  Purpose: reducer coverage for selection and drill-down separation.
- `frontend/atlas/src/lib/evidenceSections.ts`
  Purpose: client-side assembly of representatives, bridges, and long-tail display sections.
- `frontend/atlas/src/lib/evidenceSections.test.ts`
  Purpose: section grouping coverage.
- `frontend/atlas/src/canvas/AtlasCanvas.tsx`
  Purpose: PixiJS scene host and event bridge into React state.
- `frontend/atlas/src/components/AtlasToolbar.tsx`
  Purpose: level-0 and shared search/filter controls.
- `frontend/atlas/src/components/InsightDock.tsx`
  Purpose: persistent right-hand workbench.
- `frontend/atlas/src/components/RegionNavigator.tsx`
  Purpose: breadcrumbs and explicit drill-down controls.
- `frontend/atlas/src/components/EvidenceList.tsx`
  Purpose: virtualized evidence list grouped by representatives, bridges, and long tail.

### Modify

- `.gitignore`
  Purpose: ignore `frontend/atlas/node_modules` and `frontend/atlas/dist`.
- `README.md`
  Purpose: document atlas build, rebuild, and local run commands.
- `src/memoria/api/app.py`
  Purpose: register atlas router and pass optional frontend build path.
- `src/memoria/api/schemas.py`
  Purpose: add atlas response models and request-scoped overlay schemas.
- `src/memoria/admin/cli.py`
  Purpose: add atlas rebuild command.
- `src/memoria/admin/service.py`
  Purpose: expose guarded atlas rebuild service function.
- `src/memoria/domain/models.py`
  Purpose: add atlas ORM models.
- `tests/integration/_screenshot_read_helpers.py`
  Purpose: seed a richer atlas fixture with multiple clusters, bridges, and stable timestamps.
- `tests/integration/test_admin_service.py`
  Purpose: verify atlas rebuild guard and CLI surface.
- `tests/integration/test_schema_tables.py`
  Purpose: verify atlas tables after alembic upgrade.

---

### Task 1: Create The Dedicated Worktree And Capture The Baseline

**Files:**
- Verify only: current checkout and `.worktrees/memoria-semantic-atlas`

- [ ] **Step 1: Create the worktree on a dedicated branch**

Run:

```bash
git worktree add .worktrees/memoria-semantic-atlas -b feat/semantic-atlas main
```

Expected: a new worktree exists at `.worktrees/memoria-semantic-atlas` and is checked out on `feat/semantic-atlas`.

- [ ] **Step 2: Enter the worktree and confirm it is clean**

Run:

```bash
cd .worktrees/memoria-semantic-atlas
git status --short
```

Expected:

```text
[no output]
```

- [ ] **Step 3: Point the worktree at a separate development database**

Run:

```bash
mkdir -p var
printf '%s\n' "MEMORIA_DATABASE_URL=sqlite:///$PWD/var/semantic-atlas.db" > .env.local
```

Expected: `.env.local` exists and points to a SQLite database under the worktree.

- [ ] **Step 4: Run the Python baseline suite from the worktree**

Run:

```bash
uv run pytest -v
```

Expected:

```text
104 passed
```

- [ ] **Step 5: Confirm you are not on `main`**

Run:

```bash
git rev-parse --abbrev-ref HEAD
```

Expected:

```text
feat/semantic-atlas
```

---

### Task 2: Add Atlas Projection Tables And Alembic Migration

**Files:**
- Create: `alembic/versions/20260411_04_add_atlas_projection_tables.py`
- Modify: `src/memoria/domain/models.py`
- Modify: `tests/integration/test_schema_tables.py`

- [ ] **Step 1: Extend the schema test to require atlas tables**

```python
# tests/integration/test_schema_tables.py
assert {
    "atlas_runs",
    "atlas_regions",
    "atlas_items",
    "atlas_edges",
} <= table_names
```

- [ ] **Step 2: Run the schema test and verify it fails**

Run:

```bash
uv run pytest tests/integration/test_schema_tables.py::test_initial_schema_includes_screenshot_knowledge_core_tables -v
```

Expected: FAIL because the new `atlas_*` tables are missing.

- [ ] **Step 3: Add atlas ORM models and the alembic migration**

```python
# src/memoria/domain/models.py
class AtlasRun(Base):
    __tablename__ = "atlas_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    atlas_key: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    source_family: Mapped[str] = mapped_column(String(32), index=True)
    source_count: Mapped[int] = mapped_column(Integer)
    layout_version: Mapped[str] = mapped_column(String(64))
    embedding_type: Mapped[str] = mapped_column(String(64))
    embedding_model: Mapped[str] = mapped_column(String(128))
    embedding_version: Mapped[str] = mapped_column(String(64))
    clustering_method: Mapped[str] = mapped_column(String(128))
    clustering_params_json: Mapped[str] = mapped_column(Text, default="{}")
    random_seed: Mapped[int] = mapped_column(Integer)
    source_snapshot_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    corpus_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, index=True)


class AtlasRegion(Base):
    __tablename__ = "atlas_regions"
    __table_args__ = (
        UniqueConstraint("atlas_run_id", "region_key", name="uq_atlas_region_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    atlas_run_id: Mapped[int] = mapped_column(ForeignKey("atlas_runs.id", ondelete="CASCADE"), index=True)
    region_key: Mapped[str] = mapped_column(String(128), index=True)
    parent_region_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    level: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    x: Mapped[float] = mapped_column(Float, default=0.0)
    y: Mapped[float] = mapped_column(Float, default=0.0)
    region_shape_json: Mapped[str] = mapped_column(Text, default="{}")
    label_anchor_json: Mapped[str] = mapped_column(Text, default="{}")
    item_count: Mapped[int] = mapped_column(Integer)
    top_labels_json: Mapped[str] = mapped_column(Text, default="[]")
    top_apps_json: Mapped[str] = mapped_column(Text, default="[]")
    top_people_json: Mapped[str] = mapped_column(Text, default="[]")
    top_entities_json: Mapped[str] = mapped_column(Text, default="[]")
    representatives_json: Mapped[str] = mapped_column(Text, default="[]")
    bridge_neighbors_json: Mapped[str] = mapped_column(Text, default="[]")
    cohesion_score: Mapped[float] = mapped_column(Float, default=0.0)
    time_start: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    time_end: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)


class AtlasItem(Base):
    __tablename__ = "atlas_items"
    __table_args__ = (
        UniqueConstraint("atlas_run_id", "source_item_id", name="uq_atlas_item_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    atlas_run_id: Mapped[int] = mapped_column(ForeignKey("atlas_runs.id", ondelete="CASCADE"), index=True)
    source_item_id: Mapped[int] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"), index=True)
    region_key: Mapped[str] = mapped_column(String(128), index=True)
    subregion_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    x: Mapped[float] = mapped_column(Float, default=0.0)
    y: Mapped[float] = mapped_column(Float, default=0.0)
    is_representative: Mapped[int] = mapped_column(Integer, default=0)
    representative_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_bridge: Mapped[int] = mapped_column(Integer, default=0)
    bridge_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    secondary_region_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bridge_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_json: Mapped[str] = mapped_column(Text, default="{}")


class AtlasEdge(Base):
    __tablename__ = "atlas_edges"
    __table_args__ = (
        UniqueConstraint(
            "atlas_run_id",
            "source_region_key",
            "target_region_key",
            "edge_type",
            name="uq_atlas_edge_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    atlas_run_id: Mapped[int] = mapped_column(ForeignKey("atlas_runs.id", ondelete="CASCADE"), index=True)
    source_region_key: Mapped[str] = mapped_column(String(128), index=True)
    target_region_key: Mapped[str] = mapped_column(String(128), index=True)
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    edge_type: Mapped[str] = mapped_column(String(32))
```

```python
# alembic/versions/20260411_04_add_atlas_projection_tables.py
def upgrade() -> None:
    op.create_table(
        "atlas_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("atlas_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_family", sa.String(length=32), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("layout_version", sa.String(length=64), nullable=False),
        sa.Column("embedding_type", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_version", sa.String(length=64), nullable=False),
        sa.Column("clustering_method", sa.String(length=128), nullable=False),
        sa.Column("clustering_params_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("random_seed", sa.Integer(), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=128), nullable=True),
        sa.Column("corpus_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_atlas_runs_atlas_key", "atlas_runs", ["atlas_key"])
    op.create_index("ix_atlas_runs_status", "atlas_runs", ["status"])
    op.create_index("ix_atlas_runs_published_at", "atlas_runs", ["published_at"])
    op.create_table(
        "atlas_regions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("atlas_run_id", sa.Integer(), sa.ForeignKey("atlas_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("region_key", sa.String(length=128), nullable=False),
        sa.Column("parent_region_key", sa.String(length=128), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("x", sa.Float(), nullable=False, server_default="0"),
        sa.Column("y", sa.Float(), nullable=False, server_default="0"),
        sa.Column("region_shape_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("label_anchor_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("top_labels_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("top_apps_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("top_people_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("top_entities_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("representatives_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("bridge_neighbors_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("cohesion_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("time_start", sa.DateTime(), nullable=True),
        sa.Column("time_end", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("atlas_run_id", "region_key", name="uq_atlas_region_identity"),
    )
    op.create_table(
        "atlas_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("atlas_run_id", sa.Integer(), sa.ForeignKey("atlas_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_item_id", sa.Integer(), sa.ForeignKey("source_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("region_key", sa.String(length=128), nullable=False),
        sa.Column("subregion_key", sa.String(length=128), nullable=True),
        sa.Column("x", sa.Float(), nullable=False, server_default="0"),
        sa.Column("y", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_representative", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("representative_rank", sa.Integer(), nullable=True),
        sa.Column("is_bridge", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bridge_type", sa.String(length=32), nullable=True),
        sa.Column("secondary_region_key", sa.String(length=128), nullable=True),
        sa.Column("bridge_score", sa.Float(), nullable=True),
        sa.Column("score_json", sa.Text(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("atlas_run_id", "source_item_id", name="uq_atlas_item_identity"),
    )
    op.create_table(
        "atlas_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("atlas_run_id", sa.Integer(), sa.ForeignKey("atlas_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_region_key", sa.String(length=128), nullable=False),
        sa.Column("target_region_key", sa.String(length=128), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="0"),
        sa.Column("edge_type", sa.String(length=32), nullable=False),
        sa.UniqueConstraint(
            "atlas_run_id",
            "source_region_key",
            "target_region_key",
            "edge_type",
            name="uq_atlas_edge_identity",
        ),
    )


def downgrade() -> None:
    op.drop_table("atlas_edges")
    op.drop_table("atlas_items")
    op.drop_table("atlas_regions")
    op.drop_table("atlas_runs")
```

- [ ] **Step 4: Run the migration-backed schema test again**

Run:

```bash
uv run pytest tests/integration/test_schema_tables.py::test_initial_schema_includes_screenshot_knowledge_core_tables -v
```

Expected:

```text
PASSED
```

- [ ] **Step 5: Commit the schema change**

Run:

```bash
git add alembic/versions/20260411_04_add_atlas_projection_tables.py src/memoria/domain/models.py tests/integration/test_schema_tables.py
git commit -m "feat: add atlas projection tables"
```

---

### Task 3: Build Atlas Projection Logic And Seed A Rich Atlas Fixture

**Files:**
- Create: `src/memoria/atlas/__init__.py`
- Create: `src/memoria/atlas/contracts.py`
- Create: `src/memoria/atlas/projection.py`
- Create: `tests/unit/test_atlas_projection_helpers.py`
- Create: `tests/integration/test_atlas_projection.py`
- Modify: `tests/integration/_screenshot_read_helpers.py`

- [ ] **Step 1: Add failing unit tests for region reuse, representative ranking, and bridges**

```python
# tests/unit/test_atlas_projection_helpers.py
from memoria.atlas.projection import classify_bridge
from memoria.atlas.projection import pick_region_key
from memoria.atlas.projection import rank_representative_candidates


def test_pick_region_key_reuses_previous_region_when_overlap_is_high() -> None:
    previous = [{"region_key": "region-telegram", "source_ids": {1, 2, 3, 4}}]
    current = {2, 3, 4, 5}

    assert pick_region_key(previous_regions=previous, current_source_ids=current, fallback_key="region-new") == "region-telegram"


def test_rank_representative_candidates_prefers_semantic_medoid_then_metadata() -> None:
    ranked = rank_representative_candidates(
        [
            {"source_item_id": 10, "distance": 0.10, "has_summary": True, "has_app_hint": True, "object_ref_count": 2, "knowledge_count": 1},
            {"source_item_id": 11, "distance": 0.08, "has_summary": False, "has_app_hint": False, "object_ref_count": 0, "knowledge_count": 0},
        ]
    )

    assert ranked[0] == 10


def test_classify_bridge_marks_internal_when_secondary_subregion_is_close() -> None:
    bridge = classify_bridge(
        primary_region_key="region-chat",
        secondary_region_key="region-chat",
        primary_subregion_key="sub-a",
        secondary_subregion_key="sub-b",
        primary_score=0.81,
        secondary_score=0.76,
    )

    assert bridge["is_bridge"] is True
    assert bridge["bridge_type"] == "internal_bridge"
```

- [ ] **Step 2: Add a failing integration test for rebuilding a complete atlas run**

```python
# tests/integration/test_atlas_projection.py
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.atlas.projection import rebuild_screenshot_atlas_projection
from memoria.domain.models import AtlasEdge
from memoria.domain.models import AtlasItem
from memoria.domain.models import AtlasRegion
from memoria.domain.models import AtlasRun
from tests.integration._screenshot_read_helpers import create_test_engine
from tests.integration._screenshot_read_helpers import seed_atlas_fixture


def test_rebuild_screenshot_atlas_projection_creates_completed_published_run(tmp_path):
    engine = create_test_engine(tmp_path, "atlas-projection.db")
    seed_atlas_fixture(engine, tmp_path)

    with Session(engine) as session:
        rebuild_screenshot_atlas_projection(session, atlas_key="screenshots_atlas_v1")
        session.commit()

    with Session(engine) as session:
        run = session.scalar(
            select(AtlasRun).where(AtlasRun.atlas_key == "screenshots_atlas_v1").order_by(AtlasRun.id.desc())
        )
        assert run is not None
        assert run.status == "completed"
        assert run.completed_at is not None
        assert run.published_at is not None
        assert session.scalar(select(func.count()).select_from(AtlasRegion)) > 0
        assert session.scalar(select(func.count()).select_from(AtlasItem)) > 0
        assert session.scalar(select(func.count()).select_from(AtlasEdge)) > 0
```

- [ ] **Step 3: Run the new atlas tests and verify they fail**

Run:

```bash
uv run pytest tests/unit/test_atlas_projection_helpers.py tests/integration/test_atlas_projection.py -v
```

Expected: FAIL with import errors for `memoria.atlas`.

- [ ] **Step 4: Implement the atlas projection module and richer atlas fixture**

```python
# src/memoria/atlas/contracts.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AtlasProjectionConfig:
    atlas_key: str = "screenshots_atlas_v1"
    layout_version: str = "atlas-layout-v1"
    embedding_type: str = "screenshot_semantic_text"
    embedding_model: str = "hashed-text-v1"
    embedding_version: str = "mvp"
    clustering_method: str = "semantic-map-top-level-v1+greedy-subregions-v1"
    random_seed: int = 42


@dataclass(frozen=True, slots=True)
class AtlasRebuildResult:
    atlas_run_id: int
    region_count: int
    subregion_count: int
    edge_count: int
    item_count: int
    published_at: datetime
```

```python
# src/memoria/atlas/projection.py
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from math import atan2
from math import cos
from math import sin

from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.atlas.contracts import AtlasProjectionConfig
from memoria.atlas.contracts import AtlasRebuildResult
from memoria.domain.models import AtlasEdge
from memoria.domain.models import AtlasItem
from memoria.domain.models import AtlasRegion
from memoria.domain.models import AtlasRun
from memoria.domain.models import AssetInterpretation
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import SemanticCluster
from memoria.domain.models import SemanticMapPoint
from memoria.domain.models import SemanticMapRun
from memoria.domain.models import SourceItem


def rebuild_screenshot_atlas_projection(
    session: Session,
    *,
    atlas_key: str = "screenshots_atlas_v1",
) -> AtlasRebuildResult:
    latest_map_run = session.scalar(
        select(SemanticMapRun).where(SemanticMapRun.map_key == "screenshots_semantic_v1").order_by(SemanticMapRun.id.desc())
    )
    if latest_map_run is None:
        raise RuntimeError("semantic map run not found")

    atlas_run = AtlasRun(
        atlas_key=atlas_key,
        status="building",
        source_family="screenshot",
        source_count=latest_map_run.source_count,
        layout_version="atlas-layout-v1",
        embedding_type="screenshot_semantic_text",
        embedding_model="hashed-text-v1",
        embedding_version="mvp",
        clustering_method="semantic-map-top-level-v1+greedy-subregions-v1",
        clustering_params_json=json.dumps({"top_level_source": "semantic_map", "subregion_merge_min_size": 3}, sort_keys=True),
        random_seed=42,
        source_snapshot_id=str(latest_map_run.id),
        corpus_hash=_compute_corpus_hash(session, latest_map_run.id),
    )
    session.add(atlas_run)
    session.flush()

    top_regions = _project_top_regions(session, atlas_run_id=atlas_run.id, map_run_id=latest_map_run.id)
    edge_count = _persist_region_edges(session, atlas_run_id=atlas_run.id, regions=top_regions)

    published_at = datetime.utcnow()
    atlas_run.status = "completed"
    atlas_run.completed_at = published_at
    atlas_run.published_at = published_at
    session.add(atlas_run)
    session.flush()

    return AtlasRebuildResult(
        atlas_run_id=atlas_run.id,
        region_count=sum(1 for region in top_regions if region["level"] == 0),
        subregion_count=sum(1 for region in top_regions if region["level"] == 1),
        edge_count=edge_count,
        item_count=sum(region["item_count"] for region in top_regions if region["level"] == 0),
        published_at=published_at,
    )


def pick_region_key(*, previous_regions: list[dict[str, object]], current_source_ids: set[int], fallback_key: str) -> str:
    best_key = fallback_key
    best_overlap = 0.0
    for candidate in previous_regions:
        overlap = len(current_source_ids & set(candidate["source_ids"])) / max(len(current_source_ids | set(candidate["source_ids"])), 1)
        if overlap > best_overlap:
            best_overlap = overlap
            best_key = str(candidate["region_key"])
    return best_key if best_overlap >= 0.5 else fallback_key


def rank_representative_candidates(candidates: list[dict[str, object]]) -> list[int]:
    ranked = sorted(
        candidates,
        key=lambda item: (
            float(item["distance"]),
            -int(bool(item["has_summary"])),
            -int(bool(item["has_app_hint"])),
            -int(item["object_ref_count"]),
            -int(item["knowledge_count"]),
        ),
    )
    return [int(item["source_item_id"]) for item in ranked]


def classify_bridge(*, primary_region_key: str, secondary_region_key: str, primary_subregion_key: str | None, secondary_subregion_key: str | None, primary_score: float, secondary_score: float) -> dict[str, object]:
    margin = primary_score - secondary_score
    if secondary_region_key == "" or margin > 0.08:
        return {"is_bridge": False, "bridge_type": None, "bridge_score": None}
    bridge_type = "internal_bridge" if primary_region_key == secondary_region_key and primary_subregion_key != secondary_subregion_key else "external_bridge"
    return {"is_bridge": True, "bridge_type": bridge_type, "bridge_score": round(secondary_score, 4)}
```

```python
# tests/integration/_screenshot_read_helpers.py
@dataclass(frozen=True, slots=True)
class SeededAtlasFixture:
    region_source_ids: dict[str, list[int]]


def seed_atlas_fixture(engine, tmp_path: Path) -> SeededAtlasFixture:
    fixture_specs = [
        ("telegram-chat-1.png", "atlas-telegram-1", b"telegram-1", "mobile-sync", "Telegram Berlin trip planning and ticket booking.", "telegram"),
        ("telegram-chat-2.png", "atlas-telegram-2", b"telegram-2", "mobile-sync", "Telegram hotel shortlist for Berlin trip.", "telegram"),
        ("claude-code-1.png", "atlas-claude-1", b"claude-1", "desktop-sync", "Claude Code cost estimate and token usage summary.", "claude-code"),
        ("claude-code-2.png", "atlas-claude-2", b"claude-2", "desktop-sync", "Claude Code budget planning for agent runs.", "claude-code"),
        ("instagram-fashion-1.png", "atlas-instagram-1", b"instagram-1", "manual-upload", "Instagram outfit inspiration and fashion carousel.", "instagram"),
        ("instagram-fashion-2.png", "atlas-instagram-2", b"instagram-2", "manual-upload", "Instagram fashion reel with styling notes.", "instagram"),
        ("bridge-booking.png", "atlas-bridge-booking", b"bridge-booking", "mobile-sync", "Telegram booking chat with budgeting notes copied into Claude Code.", "telegram"),
    ]

    region_source_ids: dict[str, list[int]] = {"telegram": [], "claude-code": [], "instagram": []}
    for filename, external_id, content, connector_instance_id, ocr_text, app_hint in fixture_specs:
        source_item_id = _seed_interpretation_only(
            engine,
            tmp_path,
            filename=filename,
            external_id=external_id,
            content=content,
            ocr_text=ocr_text,
            connector_instance_id=connector_instance_id,
        )
        key = "telegram" if app_hint == "telegram" else app_hint
        if key in region_source_ids:
            region_source_ids[key].append(source_item_id)

    with Session(engine) as seeded_session:
        from memoria.map.service import rebuild_semantic_map

        rebuild_semantic_map(seeded_session, source_family="screenshot")
        seeded_session.commit()

    return SeededAtlasFixture(region_source_ids=region_source_ids)
```

- [ ] **Step 5: Run the atlas projection tests and commit**

Run:

```bash
uv run pytest tests/unit/test_atlas_projection_helpers.py tests/integration/test_atlas_projection.py -v
git add src/memoria/atlas/__init__.py src/memoria/atlas/contracts.py src/memoria/atlas/projection.py tests/unit/test_atlas_projection_helpers.py tests/integration/test_atlas_projection.py tests/integration/_screenshot_read_helpers.py
git commit -m "feat: add atlas projection rebuild"
```

Expected:

```text
PASSED
```

---

### Task 4: Add The Guarded Atlas Rebuild Admin Command

**Files:**
- Modify: `src/memoria/admin/cli.py`
- Modify: `src/memoria/admin/service.py`
- Modify: `tests/integration/test_admin_service.py`

- [ ] **Step 1: Add failing admin tests for atlas rebuild guarding**

```python
# tests/integration/test_admin_service.py
import pytest
from sqlalchemy.orm import Session

from memoria.ingest.service import IngestScreenshotCommand
from memoria.ingest.service import ingest_screenshot

from memoria.admin.service import rebuild_screenshot_atlas


def test_rebuild_screenshot_atlas_refuses_active_screenshot_runs(tmp_path) -> None:
    engine = _create_engine(tmp_path, "atlas-rebuild-guard.db")
    blob_dir = tmp_path / "blobs"

    with Session(engine) as session:
        ingest_screenshot(
            session,
            IngestScreenshotCommand(
                filename="Screenshot_20240411_101500_ChatGPT.png",
                media_type="image/png",
                content=b"active atlas rebuild run",
                connector_instance_id="manual-upload",
                external_id="active-atlas-run",
                blob_dir=blob_dir,
            ),
        )
        session.commit()

    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="active screenshot pipeline runs: 1"):
            rebuild_screenshot_atlas(session)


def test_admin_cli_rebuild_screenshot_atlas_command_accepts_force_flag(tmp_path, monkeypatch, capsys) -> None:
    from memoria.admin import cli

    _create_engine(tmp_path, "atlas-rebuild-cli.db")

    received = {}

    def _fake_rebuild(session, *, force=False):
        received["force"] = force
        return {"atlas_run_id": 1, "edge_count": 2, "item_count": 7, "published_at": "2026-04-11T12:00:00", "region_count": 3, "subregion_count": 5}

    monkeypatch.setattr(cli, "rebuild_screenshot_atlas", _fake_rebuild)

    exit_code = cli.main(
        [
            "--database-url",
            f"sqlite:///{tmp_path / 'atlas-rebuild-cli.db'}",
            "rebuild-screenshot-atlas",
            "--force",
        ]
    )

    assert exit_code == 0
    assert received["force"] is True
    assert '"atlas_run_id": 1' in capsys.readouterr().out
```

- [ ] **Step 2: Run the admin atlas tests and verify they fail**

Run:

```bash
uv run pytest tests/integration/test_admin_service.py -v
```

Expected: FAIL because the CLI command and service function do not exist yet.

- [ ] **Step 3: Implement the guarded admin service and CLI command**

```python
# src/memoria/admin/service.py
from memoria.atlas.projection import rebuild_screenshot_atlas_projection


def rebuild_screenshot_atlas(session: Session, *, force: bool = False) -> dict[str, object]:
    active_runs = count_running_screenshot_pipeline_runs(session)
    if active_runs > 0 and not force:
        raise RuntimeError(f"active screenshot pipeline runs: {active_runs}")

    result = rebuild_screenshot_atlas_projection(session, atlas_key="screenshots_atlas_v1")
    reconcile_pipeline_runs(session)
    return {
        "atlas_run_id": result.atlas_run_id,
        "edge_count": result.edge_count,
        "item_count": result.item_count,
        "published_at": result.published_at.isoformat(),
        "region_count": result.region_count,
        "subregion_count": result.subregion_count,
    }
```

```python
# src/memoria/admin/cli.py
atlas_parser = subparsers.add_parser("rebuild-screenshot-atlas")
atlas_parser.add_argument("--force", action="store_true")

elif args.command == "rebuild-screenshot-atlas":
    payload = rebuild_screenshot_atlas(session, force=args.force)
    session.commit()
```

- [ ] **Step 4: Re-run the admin service tests**

Run:

```bash
uv run pytest tests/integration/test_admin_service.py -v
```

Expected:

```text
PASSED
```

- [ ] **Step 5: Commit the admin command**

Run:

```bash
git add src/memoria/admin/cli.py src/memoria/admin/service.py tests/integration/test_admin_service.py
git commit -m "admin: add guarded screenshot atlas rebuild"
```

---

### Task 5: Expose Atlas Read APIs And Response Models

**Files:**
- Create: `src/memoria/atlas/service.py`
- Create: `src/memoria/api/atlas.py`
- Create: `tests/integration/test_atlas_api.py`
- Modify: `src/memoria/api/app.py`
- Modify: `src/memoria/api/schemas.py`

- [ ] **Step 1: Add failing API tests for overview, region detail, and evidence slice**

```python
# tests/integration/test_atlas_api.py
from sqlalchemy.orm import Session

from memoria.atlas.projection import rebuild_screenshot_atlas_projection
from tests.integration._screenshot_read_helpers import create_test_client
from tests.integration._screenshot_read_helpers import seed_atlas_fixture


def test_get_atlas_overview_returns_regions_edges_and_overlays(tmp_path):
    client, engine = create_test_client(tmp_path, "atlas-api.db")
    seed_atlas_fixture(engine, tmp_path)
    with Session(engine) as session:
        rebuild_screenshot_atlas_projection(session)
        session.commit()

    response = client.get("/atlas/overview", params={"q": "telegram"})
    payload = response.json()

    assert response.status_code == 200
    assert payload["run"]["atlas_key"] == "screenshots_atlas_v1"
    assert payload["regions"]
    assert "region_overlays" in payload


def test_get_atlas_region_detail_returns_subregions_and_representatives(tmp_path):
    client, engine = create_test_client(tmp_path, "atlas-region-detail.db")
    seed_atlas_fixture(engine, tmp_path)
    with Session(engine) as session:
        rebuild_screenshot_atlas_projection(session)
        session.commit()

    overview = client.get("/atlas/overview").json()
    region_key = overview["regions"][0]["region_key"]

    response = client.get(f"/atlas/regions/{region_key}")
    payload = response.json()

    assert response.status_code == 200
    assert payload["region"]["region_key"] == region_key
    assert payload["subregions"]
    assert payload["representatives"]


def test_get_atlas_evidence_slice_splits_representatives_bridges_and_long_tail(tmp_path):
    client, engine = create_test_client(tmp_path, "atlas-evidence.db")
    seed_atlas_fixture(engine, tmp_path)
    with Session(engine) as session:
        rebuild_screenshot_atlas_projection(session)
        session.commit()

    overview = client.get("/atlas/overview").json()
    region_key = overview["regions"][0]["region_key"]

    response = client.get(f"/atlas/regions/{region_key}/evidence")
    payload = response.json()

    assert response.status_code == 200
    assert "representatives" in payload
    assert "bridges" in payload
    assert "long_tail_page" in payload
```

- [ ] **Step 2: Run the atlas API tests and verify they fail**

Run:

```bash
uv run pytest tests/integration/test_atlas_api.py -v
```

Expected: FAIL because `/atlas/*` JSON endpoints do not exist.

- [ ] **Step 3: Implement atlas contracts, read service, and router**

```python
# src/memoria/api/schemas.py
class AtlasRunResponse(BaseModel):
    atlas_run_id: int
    atlas_key: str
    status: str
    generated_at: datetime
    completed_at: datetime | None
    published_at: datetime | None
    source_count: int
    layout_version: str
    embedding_type: str
    embedding_model: str
    embedding_version: str
    clustering_method: str
    random_seed: int


class AtlasRegionOverlayResponse(BaseModel):
    region_key: str
    match_count: int


class AtlasShapePointResponse(BaseModel):
    x: float
    y: float


class AtlasRegionShapeResponse(BaseModel):
    kind: str
    polygons: list[list[AtlasShapePointResponse]]


class AtlasRegionResponse(BaseModel):
    atlas_run_id: int
    region_key: str
    parent_region_key: str | None
    level: int
    title: str
    x: float
    y: float
    region_shape: AtlasRegionShapeResponse
    item_count: int
    top_labels: list[str]
    top_apps: list[str]
    top_people: list[str]
    top_entities: list[str]
    time_start: datetime | None
    time_end: datetime | None
    cohesion_score: float


class AtlasItemResponse(BaseModel):
    atlas_run_id: int
    source_item_id: int
    region_key: str
    subregion_key: str | None
    x: float
    y: float
    semantic_summary: str | None
    app_hint: str | None
    observed_at: datetime | None
    object_refs: list[str]
    is_representative: bool
    representative_rank: int | None
    is_bridge: bool
    bridge_type: str | None
    secondary_region_key: str | None
    bridge_score: float | None
    screenshot_detail_url: str


class AtlasEvidenceSectionResponse(BaseModel):
    total_count: int
    items: list[AtlasItemResponse]


class AtlasItemPageResponse(BaseModel):
    total_count: int
    offset: int
    limit: int
    items: list[AtlasItemResponse]


class AtlasOverviewResponse(BaseModel):
    run: AtlasRunResponse
    regions: list[AtlasRegionResponse]
    region_overlays: list[AtlasRegionOverlayResponse]
    edges: list[dict[str, object]]
    active_filters: dict[str, object]


class AtlasRegionDetailResponse(BaseModel):
    run: AtlasRunResponse
    region: AtlasRegionResponse
    region_overlay: AtlasRegionOverlayResponse
    subregions: list[AtlasRegionResponse]
    subregion_overlays: list[AtlasRegionOverlayResponse]
    representatives: list[AtlasItemResponse]
    active_filters: dict[str, object]


class AtlasEvidenceSliceResponse(BaseModel):
    run: AtlasRunResponse
    active_region_key: str
    active_subregion_key: str | None
    representatives: AtlasEvidenceSectionResponse
    bridges: AtlasEvidenceSectionResponse
    long_tail_page: AtlasItemPageResponse
    active_filters: dict[str, object]
```

```python
# src/memoria/api/atlas.py
from fastapi import APIRouter
from fastapi import HTTPException
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from memoria.atlas.service import AtlasFilters
from memoria.atlas.service import get_atlas_evidence_slice
from memoria.atlas.service import get_atlas_overview
from memoria.atlas.service import get_atlas_region_detail


def create_atlas_router(*, engine: Engine) -> APIRouter:
    router = APIRouter()

    @router.get("/atlas/overview", response_model=AtlasOverviewResponse)
    def atlas_overview_endpoint(q: str | None = None, app_hint: str | None = None, topic_slug: str | None = None, person_slug: str | None = None, observed_from: datetime | None = None, observed_to: datetime | None = None) -> dict[str, object]:
        filters = AtlasFilters(q=q, app_hint=app_hint, topic_slug=topic_slug, person_slug=person_slug, observed_from=observed_from, observed_to=observed_to)
        with Session(engine) as session:
            return get_atlas_overview(session, filters=filters)

    @router.get("/atlas/regions/{region_key}", response_model=AtlasRegionDetailResponse)
    def atlas_region_detail_endpoint(region_key: str, q: str | None = None) -> dict[str, object]:
        with Session(engine) as session:
            payload = get_atlas_region_detail(session, region_key=region_key, filters=AtlasFilters(q=q))
        if payload is None:
            raise HTTPException(status_code=404, detail="atlas region not found")
        return payload

    @router.get("/atlas/regions/{region_key}/evidence", response_model=AtlasEvidenceSliceResponse)
    def atlas_evidence_endpoint(region_key: str, subregion_key: str | None = None, q: str | None = None, offset: int = 0, limit: int = 50) -> dict[str, object]:
        with Session(engine) as session:
            payload = get_atlas_evidence_slice(
                session,
                region_key=region_key,
                subregion_key=subregion_key,
                filters=AtlasFilters(q=q),
                offset=offset,
                limit=limit,
            )
        if payload is None:
            raise HTTPException(status_code=404, detail="atlas region not found")
        return payload

    return router
```

```python
# src/memoria/api/app.py
from memoria.api.atlas import create_atlas_router

app.include_router(create_atlas_router(engine=engine))
```

- [ ] **Step 4: Run the atlas API tests**

Run:

```bash
uv run pytest tests/integration/test_atlas_api.py -v
```

Expected:

```text
PASSED
```

- [ ] **Step 5: Commit the atlas backend API**

Run:

```bash
git add src/memoria/atlas/service.py src/memoria/api/atlas.py src/memoria/api/app.py src/memoria/api/schemas.py tests/integration/test_atlas_api.py
git commit -m "api: add atlas read endpoints"
```

---

### Task 6: Scaffold The Frontend Workspace And Ignore Local Build Artifacts

**Files:**
- Create: `frontend/atlas/package.json`
- Create: `frontend/atlas/tsconfig.json`
- Create: `frontend/atlas/vite.config.ts`
- Create: `frontend/atlas/index.html`
- Create: `frontend/atlas/src/main.tsx`
- Create: `frontend/atlas/src/App.tsx`
- Create: `frontend/atlas/src/styles.css`
- Modify: `.gitignore`

- [ ] **Step 1: Add frontend ignores and the Vite workspace files**

```gitignore
# .gitignore
frontend/atlas/node_modules/
frontend/atlas/dist/
```

```json
// frontend/atlas/package.json
{
  "name": "memoria-semantic-atlas",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "@tanstack/react-virtual": "^3.13.12",
    "d3-array": "^3.2.4",
    "d3-polygon": "^3.0.1",
    "d3-scale": "^4.0.2",
    "pixi.js": "^8.10.1",
    "react": "^19.1.0",
    "react-dom": "^19.1.0"
  },
  "devDependencies": {
    "@types/react": "^19.1.10",
    "@types/react-dom": "^19.1.7",
    "@vitejs/plugin-react": "^5.0.0",
    "typescript": "^5.9.2",
    "vite": "^7.1.3",
    "vitest": "^3.2.4"
  }
}
```

```tsx
// frontend/atlas/src/App.tsx
export function App() {
  return (
    <main className="app-shell">
      <section className="atlas-panel">Semantic Atlas loading…</section>
      <aside className="dock-panel">Atlas workbench</aside>
    </main>
  );
}
```

- [ ] **Step 2: Install the frontend dependencies**

Run:

```bash
npm --prefix frontend/atlas install
```

Expected: `package-lock.json` is created under `frontend/atlas/`.

- [ ] **Step 3: Build the empty scaffold and verify the toolchain works**

Run:

```bash
npm --prefix frontend/atlas run build
```

Expected:

```text
vite v
✓ built in
```

- [ ] **Step 4: Verify the Python suite still passes after adding the workspace**

Run:

```bash
uv run pytest tests/integration/test_schema_tables.py tests/integration/test_atlas_api.py -v
```

Expected:

```text
PASSED
```

- [ ] **Step 5: Commit the frontend scaffold**

Run:

```bash
git add .gitignore frontend/atlas/package.json frontend/atlas/package-lock.json frontend/atlas/tsconfig.json frontend/atlas/vite.config.ts frontend/atlas/index.html frontend/atlas/src/main.tsx frontend/atlas/src/App.tsx frontend/atlas/src/styles.css
git commit -m "feat: scaffold semantic atlas frontend workspace"
```

---

### Task 7: Implement Level-0 Atlas Overview State, Filters, And Page Hosting

**Files:**
- Create: `frontend/atlas/src/api/contracts.ts`
- Create: `frontend/atlas/src/api/client.ts`
- Create: `frontend/atlas/src/state/atlasReducer.ts`
- Create: `frontend/atlas/src/state/atlasReducer.test.ts`
- Create: `frontend/atlas/src/components/AtlasToolbar.tsx`
- Create: `frontend/atlas/src/components/InsightDock.tsx`
- Create: `frontend/atlas/src/canvas/AtlasCanvas.tsx`
- Modify: `src/memoria/api/app.py`
- Modify: `src/memoria/api/atlas.py`
- Modify: `frontend/atlas/src/App.tsx`
- Modify: `frontend/atlas/src/styles.css`
- Modify: `tests/integration/test_atlas_api.py`

- [ ] **Step 1: Add failing tests for state transitions and atlas page hosting**

```ts
// frontend/atlas/src/state/atlasReducer.test.ts
import { describe, expect, it } from "vitest";

import { atlasReducer, initialAtlasState } from "./atlasReducer";


describe("atlasReducer", () => {
  it("keeps selection separate from drill-down", () => {
    const selected = atlasReducer(initialAtlasState, { type: "region-selected", regionKey: "region-telegram" });
    expect(selected.level).toBe(0);
    expect(selected.selectedRegionKey).toBe("region-telegram");

    const drilled = atlasReducer(selected, { type: "region-drilled" });
    expect(drilled.level).toBe(1);
  });
});
```

```python
# tests/integration/test_atlas_api.py
from fastapi.testclient import TestClient

from memoria.api.app import create_app

def test_atlas_page_returns_build_missing_fallback_when_no_frontend_dist(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'atlas.db'}", blob_dir=tmp_path / "blobs", atlas_frontend_dist=tmp_path / "missing-dist")
    client = TestClient(app)

    response = client.get("/atlas")

    assert response.status_code == 200
    assert "frontend build missing" in response.text.lower()
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
npm --prefix frontend/atlas run test
uv run pytest tests/integration/test_atlas_api.py::test_atlas_page_returns_build_missing_fallback_when_no_frontend_dist -v
```

Expected: FAIL because the reducer does not exist and `/atlas` page hosting is not implemented.

- [ ] **Step 3: Implement the level-0 state machine, API client, toolbar, dock, Pixi host, and atlas page route**

```ts
// frontend/atlas/src/state/atlasReducer.ts
export type AtlasLevel = 0 | 1 | 2;

export type AtlasState = {
  level: AtlasLevel;
  selectedRegionKey: string | null;
  selectedSubregionKey: string | null;
  selectedItemId: number | null;
  query: string;
  appHint: string;
};

export const initialAtlasState: AtlasState = {
  level: 0,
  selectedRegionKey: null,
  selectedSubregionKey: null,
  selectedItemId: null,
  query: "",
  appHint: "",
};

export type AtlasAction =
  | { type: "region-selected"; regionKey: string }
  | { type: "region-drilled" }
  | { type: "query-updated"; query: string }
  | { type: "app-hint-updated"; appHint: string };

export function atlasReducer(state: AtlasState, action: AtlasAction): AtlasState {
  switch (action.type) {
    case "region-selected":
      return { ...state, selectedRegionKey: action.regionKey, selectedSubregionKey: null, selectedItemId: null };
    case "region-drilled":
      return state.selectedRegionKey ? { ...state, level: 1 } : state;
    case "query-updated":
      return { ...state, query: action.query };
    case "app-hint-updated":
      return { ...state, appHint: action.appHint };
    default:
      return state;
  }
}
```

```tsx
// frontend/atlas/src/App.tsx
import { useEffect, useReducer, useState } from "react";

import { fetchAtlasOverview } from "./api/client";
import { AtlasCanvas } from "./canvas/AtlasCanvas";
import { AtlasToolbar } from "./components/AtlasToolbar";
import { InsightDock } from "./components/InsightDock";
import { atlasReducer, initialAtlasState } from "./state/atlasReducer";


export function App() {
  const [state, dispatch] = useReducer(atlasReducer, initialAtlasState);
  const [overview, setOverview] = useState(null);

  useEffect(() => {
    fetchAtlasOverview({ q: state.query, app_hint: state.appHint }).then(setOverview);
  }, [state.query, state.appHint]);

  return (
    <main className="app-shell">
      <section className="atlas-panel">
        <AtlasToolbar
          query={state.query}
          appHint={state.appHint}
          onQueryChange={(query) => dispatch({ type: "query-updated", query })}
          onAppHintChange={(appHint) => dispatch({ type: "app-hint-updated", appHint })}
        />
        <AtlasCanvas
          level={state.level}
          overview={overview}
          selectedRegionKey={state.selectedRegionKey}
          onRegionSelect={(regionKey) => dispatch({ type: "region-selected", regionKey })}
        />
      </section>
      <InsightDock
        level={state.level}
        overview={overview}
        selectedRegionKey={state.selectedRegionKey}
        onDrillDown={() => dispatch({ type: "region-drilled" })}
      />
    </main>
  );
}
```

```python
# src/memoria/api/atlas.py
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
from pathlib import Path


def create_atlas_router(*, engine: Engine, frontend_dist: Path | None = None) -> APIRouter:
    router = APIRouter()
    resolved_frontend_dist = frontend_dist

    @router.get("/atlas", response_class=HTMLResponse)
    def atlas_page() -> HTMLResponse | FileResponse:
        if resolved_frontend_dist is None or not (resolved_frontend_dist / "index.html").exists():
            return HTMLResponse("<!doctype html><html><body><p>Atlas frontend build missing.</p></body></html>")
        return FileResponse(resolved_frontend_dist / "index.html")
```

```python
# src/memoria/api/app.py
from fastapi.staticfiles import StaticFiles


def create_app(
    *,
    database_url: str | None = None,
    blob_dir: Path,
    runtime_settings: RuntimeSettings | None = None,
    ocr_engine: OcrEngine | None = None,
    vision_engine: VisionEngine | None = None,
    atlas_frontend_dist: Path | None = None,
) -> FastAPI:
    app.include_router(create_atlas_router(engine=engine, frontend_dist=atlas_frontend_dist))
    if atlas_frontend_dist is not None and (atlas_frontend_dist / "assets").exists():
        app.mount("/atlas/assets", StaticFiles(directory=atlas_frontend_dist / "assets"), name="atlas-assets")
```

- [ ] **Step 4: Run the frontend tests, atlas page test, and build**

Run:

```bash
npm --prefix frontend/atlas run test
npm --prefix frontend/atlas run build
uv run pytest tests/integration/test_atlas_api.py -v
```

Expected:

```text
PASSED
```

- [ ] **Step 5: Commit the level-0 atlas shell**

Run:

```bash
git add frontend/atlas/src/api/contracts.ts frontend/atlas/src/api/client.ts frontend/atlas/src/state/atlasReducer.ts frontend/atlas/src/state/atlasReducer.test.ts frontend/atlas/src/components/AtlasToolbar.tsx frontend/atlas/src/components/InsightDock.tsx frontend/atlas/src/canvas/AtlasCanvas.tsx frontend/atlas/src/App.tsx frontend/atlas/src/styles.css src/memoria/api/app.py src/memoria/api/atlas.py tests/integration/test_atlas_api.py
git commit -m "feat: add atlas overview ui shell"
```

---

### Task 8: Implement Region Focus, Evidence Focus, And Virtualized Evidence Sections

**Files:**
- Create: `frontend/atlas/src/lib/evidenceSections.ts`
- Create: `frontend/atlas/src/lib/evidenceSections.test.ts`
- Create: `frontend/atlas/src/components/RegionNavigator.tsx`
- Create: `frontend/atlas/src/components/EvidenceList.tsx`
- Modify: `frontend/atlas/src/App.tsx`
- Modify: `frontend/atlas/src/canvas/AtlasCanvas.tsx`
- Modify: `frontend/atlas/src/components/InsightDock.tsx`
- Modify: `frontend/atlas/src/state/atlasReducer.ts`

- [ ] **Step 1: Add failing tests for evidence grouping and subregion drill-down**

```ts
// frontend/atlas/src/lib/evidenceSections.test.ts
import { describe, expect, it } from "vitest";

import { buildEvidenceSections } from "./evidenceSections";


describe("buildEvidenceSections", () => {
  it("keeps representatives and bridges out of long tail", () => {
    const sections = buildEvidenceSections({
      representatives: [{ source_item_id: 1 }],
      bridges: [{ source_item_id: 2 }],
      longTailPage: { items: [{ source_item_id: 1 }, { source_item_id: 2 }, { source_item_id: 3 }] },
    });

    expect(sections.longTail.items.map((item) => item.source_item_id)).toEqual([3]);
  });
});
```

```ts
// frontend/atlas/src/state/atlasReducer.test.ts
it("requires explicit drill-down for subregions as well", () => {
  const levelOne = {
    ...initialAtlasState,
    level: 1 as const,
    selectedRegionKey: "region-telegram",
  };
  const selected = atlasReducer(levelOne, { type: "subregion-selected", subregionKey: "sub-bookings" });
  expect(selected.level).toBe(1);
  const drilled = atlasReducer(selected, { type: "subregion-drilled" });
  expect(drilled.level).toBe(2);
});
```

- [ ] **Step 2: Run the frontend tests and verify they fail**

Run:

```bash
npm --prefix frontend/atlas run test
```

Expected: FAIL because `buildEvidenceSections` and subregion drill-down actions are missing.

- [ ] **Step 3: Implement evidence grouping, deeper reducer actions, and dock/canvas components**

```ts
// frontend/atlas/src/lib/evidenceSections.ts
export function buildEvidenceSections(input: {
  representatives: Array<{ source_item_id: number }>;
  bridges: Array<{ source_item_id: number }>;
  longTailPage: { items: Array<{ source_item_id: number }> };
}) {
  const excluded = new Set([
    ...input.representatives.map((item) => item.source_item_id),
    ...input.bridges.map((item) => item.source_item_id),
  ]);

  return {
    representatives: { items: input.representatives },
    bridges: { items: input.bridges },
    longTail: {
      items: input.longTailPage.items.filter((item) => !excluded.has(item.source_item_id)),
    },
  };
}
```

```ts
// frontend/atlas/src/state/atlasReducer.ts
export type AtlasAction =
  | { type: "region-selected"; regionKey: string }
  | { type: "region-drilled" }
  | { type: "subregion-selected"; subregionKey: string }
  | { type: "subregion-drilled" }
  | { type: "item-selected"; sourceItemId: number }
  | { type: "navigate-up"; level: 0 | 1 }
  | { type: "query-updated"; query: string }
  | { type: "app-hint-updated"; appHint: string };

export function atlasReducer(state: AtlasState, action: AtlasAction): AtlasState {
  switch (action.type) {
    case "region-selected":
      return { ...state, selectedRegionKey: action.regionKey, selectedSubregionKey: null, selectedItemId: null };
    case "region-drilled":
      return state.selectedRegionKey ? { ...state, level: 1 } : state;
    case "subregion-selected":
      return { ...state, selectedSubregionKey: action.subregionKey, selectedItemId: null };
    case "subregion-drilled":
      return state.selectedSubregionKey ? { ...state, level: 2 } : state;
    case "item-selected":
      return { ...state, selectedItemId: action.sourceItemId };
    case "navigate-up":
      return action.level === 0
        ? { ...state, level: 0, selectedSubregionKey: null, selectedItemId: null }
        : { ...state, level: 1, selectedItemId: null };
    case "query-updated":
      return { ...state, query: action.query };
    case "app-hint-updated":
      return { ...state, appHint: action.appHint };
    default:
      return state;
  }
}
```

```tsx
// frontend/atlas/src/components/EvidenceList.tsx
import { useVirtualizer } from "@tanstack/react-virtual";
import { useRef } from "react";


export function EvidenceList({ representatives, bridges, longTail, onSelectItem }) {
  const parentRef = useRef<HTMLDivElement | null>(null);
  const virtualizer = useVirtualizer({
    count: longTail.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 80,
  });

  return (
    <div className="evidence-list">
      <section>
        <h3>Representatives</h3>
        {representatives.map((item) => (
          <button key={item.source_item_id} onClick={() => onSelectItem(item.source_item_id)}>
            {item.semantic_summary}
          </button>
        ))}
      </section>
      <section>
        <h3>Bridges</h3>
        {bridges.map((item) => (
          <button key={item.source_item_id} onClick={() => onSelectItem(item.source_item_id)}>
            {item.semantic_summary}
          </button>
        ))}
      </section>
      <section>
        <h3>All Items</h3>
        <div ref={parentRef} className="virtual-list">
          <div style={{ height: `${virtualizer.getTotalSize()}px`, position: "relative" }}>
            {virtualizer.getVirtualItems().map((virtualRow) => {
              const item = longTail[virtualRow.index];
              return (
                <button
                  key={item.source_item_id}
                  className="evidence-row"
                  onClick={() => onSelectItem(item.source_item_id)}
                  style={{ position: "absolute", transform: `translateY(${virtualRow.start}px)` }}
                >
                  {item.semantic_summary}
                </button>
              );
            })}
          </div>
        </div>
      </section>
    </div>
  );
}
```

```tsx
// frontend/atlas/src/components/InsightDock.tsx
import { EvidenceList } from "./EvidenceList";
import { RegionNavigator } from "./RegionNavigator";


export function InsightDock({ level, regionDetail, evidenceSlice, onRegionDrillDown, onSubregionDrillDown, onSelectItem, onNavigateUp }) {
  return (
    <aside className="dock-panel">
      <RegionNavigator level={level} regionDetail={regionDetail} onRegionDrillDown={onRegionDrillDown} onSubregionDrillDown={onSubregionDrillDown} onNavigateUp={onNavigateUp} />
      {level === 2 && evidenceSlice ? (
        <EvidenceList
          representatives={evidenceSlice.representatives.items}
          bridges={evidenceSlice.bridges.items}
          longTail={evidenceSlice.long_tail_page.items}
          onSelectItem={onSelectItem}
        />
      ) : null}
    </aside>
  );
}
```

- [ ] **Step 4: Run the frontend tests and build again**

Run:

```bash
npm --prefix frontend/atlas run test
npm --prefix frontend/atlas run build
```

Expected:

```text
PASSED
```

- [ ] **Step 5: Commit the deeper atlas UX**

Run:

```bash
git add frontend/atlas/src/lib/evidenceSections.ts frontend/atlas/src/lib/evidenceSections.test.ts frontend/atlas/src/components/RegionNavigator.tsx frontend/atlas/src/components/EvidenceList.tsx frontend/atlas/src/App.tsx frontend/atlas/src/canvas/AtlasCanvas.tsx frontend/atlas/src/components/InsightDock.tsx frontend/atlas/src/state/atlasReducer.ts frontend/atlas/src/state/atlasReducer.test.ts
git commit -m "feat: add atlas region and evidence drilldown"
```

---

### Task 9: Document The Workflow And Run Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add atlas build and rebuild instructions to the README**

````md
## Semantic Atlas

Rebuild atlas projection:

```bash
uv run memoria-admin --database-url sqlite:///data/memoria.db rebuild-screenshot-atlas
```

Build atlas frontend:

```bash
npm --prefix frontend/atlas install
npm --prefix frontend/atlas run build
```

Run API app with atlas frontend dist:

```python
from pathlib import Path

from memoria.api.app import create_app

app = create_app(
    database_url="sqlite:///data/memoria.db",
    blob_dir=Path("var/blobs"),
    atlas_frontend_dist=Path("frontend/atlas/dist"),
)
```
````

- [ ] **Step 2: Verify the migration on a clean database**

Run:

```bash
rm -f var/semantic-atlas.db
uv run alembic upgrade head
```

Expected:

```text
INFO  [alembic.runtime.migration] Running upgrade
```

- [ ] **Step 3: Run the full backend and frontend verification suite**

Run:

```bash
uv run pytest -v
npm --prefix frontend/atlas run test
npm --prefix frontend/atlas run build
```

Expected:

```text
backend tests passed
frontend tests passed
vite build completed
```

- [ ] **Step 4: Smoke-check atlas routes in the app object**

Run:

```bash
uv run python -c "from pathlib import Path; from memoria.api.app import create_app; app = create_app(database_url='sqlite:///var/semantic-atlas.db', blob_dir=Path('var/blobs'), atlas_frontend_dist=Path('frontend/atlas/dist')); print(sorted(route.path for route in app.routes if route.path.startswith('/atlas')))"
```

Expected:

```text
['/atlas', '/atlas/overview', '/atlas/regions/{region_key}', '/atlas/regions/{region_key}/evidence']
```

- [ ] **Step 5: Commit the docs and final verification state**

Run:

```bash
git add README.md
git commit -m "docs: add semantic atlas development workflow"
```

---

## Self-Review

### Spec Coverage

- Atlas read model location: covered by Task 2 schema work and Task 3 `src/memoria/atlas/`.
- MVP rebuild policy and lifecycle: covered by Task 3 projection lifecycle and Task 4 admin rebuild command.
- Embedding basis `hashed-text-v1` and semantic map reuse: covered by Task 3 projection config and rebuild logic.
- Coordinate contract: covered by Task 3 atlas item and region persistence plus Pixi world-space rendering in Tasks 7 and 8.
- `AtlasRun` lifecycle and publish semantics: covered by Task 2 table design and Task 3 rebuild lifecycle.
- Persisted vs request-scoped counts: covered by Task 5 response models with overlays separate from persisted region rows.
- `AtlasEvidenceSlice` split into `representatives`, `bridges`, and `long_tail_page`: covered by Task 5 API models and Task 8 frontend grouping.
- Level 0 search/filter and persistent dock: covered by Tasks 5 and 7.
- Level 1/2 drill-down and EvidenceList: covered by Task 8.
- React + TypeScript + PixiJS + TanStack Virtual stack: covered by Tasks 6, 7, and 8.

### Placeholder Scan

- No `TBD`, `TODO`, or “similar to previous task” placeholders remain.
- Every task names concrete files, commands, and expected results.
- Every code-changing task includes explicit snippets.

### Type Consistency

- Backend naming consistently uses `atlas_run_id`, `region_key`, `subregion_key`, `representatives`, `bridges`, and `long_tail_page`.
- Frontend naming matches the API contract and keeps selection separate from drill-down.
- Atlas rebuild command is consistently named `rebuild-screenshot-atlas`.
