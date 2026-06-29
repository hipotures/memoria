import { afterEach, describe, expect, it, vi } from "vitest";

import { buildAtlasRequestUrl, fetchAtlasEvidenceSlice, fetchAtlasOverview } from "./client";

describe("client atlas URL handling", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses a relative atlas path by default so Vite dev proxy can forward requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        atlas_run: null,
        regions: [],
        edges: [],
        active_filters: {},
      }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await fetchAtlasOverview({ app_hint: "telegram" });

    expect(fetchMock).toHaveBeenCalledWith("/atlas/overview?app_hint=telegram");
  });

  it("supports an explicit atlas API origin without requiring callers to pass baseUrl manually", () => {
    expect(
      buildAtlasRequestUrl(
        "/atlas/evidence",
        { region_key: "region-a", limit: 25 },
        { envOrigin: "http://127.0.0.1:8000" },
      ),
    ).toBe("http://127.0.0.1:8000/atlas/evidence?region_key=region-a&limit=25");
  });

  it("passes atlas search and sort params through to backend requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        atlas_run: {
          atlas_run_id: 1,
          atlas_key: "screenshots_atlas_v1",
          status: "published",
        },
        region_key: "region-a",
        subregion_key: "region-a/subregion-1",
        sort: "semantic_summary_asc",
        representatives: [],
        bridges: [],
        long_tail_page: { items: [], limit: 25, offset: 0, total: 0 },
        section_totals: { representatives: 0, bridges: 0, long_tail: 0 },
        active_filters: {},
      }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await fetchAtlasEvidenceSlice({
      regionKey: "region-a",
      subregionKey: "region-a/subregion-1",
      sort: "semantic_summary_asc",
      search_query: "hotel",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/atlas/evidence?region_key=region-a&subregion_key=region-a%2Fsubregion-1&sort=semantic_summary_asc&limit=25&offset=0&search_query=hotel",
    );
  });
});
