import { describe, expect, it } from "vitest";

import type { AtlasRegion } from "../api/contracts";
import { applyRegionFocusScope, resolveCanvasSubregions } from "./atlasPresentation";

describe("applyRegionFocusScope", () => {
  it("keeps the highest-signal subregions in featured mode", () => {
    const regions = Array.from({ length: 10 }, (_value, index) =>
      buildRegion({
        region_key: `region/subregion-${index + 1}`,
        title: `Lane ${index + 1}`,
        item_count: 20 - index,
        overlay: { match_count: index < 6 ? 8 - index : 1 },
      }),
    );

    const featured = applyRegionFocusScope(regions, "featured", null);

    expect(featured).toHaveLength(8);
    expect(featured.map((region) => region.region_key)).toEqual([
      "region/subregion-1",
      "region/subregion-2",
      "region/subregion-3",
      "region/subregion-4",
      "region/subregion-5",
      "region/subregion-6",
      "region/subregion-7",
      "region/subregion-8",
    ]);
  });

  it("keeps the selected subregion visible even when it falls outside the featured slice", () => {
    const regions = Array.from({ length: 10 }, (_value, index) =>
      buildRegion({
        region_key: `region/subregion-${index + 1}`,
        title: `Lane ${index + 1}`,
        item_count: 10 - index,
        overlay: { match_count: 1 },
      }),
    );

    const featured = applyRegionFocusScope(regions, "featured", "region/subregion-10");

    expect(featured.map((region) => region.region_key)).toContain("region/subregion-10");
  });

  it("uses the scoped subregion slice for atlas canvas outside overview mode", () => {
    const structural = Array.from({ length: 12 }, (_value, index) =>
      buildRegion({
        region_key: `region/subregion-${index + 1}`,
        title: `Lane ${index + 1}`,
        item_count: 20 - index,
        overlay: { match_count: index < 8 ? 20 - index : 1 },
      }),
    );
    const visible = structural.slice(0, 8);

    expect(resolveCanvasSubregions("region", structural, visible)).toEqual(visible);
    expect(resolveCanvasSubregions("evidence", structural, visible)).toEqual(visible);
    expect(resolveCanvasSubregions("overview", structural, visible)).toEqual(structural);
  });
});

function buildRegion({
  region_key,
  title,
  item_count,
  overlay,
}: {
  region_key: string;
  title: string;
  item_count: number;
  overlay: { match_count: number };
}): AtlasRegion {
  return {
    region_key,
    parent_region_key: "region",
    level: 1,
    title,
    x: 0,
    y: 0,
    label_x: 0,
    label_y: 0,
    region_shape: { shape_type: "polygon", rings: [] },
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
    overlay,
  };
}
