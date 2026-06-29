# Similarity Graph Semantics And Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/similarity` a truthful region-to-region overview graph with backend-owned label semantics, progressive labels, and lightweight handoff into `/atlas`.

**Architecture:** Improve atlas projection metadata first so region titles and label anchors are worth consuming. Then extend the similarity service and API response to expose render-ready node and graph semantics. Finally update the Plotly frontend to consume those semantics directly, render labels by mode, and show a lightweight selected-node summary with CTA links into existing atlas drill-down.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Pydantic, React, TypeScript, Plotly 3.5.0, pytest, vitest

---

## File Map

### Backend

- Modify: `src/memoria/atlas/projection.py`
  - Improve region title generation and persisted label anchors.
- Modify: `tests/unit/test_atlas_projection_helpers.py`
  - Add focused tests for region title helpers and label anchor behavior.
- Modify: `src/memoria/similarity/service.py`
  - Extend node and graph semantics (`label`, `label_x`, `label_y`, `degree`, `label_priority`, `duplicate_title_count`, `edge_type`, `graph_kind`, `edge_scope`).
- Modify: `tests/unit/test_similarity_service.py`
  - Cover duplicate-title disambiguation, filter-aware `degree`, preserved snapshot edges, and response ordering.
- Modify: `src/memoria/api/schemas.py`
  - Extend similarity response DTOs additively.
- Modify: `src/memoria/api/similarity.py`
  - Keep route additive-compatible and tighten fallback copy.
- Modify: `tests/integration/test_similarity_api.py`
  - Lock response shape, graph metadata, and additive compatibility.

### Frontend

- Modify: `frontend/similarity/src/api/contracts.ts`
  - Match the expanded similarity response DTOs.
- Modify: `frontend/similarity/src/App.tsx`
  - Replace `Show labels` with `labelMode`, wire selection summary, and keep handoff lightweight.
- Modify: `frontend/similarity/src/lib/traces.ts`
  - Use backend `label`, `label_x`, `label_y`, `label_priority`, `degree`, `edge_type`, `graph_kind`, `edge_scope`.
- Modify: `frontend/similarity/src/lib/traces.test.ts`
  - Lock label modes, default label limits, and selected-neighborhood emphasis.
- Modify: `frontend/similarity/src/App.test.tsx`
  - Verify label mode controls, summary box contents, and CTA links.
- Modify: `frontend/similarity/src/styles.css`
  - Add styling for label mode controls and selected summary box.

## Task 1: Fix Atlas Region Titles And Label Anchors

**Files:**
- Modify: `src/memoria/atlas/projection.py`
- Test: `tests/unit/test_atlas_projection_helpers.py`

- [ ] **Step 1: Write the failing title-selection tests**

Add tests covering generic labels and semantic fallbacks:

```python
def test_build_region_title_prefers_semantic_label_over_generic_platform() -> None:
    summary = _summarize_points(
        [
            _make_point(cluster_hints=["chrome", "dns management"], app_hint="chrome"),
            _make_point(cluster_hints=["chrome", "dns management"], app_hint="chrome"),
        ],
        fallback_title="cluster-001",
    )

    assert summary["title"] == "chrome · dns management"


def test_build_region_title_falls_back_to_two_semantic_labels_without_app() -> None:
    summary = _summarize_points(
        [
            _make_point(cluster_hints=["delivery status", "refund tracking"], app_hint=None),
            _make_point(cluster_hints=["delivery status", "refund tracking"], app_hint=None),
        ],
        fallback_title="cluster-002",
    )

    assert summary["title"] == "delivery status, refund tracking"
```

- [ ] **Step 2: Write the failing label-anchor test**

Add a focused test that proves labels are no longer centered on the node:

```python
def test_compute_label_anchor_offsets_from_region_center() -> None:
    anchor_x, anchor_y = _compute_label_anchor(
        region_x=0.4,
        region_y=0.5,
        region_shape={"shape_type": "polygon", "rings": [[[0.35, 0.45], [0.45, 0.45], [0.45, 0.55], [0.35, 0.55]]]},
        atlas_center=(0.5, 0.5),
    )

    assert (anchor_x, anchor_y) != (0.4, 0.5)
    assert anchor_y < 0.5 or anchor_x != 0.4
```

- [ ] **Step 3: Run the projection helper tests to verify failure**

