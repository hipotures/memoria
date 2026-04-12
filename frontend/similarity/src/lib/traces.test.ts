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

    expect(figure.data[1]).toMatchObject({
      type: "scattergl",
      mode: "markers",
      name: "social",
      customdata: [["Social cluster", 21, "social", "telegram, chat", "Telegram"]],
    });
    expect(figure.data[2]).toMatchObject({
      type: "scattergl",
      mode: "markers",
      name: "research",
    });
    expect(figure.data[3]).toMatchObject({
      type: "scattergl",
      mode: "markers",
      name: "utility",
    });
    expect(figure.data[4]).toMatchObject({
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

    const labelTrace = figure.data[4];
    expect(labelTrace).toMatchObject({
      mode: "text",
      text: ["Social cluster", "Research cluster", "Utility cluster"],
    });
  });

  it("keeps the selected region label visible when showLabels is false", () => {
    const figure = buildSimilarityFigure(graphFixture, {
      showLabels: false,
      selectedRegionKey: "region-research",
    });

    expect(figure.data[4]).toMatchObject({
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

    expect(figure.data[4]).toMatchObject({
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

    expect(figure.data[1]).toMatchObject({
      hovertemplate:
        "<b>%{customdata[0]}</b><br>" +
        "items: %{customdata[1]}<br>" +
        "screen category: %{customdata[2]}<br>" +
        "top labels: %{customdata[3]}<br>" +
        "top apps: %{customdata[4]}<extra></extra>",
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
