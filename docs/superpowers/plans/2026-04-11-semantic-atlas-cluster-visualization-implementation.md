# Semantic Atlas Cluster Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first screenshot semantic atlas as a dedicated backend projection plus a React workbench that renders a stable, cluster-first atlas with explicit drill-down from regions to subregions to screenshot evidence.

**Architecture:** Keep ingest, OCR, vision, absorb, screenshots read APIs, and the existing semantic map intact. Add a new atlas projection under `src/memoria/atlas/`, persist it in dedicated `atlas_*` tables, expose read-only atlas endpoints under `/atlas/*`, and serve a separately built React + PixiJS frontend that consumes those atlas endpoints without recomputing clustering in the browser.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.x, Alembic, SQLite, pytest, React, TypeScript, Vite, PixiJS v8, TanStack Virtual, Vitest, helper-only d3 modules

---

## Current Status

Fresh verification in the restart worktree:

```bash
uv run pytest -v
```

Observed before writing this plan:

```text
104 passed in 6.11s
```

Implementation constraints confirmed against the repo:

- atlas tables do not exist yet, so this feature requires a migration;
- the repo already has screenshot filters, knowledge read APIs, and semantic map APIs;
- the repo does not have an existing React/Vite frontend workspace;
- runtime settings load the repo-local `.env`;
- the current `/map` HTML page is a simple server-rendered shell, not a reusable frontend app;
- atlas rebuilds must follow the same operational guard style as `rebuild-screenshot-derived-data`.

## Repository Roots

- Main checkout: `/home/xai/DEV/memoria`
- Restart worktree: `/home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart`
- Branch for this restart plan: `feat/semantic-atlas-restart-plan`
- Plan file in this worktree: `docs/superpowers/plans/2026-04-11-semantic-atlas-cluster-visualization-implementation.md`

## File Structure

### Existing files to follow

- `src/memoria/domain/models.py`
  Existing ORM table definitions and naming style.
- `src/memoria/map/service.py`
  Current screenshot semantic map rebuild/read logic; atlas should layer on top of this, not replace it.
- `src/memoria/admin/service.py`
  Existing guard pattern for rebuilds when screenshot pipeline runs are active.
- `src/memoria/admin/cli.py`
  Existing Typer-like CLI entrypoint and JSON output style.
- `src/memoria/api/app.py`
  FastAPI wiring and router registration.
- `src/memoria/api/schemas.py`
  Existing Pydantic response schemas.
- `src/memoria/screenshots/read/filters.py`
  Shared screenshot filter contract that atlas should reuse.
- `src/memoria/search/embeddings.py`
  Existing MVP embedding basis: `screenshot_semantic_text` with `hashed-text-v1`, `96d`.
- `tests/integration/_screenshot_read_helpers.py`
  Existing screenshot fixture helpers to extend for atlas data.

### Files to create

- `alembic/versions/20260411_04_add_atlas_projection_tables.py`
- `src/memoria/atlas/__init__.py`
- `src/memoria/atlas/contracts.py`
- `src/memoria/atlas/projection.py`
- `src/memoria/atlas/service.py`
- `src/memoria/api/atlas.py`
- `tests/unit/test_atlas_projection_helpers.py`
- `tests/integration/test_atlas_projection.py`
- `tests/integration/test_atlas_api.py`
- `frontend/atlas/package.json`
- `frontend/atlas/package-lock.json`
- `frontend/atlas/tsconfig.json`
- `frontend/atlas/vite.config.ts`
- `frontend/atlas/index.html`
- `frontend/atlas/src/main.tsx`
- `frontend/atlas/src/App.tsx`
- `frontend/atlas/src/styles.css`
- `frontend/atlas/src/api/client.ts`
- `frontend/atlas/src/api/contracts.ts`
- `frontend/atlas/src/state/atlasReducer.ts`
- `frontend/atlas/src/state/atlasReducer.test.ts`
- `frontend/atlas/src/lib/evidenceSections.ts`
- `frontend/atlas/src/lib/evidenceSections.test.ts`
- `frontend/atlas/src/canvas/AtlasCanvas.tsx`
- `frontend/atlas/src/components/AtlasToolbar.tsx`
- `frontend/atlas/src/components/InsightDock.tsx`
- `frontend/atlas/src/components/RegionNavigator.tsx`
- `frontend/atlas/src/components/EvidenceList.tsx`

### Files to modify

- `.gitignore`
- `README.md`
- `src/memoria/domain/models.py`
- `src/memoria/admin/service.py`
- `src/memoria/admin/cli.py`
- `src/memoria/api/app.py`
- `src/memoria/api/schemas.py`
- `tests/integration/_screenshot_read_helpers.py`
- `tests/integration/test_admin_service.py`
- `tests/integration/test_schema_tables.py`

---

