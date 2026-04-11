import { describe, expect, it } from "vitest";

import {
  atlasRegionDisplayCount,
  atlasRegionDisplayDomainMax,
  atlasRegionDisplayLabel,
} from "./displayCounts";

describe("atlas display counts", () => {
  it("uses request-scoped overlay match counts even when they are zero", () => {
    const region = buildRegion({ item_count: 6, overlay: { match_count: 0 } });

    expect(atlasRegionDisplayCount(region)).toBe(0);
    expect(atlasRegionDisplayLabel(region)).toBe("0 items");
  });

  it("scales the stage from overlay counts rather than unfiltered item counts", () => {
    const regions = [
      buildRegion({ region_key: "region-a", item_count: 12, overlay: { match_count: 0 } }),
      buildRegion({ region_key: "region-b", item_count: 9, overlay: { match_count: 3 } }),
    ];

    expect(atlasRegionDisplayDomainMax(regions)).toBe(3);
  });
});

function buildRegion(overrides: Record<string, unknown>) {
  return {
    atlas_run_id: 7,
    region_key: "region-default",
    parent_region_key: null,
    level: 0,
    title: "Default region",
    x: 0,
    y: 0,
    label_x: 0,
    label_y: 0,
    region_shape: { shape_type: "polygon", rings: [] },
    item_count: 6,
    top_labels: [],
    top_apps: [],
    top_people: [],
    top_entities: [],
    time_start: null,
    time_end: null,
    representatives: [],
    bridge_neighbors: [],
    cohesion_score: 0.61,
    overlay: { match_count: 0 },
    ...overrides,
  };
}
