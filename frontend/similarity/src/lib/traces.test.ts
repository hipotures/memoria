import { describe, expect, it } from "vitest";

import type { SimilarityGraphResponse } from "../api/contracts";
import { buildSimilarityFigure } from "./traces";

describe("buildSimilarityFigure", () => {
  it("builds one edge trace, one node trace per category, and a sparse label trace", () => {
    const figure = buildSimilarityFigure(graphFixture, {
      showLabels: true,
      selectedRegionKey: null,
    });

    expect(figure.data[0]).toMatchObject({
      type: "scattergl",
      mode: "lines",
      showlegend: false,
      hoverinfo: "skip",
    });

    expect(findTrace(figure, "social")).toMatchObject({
      type: "scattergl",
      mode: "markers",
      name: "social",
      customdata: [["region-social", "Social cluster", 21, "social", "telegram, chat", "Telegram"]],
    });
    expect(findTrace(figure, "research")).toMatchObject({
      type: "scattergl",
      mode: "markers",
      name: "research",
    });
    expect(findTrace(figure, "utility")).toMatchObject({
      type: "scattergl",
      mode: "markers",
      name: "utility",
    });
    expect(findTextTrace(figure)).toMatchObject({
      type: "scattergl",
      mode: "text",
      showlegend: false,
      text: ["Social cluster", "Utility cluster"],
    });

    expect(figure.layout).toMatchObject({
      paper_bgcolor: "#001f2d",
      plot_bgcolor: "#001f2d",
      legend: {
        x: 1.02,
        y: 1,
        title: { text: "dominant screen category" },
      },
      hoverlabel: {
        bgcolor: "rgba(15,20,25,0.95)",
      },
    });
    expect(figure.config).toMatchObject({
      displaylogo: false,
      responsive: true,
      scrollZoom: true,
    });
  });

  it("includes the selected region in labels even when it is not otherwise labeled", () => {
    const figure = buildSimilarityFigure(graphFixture, {
      showLabels: true,
      selectedRegionKey: "region-research",
    });

    const labelTrace = findTextTrace(figure);
    expect(labelTrace).toMatchObject({
      mode: "text",
      text: ["Social cluster", "Research cluster", "Utility cluster"],
    });
  });

  it("adds a dedicated highlight marker trace for the selected region", () => {
    const figure = buildSimilarityFigure(graphFixture, {
      showLabels: true,
      selectedRegionKey: "region-research",
    });

    expect(findHighlightTrace(figure)).toMatchObject({
      type: "scattergl",
      mode: "markers",
      name: "selected-highlight",
      showlegend: false,
      hoverinfo: "skip",
      x: [0.68],
      y: [0.23],
      marker: {
        symbol: "circle-open",
        line: {
          color: "rgba(255,255,255,0.95)",
        },
      },
    });
  });

  it("keeps the selected region label visible when showLabels is false", () => {
    const figure = buildSimilarityFigure(graphFixture, {
      showLabels: false,
      selectedRegionKey: "region-research",
    });

    expect(findTextTrace(figure)).toMatchObject({
      mode: "text",
      text: ["Research cluster"],
      x: [0.68],
      y: [0.23],
    });
  });

  it("omits labels when showLabels is false and nothing is selected", () => {
    const figure = buildSimilarityFigure(graphFixture, {
      showLabels: false,
      selectedRegionKey: null,
    });

    expect(findTextTrace(figure)).toMatchObject({
      mode: "text",
      text: [],
      x: [],
      y: [],
    });
  });

  it("formats hover content without exposing region keys or top entities", () => {
    const figure = buildSimilarityFigure(graphFixture, {
      showLabels: true,
      selectedRegionKey: null,
    });

    expect(findTrace(figure, "social")).toMatchObject({
      hovertemplate:
        "<b>%{customdata[1]}</b><br>" +
        "items: %{customdata[2]}<br>" +
        "screen category: %{customdata[3]}<br>" +
        "top labels: %{customdata[4]}<br>" +
        "top apps: %{customdata[5]}<extra></extra>",
    });
  });

  it("emits region keys in per-point customdata for stable click selection", () => {
    const figure = buildSimilarityFigure(graphFixture, {
      showLabels: true,
      selectedRegionKey: null,
    });

    expect(findTrace(figure, "research")).toMatchObject({
      customdata: [["region-research", "Research cluster", 17, "research", "browser, notes", "Chrome"]],
    });
  });
});

const graphFixture: SimilarityGraphResponse = {
  run: {
    atlas_run_id: 7,
    atlas_key: "screenshots_atlas_v1",
    generated_at: "2026-04-12T10:30:00Z",
    source_count: 98,
  },
  nodes: [
    {
      region_key: "region-social",
      title: "Social cluster",
      x: 0.12,
      y: 0.44,
      size: 28,
      item_count: 21,
      dominant_screen_category: "social",
      top_labels: ["telegram", "chat"],
      top_apps: ["Telegram"],
      top_entities: ["Alice"],
      is_labeled: true,
      representative_source_item_ids: [11, 14],
    },
    {
      region_key: "region-research",
      title: "Research cluster",
      x: 0.68,
      y: 0.23,
      size: 22,
      item_count: 17,
      dominant_screen_category: "research",
      top_labels: ["browser", "notes"],
      top_apps: ["Chrome"],
      top_entities: ["Docs"],
      is_labeled: false,
      representative_source_item_ids: [21],
    },
    {
      region_key: "region-utility",
      title: "Utility cluster",
      x: -0.3,
      y: -0.2,
      size: 12,
      item_count: 6,
      dominant_screen_category: "utility",
      top_labels: ["battery"],
      top_apps: ["System UI"],
      top_entities: [],
      is_labeled: true,
      representative_source_item_ids: [30],
    },
  ],
  edges: [
    {
      source_region_key: "region-social",
      target_region_key: "region-research",
      weight: 0.61,
      support: 9,
      reason: "shared_topic_task_signature",
    },
    {
      source_region_key: "region-social",
      target_region_key: "region-utility",
      weight: 0.44,
      support: 4,
      reason: "shared_topic_task_signature",
    },
  ],
  legend: [
    {
      category: "social",
      color: "#d6ad64",
      count: 1,
    },
    {
      category: "research",
      color: "#6cc3d6",
      count: 1,
    },
    {
      category: "utility",
      color: "#7f8c8d",
      count: 1,
    },
  ],
  filters: {
    min_cluster_size: 2,
    min_edge_weight: 0.25,
    app_hint: null,
    observed_from: null,
    observed_to: null,
    has_knowledge: null,
    search_query: null,
  },
};

function findTrace(
  figure: ReturnType<typeof buildSimilarityFigure>,
  name: string,
): Record<string, unknown> {
  const trace = figure.data.find(
    (entry) => typeof entry.name === "string" && entry.name === name,
  );

  if (!trace) {
    throw new Error(`Trace not found: ${name}`);
  }

  return trace;
}

function findTextTrace(figure: ReturnType<typeof buildSimilarityFigure>): Record<string, unknown> {
  const trace = figure.data.find((entry) => entry.mode === "text");

  if (!trace) {
    throw new Error("Text trace not found.");
  }

  return trace;
}

function findHighlightTrace(
  figure: ReturnType<typeof buildSimilarityFigure>,
): Record<string, unknown> {
  return findTrace(figure, "selected-highlight");
}