Run:

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart
uv run pytest tests/unit/test_atlas_projection_helpers.py -v
```

Expected:

- FAIL because `_summarize_points()` still returns `top_labels[0]`
- FAIL because labels are still anchored exactly at `x` and `y`

- [ ] **Step 4: Implement title helper functions in `projection.py`**

Add helper functions near `_summarize_points()`:

```python
_GENERIC_REGION_LABELS = {
    "calendar",
    "chrome",
    "instagram",
    "settings",
    "terminal",
    "tiktok",
    "twitter",
    "x",
    "youtube",
}


def _normalize_title_token(value: str) -> str | None:
    normalized = value.strip().lower().replace("_", " ").replace("-", " ")
    normalized = " ".join(normalized.split())
    return normalized or None


def _is_generic_region_label(value: str) -> bool:
    normalized = _normalize_title_token(value)
    return normalized in _GENERIC_REGION_LABELS if normalized else False


def _build_region_title(
    *,
    top_labels: list[str],
    top_apps: list[str],
    fallback_title: str,
) -> str:
    semantic_labels = [label for label in top_labels if not _is_generic_region_label(label)]
    top_app = top_apps[0] if top_apps else None

    if top_app and semantic_labels:
        return f"{top_app} · {semantic_labels[0]}"
    if len(semantic_labels) >= 2:
        return f"{semantic_labels[0]}, {semantic_labels[1]}"
    if semantic_labels:
        return semantic_labels[0]
    if top_app:
        return top_app
    return fallback_title
```

- [ ] **Step 5: Implement label anchor calculation and wire it into region creation**

Update region construction to call a new anchor helper instead of copying `x` and `y`:

```python
def _compute_label_anchor(
    *,
    region_x: float,
    region_y: float,
    region_shape: dict[str, object],
    atlas_center: tuple[float, float],
) -> tuple[float, float]:
    min_x, min_y, max_x, max_y = _region_bounds(region_shape)
    span = max(max_x - min_x, max_y - min_y, 0.02)
    offset = max(0.018, min(0.06, span * 0.35))
    horizontal = -offset if region_x >= atlas_center[0] else offset
    vertical = -offset if region_y >= atlas_center[1] else offset
    return (region_x + horizontal, region_y + vertical)


summary = _summarize_points(points, fallback_title=fallback_title)
label_x, label_y = _compute_label_anchor(
    region_x=region_x,
    region_y=region_y,
    region_shape=region_shape,
    atlas_center=atlas_center,
)
```

- [ ] **Step 6: Run projection helper tests to verify pass**

Run:

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart
uv run pytest tests/unit/test_atlas_projection_helpers.py -v
```

Expected:

- PASS for semantic-title and anchor-offset tests

- [ ] **Step 7: Commit the atlas projection change**

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart
git add src/memoria/atlas/projection.py tests/unit/test_atlas_projection_helpers.py
git commit -m "atlas: improve region titles and label anchors"
```

## Task 2: Extend Similarity Service And API Contract

**Files:**
- Modify: `src/memoria/similarity/service.py`
- Modify: `src/memoria/api/schemas.py`
- Modify: `src/memoria/api/similarity.py`
- Test: `tests/unit/test_similarity_service.py`
- Test: `tests/integration/test_similarity_api.py`

- [ ] **Step 1: Write the failing service tests for new node semantics**

Add unit tests for duplicate-title labels, degree, and filtered edges:

```python
def test_similarity_graph_disambiguates_duplicate_titles_and_computes_degree() -> None:
    with Session(engine) as session:
        _seed_similarity_fixture_with_duplicate_titles(session)
        graph = get_similarity_graph(session)

    nodes = {node.region_key: node for node in graph.nodes}
    assert nodes["region-a"].canonical_title == "chrome"
    assert nodes["region-a"].duplicate_title_count == 2
    assert nodes["region-a"].degree == 1
    assert nodes["region-a"].label_priority == nodes["region-a"].item_count + 3 * nodes["region-a"].degree
    assert nodes["region-a"].label != nodes["region-b"].label


def test_similarity_graph_keeps_snapshot_edges_under_item_filters() -> None:
    with Session(engine) as session:
        _seed_similarity_fixture(session)
        graph = get_similarity_graph(
            session,
            filters=SimilarityGraphFilters(app_hint="telegram", min_cluster_size=1),
        )

    assert graph.edge_scope == "atlas_snapshot"
    assert [(edge.source_region_key, edge.target_region_key) for edge in graph.edges] == [
        ("region-a", "region-b")
    ]
