# Cluster Similarity Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a separate `/similarity` page that renders a Plotly 3.5.0 cluster similarity graph from Memoria backend data without changing `/atlas`.

**Architecture:** Reuse the latest published atlas run as the data source, but expose it through a separate read-side service and `GET /similarity/graph` endpoint. Serve a new `frontend/similarity` bundle that loads Plotly from the requested CDN, renders graph traces close to the local prototype, and keeps Plotly-native interactions intact.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.x, pytest, React, TypeScript, Vite, Vitest, Plotly 3.5.0 from CDN

---

## Current Context

Verified repository state before writing the plan:

- atlas read-side already exists under `src/memoria/atlas/`
- atlas frontend bundle already exists under `frontend/atlas`
- `src/memoria/api/app.py` already knows how to mount one separately built frontend
- there is no `similarity` router, service, schema, or frontend bundle yet
- the target prototype lives outside the repo at:
  - `/home/xai/Downloads/memoria_cluster_similarity_network.html`
  - `/home/xai/Downloads/memoria_visualization_recommendations.md`

Implementation constraints:

- `/similarity` must stay separate from `/atlas`
- Plotly must come from `https://cdn.plot.ly/plotly-3.5.0.min.js`
- MVP uses existing atlas outputs as the source of truth
- no new persistence tables or migrations are required for MVP

## File Structure

### Existing files to modify

- `src/memoria/api/app.py`
  Register the new router and serve the new frontend bundle.
- `src/memoria/api/schemas.py`
  Add similarity graph response models.
- `tests/integration/test_api_routes.py` or the nearest existing app wiring test file
  Verify the new route is mounted if such a test already exists.

### New backend files

- `src/memoria/similarity/__init__.py`
  Package marker.
- `src/memoria/similarity/service.py`
  Read-side graph assembly from atlas regions and edges.
- `src/memoria/api/similarity.py`
  FastAPI router and HTML/static mounting for `/similarity`.
- `tests/unit/test_similarity_service.py`
  Service-level graph transformation tests.
- `tests/integration/test_similarity_api.py`
  Endpoint contract tests.

### New frontend files

- `frontend/similarity/package.json`
- `frontend/similarity/package-lock.json`
- `frontend/similarity/tsconfig.json`
- `frontend/similarity/vite.config.ts`
- `frontend/similarity/index.html`
- `frontend/similarity/src/main.tsx`
- `frontend/similarity/src/App.tsx`
- `frontend/similarity/src/styles.css`
- `frontend/similarity/src/api/client.ts`
- `frontend/similarity/src/api/contracts.ts`
- `frontend/similarity/src/lib/plotly.ts`
- `frontend/similarity/src/lib/traces.ts`
- `frontend/similarity/src/lib/traces.test.ts`
- `frontend/similarity/src/App.test.tsx`
- `frontend/similarity/src/setupTests.ts`

## Task 1: Add Similarity Graph Backend Contracts And Service

**Files:**
- Create: `src/memoria/similarity/__init__.py`
- Create: `src/memoria/similarity/service.py`
- Modify: `src/memoria/api/schemas.py`
- Test: `tests/unit/test_similarity_service.py`

- [ ] **Step 1: Write the failing unit test for graph assembly**

```python
def test_build_similarity_graph_groups_nodes_by_category_and_filters_weak_edges(session):
    overview = get_similarity_graph(session, min_cluster_size=2, min_edge_weight=0.3)

    assert [node.region_key for node in overview.nodes] == ["region-a", "region-b"]
    assert overview.legend[0].category == "social"
    assert [(edge.source_region_key, edge.target_region_key) for edge in overview.edges] == [
        ("region-a", "region-b")
    ]
```

- [ ] **Step 2: Run the unit test to verify it fails**

Run:

```bash
uv run pytest tests/unit/test_similarity_service.py::test_build_similarity_graph_groups_nodes_by_category_and_filters_weak_edges -v
```

Expected:

```text
FAILED tests/unit/test_similarity_service.py::test_build_similarity_graph_groups_nodes_by_category_and_filters_weak_edges
```

- [ ] **Step 3: Add response schemas and the minimal service implementation**

