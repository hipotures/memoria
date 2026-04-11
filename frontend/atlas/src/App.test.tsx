import { act } from "react";
import type { Root } from "react-dom/client";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

describe("App", () => {
  let container: HTMLDivElement;
  let root: Root;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");

      if (url.pathname === "/atlas/overview") {
        return jsonResponse({
          atlas_run: buildAtlasRun(),
          regions: [
            buildRegion({
              region_key: "region-travel",
              title: "Travel Planning",
              x: -200,
              y: 30,
              overlay: { match_count: 8 },
              top_apps: ["Telegram", "Gmail"],
              top_labels: ["travel planning", "itinerary"],
            }),
            buildRegion({
              region_key: "region-finance",
              title: "Finance Review",
              x: 220,
              y: -40,
              overlay: { match_count: 2 },
              top_apps: ["Slack"],
              top_labels: ["budget"],
            }),
          ],
          edges: [
            {
              source_region_key: "region-travel",
              target_region_key: "region-finance",
              weight: 0.36,
              edge_type: "bridge",
            },
          ],
          active_filters: {
            app_hint: url.searchParams.get("app_hint"),
            observed_from: url.searchParams.get("observed_from"),
            observed_to: url.searchParams.get("observed_to"),
            has_knowledge:
              url.searchParams.get("has_knowledge") === null
                ? null
                : url.searchParams.get("has_knowledge") === "true",
          },
        });
      }

      if (url.pathname === "/atlas/regions/region-travel") {
        return jsonResponse({
          atlas_run: buildAtlasRun(),
          region: buildRegion({
            region_key: "region-travel",
            title: "Travel Planning",
            overlay: { match_count: 8 },
            top_apps: ["Telegram", "Gmail"],
            top_labels: ["travel planning", "itinerary"],
          }),
          subregions: [
            buildRegion({
              region_key: "region-travel/subregion-1",
              parent_region_key: "region-travel",
              level: 1,
              title: "Trip booking lane",
              x: -110,
              y: -20,
              overlay: { match_count: 5 },
            }),
            buildRegion({
              region_key: "region-travel/subregion-2",
              parent_region_key: "region-travel",
              level: 1,
              title: "Packing lane",
              x: 120,
              y: 35,
              overlay: { match_count: 3 },
            }),
          ],
          representatives: [
            buildItem({
              source_item_id: 101,
              region_key: "region-travel",
              semantic_summary: "Trip research in Telegram",
              app_hint: "Telegram",
              is_representative: true,
              representative_rank: 1,
            }),
          ],
          active_filters: {},
        });
      }

      if (url.pathname === "/atlas/evidence") {
        return jsonResponse({
          atlas_run: buildAtlasRun(),
          region_key: "region-travel",
          subregion_key: url.searchParams.get("subregion_key"),
          sort: "observed_at_desc",
          representatives: [
            buildItem({
              source_item_id: 101,
              region_key: "region-travel",
              subregion_key: "region-travel/subregion-1",
              semantic_summary: "Trip research in Telegram",
              app_hint: "Telegram",
              is_representative: true,
              representative_rank: 1,
            }),
          ],
          bridges: [
            buildItem({
              source_item_id: 202,
              region_key: "region-travel",
              subregion_key: "region-travel/subregion-1",
              semantic_summary: "Budget handoff to finance notes",
              app_hint: "Sheets",
              is_bridge: true,
              bridge_type: "cross-region",
            }),
          ],
          long_tail_page: {
            items: [
              buildItem({
                source_item_id: 303,
                region_key: "region-travel",
                subregion_key: "region-travel/subregion-1",
                semantic_summary: "Hotel shortlist screenshot",
                app_hint: "Chrome",
              }),
            ],
            limit: 25,
            offset: 0,
            total: 1,
          },
          section_totals: {
            representatives: 1,
            bridges: 1,
            long_tail: 1,
          },
          active_filters: {},
        });
      }

      throw new Error(`Unhandled atlas request: ${url.pathname}`);
    });

    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it("keeps the dock active from overview and drills down only on explicit actions", async () => {
    await renderApp(root);

    await waitForText(container, "Atlas overview");
    expect(container.textContent).toContain("Travel Planning");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(requestPaths(fetchMock)).toEqual(["/atlas/overview"]);

    act(() => {
      findButton("Travel Planning", container).click();
    });

    expect(requestPaths(fetchMock)).toEqual(["/atlas/overview"]);
    expect(findButton("Enter region", container).disabled).toBe(false);
    expect(container.textContent).toContain("Travel Planning");
    expect(container.textContent).toContain("8 matching screenshots");

    act(() => {
      findButton("Enter region", container).click();
    });

    await waitForText(container, "Trip booking lane");
    expect(requestPaths(fetchMock)).toEqual(["/atlas/overview", "/atlas/regions/region-travel"]);
    expect(findButton("Open evidence", container).disabled).toBe(true);

    act(() => {
      findButton("Trip booking lane", container).click();
    });

    expect(requestPaths(fetchMock)).toEqual(["/atlas/overview", "/atlas/regions/region-travel"]);
    expect(findButton("Open evidence", container).disabled).toBe(false);

    act(() => {
      findButton("Open evidence", container).click();
    });

    await waitForText(container, "Representatives");
    expect(requestPaths(fetchMock)).toEqual([
      "/atlas/overview",
      "/atlas/regions/region-travel",
      "/atlas/evidence",
    ]);
    expect(container.textContent).toContain("Budget handoff to finance notes");
    expect(container.textContent).toContain("Hotel shortlist screenshot");
  });

  it("applies toolbar filters to overview requests and can reset them", async () => {
    await renderApp(root);
    await waitForText(container, "Atlas overview");

    act(() => {
      changeInput(findInput("Search atlas", container), "travel");
      changeInput(findInput("App", container), "Telegram");
      changeInput(findInput("Observed from", container), "2026-03-01");
      changeInput(findInput("Observed to", container), "2026-03-31");
      changeSelect(findSelect("Knowledge", container), "with");
    });

    act(() => {
      findButton("Apply filters", container).click();
    });

    await flush();

    const applyRequest = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]?.[0] as string;
    const applyUrl = new URL(applyRequest, "http://localhost");
    expect(applyUrl.pathname).toBe("/atlas/overview");
    expect(applyUrl.searchParams.get("app_hint")).toBe("Telegram");
    expect(applyUrl.searchParams.get("observed_from")).toBe("2026-03-01T00:00:00.000Z");
    expect(applyUrl.searchParams.get("observed_to")).toBe("2026-03-31T23:59:59.999Z");
    expect(applyUrl.searchParams.get("has_knowledge")).toBe("true");
    expect(container.textContent).toContain("1 active search term");

    act(() => {
      findButton("Reset filters", container).click();
    });

    await flush();

    const resetRequest = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]?.[0] as string;
    const resetUrl = new URL(resetRequest, "http://localhost");
    expect(resetUrl.pathname).toBe("/atlas/overview");
    expect(resetUrl.search).toBe("");
    expect(findInput("App", container).value).toBe("");
    expect(findSelect("Knowledge", container).value).toBe("all");
  });
});