```

- [ ] **Step 2: Write the failing integration test for additive API shape**

Extend API expectations with new fields while keeping compatibility:

```python
def test_similarity_graph_endpoint_reports_graph_kind_edge_scope_and_render_labels(tmp_path: Path) -> None:
    client, engine = _create_test_client(tmp_path, "similarity-graph-shape.db")
    _seed_similarity_fixture(engine)

    response = client.get("/similarity/graph")

    assert response.status_code == 200
    payload = response.json()
    assert payload["graph_kind"] == "region_similarity"
    assert payload["edge_scope"] == "atlas_snapshot"
    assert payload["nodes"][0]["label"]
    assert payload["nodes"][0]["label_x"] != payload["nodes"][0]["x"] or payload["nodes"][0]["label_y"] != payload["nodes"][0]["y"]
    assert payload["edges"][0]["edge_type"] == "semantic_similarity"
    assert payload["edges"][0]["reason"] == "semantic_similarity"
```

- [ ] **Step 3: Run similarity backend tests to verify failure**

Run:

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart
uv run pytest tests/unit/test_similarity_service.py tests/integration/test_similarity_api.py -v
```

Expected:

- FAIL because `SimilarityGraphNode` lacks `label`, `canonical_title`, `degree`, `label_priority`
- FAIL because `SimilarityGraph` lacks `graph_kind` and `edge_scope`
- FAIL because filtered edges are still dropped to `[]`

- [ ] **Step 4: Extend dataclasses and helper flow in `similarity/service.py`**

Update the service dataclasses and add helper functions:

```python
@dataclass(frozen=True, slots=True)
class SimilarityGraphNode:
    region_key: str
    title: str
    label: str
    canonical_title: str
    duplicate_title_count: int
    x: float
    y: float
    label_x: float
    label_y: float
    size: float
    item_count: int
    degree: int
    label_priority: float
    dominant_screen_category: str
    top_labels: list[str]
    top_apps: list[str]
    top_entities: list[str]
    representative_source_item_ids: list[int]


@dataclass(frozen=True, slots=True)
class SimilarityGraph:
    run: SimilarityGraphRun | None
    nodes: list[SimilarityGraphNode]
    edges: list[SimilarityGraphEdge]
    legend: list[SimilarityGraphLegendEntry]
    filters: SimilarityGraphFilters
    graph_kind: str
    edge_scope: str
    default_label_limit: int | None = None
```

Add helpers:

```python
def _normalize_title(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())


def _compute_node_degree(edges: list[SimilarityGraphEdge]) -> dict[str, int]:
    degree: Counter[str] = Counter()
    for edge in edges:
        degree[edge.source_region_key] += 1
        degree[edge.target_region_key] += 1
    return dict(degree)


def _compute_label_priority(*, item_count: int, degree: int) -> float:
    return float(item_count + 3 * degree)
```

- [ ] **Step 5: Make node decoration deterministic and filter-aware**

Decorate raw nodes after edges are loaded:

```python
def _decorate_nodes_for_rendering(
    nodes: list[SimilarityGraphNode],
    edges: list[SimilarityGraphEdge],
) -> list[SimilarityGraphNode]:
    degree_by_region = _compute_node_degree(edges)
    canonical_counts = Counter(_normalize_title(node.title) for node in nodes)

    decorated: list[SimilarityGraphNode] = []
    for node in nodes:
        canonical_title = _normalize_title(node.title)
        duplicate_count = canonical_counts[canonical_title]
        label = _build_display_label(
            title=node.title,
            canonical_title=canonical_title,
            duplicate_title_count=duplicate_count,
            top_apps=node.top_apps,
            item_count=node.item_count,
            region_key=node.region_key,
        )
        degree = degree_by_region.get(node.region_key, 0)
        decorated.append(
            replace(
                node,
                label=label,
                canonical_title=canonical_title,
                duplicate_title_count=duplicate_count,
                degree=degree,
                label_priority=_compute_label_priority(item_count=node.item_count, degree=degree),
            )
        )
    return decorated
```

Keep `support=1` and set semantic truth explicitly:

```python
SimilarityGraphEdge(
    source_region_key=row.source_region_key,
    target_region_key=row.target_region_key,
    weight=row.weight,
    support=1,
    edge_type=row.edge_type,
    reason=row.edge_type,
)
```

- [ ] **Step 6: Keep filtered snapshot edges instead of dropping them**

Change `_load_similarity_edges()` to filter only by visible region keys and threshold:

