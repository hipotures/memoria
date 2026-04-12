import { useEffect, useRef, useState } from "react";

import { fetchSimilarityGraph } from "./api/client";
import type { SimilarityGraphResponse } from "./api/contracts";
import { resolvePlotly } from "./lib/plotly";
import { buildSimilarityFigure } from "./lib/traces";

type LoadState = "loading" | "ready" | "error";

export default function App() {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [graph, setGraph] = useState<SimilarityGraphResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void fetchSimilarityGraph()
      .then((response) => {
        if (cancelled) {
          return;
        }

        setGraph(response);
        setLoadState("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }

        setLoadState("error");
        setErrorMessage(
          error instanceof Error ? error.message : "Could not load the similarity graph.",
        );
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (graph === null || stageRef.current === null) {
      return;
    }

    const plotly = resolvePlotly();
    const figure = buildSimilarityFigure(graph, {
      showLabels: true,
      selectedRegionKey: null,
    });

    void plotly.newPlot(
      stageRef.current,
      figure.data,
      figure.layout,
      figure.config,
    );
  }, [graph]);

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
          <p>{graph?.run ? `Atlas source: ${graph.run.atlas_key}` : "Atlas source unavailable"}</p>
        </footer>
      </section>
    </main>
  );
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
