import { useEffect, useRef, useState } from "react";

import { fetchSimilarityGraph } from "./api/client";
import type { SimilarityGraphResponse } from "./api/contracts";
import { resolvePlotly } from "./lib/plotly";
import { buildSimilarityFigure } from "./lib/traces";
import type { LabelMode } from "./lib/traces";

type LoadState = "loading" | "ready" | "error";
type GraphQuery = {
  minClusterSize?: number;
  minEdgeWeight?: number;
};
type PlotlyClickPoint = {
  customdata?: unknown;
  data?: { name?: unknown };
  pointNumber?: unknown;
};
type PlotlyClickEvent = {
  points?: PlotlyClickPoint[];
};
type PlotlyLegendEvent = {
  curveNumber?: unknown;
  data?: { name?: unknown };
};
type PlotlyTraceState = {
  name?: unknown;
};
type PlotlyStageElement = HTMLDivElement & {
  on?: (
    eventName: string,
    handler: ((event: PlotlyClickEvent) => void) | ((event: PlotlyLegendEvent) => boolean),
  ) => unknown;
  __memoriaSimilarityClickBound__?: boolean;
  data?: PlotlyTraceState[];
};

export default function App() {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const mountedRef = useRef(false);
  const plotReadyRef = useRef(false);
  const activeRequestIdRef = useRef(0);
  const graphRef = useRef<SimilarityGraphResponse | null>(null);
  const visibleCategoriesRef = useRef<Set<string> | null>(null);
  const [graph, setGraph] = useState<SimilarityGraphResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [minClusterSizeInput, setMinClusterSizeInput] = useState("1");
  const [minEdgeWeightInput, setMinEdgeWeightInput] = useState("0");
  const [labelMode, setLabelMode] = useState<LabelMode>("default");
  const [selectedRegionKey, setSelectedRegionKey] = useState<string | null>(null);
  const [visibleCategories, setVisibleCategories] = useState<Set<string> | null>(null);

  useEffect(() => {
    graphRef.current = graph;
  }, [graph]);

  useEffect(() => {
    visibleCategoriesRef.current = visibleCategories;
  }, [visibleCategories]);

  useEffect(() => {
    mountedRef.current = true;
    startGraphLoad();

    return () => {
      mountedRef.current = false;
      activeRequestIdRef.current += 1;
    };
  }, []);

  useEffect(() => {
    if (graph === null || stageRef.current === null) {
      return;
    }

    let plotly;
    try {
      plotly = resolvePlotly();
    } catch (error: unknown) {
      applyErrorState(error);
      return;
    }

    const figure = buildSimilarityFigure(graph, {
      labelMode,
      selectedRegionKey,
      visibleCategories,
    });
    const stage = stageRef.current as PlotlyStageElement;
    const renderPlot = plotReadyRef.current ? plotly.react : plotly.newPlot;
    const renderPromise = renderPlot(stage, figure.data, figure.layout, figure.config);
    bindPlotlyHandlers(stage);

    void renderPromise
      .then(() => {
        plotReadyRef.current = true;
        bindPlotlyHandlers(stage);
      })
      .catch((error: unknown) => {
        applyErrorState(error);
      });
  }, [graph, labelMode, selectedRegionKey, visibleCategories]);

  useEffect(() => {
    if (
      graph === null ||
      selectedRegionKey === null ||
      visibleCategories === null ||
      isRegionVisible(graph, selectedRegionKey, visibleCategories)
    ) {
      return;
    }

    setSelectedRegionKey(null);
  }, [graph, selectedRegionKey, visibleCategories]);

  const selectedNode = graph?.nodes.find((node) => node.region_key === selectedRegionKey) ?? null;
  const regionDetailsHref =
    selectedNode === null
      ? null
      : buildAtlasHandoffUrl(`/atlas/regions/${encodeURIComponent(selectedNode.region_key)}`);
  const evidenceHref =
    selectedNode === null
      ? null
      : buildAtlasHandoffUrl("/atlas/evidence", { region_key: selectedNode.region_key });

  return (
    <main className="similarity-app-shell">
      <section className="similarity-hero">
        <p className="similarity-hero__eyebrow">Semantic atlas restart</p>
        <h1>Cluster similarity network</h1>
        <p className="similarity-hero__lede">
          Region-to-region semantic similarity across atlas regions, with lightweight handoff into
          atlas drill-down.
        </p>
        <p>{graph ? `Graph kind: ${graph.graph_kind}` : "Graph kind unavailable"}</p>
        <p>{graph ? `Edge scope: ${graph.edge_scope}` : "Edge scope unavailable"}</p>
      </section>

      <section className="similarity-stage-card">
        <header className="similarity-stage-card__header">
          <div>
            <p className="similarity-stage-card__label">Similarity graph stage</p>
            <h2>Overview graph</h2>
          </div>
          <div className="similarity-stage-card__meta" aria-label="Similarity graph summary">
            <span>{statusLabel(loadState)}</span>
            <span>{graph ? `${graph.nodes.length} clusters` : "Waiting for graph payload"}</span>
            <span>{graph ? `${graph.edges.length} edges` : "No edges yet"}</span>
          </div>
        </header>

        <form className="similarity-controls" onSubmit={handleApplyFilters}>
          <label className="similarity-control">
            <span className="similarity-control__label">Min cluster size</span>
            <input
              className="similarity-control__input"
              type="number"
              min="0"
              step="1"
              value={minClusterSizeInput}
              onChange={(event) => {
                setMinClusterSizeInput(event.target.value);
              }}
            />
          </label>
          <label className="similarity-control">
            <span className="similarity-control__label">Min edge weight</span>
            <input
              className="similarity-control__input"
              type="number"
              min="0"
              step="0.01"
              value={minEdgeWeightInput}
              onChange={(event) => {
                setMinEdgeWeightInput(event.target.value);
              }}
            />
          </label>
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
          <button className="similarity-controls__submit" type="submit">
            Apply graph filters
          </button>
        </form>

        <div className="similarity-stage-card__stage">
          <div
            ref={stageRef}
            id="similarity-plot"
            className="similarity-stage-card__plot"
            aria-label="Similarity graph stage"
          />
          {loadState === "loading" ? (
            <p className="similarity-stage-card__overlay">Loading graph payload…</p>
          ) : null}
          {loadState === "error" && errorMessage !== null ? (
            <p className="similarity-stage-card__overlay similarity-stage-card__overlay--error">
              {errorMessage}
            </p>
          ) : null}
        </div>

        {selectedNode ? (
          <aside className="similarity-selection-card" aria-label="Selected similarity region">
            <h3>{selectedNode.label}</h3>
            <dl>
              <div>
                <dt>Title</dt>
                <dd>{selectedNode.title}</dd>
              </div>
              <div>
                <dt>Region key</dt>
                <dd>{selectedNode.region_key}</dd>
              </div>
              <div>
                <dt>Items</dt>
                <dd>{selectedNode.item_count}</dd>
              </div>
              <div>
                <dt>Category</dt>
                <dd>{selectedNode.dominant_screen_category}</dd>
              </div>
              <div>
                <dt>Degree</dt>
                <dd>{selectedNode.degree}</dd>
              </div>
            </dl>
            <p>{selectedNode.top_labels.slice(0, 5).join(", ")}</p>
            <p>{selectedNode.top_apps.slice(0, 3).join(", ")}</p>
            <div className="similarity-selection-card__actions">
              <a href={regionDetailsHref ?? "#"}>Region details</a>
              <a href={evidenceHref ?? "#"}>Evidence</a>
            </div>
          </aside>
        ) : null}

        <footer className="similarity-stage-card__footer">
          <p>
            CDN Plotly version: <code>{window.__PLOTLY_CDN_VERSION__ ?? "missing"}</code>
          </p>
          <p>
            Active thresholds: cluster size{" "}
            <code>{graph?.filters.min_cluster_size ?? minClusterSizeInput}</code>, edge weight{" "}
            <code>{graph?.filters.min_edge_weight ?? minEdgeWeightInput}</code>
          </p>
          <p>{selectedNode ? `Selected cluster: ${selectedNode.title}` : "Selected cluster: none"}</p>
          <p>{graph?.run ? `Atlas source: ${graph.run.atlas_key}` : "Atlas source unavailable"}</p>
        </footer>
      </section>
    </main>
  );

  function startGraphLoad(query: GraphQuery = {}): void {
    const requestId = activeRequestIdRef.current + 1;
    activeRequestIdRef.current = requestId;
    setLoadState("loading");
    setErrorMessage(null);

    void fetchSimilarityGraph(query)
      .then((response) => {
        if (!shouldHandleRequest(requestId)) {
          return;
        }

        syncGraphState(response);
      })
      .catch((error: unknown) => {
        if (!shouldHandleRequest(requestId)) {
          return;
        }

        applyErrorState(error);
      });
  }

  function syncGraphState(response: SimilarityGraphResponse): void {
    const nextVisibleCategories = new Set(response.legend.map((entry) => entry.category));
    graphRef.current = response;
    setGraph(response);
    visibleCategoriesRef.current = nextVisibleCategories;
    setVisibleCategories(nextVisibleCategories);
    setLoadState("ready");
    setErrorMessage(null);
    setSelectedRegionKey(null);
    setMinClusterSizeInput(String(response.filters.min_cluster_size ?? minClusterSizeInput));
    setMinEdgeWeightInput(String(response.filters.min_edge_weight ?? minEdgeWeightInput));
  }

  function applyErrorState(error: unknown): void {
    setGraph(null);
    setVisibleCategories(null);
    setSelectedRegionKey(null);
    setLoadState("error");
    setErrorMessage(
      error instanceof Error ? error.message : "Could not load the similarity graph.",
    );
    plotReadyRef.current = false;
    stageRef.current?.replaceChildren();
  }

  function handleApplyFilters(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();

    startGraphLoad({
      minClusterSize: parseInteger(minClusterSizeInput, graph?.filters.min_cluster_size ?? 1),
      minEdgeWeight: parseFloatValue(minEdgeWeightInput, graph?.filters.min_edge_weight ?? 0),
    });
  }

  function handlePlotlyClick(event: PlotlyClickEvent): void {
    const point = event.points?.[0];
    const clickedRegionKey = resolveClickedRegionKey(point);

    if (clickedRegionKey !== null) {
      setSelectedRegionKey((current) => (current === clickedRegionKey ? null : clickedRegionKey));
    }
  }

  function handlePlotlyLegendClick(event: PlotlyLegendEvent): boolean {
    const category = resolveLegendCategory(event, stageRef.current as PlotlyStageElement | null);
    if (category === null) {
      return false;
    }

    setVisibleCategories(toggleLegendCategory(graphRef.current, visibleCategoriesRef.current, category));
    return false;
  }

  function handlePlotlyLegendDoubleClick(event: PlotlyLegendEvent): boolean {
    const category = resolveLegendCategory(event, stageRef.current as PlotlyStageElement | null);
    if (category === null) {
      return false;
    }

    setVisibleCategories(
      isolateLegendCategory(graphRef.current, visibleCategoriesRef.current, category),
    );
    return false;
  }

  function shouldHandleRequest(requestId: number): boolean {
    return mountedRef.current && activeRequestIdRef.current === requestId;
  }

  function bindPlotlyHandlers(stage: PlotlyStageElement): void {
    if (stage.__memoriaSimilarityClickBound__ || typeof stage.on !== "function") {
      return;
    }

    stage.on("plotly_click", handlePlotlyClick);
    stage.on("plotly_legendclick", handlePlotlyLegendClick);
    stage.on("plotly_legenddoubleclick", handlePlotlyLegendDoubleClick);
    stage.__memoriaSimilarityClickBound__ = true;
  }
}