```python
if not region_keys:
    return []

rows = session.scalars(
    select(AtlasEdge).where(
        AtlasEdge.atlas_run_id == atlas_run_id,
        AtlasEdge.edge_type == "semantic_similarity",
        AtlasEdge.source_region_key.in_(region_keys),
        AtlasEdge.target_region_key.in_(region_keys),
        AtlasEdge.weight >= min_edge_weight,
    )
).all()
```

- [ ] **Step 7: Extend Pydantic response schemas additively**

Update `src/memoria/api/schemas.py`:

```python
class SimilarityGraphNodeResponse(BaseModel):
    region_key: str
    title: str
    label: str
    canonical_title: str
    duplicate_title_count: int
    x: float
    y: float
    label_x: float
    label_y: float
    size: float
    item_count: int
    degree: int
    label_priority: float
    dominant_screen_category: str
    top_labels: list[str]
    top_apps: list[str]
    top_entities: list[str]
    representative_source_item_ids: list[int]


class SimilarityGraphEdgeResponse(BaseModel):
    source_region_key: str
    target_region_key: str
    weight: float
    support: int
    edge_type: str
    reason: str


class SimilarityGraphResponse(BaseModel):
    run: SimilarityGraphRunResponse | None
    nodes: list[SimilarityGraphNodeResponse]
    edges: list[SimilarityGraphEdgeResponse]
    legend: list[SimilarityGraphLegendEntryResponse]
    filters: SimilarityGraphFiltersResponse
    graph_kind: str
    edge_scope: str
    default_label_limit: int | None = None
```

- [ ] **Step 8: Tighten route copy and preserve additive rollout**

Update fallback HTML in `src/memoria/api/similarity.py`:

```python
<h1>Atlas region similarity graph frontend build is not present</h1>
<li><code>/similarity/graph</code> for region nodes, semantic similarity edges, legend entries, and active filters.</li>
```

Do not remove `reason` from the response yet.

- [ ] **Step 9: Run backend tests to verify pass**

Run:

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart
uv run pytest tests/unit/test_similarity_service.py tests/integration/test_similarity_api.py -v
```

Expected:

- PASS for new semantics and additive API shape

- [ ] **Step 10: Commit the backend similarity change**

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart
git add src/memoria/similarity/service.py src/memoria/api/schemas.py src/memoria/api/similarity.py tests/unit/test_similarity_service.py tests/integration/test_similarity_api.py
git commit -m "api: add similarity graph semantics metadata"
```

## Task 3: Update Frontend Contracts And Label Modes

**Files:**
- Modify: `frontend/similarity/src/api/contracts.ts`
- Modify: `frontend/similarity/src/lib/traces.ts`
- Test: `frontend/similarity/src/lib/traces.test.ts`

- [ ] **Step 1: Write the failing trace tests for label modes and backend anchors**

Add tests that lock label behavior:

```ts
it("uses backend label anchors instead of node centers", () => {
  const figure = buildSimilarityFigure(graphFixture, {
    labelMode: "default",
    selectedRegionKey: null,
    visibleCategories: null,
  });

  const labelTrace = figure.data.find((trace) => trace.mode === "text");
  expect(labelTrace?.text).toContain("chrome · dns management");
  expect(labelTrace?.x).toContain(0.32);
  expect(labelTrace?.y).toContain(0.44);
});


it("shows only top labels by priority in default mode", () => {
  const figure = buildSimilarityFigure(graphFixture, {
    labelMode: "default",
    selectedRegionKey: null,
    visibleCategories: null,
  });

  const labelTrace = figure.data.find((trace) => trace.mode === "text");
  expect(labelTrace?.text).toEqual(["chrome · dns management", "tiktok · live streaming"]);
});
```

- [ ] **Step 2: Run frontend trace tests to verify failure**

Run:

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart/frontend/similarity
npm test -- traces.test.ts
```

Expected:

- FAIL because contracts still expose `is_labeled`
- FAIL because traces still use `node.title` and centered labels

- [ ] **Step 3: Update frontend contracts to match the backend**

Replace old node and graph shapes in `src/api/contracts.ts`:

```ts
export type SimilarityGraphNode = {
  region_key: string;
  title: string;
  label: string;
  canonical_title: string;
  duplicate_title_count: number;
  x: number;
  y: number;
  label_x: number;
  label_y: number;
  size: number;
  item_count: number;
  degree: number;
  label_priority: number;
  dominant_screen_category: string;
  top_labels: string[];
  top_apps: string[];
  top_entities: string[];
  representative_source_item_ids: number[];
};

