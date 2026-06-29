import { describe, expect, it } from "vitest";

import type { AtlasItem, AtlasRegion } from "../api/contracts";
import { buildDeckScene } from "./deckScene";

describe("buildDeckScene", () => {
  it("keeps featured region-focus lanes visible through centroid markers before a subregion is selected", () => {
    const focusRegion = buildRegion({
      region_key: "region-1",
      title: "Macro",
      item_count: 200,
      x: 0,
      y: 0,
      label_x: 0,
      label_y: 0,
      rings: [[[-10, -8], [10, -8], [12, 8], [-8, 10]]],
      overlayMatchCount: 200,
    });
    const subregions = [
      buildRegion({
        region_key: "lane-1",
        parent_region_key: "region-1",
        title: "Lane 1",
        item_count: 80,
        x: -4,
        y: 1,
        label_x: -4,
        label_y: 1,
        rings: [[[-8, -2], [-1, -2], [-1, 4], [-8, 4]]],
        overlayMatchCount: 80,
      }),
      buildRegion({
        region_key: "lane-2",
        parent_region_key: "region-1",
        title: "Lane 2",
        item_count: 50,
        x: 4,
        y: 2,
        label_x: 4,
        label_y: 2,
        rings: [[[1, -1], [8, -1], [8, 5], [1, 5]]],
        overlayMatchCount: 50,
      }),
    ];

    const scene = buildDeckScene({
      level: "region",
      width: 900,
      height: 640,
      regions: subregions,
      edges: [],
      evidenceItems: [],
      filteringActive: false,
      selectedRegionKey: "region-1",
      selectedSubregionKey: null,
      selectedItemId: null,
      focusRegion,
    });

    expect(scene.focusBackdrop).not.toBeNull();
    expect(scene.regions).toHaveLength(2);
    expect(scene.regions.every((region) => region.polygons.length === 0)).toBe(true);
    expect(scene.markers).toHaveLength(2);
    expect(scene.markers.every((marker) => marker.radius >= 9)).toBe(true);
    expect(scene.labels.map((label) => label.text)).toEqual(["Lane 1", "80 items", "Lane 2", "50 items"]);
  });

  it("renders overview regions as markers and reserves polygons for the selected region context", () => {
    const regions = [
      buildRegion({
        region_key: "region-1",
        title: "Travel",
        item_count: 200,
        x: 0,
        y: 0,
        label_x: 0,
        label_y: 0,
        rings: [[[-10, -8], [10, -8], [12, 8], [-8, 10]]],
        overlayMatchCount: 180,
      }),
      buildRegion({
        region_key: "region-2",
        title: "Finance",
        item_count: 40,
        x: 14,
        y: 5,
        label_x: 14,
        label_y: 5,
        rings: [[[10, 1], [18, 1], [18, 8], [10, 8]]],
        overlayMatchCount: 40,
      }),
    ];

    const scene = buildDeckScene({
      level: "overview",
      width: 900,
      height: 640,
      regions,
      edges: [],
      evidenceItems: [],
      filteringActive: false,
      selectedRegionKey: "region-1",
      selectedSubregionKey: null,
      selectedItemId: null,
      focusRegion: regions[0],
    });

    expect(scene.focusBackdrop).not.toBeNull();
    expect(scene.regions[0]?.polygons.length).toBeGreaterThan(0);
    expect(scene.regions[1]?.polygons).toHaveLength(0);
    expect(scene.markers).toHaveLength(2);
    expect(scene.markers[0]?.radius).toBeGreaterThan(scene.markers[1]?.radius ?? 0);
  });

  it("fits overview bounds to rendered markers instead of hidden region hulls", () => {
    const scene = buildDeckScene({
      level: "overview",
      width: 900,
      height: 640,
      regions: [
        buildRegion({
          region_key: "region-1",
          title: "Travel",
          item_count: 200,
          x: -0.9,
          y: -0.3,
          label_x: -0.9,
          label_y: -0.3,
          rings: [[[-40, -40], [40, -40], [40, 40], [-40, 40]]],
          overlayMatchCount: 180,
        }),
        buildRegion({
          region_key: "region-2",
          title: "Finance",
          item_count: 40,
          x: 0.85,
          y: 0.4,
          label_x: 0.85,
          label_y: 0.4,
          rings: [[[-50, -50], [50, -50], [50, 50], [-50, 50]]],
          overlayMatchCount: 40,
        }),
      ],
      edges: [],
      evidenceItems: [],
      filteringActive: false,
      selectedRegionKey: null,
      selectedSubregionKey: null,
      selectedItemId: null,
      focusRegion: null,
    });

    const travel = scene.markers.find((marker) => marker.regionKey === "region-1");
    const finance = scene.markers.find((marker) => marker.regionKey === "region-2");
    expect(travel).toBeDefined();
    expect(finance).toBeDefined();
    expect(Math.abs((finance?.position[0] ?? 0) - (travel?.position[0] ?? 0))).toBeGreaterThan(450);
  });

  it("renders no overview labels until a region is selected, then only the selected title", () => {
    const regions = Array.from({ length: 12 }, (_, index) =>
      buildRegion({
        region_key: `region-${index}`,
        title: index < 6 ? "chrome" : `topic-${index}`,
        item_count: 100 - index,
        x: index * 0.2,
        y: index * 0.15,
        label_x: index * 0.2,
        label_y: index * 0.15,
        rings: [[[index, index], [index + 1, index], [index + 1, index + 1], [index, index + 1]]],
        overlayMatchCount: 100 - index,
      }),
    );

    const scene = buildDeckScene({
      level: "overview",
      width: 900,
      height: 640,
      regions,
      edges: [],
      evidenceItems: [],
      filteringActive: false,
      selectedRegionKey: null,
      selectedSubregionKey: null,
      selectedItemId: null,
      focusRegion: null,
    });

    expect(scene.labels).toHaveLength(0);

    const selectedScene = buildDeckScene({
      level: "overview",
      width: 900,
      height: 640,
      regions,
      edges: [],
      evidenceItems: [],
      filteringActive: false,
      selectedRegionKey: "region-7",
      selectedSubregionKey: null,
      selectedItemId: null,
      focusRegion: regions[7] ?? null,
    });

    expect(selectedScene.labels.map((label) => label.text)).toEqual(["topic 7"]);
  });

  it("shows no overview edges by default and only a few selected-region links after selection", () => {
    const regions = Array.from({ length: 6 }, (_, index) =>
      buildRegion({
        region_key: `region-${index}`,
        title: `topic-${index}`,
        item_count: 100 - index,
        x: index * 0.3,
        y: index * 0.12,
        label_x: index * 0.3,
        label_y: index * 0.12,
        rings: [[[index, index], [index + 1, index], [index + 1, index + 1], [index, index + 1]]],
        overlayMatchCount: 100 - index,
      }),
    );
    const edges = Array.from({ length: 20 }, (_, index) => ({
      source_region_key: `region-${index % 6}`,
      target_region_key: `region-${(index + 1) % 6}`,
      weight: 0.9 - index * 0.01,
      edge_type: index < 4 ? "semantic_bridge" : "semantic_similarity",
    }));

    const scene = buildDeckScene({
      level: "overview",
      width: 900,
      height: 640,
      regions,
      edges,
      evidenceItems: [],
      filteringActive: false,
      selectedRegionKey: null,
      selectedSubregionKey: null,
      selectedItemId: null,
      focusRegion: null,
    });

    expect(scene.edges).toHaveLength(0);

    const selectedScene = buildDeckScene({
      level: "overview",
      width: 900,
      height: 640,
      regions,
      edges,
      evidenceItems: [],
      filteringActive: false,
      selectedRegionKey: "region-0",
      selectedSubregionKey: null,
      selectedItemId: null,
      focusRegion: null,
    });

    expect(selectedScene.edges.length).toBeGreaterThan(0);
    expect(selectedScene.edges.length).toBeLessThanOrEqual(4);
    expect(
      selectedScene.edges.every(
        (edge) => edge.key.startsWith("region-0:") || edge.key.endsWith(":region-0"),
      ),
    ).toBe(true);
  });

  it("renders overview point cloud from atlas points instead of only region centroids", () => {
    const scene = buildDeckScene({
      level: "overview",
      width: 900,
      height: 640,
      regions: [
        buildRegion({
          region_key: "region-1",
          title: "Travel",
          item_count: 200,
          x: -0.9,
          y: -0.3,
          label_x: -0.9,
          label_y: -0.3,
          rings: [[[-40, -40], [40, -40], [40, 40], [-40, 40]]],
          overlayMatchCount: 180,
        }),
      ],
      overviewPoints: [
        buildOverviewPoint({ source_item_id: 1, region_key: "region-1", x: -0.9, y: -0.3 }),
        buildOverviewPoint({ source_item_id: 2, region_key: "region-1", x: -0.2, y: 0.4, isRepresentative: true }),
      ],
      edges: [],
      evidenceItems: [],
      filteringActive: false,
      selectedRegionKey: null,
      selectedSubregionKey: null,
      selectedItemId: null,
      focusRegion: null,
    });

    expect(scene.overviewPoints).toHaveLength(2);
    expect(scene.overviewPoints[0]?.radius).toBeLessThan(scene.overviewPoints[1]?.radius ?? 0);
  });
});