### Task 1: Add Atlas Tables, ORM Models, And Projection Contracts

**Files:**
- Create: `alembic/versions/20260411_04_add_atlas_projection_tables.py`
- Create: `src/memoria/atlas/__init__.py`
- Create: `src/memoria/atlas/contracts.py`
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

Expected:

```text
FAILED tests/integration/test_schema_tables.py::test_initial_schema_includes_screenshot_knowledge_core_tables
```

- [ ] **Step 3: Add atlas ORM models and the migration**

```python
# src/memoria/domain/models.py
class AtlasRun(Base):
    __tablename__ = "atlas_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    atlas_key: Mapped[str] = mapped_column(String(120), index=True)
    source_family: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default="completed")
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    source_snapshot_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    corpus_hash: Mapped[str | None] = mapped_column(String(120), nullable=True)
    embedding_type: Mapped[str] = mapped_column(String(120))
    embedding_model: Mapped[str] = mapped_column(String(120))
    embedding_version: Mapped[str] = mapped_column(String(120))
    clustering_method: Mapped[str] = mapped_column(String(120))
    clustering_params_json: Mapped[str] = mapped_column(Text, default="{}")
    random_seed: Mapped[int] = mapped_column(Integer, default=42)
    layout_version: Mapped[str] = mapped_column(String(120), default="atlas-world-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AtlasRegion(Base):
    __tablename__ = "atlas_regions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    atlas_run_id: Mapped[int] = mapped_column(ForeignKey("atlas_runs.id", ondelete="CASCADE"), index=True)
    region_key: Mapped[str] = mapped_column(String(160), index=True)
    parent_region_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    level: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(240))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    label_x: Mapped[float] = mapped_column(Float)
    label_y: Mapped[float] = mapped_column(Float)
    region_shape_json: Mapped[str] = mapped_column(Text, default="[]")
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    top_labels_json: Mapped[str] = mapped_column(Text, default="[]")
    top_apps_json: Mapped[str] = mapped_column(Text, default="[]")
    top_people_json: Mapped[str] = mapped_column(Text, default="[]")
    top_entities_json: Mapped[str] = mapped_column(Text, default="[]")
    time_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    time_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    representatives_json: Mapped[str] = mapped_column(Text, default="[]")
    bridge_neighbors_json: Mapped[str] = mapped_column(Text, default="[]")
    cohesion_score: Mapped[float] = mapped_column(Float, default=0.0)
```

```python
# alembic/versions/20260411_04_add_atlas_projection_tables.py
def upgrade() -> None:
    op.create_table(
        "atlas_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("atlas_key", sa.String(length=120), nullable=False),
        sa.Column("source_family", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=120), nullable=True),
        sa.Column("corpus_hash", sa.String(length=120), nullable=True),
        sa.Column("embedding_type", sa.String(length=120), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("embedding_version", sa.String(length=120), nullable=False),
        sa.Column("clustering_method", sa.String(length=120), nullable=False),
        sa.Column("clustering_params_json", sa.Text(), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=False),
        sa.Column("layout_version", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
    )
```

```python
# src/memoria/atlas/contracts.py
@dataclass(frozen=True, slots=True)
class AtlasWorldPoint:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class AtlasRegionShape:
    shape_type: str
    rings: list[list[AtlasWorldPoint]]


@dataclass(frozen=True, slots=True)
class AtlasRequestOverlay:
    match_count: int
    matched_source_item_ids: list[int]
```

- [ ] **Step 4: Run targeted schema verification**

Run:

```bash
uv run pytest tests/integration/test_schema_tables.py -v
```

Expected:

```text
PASSED tests/integration/test_schema_tables.py::test_initial_schema_includes_screenshot_knowledge_core_tables
```

- [ ] **Step 5: Commit the schema layer**

```bash
git add alembic/versions/20260411_04_add_atlas_projection_tables.py src/memoria/atlas/__init__.py src/memoria/atlas/contracts.py src/memoria/domain/models.py tests/integration/test_schema_tables.py
git commit -m "feat: add atlas projection schema"
```

---

### Task 2: Implement Deterministic Atlas Projection Helpers

**Files:**
- Create: `src/memoria/atlas/projection.py`
- Create: `tests/unit/test_atlas_projection_helpers.py`
- Modify: `src/memoria/atlas/contracts.py`

- [ ] **Step 1: Write failing unit tests for subregions, representatives, bridges, and key reuse**