async function renderApp(root: Root) {
  await act(async () => {
    root.render(<App />);
    await flush();
  });
}

async function waitForText(container: HTMLElement, text: string) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (container.textContent?.includes(text)) {
      return;
    }
    await flush();
  }

  throw new Error(`Timed out waiting for text: ${text}`);
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function requestPaths(mock: ReturnType<typeof vi.fn>): string[] {
  return mock.mock.calls.map(([input]) => new URL(String(input), "http://localhost").pathname);
}

function findButton(label: string, container: HTMLElement): HTMLButtonElement {
  const button = Array.from(container.querySelectorAll("button")).find(
    (candidate) => candidate.textContent?.trim() === label,
  );

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`Could not find button with label: ${label}`);
  }

  return button;
}

function findInput(label: string, container: HTMLElement): HTMLInputElement {
  const input = findField(label, container);
  if (!(input instanceof HTMLInputElement)) {
    throw new Error(`Could not find input with label: ${label}`);
  }
  return input;
}

function findSelect(label: string, container: HTMLElement): HTMLSelectElement {
  const select = findField(label, container);
  if (!(select instanceof HTMLSelectElement)) {
    throw new Error(`Could not find select with label: ${label}`);
  }
  return select;
}

function findField(label: string, container: HTMLElement): HTMLElement {
  const labelElement = Array.from(container.querySelectorAll("label")).find(
    (candidate) => candidate.textContent?.includes(label),
  );

  const field = labelElement?.querySelector("input, select");
  if (!(field instanceof HTMLElement)) {
    throw new Error(`Could not find field with label: ${label}`);
  }

  return field;
}

function changeInput(input: HTMLInputElement, value: string) {
  const descriptor = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  );
  descriptor?.set?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function changeSelect(select: HTMLSelectElement, value: string) {
  const descriptor = Object.getOwnPropertyDescriptor(
    HTMLSelectElement.prototype,
    "value",
  );
  descriptor?.set?.call(select, value);
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

function jsonResponse(payload: unknown) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => payload,
  };
}

function buildAtlasRun() {
  return {
    atlas_run_id: 7,
    atlas_key: "screenshots_atlas_v1",
    status: "published",
    source_count: 12,
    source_snapshot_id: "snapshot-1",
    corpus_hash: "hash-1",
    embedding_type: "openai",
    embedding_model: "text-embedding-3-large",
    embedding_version: "1",
    clustering_method: "hdbscan",
    clustering_params: {},
    random_seed: 13,
    layout_version: "atlas-v1",
    generated_at: "2026-04-01T09:00:00Z",
    completed_at: "2026-04-01T09:05:00Z",
    published_at: "2026-04-01T09:10:00Z",
  };
}

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
    region_shape: {
      shape_type: "polygon",
      rings: [
        [
          { x: -120, y: -80 },
          { x: 120, y: -80 },
          { x: 120, y: 80 },
          { x: -120, y: 80 },
          { x: -120, y: -80 },
        ],
      ],
    },
    item_count: 6,
    top_labels: [],
    top_apps: [],
    top_people: [],
    top_entities: [],
    time_start: "2026-03-01T09:00:00Z",
    time_end: "2026-03-08T12:00:00Z",
    representatives: [],
    bridge_neighbors: [],
    cohesion_score: 0.61,
    overlay: { match_count: 0 },
    ...overrides,
  };
}

function buildItem(overrides: Record<string, unknown>) {
  return {
    source_item_id: 1,
    region_key: "region-default",
    subregion_key: null,
    x: 0,
    y: 0,
    semantic_summary: "Atlas evidence item",
    app_hint: "Telegram",
    observed_at: "2026-03-05T10:00:00Z",
    object_refs: [],
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