```python
# src/memoria/api/schemas.py
class SimilarityGraphRunResponse(BaseModel):
    atlas_run_id: int
    atlas_key: str
    generated_at: datetime
    source_count: int


class SimilarityGraphNodeResponse(BaseModel):
    region_key: str
    title: str
    x: float
    y: float
    size: float
    item_count: int
    dominant_screen_category: str
    top_labels: list[str]
    top_apps: list[str]
    top_entities: list[str]
    is_labeled: bool
    representative_source_item_ids: list[int]


class SimilarityGraphEdgeResponse(BaseModel):
    source_region_key: str
    target_region_key: str
    weight: float
    support: int
    reason: str


class SimilarityGraphLegendEntryResponse(BaseModel):
    category: str
    color: str
    count: int


class SimilarityGraphResponse(BaseModel):
    run: SimilarityGraphRunResponse | None
    nodes: list[SimilarityGraphNodeResponse]
    edges: list[SimilarityGraphEdgeResponse]
    legend: list[SimilarityGraphLegendEntryResponse]
    filters: AtlasFiltersResponse
```

```python
# src/memoria/similarity/service.py
from dataclasses import dataclass
from sqlalchemy.orm import Session

from memoria.atlas.service import _get_latest_published_run


@dataclass(frozen=True, slots=True)
class SimilarityGraphFilters:
    min_cluster_size: int = 1
    min_edge_weight: float = 0.0
    app_hint: str | None = None
    observed_from: datetime | None = None
    observed_to: datetime | None = None
    has_knowledge: bool | None = None
    search_query: str | None = None


def get_similarity_graph(session: Session, *, filters: SimilarityGraphFilters) -> SimilarityGraph:
    atlas_run = _get_latest_published_run(session)
    if atlas_run is None:
        return SimilarityGraph(run=None, nodes=[], edges=[], legend=[], filters=filters)

    regions = _load_similarity_regions(session, atlas_run_id=atlas_run.id, min_cluster_size=filters.min_cluster_size)
    region_keys = {region.region_key for region in regions}
    edges = _load_similarity_edges(
        session,
        atlas_run_id=atlas_run.id,
        region_keys=region_keys,
        min_edge_weight=filters.min_edge_weight,
    )
    legend = _build_legend(regions)
    return SimilarityGraph(
        run=_build_run_view(atlas_run),
        nodes=regions,
        edges=edges,
        legend=legend,
        filters=filters,
    )
```

- [ ] **Step 4: Run the unit test and the full unit file**

Run:

```bash
uv run pytest tests/unit/test_similarity_service.py -v
```

Expected:

```text
PASSED tests/unit/test_similarity_service.py::test_build_similarity_graph_groups_nodes_by_category_and_filters_weak_edges
```

- [ ] **Step 5: Commit the backend graph contracts**

```bash
git add src/memoria/api/schemas.py src/memoria/similarity/__init__.py src/memoria/similarity/service.py tests/unit/test_similarity_service.py
git commit -m "feat: add similarity graph service"
```

## Task 2: Expose `GET /similarity/graph` And Serve `/similarity`

**Files:**
- Create: `src/memoria/api/similarity.py`
- Modify: `src/memoria/api/app.py`
- Test: `tests/integration/test_similarity_api.py`

- [ ] **Step 1: Write the failing integration test for the graph endpoint**

```python
def test_similarity_graph_endpoint_returns_nodes_edges_and_legend(client):
    response = client.get("/similarity/graph?min_cluster_size=2&min_edge_weight=0.25")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["atlas_key"] == "screenshots_atlas_v1"
    assert payload["nodes"][0]["region_key"] == "region-social"
    assert payload["edges"][0]["reason"] == "shared_topic_task_signature"
    assert payload["legend"][0]["category"] == "social"
```

- [ ] **Step 2: Run the integration test and verify it fails**

Run:

```bash
uv run pytest tests/integration/test_similarity_api.py::test_similarity_graph_endpoint_returns_nodes_edges_and_legend -v
```

Expected:

```text
FAILED tests/integration/test_similarity_api.py::test_similarity_graph_endpoint_returns_nodes_edges_and_legend
```

- [ ] **Step 3: Add the router and mount it in the app**

```python
# src/memoria/api/similarity.py
from fastapi import APIRouter
from sqlalchemy.orm import Session

from memoria.similarity.service import SimilarityGraphFilters
from memoria.similarity.service import get_similarity_graph


def create_similarity_router(*, engine, frontend_dist_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/similarity/graph", response_model=SimilarityGraphResponse)
    def similarity_graph_endpoint(
        min_cluster_size: int = 1,
        min_edge_weight: float = 0.0,
        app_hint: str | None = None,
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
        has_knowledge: bool | None = None,
        search_query: str | None = None,
    ) -> SimilarityGraphResponse:
        with Session(engine) as session:
            return get_similarity_graph(
                session,
                filters=SimilarityGraphFilters(
                    min_cluster_size=min_cluster_size,
                    min_edge_weight=min_edge_weight,
                    app_hint=app_hint,
                    observed_from=observed_from,
                    observed_to=observed_to,
                    has_knowledge=has_knowledge,
                    search_query=search_query,
                ),
            )

    router.mount(
        "/similarity/assets",
        StaticFiles(directory=frontend_dist_dir / "assets"),
        name="similarity-assets",
    )

    @router.get("/similarity", response_class=FileResponse)
    def similarity_index() -> FileResponse:
        return FileResponse(frontend_dist_dir / "index.html")

    return router
```