```python
# tests/unit/test_atlas_projection_helpers.py
def test_derive_subregion_count_scales_with_region_size():
    assert derive_subregion_count(4) == 0
    assert derive_subregion_count(18) == 3
    assert derive_subregion_count(65) == 6


def test_select_representatives_prefers_medoid_then_metadata_quality():
    ranked = select_representatives(
        [
            AtlasCandidateItem(10, [1.0, 0.0], "thin", None, [], 0),
            AtlasCandidateItem(11, [0.98, 0.02], "rich summary", "telegram", ["topic:trip"], 2),
            AtlasCandidateItem(12, [0.97, 0.03], "rich summary", "telegram", ["topic:trip", "thread:berlin"], 3),
        ],
        limit=2,
    )
    assert [item.source_item_id for item in ranked] == [12, 11]


def test_classify_bridge_marks_small_primary_secondary_margin():
    classification = classify_bridge(
        primary_region_key="region-a",
        secondary_region_key="region-b",
        primary_distance=0.32,
        secondary_distance=0.38,
        same_parent=False,
    )
    assert classification is not None
    assert classification.bridge_type == "external_bridge"


def test_match_region_identity_reuses_prior_key_when_overlap_is_strong():
    matched = match_region_identity(
        prior_regions=[PriorRegionIdentity("atlas-r1", {1, 2, 3, 4}, [0.1, 0.2])],
        source_item_ids={1, 2, 3, 5},
        centroid=[0.1, 0.22],
        label_tokens={"telegram", "travel"},
    )
    assert matched == "atlas-r1"
```

- [ ] **Step 2: Run the helper tests and verify they fail**

Run:

```bash
uv run pytest tests/unit/test_atlas_projection_helpers.py -v
```

Expected:

```text
FAILED tests/unit/test_atlas_projection_helpers.py
```

- [ ] **Step 3: Implement the pure helper layer in `projection.py`**

```python
# src/memoria/atlas/projection.py
def derive_subregion_count(item_count: int) -> int:
    if item_count < 8:
        return 0
    if item_count < 20:
        return 3
    if item_count < 40:
        return 4
    if item_count < 80:
        return 6
    return 8


def select_representatives(
    items: list[AtlasCandidateItem],
    *,
    limit: int,
) -> list[AtlasCandidateItem]:
    ordered = sorted(
        items,
        key=lambda item: (
            -item.metadata_score,
            item.medoid_distance,
            item.source_item_id,
        ),
    )
    selected: list[AtlasCandidateItem] = []
    for candidate in ordered:
        if any(existing.near_duplicate_key == candidate.near_duplicate_key for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) == limit:
            break
    return selected


def classify_bridge(
    *,
    primary_region_key: str,
    secondary_region_key: str,
    primary_distance: float,
    secondary_distance: float,
    same_parent: bool,
) -> BridgeClassification | None:
    margin = secondary_distance - primary_distance
    if margin > 0.12:
        return None
    return BridgeClassification(
        primary_region_key=primary_region_key,
        secondary_region_key=secondary_region_key,
        bridge_type="internal_bridge" if same_parent else "external_bridge",
        bridge_score=max(0.0, 1.0 - margin),
    )
```

```python
# src/memoria/atlas/contracts.py
@dataclass(frozen=True, slots=True)
class AtlasCandidateItem:
    source_item_id: int
    vector: list[float]
    semantic_summary: str | None
    app_hint: str | None
    object_refs: list[str]
    knowledge_count: int

    @property
    def metadata_score(self) -> float:
        return (
            (2.0 if self.semantic_summary else 0.0)
            + (1.0 if self.app_hint else 0.0)
            + min(float(len(self.object_refs)), 2.0)
            + min(float(self.knowledge_count), 3.0)
        )
```

- [ ] **Step 4: Run the helper tests until they pass**

Run:

```bash
uv run pytest tests/unit/test_atlas_projection_helpers.py -v
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit the helper layer**

```bash
git add src/memoria/atlas/contracts.py src/memoria/atlas/projection.py tests/unit/test_atlas_projection_helpers.py
git commit -m "feat: add atlas projection helpers"
```

---

### Task 3: Build And Guard Atlas Rebuilds

**Files:**
- Modify: `src/memoria/atlas/projection.py`
- Modify: `src/memoria/admin/service.py`
- Modify: `src/memoria/admin/cli.py`
- Modify: `tests/integration/_screenshot_read_helpers.py`
- Create: `tests/integration/test_atlas_projection.py`
- Modify: `tests/integration/test_admin_service.py`

- [ ] **Step 1: Seed a richer atlas fixture and add failing rebuild tests**

```python
# tests/integration/test_atlas_projection.py
def test_rebuild_screenshot_atlas_persists_latest_published_run(tmp_path):
    engine = _create_engine(tmp_path, "atlas-rebuild.db")
    seeded = seed_atlas_dataset(engine, tmp_path)

    with Session(engine) as session:
        result = rebuild_screenshot_atlas(session, force=True)
        session.commit()

    assert result["atlas_run_id"] >= 1
    assert result["region_count"] >= 2
    assert result["item_count"] >= seeded.total_source_items


