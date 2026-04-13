import { describe, expect, it } from "vitest";

import type { SimilarityGraphResponse } from "../api/contracts";
import { buildSimilarityFigure } from "./traces";

describe("buildSimilarityFigure", () => {
  it("builds one edge trace, one node trace per category, and a label trace", () => {
    const figure = buildSimilarityFigure(graphFixture, figureOptions("default"));

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
      customdata: [
        ["region-social", "Social cluster", 21, "social", "live streaming, creator tools", "TikTok"],
      ],
      marker: {
        color: "#00F5D4",
      },
    });
    expect(findTrace(figure, "research")).toMatchObject({
      type: "scattergl",
      mode: "markers",
      name: "research",
      marker: {
        color: "#FF7F50",
      },
    });
    expect(findTrace(figure, "utility")).toMatchObject({
      type: "scattergl",
      mode: "markers",
      name: "utility",
      marker: {
        color: "#A0AEC0",
      },
    });
    expect(findTextTrace(figure)).toMatchObject({
      type: "scattergl",
      mode: "text",
      showlegend: false,
      text: ["chrome · dns management", "tiktok · live streaming"],
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

  it("uses backend label anchors instead of node centers", () => {
    const figure = buildSimilarityFigure(graphFixture, figureOptions("default"));

    const labelTrace = findTextTrace(figure);
    expect(labelTrace?.text).toContain("chrome · dns management");
    expect(labelTrace?.x).toContain(0.32);
    expect(labelTrace?.y).toContain(0.44);
  });

  it("shows only top labels by priority in default mode", () => {
    const figure = buildSimilarityFigure(graphFixture, figureOptions("default"));

    const labelTrace = findTextTrace(figure);
    expect(labelTrace?.text).toEqual([
      "chrome · dns management",
      "tiktok · live streaming",
    ]);
  });

  it("adds a dedicated highlight marker trace for the selected region", () => {
    const figure = buildSimilarityFigure(
      graphFixture,
      figureOptions("default", "region-research"),
    );

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

  it("shows only the selected region label in selected mode", () => {
    const figure = buildSimilarityFigure(
      graphFixture,
      figureOptions("selected", "region-research"),
    );

    expect(findTextTrace(figure)).toMatchObject({
      mode: "text",
      text: ["chrome · dns management"],
      x: [0.32],
      y: [0.44],
    });
  });

  it("omits labels in none mode even when a region is selected", () => {
    const figure = buildSimilarityFigure(graphFixture, figureOptions("none", "region-research"));

    expect(findTextTrace(figure)).toMatchObject({
      mode: "text",
      text: [],
      x: [],
      y: [],
    });
  });

  it("preserves the legacy selected-label behavior when showLabels is false", () => {
    const figure = buildSimilarityFigure(graphFixture, legacyFigureOptions(false, "region-research"));

    expect(findTextTrace(figure)).toMatchObject({
      mode: "text",
      text: ["chrome · dns management"],
      x: [0.32],
      y: [0.44],
    });
  });

  it("keeps the selected node labeled for legacy showLabels callers", () => {
    const figure = buildSimilarityFigure(graphFixture, legacyFigureOptions(true, "region-utility"));

    expect(findTextTrace(figure)).toMatchObject({
      text: [
        "chrome · dns management",
        "tiktok · live streaming",
        "settings · battery saver",
      ],
      x: [0.32, 0.32, -0.22],
      y: [0.44, 0.44, -0.26],
    });
  });

  it("falls back to legacy labeled-node titles and node centers when render metadata is absent", () => {
    const figure = buildSimilarityFigure(legacyGraphFixture, legacyFigureOptions(true));

    expect(findTextTrace(figure)).toMatchObject({
      text: ["Social cluster", "Utility cluster"],
      x: [0.12, -0.3],
      y: [0.44, -0.2],
    });
  });

  it("prefers explicit labelMode over legacy showLabels compatibility", () => {
    const figure = buildSimilarityFigure(graphFixture, {
      labelMode: "selected",
      showLabels: false,
      selectedRegionKey: "region-research",
      visibleCategories: null,
    });

    expect(findTextTrace(figure)).toMatchObject({
      text: ["chrome · dns management"],
      x: [0.32],
      y: [0.44],
    });
  });

  it("uses a default label limit of 20 when the backend omits one", () => {
    const { default_label_limit: _defaultLabelLimit, ...graphWithoutDefaultLimitBase } = graphFixture;
    const graphWithoutDefaultLimit: SimilarityGraphResponse = {
      ...graphWithoutDefaultLimitBase,
      nodes: Array.from({ length: 25 }, (_, index) => ({
        ...graphFixture.nodes[0],
        region_key: `region-${index}`,
        title: `Cluster ${index}`,
        label: `label ${String(index).padStart(2, "0")}`,
        canonical_title: `Cluster ${index}`,
        x: index,
        y: index * -1,
        label_x: index + 0.5,
        label_y: index * -1 - 0.25,
        label_priority: 100 - index,
        representative_source_item_ids: [index],
      })),
      legend: [{ category: "social", color: "#d6ad64", count: 25 }],
      edges: [],
    };

    const figure = buildSimilarityFigure(graphWithoutDefaultLimit, figureOptions("default"));

    expect(findTextTrace(figure)).toMatchObject({
      text: Array.from({ length: 20 }, (_, index) => `label ${String(index).padStart(2, "0")}`),
      x: Array.from({ length: 20 }, (_, index) => index + 0.5),
      y: Array.from({ length: 20 }, (_, index) => index * -1 - 0.25),
    });
  });

  it("formats hover content without exposing region keys or top entities", () => {
    const figure = buildSimilarityFigure(graphFixture, figureOptions("default"));

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
    const figure = buildSimilarityFigure(graphFixture, figureOptions("default"));

    expect(findTrace(figure, "research")).toMatchObject({
      customdata: [
        [
          "region-research",
          "Research cluster",
          17,
          "research",
          "dns management, workspace docs",
          "Chrome",
        ],
      ],
    });
  });

  it("does not rely on backend-provided near-duplicate legend colors when frontend overrides exist", () => {
    const figure = buildSimilarityFigure(
      {
        ...graphFixture,
        legend: [
          { category: "social", color: "#55c6cc", count: 1 },
          { category: "document", color: "#59c8cd", count: 1 },
        ],
        nodes: [
          graphFixture.nodes[0],
          {
            ...graphFixture.nodes[2],
            region_key: "region-document",
            title: "Document cluster",
            dominant_screen_category: "document",
          },
        ],
      },
      figureOptions("default"),
    );

    expect(findTrace(figure, "social")).toMatchObject({
      marker: { color: "#00F5D4" },
    });
    expect(findTrace(figure, "document")).toMatchObject({
      marker: { color: "#3DDC97" },
    });
  });

  it("filters nodes, edges, and labels to the currently visible legend categories", () => {
    const figure = buildSimilarityFigure(
      graphFixture,
      figureOptions("default", null, new Set(["social", "utility"])),
    );

    expect(findTrace(figure, "social")).toMatchObject({
      x: [0.12],
      y: [0.44],
      visible: true,
    });
    expect(findTrace(figure, "research")).toMatchObject({
      x: [0.68],
      y: [0.23],
      visible: "legendonly",
    });
    expect(findTrace(figure, "utility")).toMatchObject({
      x: [-0.3],
      y: [-0.2],
      visible: true,
    });
    expect(figure.data[0]).toMatchObject({
      x: [0.12, -0.3, null],
      y: [0.44, -0.2, null],
    });
    expect(findTextTrace(figure)).toMatchObject({
      text: ["tiktok · live streaming", "settings · battery saver"],
    });
  });

  it("drops highlight and selected-only labels when the selected category is hidden", () => {
    const figure = buildSimilarityFigure(
      graphFixture,
      figureOptions("selected", "region-research", new Set(["social", "utility"])),
    );

    expect(() => findHighlightTrace(figure)).toThrow("Trace not found: selected-highlight");
    expect(findTextTrace(figure)).toMatchObject({
      text: [],
      x: [],
      y: [],
    });
  });

  it("keeps only ego-network edges for the selected region", () => {
    const figure = buildSimilarityFigure(
      graphFixture,
      figureOptions("default", "region-social", new Set(["social", "research", "utility"])),
    );

    expect(figure.data[0]).toMatchObject({
      x: [0.12, 0.68, null, 0.12, -0.3, null],
      y: [0.44, 0.23, null, 0.44, -0.2, null],
    });
  });
});

const graphFixture = {
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
      label: "tiktok · live streaming",
      canonical_title: "Social cluster",
      duplicate_title_count: 1,
      x: 0.12,
      y: 0.44,
      label_x: 0.32,
      label_y: 0.44,
      size: 28,
      item_count: 21,
      degree: 2,
      label_priority: 70,
      dominant_screen_category: "social",
      top_labels: ["live streaming", "creator tools"],
      top_apps: ["TikTok"],
      top_entities: ["Alice"],
      is_labeled: true,
      representative_source_item_ids: [11, 14],
    },
    {
      region_key: "region-research",
      title: "Research cluster",
      label: "chrome · dns management",
      canonical_title: "Research cluster",
      duplicate_title_count: 1,
      x: 0.68,
      y: 0.23,
      label_x: 0.32,
      label_y: 0.44,
      size: 22,
      item_count: 17,
      degree: 1,
      label_priority: 90,
      dominant_screen_category: "research",
      top_labels: ["dns management", "workspace docs"],
      top_apps: ["Chrome"],
      top_entities: ["Docs"],
      is_labeled: false,
      representative_source_item_ids: [21],
    },
    {
      region_key: "region-utility",
      title: "Utility cluster",
      label: "settings · battery saver",
      canonical_title: "Utility cluster",
      duplicate_title_count: 1,
      x: -0.3,
      y: -0.2,
      label_x: -0.22,
      label_y: -0.26,
      size: 12,
      item_count: 6,
      degree: 1,
      label_priority: 10,
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
      edge_type: "semantic_similarity",
      reason: "shared_topic_task_signature",
    },
    {
      source_region_key: "region-social",
      target_region_key: "region-utility",
      weight: 0.44,
      support: 4,
      edge_type: "semantic_similarity",
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
  graph_kind: "semantic_regions",
  edge_scope: "all",
  default_label_limit: 2,
} as SimilarityGraphResponse;

const legacyGraphFixture = {
  ...graphFixture,
  nodes: graphFixture.nodes.map((node, index) => {
    const { label, canonical_title, duplicate_title_count, label_x, label_y, degree, label_priority, ...legacyNode } =
      node;

    return {
      ...legacyNode,
      is_labeled: index !== 1,
    };
  }),
} as SimilarityGraphResponse;

function figureOptions(
  labelMode: "none" | "default" | "all" | "selected",
  selectedRegionKey: string | null = null,
  visibleCategories: Set<string> | null = null,
): Parameters<typeof buildSimilarityFigure>[1] {
  return {
    labelMode,
    selectedRegionKey,
    visibleCategories,
  };
}

function legacyFigureOptions(
  showLabels: boolean,
  selectedRegionKey: string | null = null,
  visibleCategories: Set<string> | null = null,
): Parameters<typeof buildSimilarityFigure>[1] {
  return {
    showLabels,
    selectedRegionKey,
    visibleCategories,
  };
}

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