```python
# src/memoria/api/app.py
from memoria.api.similarity import create_similarity_router

app.include_router(
    create_similarity_router(
        engine=engine,
        frontend_dist_dir=similarity_frontend_dist_dir or project_root / "frontend/similarity/dist",
    )
)
```

- [ ] **Step 4: Run the similarity API tests**

Run:

```bash
uv run pytest tests/integration/test_similarity_api.py -v
```

Expected:

```text
PASSED tests/integration/test_similarity_api.py::test_similarity_graph_endpoint_returns_nodes_edges_and_legend
```

- [ ] **Step 5: Commit the API layer**

```bash
git add src/memoria/api/app.py src/memoria/api/similarity.py tests/integration/test_similarity_api.py
git commit -m "api: add similarity graph endpoint"
```

## Task 3: Scaffold `frontend/similarity` And Plotly Loader

**Files:**
- Create: `frontend/similarity/package.json`
- Create: `frontend/similarity/package-lock.json`
- Create: `frontend/similarity/tsconfig.json`
- Create: `frontend/similarity/vite.config.ts`
- Create: `frontend/similarity/index.html`
- Create: `frontend/similarity/src/main.tsx`
- Create: `frontend/similarity/src/App.tsx`
- Create: `frontend/similarity/src/styles.css`
- Create: `frontend/similarity/src/api/client.ts`
- Create: `frontend/similarity/src/api/contracts.ts`
- Create: `frontend/similarity/src/lib/plotly.ts`
- Create: `frontend/similarity/src/setupTests.ts`
- Test: `frontend/similarity/src/App.test.tsx`

- [ ] **Step 1: Write the failing frontend smoke test**

```tsx
it("loads the similarity graph payload and renders the page chrome", async () => {
  render(<App />);

  expect(await screen.findByText("Cluster similarity network")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith("/similarity/graph");
});
```

- [ ] **Step 2: Run the frontend test and verify it fails**

Run:

```bash
cd frontend/similarity && npm test
```

Expected:

```text
FAIL src/App.test.tsx
```

- [ ] **Step 3: Add the minimal bundle with Plotly CDN loading**

```html
<!-- frontend/similarity/index.html -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Memoria similarity graph</title>
    <script src="https://cdn.plot.ly/plotly-3.5.0.min.js"></script>
    <script>
      window.__PLOTLY_CDN_VERSION__ = "3.5.0";
    </script>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

```tsx
// frontend/similarity/src/App.tsx
export default function App() {
  const [graph, setGraph] = useState<SimilarityGraphResponse | null>(null);

  useEffect(() => {
    void fetchSimilarityGraph().then(setGraph);
  }, []);

  return (
    <main className="similarity-page">
      <header className="similarity-page__header">
        <h1>Cluster similarity network</h1>
        <p>Shared topic/task signatures across screenshot clusters.</p>
      </header>
      <section aria-label="Similarity graph stage" className="similarity-page__stage">
        <div id="similarity-plot" />
      </section>
    </main>
  );
}
```

```ts
// frontend/similarity/src/lib/plotly.ts
export type PlotlyLike = {
  newPlot: (element: HTMLElement, data: unknown[], layout: unknown, config: unknown) => Promise<unknown>;
  react: (element: HTMLElement, data: unknown[], layout: unknown, config: unknown) => Promise<unknown>;
};