def test_rebuild_screenshot_atlas_reuses_prior_region_keys_when_shape_is_stable(tmp_path):
    engine = _create_engine(tmp_path, "atlas-rebuild-stable.db")
    seed_atlas_dataset(engine, tmp_path)

    with Session(engine) as session:
        first = rebuild_screenshot_atlas(session, force=True)
        session.commit()
    with Session(engine) as session:
        second = rebuild_screenshot_atlas(session, force=True)
        session.commit()

    assert first["top_region_keys"] == second["top_region_keys"]
```

```python
# tests/integration/test_admin_service.py
def test_rebuild_screenshot_atlas_refuses_active_screenshot_runs(tmp_path):
    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="active screenshot pipeline runs: 1"):
            rebuild_screenshot_atlas(session)
```

- [ ] **Step 2: Run the atlas rebuild tests and verify they fail**

Run:

```bash
uv run pytest tests/integration/test_atlas_projection.py tests/integration/test_admin_service.py -v
```

Expected:

```text
FAILED tests/integration/test_atlas_projection.py::test_rebuild_screenshot_atlas_persists_latest_published_run
FAILED tests/integration/test_admin_service.py::test_rebuild_screenshot_atlas_refuses_active_screenshot_runs
```

- [ ] **Step 3: Implement atlas rebuild persistence and admin guard wiring**

```python
# src/memoria/atlas/projection.py
def rebuild_screenshot_atlas(session: Session, *, force: bool = False) -> dict[str, object]:
    if count_running_screenshot_pipeline_runs(session) > 0 and not force:
        raise RuntimeError(
            f"active screenshot pipeline runs: {count_running_screenshot_pipeline_runs(session)}"
        )

    latest_map_run = _load_latest_semantic_map_run(session)
    if latest_map_run is None:
        raise RuntimeError("semantic map run is required before atlas rebuild")

    atlas_run = AtlasRun(
        atlas_key="screenshots_atlas_v1",
        source_family="screenshot",
        status="completed",
        source_count=len(latest_map_run.points),
        source_snapshot_id=f"semantic-map-run:{latest_map_run.map_run_id}",
        corpus_hash=_hash_source_ids(latest_map_run.source_item_ids),
        embedding_type="screenshot_semantic_text",
        embedding_model="hashed-text-v1",
        embedding_version="hashed-text-v1",
        clustering_method="semantic-map-plus-subregions-v1",
        clustering_params_json=json.dumps({"subregion_cap": 8, "bridge_margin": 0.12}, sort_keys=True),
        random_seed=42,
        layout_version="atlas-world-v1",
        completed_at=_utcnow(),
        published_at=_utcnow(),
    )
    session.add(atlas_run)
    session.flush()
    _persist_regions(session, atlas_run_id=atlas_run.id, latest_map_run=latest_map_run)
    _persist_edges(session, atlas_run_id=atlas_run.id, latest_map_run=latest_map_run)
    _persist_items(session, atlas_run_id=atlas_run.id, latest_map_run=latest_map_run)
    return {"atlas_run_id": atlas_run.id, "region_count": region_count, "item_count": item_count}
```

```python
# src/memoria/admin/service.py
def rebuild_screenshot_atlas(session: Session, *, force: bool = False) -> dict[str, object]:
    active_runs = count_running_screenshot_pipeline_runs(session)
    if active_runs > 0 and not force:
        raise RuntimeError(f"active screenshot pipeline runs: {active_runs}")
    return atlas_projection.rebuild_screenshot_atlas(session, force=True)
```

```python
# src/memoria/admin/cli.py
@app.command("rebuild-screenshot-atlas")
def rebuild_screenshot_atlas_command(force: bool = False) -> None:
    with Session(engine) as session:
        payload = rebuild_screenshot_atlas(session, force=force)
        session.commit()
    print(json.dumps(payload, indent=2, sort_keys=True))
