import { useEffect, useRef, useState } from "react";

import { fetchSimilarityGraph } from "./api/client";
import type { SimilarityGraphResponse } from "./api/contracts";
import { resolvePlotly } from "./lib/plotly";
import { buildSimilarityFigure } from "./lib/traces";

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
type PlotlyStageElement = HTMLDivElement & {
  on?: (eventName: string, handler: (event: PlotlyClickEvent) => void) => unknown;
  __memoriaSimilarityClickBound__?: boolean;
};

export default function App() {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const mountedRef = useRef(false);
  const plotReadyRef = useRef(false);
  const activeRequestIdRef = useRef(0);
  const [graph, setGraph] = useState<SimilarityGraphResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [minClusterSizeInput, setMinClusterSizeInput] = useState("1");
  const [minEdgeWeightInput, setMinEdgeWeightInput] = useState("0");
  const [showLabels, setShowLabels] = useState(true);
  const [selectedRegionKey, setSelectedRegionKey] = useState<string | null>(null);

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

    const figure = buildSimilarityFigure(graph, { showLabels, selectedRegionKey });
    const stage = stageRef.current as PlotlyStageElement;
    const renderPlot = plotReadyRef.current ? plotly.react : plotly.newPlot;

    void renderPlot(stage, figure.data, figure.layout, figure.config)
      .then(() => {
        plotReadyRef.current = true;

        if (!stage.__memoriaSimilarityClickBound__ && typeof stage.on === "function") {
          stage.on("plotly_click", handlePlotlyClick);
          stage.__memoriaSimilarityClickBound__ = true;
        }
      })
      .catch((error: unknown) => {
        applyErrorState(error);
      });
  }, [graph, selectedRegionKey, showLabels]);

  const selectedNode = graph?.nodes.find((node) => node.region_key === selectedRegionKey) ?? null;

  return (
    <main className="similarity-app-shell">
      <section className="similarity-hero">
        <p className="similarity-hero__eyebrow">Semantic atlas restart</p>
        <h1>Cluster similarity network</h1>
        <p className="similarity-hero__lede">
          Shared topic and task signatures across screenshot clusters, rendered as a dedicated
          Plotly overview from the <code>/similarity</code> bundle.
        </p>
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

        <form onSubmit={handleApplyFilters}>
          <label>
            Min cluster size
            <input
              type="number"
              min="0"
              step="1"
              value={minClusterSizeInput}
              onChange={(event) => {
                setMinClusterSizeInput(event.target.value);
              }}
            />
          </label>
          <label>
            Min edge weight
            <input
              type="number"
              min="0"
              step="0.01"
              value={minEdgeWeightInput}
              onChange={(event) => {
                setMinEdgeWeightInput(event.target.value);
              }}
            />
          </label>
          <label>
            Show labels
            <input
              type="checkbox"
              checked={showLabels}
              onChange={(event) => {
                setShowLabels(event.target.checked);
              }}
            />
          </label>
          <button type="submit">Apply graph filters</button>
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
    setGraph(response);
    setLoadState("ready");
    setErrorMessage(null);
    setSelectedRegionKey(null);
    setMinClusterSizeInput(String(response.filters.min_cluster_size ?? minClusterSizeInput));
    setMinEdgeWeightInput(String(response.filters.min_edge_weight ?? minEdgeWeightInput));
  }

  function applyErrorState(error: unknown): void {
    setLoadState("error");
    setErrorMessage(
      error instanceof Error ? error.message : "Could not load the similarity graph.",
    );
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
      setSelectedRegionKey(clickedRegionKey);
    }
  }

  function shouldHandleRequest(requestId: number): boolean {
    return mountedRef.current && activeRequestIdRef.current === requestId;
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