function statusLabel(loadState: LoadState): string {
  if (loadState === "loading") {
    return "Loading";
  }

  if (loadState === "error") {
    return "Error";
  }

  return "Ready";
}

function parseInteger(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function parseFloatValue(value: string, fallback: number): number {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function resolveClickedRegionKey(point: PlotlyClickPoint | undefined): string | null {
  if (!point) {
    return null;
  }

  if (typeof point.customdata === "string" && point.customdata.length > 0) {
    return point.customdata;
  }

  if (Array.isArray(point.customdata)) {
    const regionKey = point.customdata[0];
    return typeof regionKey === "string" && regionKey.length > 0 ? regionKey : null;
  }

  return null;
}

function resolveLegendCategory(
  event: PlotlyLegendEvent,
  stage: PlotlyStageElement | null,
): string | null {
  if (typeof event.data?.name === "string" && event.data.name.length > 0) {
    return event.data.name;
  }

  if (typeof event.curveNumber === "number") {
    const traceName = stage?.data?.[event.curveNumber]?.name;
    return typeof traceName === "string" && traceName.length > 0 ? traceName : null;
  }

  return null;
}

function toggleLegendCategory(
  graph: SimilarityGraphResponse | null,
  currentVisibleCategories: Set<string> | null,
  category: string,
): Set<string> | null {
  const allCategories = graph?.legend.map((entry) => entry.category) ?? [];
  if (allCategories.length === 0) {
    return currentVisibleCategories;
  }

  const nextVisibleCategories = new Set(currentVisibleCategories ?? allCategories);
  if (nextVisibleCategories.has(category)) {
    if (nextVisibleCategories.size === 1) {
      return nextVisibleCategories;
    }

    nextVisibleCategories.delete(category);
    return nextVisibleCategories;
  }

  nextVisibleCategories.add(category);
  return nextVisibleCategories;
}

function isolateLegendCategory(
  graph: SimilarityGraphResponse | null,
  currentVisibleCategories: Set<string> | null,
  category: string,
): Set<string> | null {
  const allCategories = graph?.legend.map((entry) => entry.category) ?? [];
  if (allCategories.length === 0) {
    return currentVisibleCategories;
  }

  if (
    currentVisibleCategories !== null &&
    currentVisibleCategories.size === 1 &&
    currentVisibleCategories.has(category)
  ) {
    return new Set(allCategories);
  }

  return new Set([category]);
}

function isRegionVisible(
  graph: SimilarityGraphResponse,
  regionKey: string,
  visibleCategories: Set<string>,
): boolean {
  const node = graph.nodes.find((entry) => entry.region_key === regionKey);
  return node ? visibleCategories.has(node.dominant_screen_category) : false;
}

function buildAtlasHandoffUrl(
  path: string,
  params: Record<string, string> = {},
  currentPath?: string,
): string {
  const url = new URL(resolveAtlasHandoffPath(path, currentPath), "http://memoria.local");

  for (const [key, value] of Object.entries(params)) {
    if (value.length > 0) {
      url.searchParams.set(key, value);
    }
  }

  return `${url.pathname}${url.search}`;
}

function resolveAtlasHandoffPath(path: string, currentPath?: string): string {
  const normalizedCurrentPath = normalizeCurrentPath(currentPath);
  const atlasSuffix = path.startsWith("/atlas/") ? path.slice("/atlas/".length) : null;

  if (
    normalizedCurrentPath !== null &&
    atlasSuffix !== null &&
    normalizedCurrentPath.endsWith("/similarity")
  ) {
    const rootPath = normalizedCurrentPath.slice(0, -"/similarity".length);
    return `${rootPath}/atlas/${atlasSuffix}`;
  }

  return path;
}

function normalizeCurrentPath(currentPath?: string): string | null {
  const rawPath = currentPath ?? (typeof window === "undefined" ? null : window.location.pathname);

  if (rawPath === null) {
    return null;
  }

  const trimmed = rawPath.trim();
  if (trimmed.length === 0) {
    return null;
  }

  return trimmed.endsWith("/") ? trimmed.slice(0, -1) : trimmed;
}