export function resolvePlotly(): PlotlyLike {
  const plotly = (window as Window & { Plotly?: PlotlyLike }).Plotly;
  if (!plotly) {
    throw new Error("Plotly 3.5.0 CDN failed to load.");
  }
  return plotly;
}
```

- [ ] **Step 4: Run the frontend test and build**

Run:

```bash
cd frontend/similarity && npm test
cd frontend/similarity && npm run build
```

Expected:

```text
PASS src/App.test.tsx
vite v5...
✓ built in ...
```

- [ ] **Step 5: Commit the scaffold**

```bash
git add frontend/similarity
git commit -m "feat: scaffold similarity frontend"
```

## Task 4: Build Plotly Traces Close To The Local Prototype

**Files:**
- Create: `frontend/similarity/src/lib/traces.ts`
- Create: `frontend/similarity/src/lib/traces.test.ts`
- Modify: `frontend/similarity/src/App.tsx`
- Modify: `frontend/similarity/src/styles.css`

- [ ] **Step 1: Write the failing trace-construction test**

```ts
it("builds one edge trace, one node trace per category, and a sparse label trace", () => {
  const figure = buildSimilarityFigure(graphFixture, { showLabels: true, selectedRegionKey: null });

  expect(figure.data[0]).toMatchObject({ mode: "lines", showlegend: false });
  expect(figure.data.some((trace) => trace.name === "social")).toBe(true);
  expect(figure.data.some((trace) => trace.mode === "text")).toBe(true);
});
```

- [ ] **Step 2: Run the trace test and verify it fails**

Run:

```bash
cd frontend/similarity && npm test -- traces.test.ts
```

Expected:

```text
FAIL src/lib/traces.test.ts
```

- [ ] **Step 3: Implement the figure builder and wire it into `App.tsx`**

```ts
// frontend/similarity/src/lib/traces.ts
export function buildSimilarityFigure(
  graph: SimilarityGraphResponse,
  options: { showLabels: boolean; selectedRegionKey: string | null },
) {
  const edgeTrace = {
    type: "scattergl",
    mode: "lines",
    hoverinfo: "skip",
    showlegend: false,
    line: { color: "rgba(180,220,220,0.20)", width: 0.6 },
    x: edgeXs(graph.edges, graph.nodes),
    y: edgeYs(graph.edges, graph.nodes),
  };

  const nodeTraces = graph.legend.map((entry) => ({
    type: "scattergl",
    mode: "markers",
    name: entry.category,
    x: graph.nodes.filter((node) => node.dominant_screen_category === entry.category).map((node) => node.x),
    y: graph.nodes.filter((node) => node.dominant_screen_category === entry.category).map((node) => node.y),
    text: graph.nodes.filter((node) => node.dominant_screen_category === entry.category).map((node) => node.title),
    customdata: graph.nodes
      .filter((node) => node.dominant_screen_category === entry.category)
      .map((node) => [node.region_key, node.item_count, node.top_labels.join(", "), node.top_apps.join(", ")]),
    marker: {
      size: graph.nodes
        .filter((node) => node.dominant_screen_category === entry.category)
        .map((node) => node.size),
      color: entry.color,
      opacity: 0.88,
      line: { color: "rgba(10,18,24,0.55)", width: 0.8 },
    },
    hovertemplate:
      "<b>%{text}</b><br>%{customdata[1]} items<br>%{customdata[2]}<br>%{customdata[3]}<extra></extra>",
  }));

  const labelTrace = {
    type: "scattergl",
    mode: "text",
    showlegend: false,
    hoverinfo: "skip",
    text: labeledNodes(graph.nodes, options).map((node) => node.title),
    x: labeledNodes(graph.nodes, options).map((node) => node.x),
    y: labeledNodes(graph.nodes, options).map((node) => node.y),
    textfont: { color: "rgba(235,242,247,0.82)", size: 10 },
  };

  return {
    data: [edgeTrace, ...nodeTraces, labelTrace],
    layout: {
      paper_bgcolor: "#001f2d",
      plot_bgcolor: "#001f2d",
      title: { text: "Memoria screenshots — cluster similarity network (shared topic/task signatures)", x: 0.02 },
      xaxis: { showgrid: false, zeroline: false, showticklabels: false },
      yaxis: { showgrid: false, zeroline: false, showticklabels: false },
      legend: { x: 1.02, y: 1, bgcolor: "rgba(0,0,0,0)", title: { text: "dominant screen category" } },
      margin: { l: 30, r: 180, t: 60, b: 30 },
      hoverlabel: { bgcolor: "rgba(15,20,25,0.95)", font: { size: 12 } },
    },
    config: { displaylogo: false, scrollZoom: true, responsive: true },
  };
}
```

```tsx
// frontend/similarity/src/App.tsx
const figure = useMemo(() => {
  if (!graph) {
    return null;
  }
  return buildSimilarityFigure(graph, { showLabels, selectedRegionKey });
}, [graph, selectedRegionKey, showLabels]);

