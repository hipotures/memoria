import { afterEach, describe, expect, it, vi } from "vitest";

import { buildAtlasRequestUrl, fetchAtlasOverview } from "./client";

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
});