```

- [ ] **Step 4: Run the rebuild and admin tests until they pass**

Run:

```bash
uv run pytest tests/integration/test_atlas_projection.py tests/integration/test_admin_service.py -v
```

Expected:

```text
PASSED tests/integration/test_atlas_projection.py::test_rebuild_screenshot_atlas_persists_latest_published_run
PASSED tests/integration/test_admin_service.py::test_rebuild_screenshot_atlas_refuses_active_screenshot_runs
```

- [ ] **Step 5: Commit rebuild persistence**

```bash
git add src/memoria/atlas/projection.py src/memoria/admin/service.py src/memoria/admin/cli.py tests/integration/_screenshot_read_helpers.py tests/integration/test_atlas_projection.py tests/integration/test_admin_service.py
git commit -m "feat: add atlas rebuild pipeline"
```

---

### Task 4: Expose Atlas Overview, Region Detail, And Evidence Slice APIs

**Files:**
- Create: `src/memoria/atlas/service.py`
- Create: `src/memoria/api/atlas.py`
- Modify: `src/memoria/api/schemas.py`
- Modify: `src/memoria/api/app.py`
- Create: `tests/integration/test_atlas_api.py`

- [ ] **Step 1: Write failing API tests for overview, region detail, evidence slice, and HTML fallback**

```python
# tests/integration/test_atlas_api.py
def test_get_atlas_overview_returns_regions_and_filter_overlays(tmp_path):
    client, engine = create_test_client(tmp_path, "atlas-overview.db")
    seed_atlas_dataset(engine, tmp_path, rebuild_atlas=True)

    response = client.get("/atlas/overview", params={"app_hint": "telegram"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["atlas_run"]["atlas_key"] == "screenshots_atlas_v1"
    assert payload["regions"]
    assert "match_count" in payload["regions"][0]["overlay"]


def test_get_atlas_region_detail_returns_subregions_and_representatives(tmp_path):
    response = client.get(f"/atlas/regions/{region_key}")
    assert response.status_code == 200
    assert response.json()["subregions"]
    assert response.json()["representatives"]


def test_get_atlas_evidence_slice_splits_representatives_bridges_and_long_tail(tmp_path):
    response = client.get("/atlas/evidence", params={"region_key": region_key, "limit": 5, "offset": 0})
    assert response.status_code == 200
    payload = response.json()
    assert payload["representatives"]
    assert "items" in payload["long_tail_page"]


def test_get_atlas_page_returns_fallback_html_when_frontend_build_is_missing(tmp_path):
    response = client.get("/atlas")
    assert response.status_code == 200
    assert "Semantic Atlas frontend build is not present" in response.text
```

- [ ] **Step 2: Run the atlas API tests and verify they fail**

Run:

```bash
uv run pytest tests/integration/test_atlas_api.py -v
```

Expected:

```text
FAILED tests/integration/test_atlas_api.py
```

- [ ] **Step 3: Implement the atlas read service and HTTP surface**

```python
# src/memoria/atlas/service.py
def get_atlas_overview(
    session: Session,
    *,
    filters: ScreenshotReadFilters,
) -> AtlasOverview:
    atlas_run = _get_latest_published_run(session)
    regions = _load_regions(session, atlas_run_id=atlas_run.id, level=0)
    overlays = _build_region_overlays(session, atlas_run_id=atlas_run.id, filters=filters)
    return AtlasOverview(atlas_run=atlas_run, regions=_attach_overlays(regions, overlays))


def get_atlas_region_detail(
    session: Session,
    *,
    region_key: str,
    filters: ScreenshotReadFilters,
) -> AtlasRegionDetail | None:
    atlas_run = _get_latest_published_run(session)
    region = _load_region(session, atlas_run_id=atlas_run.id, region_key=region_key)
    if region is None:
        return None
    subregions = _load_regions(session, atlas_run_id=atlas_run.id, parent_region_key=region_key)
    representatives = _load_item_group(
        session,
        atlas_run_id=atlas_run.id,
        region_key=region_key,
        subregion_key=None,
        representative_only=True,
        bridge_only=False,
        limit=6,
        offset=0,
        filters=filters,
    )
    return AtlasRegionDetail(region=region, subregions=subregions, representatives=representatives)
```

```python
# src/memoria/api/atlas.py
@router.get("/atlas/overview", response_model=AtlasOverviewResponse)
def get_atlas_overview_endpoint(
    app_hint: str | None = Query(None),
    screen_category: str | None = Query(None),
    connector_instance_id: str | None = Query(None),
    has_knowledge: bool | None = Query(None),
    observed_from: datetime | None = Query(None),
    observed_to: datetime | None = Query(None),
):
    filters = ScreenshotReadFilters(
        connector_instance_id=connector_instance_id,
        app_hint=app_hint,
        screen_category=screen_category,
        has_knowledge=has_knowledge,
        observed_from=observed_from,
        observed_to=observed_to,
    )
    with Session(engine) as session:
        result = atlas_service.get_atlas_overview(session, filters=filters)
    return asdict(result)


@router.get("/atlas/regions/{region_key}", response_model=AtlasRegionDetailResponse)
def get_atlas_region_detail_endpoint(
    region_key: str,
    app_hint: str | None = Query(None),
    screen_category: str | None = Query(None),
    connector_instance_id: str | None = Query(None),
    has_knowledge: bool | None = Query(None),
    observed_from: datetime | None = Query(None),
    observed_to: datetime | None = Query(None),
):
    filters = ScreenshotReadFilters(
        connector_instance_id=connector_instance_id,
        app_hint=app_hint,
        screen_category=screen_category,
        has_knowledge=has_knowledge,
        observed_from=observed_from,
        observed_to=observed_to,
    )
    with Session(engine) as session:
        result = atlas_service.get_atlas_region_detail(session, region_key=region_key, filters=filters)
    if result is None:
        raise HTTPException(status_code=404, detail="atlas region not found")
    return asdict(result)


@router.get("/atlas/evidence", response_model=AtlasEvidenceSliceResponse)
def get_atlas_evidence_slice_endpoint(
    region_key: str,
    subregion_key: str | None = Query(None),
    sort: str = Query("representatives"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    app_hint: str | None = Query(None),
    screen_category: str | None = Query(None),
    connector_instance_id: str | None = Query(None),
    has_knowledge: bool | None = Query(None),
    observed_from: datetime | None = Query(None),
    observed_to: datetime | None = Query(None),
):
    filters = ScreenshotReadFilters(
        connector_instance_id=connector_instance_id,
        app_hint=app_hint,
        screen_category=screen_category,
        has_knowledge=has_knowledge,
        observed_from=observed_from,
        observed_to=observed_to,
    )
    with Session(engine) as session:
        result = atlas_service.get_atlas_evidence_slice(
            session,
            region_key=region_key,
            subregion_key=subregion_key,
            sort=sort,
            limit=limit,
            offset=offset,
            filters=filters,
        )
    return asdict(result)
```

```python
# src/memoria/api/schemas.py
class AtlasOverlayResponse(BaseModel):
    match_count: int


class AtlasRegionResponse(BaseModel):
    atlas_run_id: int
    region_key: str
    parent_region_key: str | None
    level: int
    title: str
    x: float
    y: float
    label_x: float
    label_y: float
    region_shape: dict[str, Any]
    item_count: int
    top_labels: list[str]
    top_apps: list[str]
    top_people: list[str]
    top_entities: list[str]
    overlay: AtlasOverlayResponse
```

- [ ] **Step 4: Register the atlas router in the app**

```python
# src/memoria/api/app.py
from memoria.api.atlas import create_atlas_router

app.include_router(create_atlas_router(engine=engine, frontend_dist_dir=Path("frontend/atlas/dist")))
```

- [ ] **Step 5: Run the atlas API tests until they pass**

Run:

```bash
uv run pytest tests/integration/test_atlas_api.py -v
```

Expected:

```text
4 passed
```

- [ ] **Step 6: Commit the atlas HTTP layer**

```bash
git add src/memoria/atlas/service.py src/memoria/api/atlas.py src/memoria/api/app.py src/memoria/api/schemas.py tests/integration/test_atlas_api.py
git commit -m "feat: add atlas read api"
```

---

### Task 5: Scaffold The Atlas Frontend Workspace And State Machine

**Files:**
- Create: `frontend/atlas/package.json`
- Create: `frontend/atlas/package-lock.json`
- Create: `frontend/atlas/tsconfig.json`
- Create: `frontend/atlas/vite.config.ts`
- Create: `frontend/atlas/index.html`
- Create: `frontend/atlas/src/main.tsx`
- Create: `frontend/atlas/src/App.tsx`
- Create: `frontend/atlas/src/styles.css`
- Create: `frontend/atlas/src/api/contracts.ts`
- Create: `frontend/atlas/src/api/client.ts`
- Create: `frontend/atlas/src/state/atlasReducer.ts`
- Create: `frontend/atlas/src/state/atlasReducer.test.ts`
- Create: `frontend/atlas/src/lib/evidenceSections.ts`
- Create: `frontend/atlas/src/lib/evidenceSections.test.ts`
- Modify: `.gitignore`

- [ ] **Step 1: Add failing frontend tests for state transitions and evidence sectioning**

```ts
// frontend/atlas/src/state/atlasReducer.test.ts
it("selects on single click and drills down only on explicit action", () => {
  const selected = atlasReducer(initialState, { type: "region.selected", regionKey: "region-a" });
  expect(selected.level).toBe("overview");
  const drilled = atlasReducer(selected, { type: "region.drilled", regionKey: "region-a" });
  expect(drilled.level).toBe("region");
});
```

```ts
// frontend/atlas/src/lib/evidenceSections.test.ts
it("keeps representatives and bridges out of long tail pagination", () => {
  const sections = splitEvidenceSections({
    representatives: [{ source_item_id: 1 }],
    bridges: [{ source_item_id: 2 }],
    long_tail_page: { items: [{ source_item_id: 3 }], limit: 1, offset: 0, total: 1 },
  });
  expect(sections.representatives).toHaveLength(1);
  expect(sections.bridges).toHaveLength(1);
  expect(sections.longTail.items).toHaveLength(1);
});
```

- [ ] **Step 2: Create the frontend workspace and install dependencies**

Run:

```bash
mkdir -p frontend/atlas/src/api frontend/atlas/src/state frontend/atlas/src/lib frontend/atlas/src/components frontend/atlas/src/canvas
cd frontend/atlas
npm install react react-dom pixi.js @tanstack/react-virtual d3-scale
npm install -D typescript vite vitest @vitejs/plugin-react @types/react @types/react-dom jsdom
```

Expected:

```text
added packages
```

- [ ] **Step 3: Implement the workspace scaffold and pure state layer**

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
  }
}
```

```ts
// frontend/atlas/src/state/atlasReducer.ts
export type AtlasLevel = "overview" | "region" | "evidence";

export type AtlasState = {
  level: AtlasLevel;
  selectedRegionKey: string | null;
  selectedSubregionKey: string | null;
  selectedItemId: number | null;
};

export function atlasReducer(state: AtlasState, action: AtlasAction): AtlasState {
  switch (action.type) {
    case "region.selected":
      return { ...state, selectedRegionKey: action.regionKey, selectedSubregionKey: null, selectedItemId: null };
    case "region.drilled":
      return { ...state, level: "region", selectedRegionKey: action.regionKey, selectedSubregionKey: null, selectedItemId: null };
    case "subregion.selected":
      return { ...state, selectedSubregionKey: action.subregionKey, selectedItemId: null };
    case "subregion.drilled":
      return { ...state, level: "evidence", selectedSubregionKey: action.subregionKey, selectedItemId: null };
    case "item.selected":
      return { ...state, selectedItemId: action.sourceItemId };
    case "breadcrumbs.reset":
      return { level: "overview", selectedRegionKey: null, selectedSubregionKey: null, selectedItemId: null };
  }
}
```

- [ ] **Step 4: Run the frontend unit tests**

Run:

```bash
cd frontend/atlas
npm run test
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit the frontend scaffold**

```bash
git add .gitignore frontend/atlas/package.json frontend/atlas/package-lock.json frontend/atlas/tsconfig.json frontend/atlas/vite.config.ts frontend/atlas/index.html frontend/atlas/src/main.tsx frontend/atlas/src/App.tsx frontend/atlas/src/styles.css frontend/atlas/src/api/contracts.ts frontend/atlas/src/api/client.ts frontend/atlas/src/state/atlasReducer.ts frontend/atlas/src/state/atlasReducer.test.ts frontend/atlas/src/lib/evidenceSections.ts frontend/atlas/src/lib/evidenceSections.test.ts
git commit -m "feat: scaffold atlas frontend workspace"
```

---

### Task 6: Build The Atlas Workbench UI And Serve The Built Frontend

**Files:**
- Create: `frontend/atlas/src/canvas/AtlasCanvas.tsx`
- Create: `frontend/atlas/src/components/AtlasToolbar.tsx`
- Create: `frontend/atlas/src/components/InsightDock.tsx`
- Create: `frontend/atlas/src/components/RegionNavigator.tsx`
- Create: `frontend/atlas/src/components/EvidenceList.tsx`
- Modify: `frontend/atlas/src/App.tsx`
- Modify: `frontend/atlas/src/styles.css`
- Modify: `src/memoria/api/atlas.py`

- [ ] **Step 1: Add the Pixi canvas, persistent dock, and virtualized evidence list**

```tsx
// frontend/atlas/src/App.tsx
export default function App() {
  const [state, dispatch] = useReducer(atlasReducer, initialState);
  const overview = useAtlasOverview(filters);
  const regionDetail = useAtlasRegion(state.selectedRegionKey, filters);
  const evidence = useAtlasEvidence(state.selectedRegionKey, state.selectedSubregionKey, filters, pagination);

  return (
    <div className="atlas-shell">
      <section className="atlas-stage">
        <AtlasToolbar filters={filters} onFiltersChange={setFilters} />
        <AtlasCanvas
          level={state.level}
          overview={overview}
          regionDetail={regionDetail}
          evidence={evidence}
          onRegionSelect={(regionKey) => dispatch({ type: "region.selected", regionKey })}
          onRegionDrill={(regionKey) => dispatch({ type: "region.drilled", regionKey })}
          onSubregionSelect={(subregionKey) => dispatch({ type: "subregion.selected", subregionKey })}
          onSubregionDrill={(subregionKey) => dispatch({ type: "subregion.drilled", subregionKey })}
          onItemSelect={(sourceItemId) => dispatch({ type: "item.selected", sourceItemId })}
        />
      </section>
      <InsightDock
        state={state}
        overview={overview}
        regionDetail={regionDetail}
        evidence={evidence}
        onReset={() => dispatch({ type: "breadcrumbs.reset" })}
      />
    </div>
  );
}
```

```tsx
// frontend/atlas/src/components/EvidenceList.tsx
export function EvidenceList({ slice, onSelect }: EvidenceListProps) {
  const rowVirtualizer = useVirtualizer({
    count: slice.longTailPage.items.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 72,
  });
  return (
    <section>
      <EvidenceSection title="Representatives" items={slice.representatives} onSelect={onSelect} />
      <EvidenceSection title="Bridges" items={slice.bridges} onSelect={onSelect} />
      <VirtualLongTailList virtualizer={rowVirtualizer} items={slice.longTailPage.items} onSelect={onSelect} />
    </section>
  );
}
```

- [ ] **Step 2: Serve the built frontend from FastAPI when `dist/` exists**

```python
# src/memoria/api/atlas.py
@router.get("/atlas", response_class=HTMLResponse)
def get_atlas_page() -> str:
    index_path = frontend_dist_dir / "index.html"
    if not index_path.exists():
        return _fallback_page_html()
    return index_path.read_text(encoding="utf-8")


@router.get("/atlas/assets/{asset_path:path}")
def get_atlas_asset(asset_path: str) -> FileResponse:
    asset_file = frontend_dist_dir / "assets" / asset_path
    if not asset_file.is_file():
        raise HTTPException(status_code=404, detail="atlas asset not found")
    return FileResponse(asset_file)
```

- [ ] **Step 3: Build the frontend bundle**

Run:

```bash
cd frontend/atlas
npm run build
```

Expected:

```text
dist/index.html emitted
dist/assets/* emitted
```

- [ ] **Step 4: Re-run atlas API tests now that the built page path exists**

Run:

```bash
uv run pytest tests/integration/test_atlas_api.py -v
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit the atlas UI**

```bash
git add frontend/atlas/src/canvas/AtlasCanvas.tsx frontend/atlas/src/components/AtlasToolbar.tsx frontend/atlas/src/components/InsightDock.tsx frontend/atlas/src/components/RegionNavigator.tsx frontend/atlas/src/components/EvidenceList.tsx frontend/atlas/src/App.tsx frontend/atlas/src/styles.css src/memoria/api/atlas.py
git commit -m "feat: add atlas workbench ui"
```

---

### Task 7: Document The Workflow And Run Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document atlas rebuild and frontend build commands**

```md
## Semantic Atlas

- Build atlas projection: `uv run python -m memoria.admin.cli --database-url sqlite:////absolute/path/to/semantic-atlas.db rebuild-screenshot-atlas`
- Start frontend locally: `cd frontend/atlas && npm install && npm run dev`
- Build frontend for FastAPI serving: `cd frontend/atlas && npm run build`
- Atlas read APIs: `/atlas/overview`, `/atlas/regions/{region_key}`, `/atlas/evidence`
```

- [ ] **Step 2: Run the Python regression suite**

Run:

```bash
uv run pytest -v
```

Expected:

```text
pytest session finishes with 0 failures
```

- [ ] **Step 3: Run the frontend regression commands**

Run:

```bash
cd frontend/atlas
npm run test
npm run build
```

Expected:

```text
Vitest exits with code 0
Vite build exits with code 0
```

- [ ] **Step 4: Commit docs and verification-ready changes**

```bash
git add README.md
git commit -m "docs: add semantic atlas workflow"
```

---

## Implementation Notes

- Reuse `ScreenshotReadFilters` everywhere atlas accepts filters so that overview, region detail, and evidence slice agree with the existing screenshot/search surfaces.
- Persist `item_count`, `top_labels`, `top_apps`, `top_people`, `top_entities`, and region geometry in atlas tables. Compute `match_count` only per request and keep it nested under `overlay` in API responses.
- Keep all coordinates in the same atlas world space. Never recenter coordinates per region in the API.
- Use `semantic_map_runs` and `semantic_map_points` as the top-level structural input for MVP. Subregions and bridge metadata are new atlas projection work.
- Treat `hashed-text-v1` as an MVP dependency, not a forever choice. Keep its metadata explicit in `atlas_runs`.
- Do not make the browser the source of truth for subregions, representatives, bridges, or shapes.
- Do not require a frontend build for Python tests to pass; `/atlas` must return a readable fallback page when `frontend/atlas/dist` is missing.

## Self-Review

- Spec coverage:
  - dedicated atlas read model and `atlas_*` tables: Tasks 1 and 3
  - rebuild policy and active-run guard: Task 3
  - embedding basis and atlas run reproducibility metadata: Tasks 1 and 3
  - coordinate contract, request overlays, and split evidence payload: Task 4
  - React + PixiJS + dock + evidence workbench: Tasks 5 and 6
  - README/operator workflow: Task 7
- Placeholder scan:
  - no standalone ellipsis placeholders remain in Python or shell snippets
  - no obsolete alternate dotenv filename assumption remains
- Type consistency:
  - `atlas_run_id` is carried through run, region, item, and edge records
  - `overlay.match_count` is request-scoped, while persisted `item_count` stays on the region model
  - `representatives`, `bridges`, and `long_tail_page` are separate sections in the evidence slice throughout the plan

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-11-semantic-atlas-cluster-visualization-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