function buildRegion({
  region_key,
  parent_region_key = null,
  title,
  item_count,
  x,
  y,
  label_x,
  label_y,
  rings,
  overlayMatchCount,
}: {
  region_key: string;
  parent_region_key?: string | null;
  title: string;
  item_count: number;
  x: number;
  y: number;
  label_x: number;
  label_y: number;
  rings: number[][][];
  overlayMatchCount: number;
}): AtlasRegion {
  return {
    atlas_run_id: 1,
    region_key,
    parent_region_key,
    level: parent_region_key === null ? 0 : 1,
    title,
    x,
    y,
    label_x,
    label_y,
    region_shape: {
      shape_type: "polygon",
      rings: rings.map((ring) => ring.map(([pointX, pointY]) => ({ x: pointX, y: pointY }))),
    },
    item_count,
    top_labels: [],
    top_apps: [],
    top_people: [],
    top_entities: [],
    time_start: null,
    time_end: null,
    representatives: [],
    bridge_neighbors: [],
    cohesion_score: 0.5,
    overlay: { match_count: overlayMatchCount },
  };
}

function _buildItem(): AtlasItem {
  return {
    source_item_id: 1,
    region_key: "region-1",
    subregion_key: "lane-1",
    x: 0,
    y: 0,
    semantic_summary: null,
    app_hint: null,
    observed_at: null,
    object_refs: [],
    is_representative: false,
    representative_rank: null,
    is_bridge: false,
    bridge_type: null,
    secondary_region_key: null,
    bridge_score: 0,
    screenshot_detail_url: null,
  };
}

function buildOverviewPoint({
  source_item_id,
  region_key,
  x,
  y,
  isRepresentative = false,
}: {
  source_item_id: number;
  region_key: string;
  x: number;
  y: number;
  isRepresentative?: boolean;
}) {
  return {
    source_item_id,
    region_key,
    subregion_key: null,
    x,
    y,
    semantic_summary: null,
    app_hint: "telegram",
    observed_at: null,
    object_refs: [],
    matches_filters: true,
    is_representative: isRepresentative,
    representative_rank: isRepresentative ? 1 : null,
    is_bridge: false,
    bridge_type: null,
    secondary_region_key: null,
    bridge_score: 0,
    screenshot_detail_url: null,
  };
}
