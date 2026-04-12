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
        return jsonResponse(buildOverviewPayload(url));
      }

      if (url.pathname === "/atlas/regions/region-travel") {
        return jsonResponse(buildRegionDetailPayload(url, "region-travel"));
      }

      if (url.pathname === "/atlas/regions/region-finance") {
        return jsonResponse(buildRegionDetailPayload(url, "region-finance"));
      }

      if (url.pathname === "/atlas/evidence") {
        return jsonResponse(buildEvidencePayload(url));
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

  it("loads region workbench content on overview selection before explicit drill-down", async () => {
    await renderApp(root);

    await waitForText(container, "Atlas overview");
    expect(requestPaths(fetchMock)).toEqual(["/atlas/overview"]);

    act(() => {
      findButton("Travel Planning", container).click();
    });

    await waitForText(container, "2 representative screenshots");
    expect(requestPaths(fetchMock)).toEqual(["/atlas/overview", "/atlas/regions/region-travel"]);
    expect(container.textContent).toContain("Trip research in Telegram");
    expect(container.textContent).toContain("2 representative screenshots");
    expect(container.textContent).not.toContain("Budget handoff to finance notes");

    act(() => {
      findButton("Enter region", container).click();
    });

    await waitForText(container, "Trip booking lane");
    expect(requestPaths(fetchMock)).toEqual(["/atlas/overview", "/atlas/regions/region-travel"]);

    act(() => {
      findButton("Trip booking lane", container).click();
    });

    await flush();

    expect(container.textContent).toContain("Trip booking lane");
    expect(container.textContent).toContain("arrival logistics");
    expect(container.textContent).toContain("maps");
    expect(container.textContent).toContain("alice");
    expect(container.textContent).toContain("Mar 2, 2026");
    expect(findButton("Open evidence", container).disabled).toBe(false);
  });

  it("keeps the atlas field visible when filters produce zero matches", async () => {
    await renderApp(root);
    await waitForText(container, "Atlas overview");

    act(() => {
      changeInput(findInput("Search atlas", container), "void");
    });

    act(() => {
      findButton("Apply filters", container).click();
    });

    await waitForText(container, "No regions match the current filters");
    expect(container.textContent).toContain("Canvas preview unavailable in this environment.");
  });

  it("supports Enter drill shortcuts outside form fields without hijacking form controls", async () => {
    await renderApp(root);
    await waitForText(container, "Atlas overview");

    act(() => {
      findButton("Travel Planning", container).click();
    });

    await waitForText(container, "2 representative screenshots");

    act(() => {
      pressEnter(findInput("Search atlas", container));
    });

    await flush();
    expect(queryButton("Open evidence", container)).toBeNull();

    act(() => {
      pressEnter(document.body);
    });

    await waitForText(container, "Open evidence");

    act(() => {
      findButton("Trip booking lane", container).click();
    });

    await flush();

    act(() => {
      pressEnter(document.body);
    });

    await waitForText(container, "Evidence stack");
  });

  it("opens region-level evidence explicitly when a region has no generated subregions", async () => {
    await renderApp(root);
    await waitForText(container, "Atlas overview");

    act(() => {
      findButton("Finance Review", container).click();
    });

    await waitForText(container, "1 representative screenshot");
    expect(container.textContent).toContain("Month-end close triage");

    act(() => {
      findButton("Enter region", container).click();
    });

    await waitForText(container, "No generated lanes for this region yet");
    expect(container.textContent).toContain("Canvas preview unavailable in this environment.");
    expect(findButton("Open region evidence", container).disabled).toBe(false);

    act(() => {
      findButton("Open region evidence", container).click();
    });

    await waitForText(container, "Evidence stack");

    const evidenceUrl = lastRequestUrl(fetchMock);
    expect(evidenceUrl.pathname).toBe("/atlas/evidence");
    expect(evidenceUrl.searchParams.get("region_key")).toBe("region-finance");
    expect(evidenceUrl.searchParams.get("subregion_key")).toBeNull();
    expect(container.textContent).toContain("Slack budget close thread");
  });

  it("clears stale subregion targets before Enter can drill a filtered-out lane", async () => {
    await renderApp(root);
    await waitForText(container, "Atlas overview");

    act(() => {
      findButton("Travel Planning", container).click();
    });

    await waitForText(container, "2 representative screenshots");

    act(() => {
      findButton("Enter region", container).click();
    });

    await waitForText(container, "Packing lane");

    act(() => {
      findButton("Packing lane", container).click();
    });

    await flush();
    expect(findButton("Open evidence", container).disabled).toBe(false);

    act(() => {
      changeInput(findInput("Search atlas", container), "prune");
    });

    act(() => {
      findButton("Apply filters", container).click();
    });

    await flush();

    expect(findButton("Open evidence", container).disabled).toBe(true);

    act(() => {
      pressEnter(document.body);
    });

    await flush();

    expect(container.textContent).not.toContain("Evidence stack");
    expect(requestPaths(fetchMock)).not.toContain("/atlas/evidence");
  });

  it("sends backend search state through overview, region detail, and evidence requests", async () => {
    await renderApp(root);
    await waitForText(container, "Atlas overview");

    act(() => {
      changeInput(findInput("Search atlas", container), "hotel");
      changeInput(findInput("App", container), "Telegram");
      changeInput(findInput("Observed from", container), "2026-03-01");
      changeInput(findInput("Observed to", container), "2026-03-31");
      changeSelect(findSelect("Knowledge", container), "with");
    });

    act(() => {
      findButton("Apply filters", container).click();
    });

    await flush();

    const overviewUrl = lastRequestUrl(fetchMock);
    expect(overviewUrl.pathname).toBe("/atlas/overview");
    expect(overviewUrl.searchParams.get("search_query")).toBe("hotel");
    expect(overviewUrl.searchParams.get("app_hint")).toBe("Telegram");
    expect(overviewUrl.searchParams.get("observed_from")).toBe("2026-03-01T00:00:00.000Z");
    expect(overviewUrl.searchParams.get("observed_to")).toBe("2026-03-31T23:59:59.999Z");
    expect(overviewUrl.searchParams.get("has_knowledge")).toBe("true");

    act(() => {
      findButton("Travel Planning", container).click();
    });

    await waitForText(container, "Hotel confirmation thread");

    const detailUrl = lastRequestUrl(fetchMock);
    expect(detailUrl.pathname).toBe("/atlas/regions/region-travel");
    expect(detailUrl.searchParams.get("search_query")).toBe("hotel");
    expect(detailUrl.searchParams.get("app_hint")).toBe("Telegram");

    act(() => {
      findButton("Enter region", container).click();
    });

    await waitForText(container, "Trip booking lane");

    act(() => {
      findButton("Trip booking lane", container).click();
    });

    await flush();

    act(() => {
      findButton("Open evidence", container).click();
    });

    await waitForText(container, "Evidence stack");

    const evidenceUrl = lastRequestUrl(fetchMock);
    expect(evidenceUrl.pathname).toBe("/atlas/evidence");
    expect(evidenceUrl.searchParams.get("search_query")).toBe("hotel");
    expect(evidenceUrl.searchParams.get("sort")).toBe("observed_at_desc");
    expect(container.textContent).toContain("Showing 1-1 of 8");
  });

  it("surfaces dock metadata and local focus controls for the active focus", async () => {
    await renderApp(root);
    await waitForText(container, "Atlas overview");

    act(() => {
      findButton("Travel Planning", container).click();
    });

    await waitForText(container, "2 representative screenshots");
    expect(container.textContent).toContain("trip to berlin");
    expect(container.textContent).toContain("Mar 1, 2026");

    act(() => {
      findButton("Filter app: Telegram", container).click();
    });

    await flush();

    const appFilteredUrl = lastRequestUrl(fetchMock);
    expect(requestPaths(fetchMock).slice(-2)).toEqual([
      "/atlas/overview",
      "/atlas/regions/region-travel",
    ]);
    expect(appFilteredUrl.pathname).toBe("/atlas/regions/region-travel");
    expect(appFilteredUrl.searchParams.get("app_hint")).toBe("telegram");

    act(() => {
      findButton("Use focus window", container).click();
    });

    await flush();

    const timeFilteredUrl = lastRequestUrl(fetchMock);
    expect(requestPaths(fetchMock).slice(-2)).toEqual([
      "/atlas/overview",
      "/atlas/regions/region-travel",
    ]);
    expect(timeFilteredUrl.pathname).toBe("/atlas/regions/region-travel");
    expect(timeFilteredUrl.searchParams.get("observed_from")).toBe("2026-03-01T00:00:00.000Z");
    expect(timeFilteredUrl.searchParams.get("observed_to")).toBe("2026-03-08T23:59:59.999Z");
  });

  it("uses backend evidence sort options rather than client-side reshuffling", async () => {
    await renderApp(root);
    await waitForText(container, "Atlas overview");

    act(() => {
      findButton("Travel Planning", container).click();
    });

    await waitForText(container, "2 representative screenshots");

    act(() => {
      findButton("Enter region", container).click();
    });

    await waitForText(container, "Trip booking lane");

    act(() => {
      findButton("Trip booking lane", container).click();
    });

    await flush();

    act(() => {
      findButton("Open evidence", container).click();
    });

    await waitForText(container, "Notes packing checklist");
    expect(container.textContent).toContain("Summary / topic-ish");
    expect(indexOfText(container, "Notes packing checklist")).toBeLessThan(
      indexOfText(container, "Browser booking confirmation"),
    );

    act(() => {
      changeSelect(findSelect("Evidence order", container), "app_hint_asc");
    });

    await waitForText(container, "Calendar departure reminder");

    const sortedEvidenceUrl = lastRequestUrl(fetchMock);
    expect(sortedEvidenceUrl.pathname).toBe("/atlas/evidence");
    expect(sortedEvidenceUrl.searchParams.get("sort")).toBe("app_hint_asc");
    expect(indexOfText(container, "Browser booking confirmation")).toBeLessThan(
      indexOfText(container, "Calendar departure reminder"),
    );
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

function lastRequestUrl(mock: ReturnType<typeof vi.fn>): URL {
  const request = mock.mock.calls[mock.mock.calls.length - 1]?.[0] as string;
  return new URL(request, "http://localhost");
}

function findButton(label: string, container: HTMLElement): HTMLButtonElement {
  const button = queryButton(label, container);

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`Could not find button with label: ${label}`);
  }

  return button;
}

function queryButton(label: string, container: HTMLElement): HTMLButtonElement | null {
  const button = Array.from(container.querySelectorAll("button")).find(
    (candidate) => candidate.textContent?.trim() === label,
  );
  return button instanceof HTMLButtonElement ? button : null;
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
  const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
  descriptor?.set?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function changeSelect(select: HTMLSelectElement, value: string) {
  const descriptor = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value");
  descriptor?.set?.call(select, value);
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

function pressEnter(target: EventTarget) {
  target.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
}

function indexOfText(container: HTMLElement, text: string): number {
  const content = container.textContent ?? "";
  const index = content.indexOf(text);
  if (index === -1) {
    throw new Error(`Could not find text: ${text}`);
  }
  return index;
}

function jsonResponse(payload: unknown) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => payload,
  };
}

function buildOverviewPayload(url: URL) {
  const searchQuery = url.searchParams.get("search_query");
  const filteredMatchCount =
    searchQuery === "hotel" ? 3 : searchQuery === "void" ? 0 : searchQuery === "prune" ? 2 : 8;

  return {
    atlas_run: buildAtlasRun(),
    regions: [
      buildRegion({
        region_key: "region-travel",
        title: "Travel Planning",
        x: -200,
        y: 30,
        overlay: { match_count: filteredMatchCount },
        top_apps: ["telegram", "gmail"],
        top_labels: ["travel planning", "itinerary"],
        top_entities: ["topic:trip-to-berlin"],
      }),
      buildRegion({
        region_key: "region-finance",
        title: "Finance Review",
        x: 220,
        y: -40,
        overlay: {
          match_count:
            searchQuery === "hotel" || searchQuery === "void" || searchQuery === "prune" ? 0 : 2,
        },
        top_apps: ["slack"],
        top_labels: ["budget review"],
        top_entities: ["topic:month-end-close"],
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
    active_filters: buildActiveFilters(url),
  };
}

function buildRegionDetailPayload(url: URL, regionKey: string) {
  if (regionKey === "region-finance") {
    return {
      atlas_run: buildAtlasRun(),
      region: buildRegion({
        region_key: "region-finance",
        title: "Finance Review",
        overlay: { match_count: 2 },
        item_count: 3,
        top_apps: ["slack", "sheets"],
        top_labels: ["budget review", "month-end close"],
        top_people: ["person:morgan"],
        top_entities: ["topic:month-end-close"],
        time_start: "2026-03-09T09:00:00Z",
        time_end: "2026-03-10T11:00:00Z",
      }),
      subregions: [],
      representatives: [
        buildItem({
          source_item_id: 401,
          region_key: "region-finance",
          subregion_key: null,
          semantic_summary: "Month-end close triage",
          app_hint: "Slack",
          is_representative: true,
          representative_rank: 1,
          object_refs: ["topic:month-end-close", "person:morgan"],
          observed_at: "2026-03-09T09:00:00Z",
        }),
      ],
      active_filters: buildActiveFilters(url),
    };
  }

  const searchQuery = url.searchParams.get("search_query");
  const subregions =
    searchQuery === "prune"
      ? [
          buildRegion({
            region_key: "region-travel/subregion-1",
            parent_region_key: "region-travel",
            level: 1,
            title: "Trip booking lane",
            x: -110,
            y: -20,
            overlay: { match_count: 2 },
            top_labels: ["arrival logistics"],
            top_apps: ["maps"],
            top_people: ["person:alice"],
            top_entities: ["task:plan-arrival"],
            time_start: "2026-03-02T08:00:00Z",
            time_end: "2026-03-04T11:00:00Z",
          }),
        ]
      : [
          buildRegion({
            region_key: "region-travel/subregion-1",
            parent_region_key: "region-travel",
            level: 1,
            title: "Trip booking lane",
            x: -110,
            y: -20,
            overlay: {
              match_count: searchQuery === "hotel" ? 1 : searchQuery === "void" ? 0 : 5,
            },
            top_labels: ["arrival logistics"],
            top_apps: ["maps"],
            top_people: ["person:alice"],
            top_entities: ["task:plan-arrival"],
            time_start: "2026-03-02T08:00:00Z",
            time_end: "2026-03-04T11:00:00Z",
          }),
          buildRegion({
            region_key: "region-travel/subregion-2",
            parent_region_key: "region-travel",
            level: 1,
            title: "Packing lane",
            x: 120,
            y: 35,
            overlay: { match_count: searchQuery === "hotel" || searchQuery === "void" ? 0 : 3 },
            top_labels: ["packing"],
            top_apps: ["notes"],
            top_entities: ["task:review-final-checklist"],
          }),
        ];

  return {
    atlas_run: buildAtlasRun(),
    region: buildRegion({
      region_key: "region-travel",
      title: "Travel Planning",
      overlay: { match_count: searchQuery === "hotel" ? 3 : 8 },
      top_apps: ["telegram", "gmail"],
      top_labels: ["travel planning", "itinerary"],
      top_entities: ["topic:trip-to-berlin"],
    }),
    subregions,
    representatives:
      searchQuery === "hotel"
        ? [
            buildItem({
              source_item_id: 111,
              region_key: "region-travel",
              semantic_summary: "Hotel confirmation thread",
              app_hint: "Telegram",
              is_representative: true,
              representative_rank: 1,
            }),
          ]
        : searchQuery === "void"
          ? []
        : [
            buildItem({
              source_item_id: 101,
              region_key: "region-travel",
              semantic_summary: "Trip research in Telegram",
              app_hint: "Telegram",
              is_representative: true,
              representative_rank: 1,
            }),
            buildItem({
              source_item_id: 102,
              region_key: "region-travel",
              semantic_summary: "Museum itinerary notes",
              app_hint: "Telegram",
              is_representative: true,
              representative_rank: 2,
            }),
          ],
    active_filters: buildActiveFilters(url),
  };
}

function buildEvidencePayload(url: URL) {
  const regionKey = url.searchParams.get("region_key");
  const sort = url.searchParams.get("sort") ?? "observed_at_desc";
  const searchQuery = url.searchParams.get("search_query");

  if (regionKey === "region-finance") {
    return {
      atlas_run: buildAtlasRun(),
      region_key: "region-finance",
      subregion_key: null,
      sort,
      representatives: [
        buildItem({
          source_item_id: 401,
          region_key: "region-finance",
          subregion_key: null,
          semantic_summary: "Month-end close triage",
          app_hint: "Slack",
          is_representative: true,
          representative_rank: 1,
          object_refs: ["topic:month-end-close", "person:morgan"],
          observed_at: "2026-03-09T09:00:00Z",
        }),
      ],
      bridges: [],
      long_tail_page: {
        items: [
          buildItem({
            source_item_id: 402,
            region_key: "region-finance",
            subregion_key: null,
            semantic_summary: "Slack budget close thread",
            app_hint: "Slack",
            object_refs: ["topic:month-end-close"],
            observed_at: "2026-03-10T10:00:00Z",
          }),
          buildItem({
            source_item_id: 403,
            region_key: "region-finance",
            subregion_key: null,
            semantic_summary: "Variance sheet review",
            app_hint: "Sheets",
            object_refs: ["task:check-variance"],
            observed_at: "2026-03-10T11:00:00Z",
          }),
        ],
        limit: 25,
        offset: 0,
        total: 2,
      },
      section_totals: {
        representatives: 1,
        bridges: 0,
        long_tail: 2,
      },
      active_filters: buildActiveFilters(url),
    };
  }

  if (searchQuery === "hotel") {
    return {
      atlas_run: buildAtlasRun(),
      region_key: "region-travel",
      subregion_key: url.searchParams.get("subregion_key"),
      sort,
      representatives: [
        buildItem({
          source_item_id: 111,
          region_key: "region-travel",
          subregion_key: "region-travel/subregion-1",
          semantic_summary: "Hotel confirmation thread",
          app_hint: "Telegram",
          is_representative: true,
          representative_rank: 1,
        }),
      ],
      bridges: [],
      long_tail_page: {
        items: [
          buildItem({
            source_item_id: 333,
            region_key: "region-travel",
            subregion_key: "region-travel/subregion-1",
            semantic_summary: "Hotel shortlist screenshot",
            app_hint: "Browser",
          }),
        ],
        limit: 1,
        offset: 0,
        total: 8,
      },
      section_totals: {
        representatives: 1,
        bridges: 0,
        long_tail: 8,
      },
      active_filters: buildActiveFilters(url),
    };
  }

  return {
    atlas_run: buildAtlasRun(),
    region_key: "region-travel",
    subregion_key: url.searchParams.get("subregion_key"),
    sort,
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
      items: buildLongTailItems(sort),
      limit: 25,
      offset: 0,
      total: 4,
    },
    section_totals: {
      representatives: 1,
      bridges: 1,
      long_tail: 4,
    },
    active_filters: buildActiveFilters(url),
  };
}

function buildLongTailItems(sort: string) {
  switch (sort) {
    case "app_hint_asc":
      return [
        buildItem({
          source_item_id: 307,
          semantic_summary: "Browser booking confirmation",
          app_hint: "Browser",
        }),
        buildItem({
          source_item_id: 306,
          semantic_summary: "Calendar departure reminder",
          app_hint: "Calendar",
        }),
      ];
    case "semantic_summary_asc":
      return [
        buildItem({
          source_item_id: 307,
          semantic_summary: "Browser booking confirmation",
          app_hint: "Browser",
        }),
        buildItem({
          source_item_id: 306,
          semantic_summary: "Calendar departure reminder",
          app_hint: "Calendar",
        }),
      ];
    case "observed_at_asc":
      return [
        buildItem({
          source_item_id: 305,
          semantic_summary: "Email itinerary checkpoint",
          app_hint: "Gmail",
          observed_at: "2026-03-01T09:00:00Z",
        }),
        buildItem({
          source_item_id: 306,
          semantic_summary: "Calendar departure reminder",
          app_hint: "Calendar",
          observed_at: "2026-03-02T09:00:00Z",
        }),
      ];
    default:
      return [
        buildItem({
          source_item_id: 308,
          semantic_summary: "Notes packing checklist",
          app_hint: "Notes",
          observed_at: "2026-03-08T09:00:00Z",
        }),
        buildItem({
          source_item_id: 307,
          semantic_summary: "Browser booking confirmation",
          app_hint: "Browser",
          observed_at: "2026-03-07T09:00:00Z",
        }),
      ];
  }
}

function buildActiveFilters(url: URL) {
  return {
    app_hint: url.searchParams.get("app_hint"),
    observed_from: url.searchParams.get("observed_from"),
    observed_to: url.searchParams.get("observed_to"),
    has_knowledge:
      url.searchParams.get("has_knowledge") === null
        ? null
        : url.searchParams.get("has_knowledge") === "true",
    search_query: url.searchParams.get("search_query"),
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
    region_key: "region-travel",
    subregion_key: "region-travel/subregion-1",
    x: 0,
    y: 0,
    semantic_summary: "Atlas evidence item",
    app_hint: "Telegram",
    observed_at: "2026-03-05T10:00:00Z",
    object_refs: ["topic:trip-to-berlin"],
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
