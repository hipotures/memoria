import { act } from "react";
import type { Root } from "react-dom/client";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

describe("App", () => {
  let container: HTMLDivElement;
  let root: Root;
  let fetchMock: ReturnType<typeof vi.fn>;
  let newPlotMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");

      if (url.pathname === "/similarity/graph") {
        return jsonResponse(buildGraphPayload());
      }

      throw new Error(`Unhandled similarity request: ${url.pathname}`);
    });

    vi.stubGlobal("fetch", fetchMock);
    window.__PLOTLY_CDN_VERSION__ = "3.5.0";
    newPlotMock = vi.fn(async () => undefined);
    window.Plotly = {
      newPlot: newPlotMock,
      react: vi.fn(async () => undefined),
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it("loads the similarity graph payload and renders the page chrome", async () => {
    await act(async () => {
      root.render(<App />);
    });

    await waitForText(container, "Cluster similarity network");
    expect(requestPaths(fetchMock)).toEqual(["/similarity/graph"]);
    expect(newPlotMock).toHaveBeenCalledOnce();

    const plotConfig = newPlotMock.mock.calls[0]?.[3];
    expect(plotConfig).toMatchObject({ responsive: true });
    expect(plotConfig).not.toHaveProperty("displayModeBar", false);
  });
});

async function waitForText(container: HTMLElement, text: string): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (container.textContent?.includes(text)) {
      return;
    }

    await act(async () => {
      await Promise.resolve();
    });
  }

  throw new Error(`Timed out waiting for text: ${text}`);
}

function requestPaths(fetchMock: ReturnType<typeof vi.fn>): string[] {
  return fetchMock.mock.calls.map(([input]) => {
    const url = new URL(String(input), "http://localhost");
    return `${url.pathname}${url.search}`;
  });
}

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function buildGraphPayload() {
  return {
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
    ],
    edges: [
      {
        source_region_key: "region-social",
        target_region_key: "region-research",
        weight: 0.61,
        support: 9,
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
}