export type SimilarityGraphResponse = {
  run: SimilarityGraphRun | null;
  nodes: SimilarityGraphNode[];
  edges: SimilarityGraphEdge[];
  legend: SimilarityGraphLegendEntry[];
  filters: SimilarityGraphFilters;
  graph_kind: string;
  edge_scope: string;
  default_label_limit?: number | null;
};
```

- [ ] **Step 4: Replace `showLabels` with explicit `labelMode` behavior**

In `src/lib/traces.ts`:

```ts
export type LabelMode = "none" | "default" | "all" | "selected";

export type SimilarityFigureOptions = {
  labelMode: LabelMode;
  selectedRegionKey: string | null;
  visibleCategories: Set<string> | null;
};
```

Select labels by mode:

```ts
function selectLabeledNodes(
  nodes: SimilarityGraphNode[],
  options: SimilarityFigureOptions,
  selectedNode: SimilarityGraphNode | null,
  defaultLabelLimit: number,
): SimilarityGraphNode[] {
  if (options.labelMode === "none") return [];
  if (options.labelMode === "selected") return selectedNode ? [selectedNode] : [];
  if (options.labelMode === "all") return nodes;

  return [...nodes]
    .sort((left, right) => right.label_priority - left.label_priority || left.label.localeCompare(right.label))
    .slice(0, defaultLabelLimit);
}
```

- [ ] **Step 5: Use render labels and anchors instead of centered titles**

Update label trace construction:

```ts
const labelTrace = {
  type: "scattergl",
  mode: "text",
  showlegend: false,
  hoverinfo: "skip",
  text: labeledNodes.map((node) => node.label),
  x: labeledNodes.map((node) => node.label_x),
  y: labeledNodes.map((node) => node.label_y),
  textposition: "middle center",
  textfont: {
    color: "rgba(235,240,245,0.92)",
    size: 11,
  },
};
```

- [ ] **Step 6: Run trace tests to verify pass**

Run:

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart/frontend/similarity
npm test -- traces.test.ts
```

Expected:

- PASS for `labelMode` handling and backend label anchors

- [ ] **Step 7: Commit frontend contract and trace changes**

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart
git add frontend/similarity/src/api/contracts.ts frontend/similarity/src/lib/traces.ts frontend/similarity/src/lib/traces.test.ts
git commit -m "feat: add similarity label modes and render metadata"
```

## Task 4: Add Selected Summary And Atlas Handoff

**Files:**
- Modify: `frontend/similarity/src/App.tsx`
- Modify: `frontend/similarity/src/App.test.tsx`
- Modify: `frontend/similarity/src/styles.css`

- [ ] **Step 1: Write the failing app test for selected-node summary**

Add a test that locks the lightweight summary contract:

```ts
it("shows a lightweight summary and atlas handoff when a node is selected", async () => {
  render(<App />);

  await screen.findByText("Overview graph");
  fireEvent.click(await screen.findByRole("button", { name: /chrome · dns management/i }));

  expect(screen.getByText(/region similarity/i)).toBeInTheDocument();
  expect(screen.getByText(/region-a/i)).toBeInTheDocument();
  expect(screen.getByText(/degree: 2/i)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /region details/i })).toHaveAttribute(
    "href",
    "/atlas/regions/region-a",
  );
  expect(screen.getByRole("link", { name: /evidence/i })).toHaveAttribute(
    "href",
    "/atlas/evidence?region_key=region-a",
  );
});
```

- [ ] **Step 2: Run app tests to verify failure**

Run:

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart/frontend/similarity
npm test -- App.test.tsx
```

Expected:

- FAIL because current App only shows footer metadata and no selected summary CTA box

- [ ] **Step 3: Replace the checkbox control with label-mode UI**

In `src/App.tsx` add state and controls:

```tsx
const [labelMode, setLabelMode] = useState<LabelMode>("default");

<label className="similarity-control">
  <span className="similarity-control__label">Label mode</span>
  <select
    className="similarity-control__select"
    value={labelMode}
    onChange={(event) => setLabelMode(event.target.value as LabelMode)}
  >
    <option value="none">None</option>
    <option value="default">Default</option>
    <option value="all">All</option>
    <option value="selected">Selected</option>
  </select>
</label>
```

- [ ] **Step 4: Add the selected summary panel without eager atlas fetches**

Use only selected node payload:

