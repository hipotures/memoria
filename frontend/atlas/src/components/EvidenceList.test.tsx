import { describe, expect, it } from "vitest";

import type { AtlasItem } from "../api/contracts";
import type { EvidenceSections } from "../lib/evidenceSections";
import { estimateEvidenceRowSize } from "./EvidenceList";

describe("EvidenceList", () => {
  it("starts virtual evidence cards with enough space for wrapped summaries", () => {
    const sections = buildSections();
    expect(estimateEvidenceRowSize({ kind: "section" })).toBe(48);
    expect(estimateEvidenceRowSize({ kind: "pager" })).toBe(80);
    expect(estimateEvidenceRowSize({ kind: "item", item: sections.longTail.items[0] })).toBeGreaterThanOrEqual(
      160,
    );
  });
});

function buildSections(): EvidenceSections<AtlasItem> {
  return {
    representatives: [
      buildItem({
        source_item_id: 101,
        semantic_summary:
          "A long social feed screenshot description that wraps across several lines inside the narrow evidence dock.",
        is_representative: true,
        representative_rank: 1,
      }),
    ],
    bridges: [
      buildItem({
        source_item_id: 202,
        semantic_summary:
          "Another long bridge description with enough text to exceed the old fixed row estimate.",
        is_bridge: true,
        bridge_type: "external",
      }),
    ],
    longTail: {
      items: [
        buildItem({
          source_item_id: 303,
          semantic_summary:
            "A long-tail evidence card containing a verbose summary and several object refs that must not collide with the following row.",
        }),
      ],
      limit: 25,
      offset: 0,
      total: 1,
    },
    totals: {
      representatives: 1,
      bridges: 1,
      longTail: 1,
    },
  };
}

function buildItem(overrides: Partial<AtlasItem>): AtlasItem {
  return {
    source_item_id: 1,
    region_key: "region",
    subregion_key: "region/subregion",
    x: 0,
    y: 0,
    semantic_summary: "Evidence item",
    app_hint: "tiktok",
    observed_at: "2023-10-15T09:00:00Z",
    object_refs: ["thread:tiktok-entertainment", "topic:movie-discussion", "person:creator"],
    is_representative: false,
    representative_rank: null,
    is_bridge: false,
    bridge_type: null,
    secondary_region_key: null,
    bridge_score: 0,
    screenshot_detail_url: "/screenshots/1",
    ...overrides,
  };
}