useEffect(() => {
  if (!figure || !plotRef.current) {
    return;
  }
  const Plotly = resolvePlotly();
  void Plotly.react(plotRef.current, figure.data, figure.layout, figure.config);
}, [figure]);
```

- [ ] **Step 4: Run frontend tests and the production build**

Run:

```bash
cd frontend/similarity && npm test
cd frontend/similarity && npm run build
```

Expected:

```text
PASS src/lib/traces.test.ts
PASS src/App.test.tsx
✓ built in ...
```

- [ ] **Step 5: Commit the Plotly figure layer**

```bash
git add frontend/similarity/src/App.tsx frontend/similarity/src/styles.css frontend/similarity/src/lib/traces.ts frontend/similarity/src/lib/traces.test.ts
git commit -m "feat: render similarity graph with plotly"
```

## Task 5: Add Selection, Controls, And Live Verification

**Files:**
- Modify: `frontend/similarity/src/App.tsx`
- Modify: `frontend/similarity/src/api/client.ts`
- Modify: `frontend/similarity/src/api/contracts.ts`
- Test: `frontend/similarity/src/App.test.tsx`
- Test: `tests/integration/test_similarity_api.py`

- [ ] **Step 1: Write the failing UI test for controls and node selection**

```tsx
it("refetches with thresholds and highlights the clicked cluster", async () => {
  render(<App />);

  await screen.findByText("Cluster similarity network");
  await user.type(screen.getByLabelText("Min cluster size"), "8");
  await user.click(screen.getByRole("button", { name: "Apply graph filters" }));

  expect(lastRequestUrl(fetchMock).searchParams.get("min_cluster_size")).toBe("8");
});
```

- [ ] **Step 2: Run the UI test and verify it fails**

Run:

```bash
cd frontend/similarity && npm test -- App.test.tsx
```

Expected:

```text
FAIL src/App.test.tsx
```

- [ ] **Step 3: Implement controls, selection, and fetch wiring**

```tsx
// frontend/similarity/src/App.tsx
const [minClusterSize, setMinClusterSize] = useState(2);
const [minEdgeWeight, setMinEdgeWeight] = useState(0.15);
const [showLabels, setShowLabels] = useState(true);
const [selectedRegionKey, setSelectedRegionKey] = useState<string | null>(null);

async function loadGraph() {
  const next = await fetchSimilarityGraph({ minClusterSize, minEdgeWeight });
  setGraph(next);
}

function handleApplyFilters(event: FormEvent) {
  event.preventDefault();
  void loadGraph();
}
```

```ts
// frontend/similarity/src/api/client.ts
export async function fetchSimilarityGraph(query: {
  minClusterSize?: number;
  minEdgeWeight?: number;
} = {}): Promise<SimilarityGraphResponse> {
  const url = new URL("/similarity/graph", window.location.origin);
  if (query.minClusterSize !== undefined) {
    url.searchParams.set("min_cluster_size", String(query.minClusterSize));
  }
  if (query.minEdgeWeight !== undefined) {
    url.searchParams.set("min_edge_weight", String(query.minEdgeWeight));
  }
  const response = await fetch(url.pathname + url.search);
  if (!response.ok) {
    throw new Error("Could not load similarity graph.");
  }
  return response.json();
}
```

- [ ] **Step 4: Run targeted tests, then end-to-end verification commands**

Run:

```bash
cd frontend/similarity && npm test
uv run pytest tests/integration/test_similarity_api.py -v
cd frontend/similarity && npm run build
```

Expected:

```text
PASS src/App.test.tsx
PASSED tests/integration/test_similarity_api.py::...
✓ built in ...
```

Then run a live smoke in the worktree:

```bash
cd /home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart
MEMORIA_DATABASE_URL="sqlite:///$PWD/data/memoria.db" uv run --active --with uvicorn python -c 'from pathlib import Path; import uvicorn; from memoria.api.app import create_app; uvicorn.run(create_app(blob_dir=Path("var/blobs")), host="127.0.0.1", port=8001)'
```

Open:

```text
http://127.0.0.1:8001/similarity
```

Confirm:

- Plotly graph loads on dark background
- legend appears on the right
- wheel zoom and reset axes work
- clicking a node highlights the selected cluster
- thresholds change the fetched graph

- [ ] **Step 5: Commit the finished similarity graph MVP**

```bash
git add frontend/similarity src/memoria/api/app.py src/memoria/api/schemas.py src/memoria/api/similarity.py src/memoria/similarity tests/unit/test_similarity_service.py tests/integration/test_similarity_api.py
git commit -m "feat: add cluster similarity graph page"
```

## Self-Review Checklist

- Spec coverage:
  - separate `/similarity` page: Tasks 2-5
  - Plotly 3.5.0 CDN: Task 3
  - graph-ready backend payload: Tasks 1-2
  - prototype-like visuals: Task 4
  - controls and selection: Task 5
- Placeholder scan:
  - no `TODO`, `TBD`, or "appropriate handling" placeholders remain
- Type consistency:
  - backend response names mirror the design doc:
    `run`, `nodes`, `edges`, `legend`, `filters`