```tsx
const selectedNode = graph?.nodes.find((node) => node.region_key === selectedRegionKey) ?? null;

{selectedNode ? (
  <aside className="similarity-selection-card" aria-label="Selected similarity region">
    <p className="similarity-selection-card__eyebrow">{graph?.graph_kind ?? "region similarity"}</p>
    <h3>{selectedNode.label}</h3>
    <dl>
      <div><dt>Title</dt><dd>{selectedNode.title}</dd></div>
      <div><dt>Region key</dt><dd>{selectedNode.region_key}</dd></div>
      <div><dt>Items</dt><dd>{selectedNode.item_count}</dd></div>
      <div><dt>Category</dt><dd>{selectedNode.dominant_screen_category}</dd></div>
      <div><dt>Degree</dt><dd>{selectedNode.degree}</dd></div>
    </dl>
    <p>{selectedNode.top_labels.slice(0, 5).join(", ")}</p>
    <p>{selectedNode.top_apps.slice(0, 3).join(", ")}</p>
    <div className="similarity-selection-card__actions">
      <a href={`/atlas/regions/${selectedNode.region_key}`}>Region details</a>
      <a href={`/atlas/evidence?region_key=${selectedNode.region_key}`}>Evidence</a>
    </div>
  </aside>
) : null}
```

- [ ] **Step 5: Surface graph metadata in the shell**

Update header/footer copy to reflect the truthful graph semantics:

```tsx
<p className="similarity-hero__lede">
  Region-to-region semantic similarity across atlas regions, with lightweight handoff into
  atlas drill-down.
</p>

<p>{graph ? `Graph kind: ${graph.graph_kind}` : "Graph kind unavailable"}</p>
<p>{graph ? `Edge scope: ${graph.edge_scope}` : "Edge scope unavailable"}</p>
```

- [ ] **Step 6: Style the new controls and summary card**

Add CSS in `src/styles.css`:

```css
.similarity-control__select {
  min-width: 9rem;
  border-radius: 999px;
  border: 1px solid rgba(141, 166, 184, 0.28);
  background: rgba(30, 52, 68, 0.84);
  color: rgba(244, 247, 250, 0.94);
  padding: 0.55rem 0.85rem;
}

.similarity-selection-card {
  margin-top: 1rem;
  padding: 1rem 1.1rem;
  border-radius: 18px;
  background: rgba(11, 36, 50, 0.86);
  border: 1px solid rgba(113, 156, 178, 0.22);
}
```

- [ ] **Step 7: Run app tests and frontend build**

Run:

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart/frontend/similarity
npm test -- App.test.tsx
npm run build
```

Expected:

- PASS for selected summary and CTA links
- build succeeds with the updated shell

- [ ] **Step 8: Commit selected summary and handoff**

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart
git add frontend/similarity/src/App.tsx frontend/similarity/src/App.test.tsx frontend/similarity/src/styles.css
git commit -m "feat: add similarity selection summary handoff"
```

## Task 5: Final Verification

**Files:**
- Verify only; no planned code changes

- [ ] **Step 1: Run targeted backend verification**

Run:

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart
uv run pytest tests/unit/test_atlas_projection_helpers.py tests/unit/test_similarity_service.py tests/integration/test_similarity_api.py -v
```

Expected:

- PASS for all atlas and similarity backend tests

- [ ] **Step 2: Run targeted frontend verification**

Run:

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart/frontend/similarity
npm test
npm run build
```

Expected:

- PASS for all similarity frontend tests
- build succeeds and emits `dist/`

- [ ] **Step 3: Run full repo regression**

Run:

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart
uv run pytest -v
```

Expected:

- PASS for the full Python suite

- [ ] **Step 4: Commit any final polish or test-only fixes**

If verification required small follow-up edits:

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart
git add -A
git commit -m "test: finalize similarity graph semantics rollout"
```

If no further edits were needed after verification, skip this step.

## Self-Review

### Spec coverage

- Better region titles and label anchors: Task 1
- `label`, `canonical_title`, `duplicate_title_count`, `degree`, `label_priority`: Task 2
- `edge_type`, `graph_kind`, `edge_scope`, additive rollout: Task 2
- `labelMode`, progressive labels, selected summary, CTA handoff: Tasks 3 and 4
- no migration, no inline explorer: preserved by task boundaries

### Placeholder scan

- No `TODO`, `TBD`, or deferred implementation notes remain in task steps.
- Every code-changing step contains concrete code or assertions.

### Type consistency

- Backend node fields in Task 2 match frontend contract updates in Task 3.
- `labelMode` naming is consistent between App and trace builder.
- `reason` remains additive-compatible while `edge_type` becomes authoritative.
