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
  let reactMock: ReturnType<typeof vi.fn>;
  let plotlyClickHandler:
    | ((event: {
        points?: Array<{
          data?: { name?: string };
          pointNumber?: number;
        }>;
      }) => void)
    | null;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    plotlyClickHandler = null;

    fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");

      if (url.pathname === "/similarity/graph") {
        return jsonResponse(buildGraphPayload());
      }

      throw new Error(`Unhandled similarity request: ${url.pathname}`);
    });

    vi.stubGlobal("fetch", fetchMock);
    window.__PLOTLY_CDN_VERSION__ = "3.5.0";
    newPlotMock = vi.fn(async (element: HTMLElement) => {
      bindPlotlyEvents(element);
      return undefined;
    });
    reactMock = vi.fn(async (element: HTMLElement) => {
      bindPlotlyEvents(element);
      return undefined;
    });
    window.Plotly = {
      newPlot: newPlotMock,
      react: reactMock,
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it("refetches with thresholds and adds a visual highlight trace for the clicked cluster", async () => {
    await act(async () => {
      root.render(<App />);
    });

    await waitForText(container, "Cluster similarity network");
    await waitForText(container, "Show labels");

    changeInputValue(findInput(container, "Min cluster size"), "8");
    changeInputValue(findInput(container, "Min edge weight"), "0.55");
    clickElement(findCheckbox(container, "Show labels"));
    clickElement(findButton(container, "Apply graph filters"));

    await waitForRequestCount(fetchMock, 2);
    expect(requestPaths(fetchMock)).toEqual([
      "/similarity/graph",
      "/similarity/graph?min_cluster_size=8&min_edge_weight=0.55",
    ]);
    expect(newPlotMock).toHaveBeenCalledOnce();
    expect(reactMock).toHaveBeenCalled();

    act(() => {
      plotlyClickHandler?.({
        points: [
          {
            data: { name: "research" },
            pointNumber: 0,
          },
        ],
      });
    });

    await waitForPlotUpdates(reactMock, 2);
    const plotConfig = newPlotMock.mock.calls[0]?.[3];
    expect(plotConfig).toMatchObject({ responsive: true });
    expect(plotConfig).not.toHaveProperty("displayModeBar", false);

    const lastFigureData = reactMock.mock.calls.at(-1)?.[1] as Array<Record<string, unknown>>;
    const highlightTrace = lastFigureData.find(
      (trace) => trace.name === "selected-highlight",
    );
    expect(highlightTrace).toMatchObject({
      type: "scattergl",
      mode: "markers",
      x: [0.68],
      y: [0.23],
      marker: {
        symbol: "circle-open",
      },
    });
  });

  it("surfaces Plotly init failures through the existing error UI", async () => {
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    window.Plotly = undefined;

    await act(async () => {
      root.render(<App />);
    });

    await waitForText(container, "Plotly 3.5.0 CDN failed to load.");
    expect(consoleErrorSpy).not.toHaveBeenCalled();
  });

  function bindPlotlyEvents(element: HTMLElement): void {
    const plotElement = element as HTMLElement & {
      on?: (eventName: string, handler: typeof plotlyClickHandler) => HTMLElement;
    };

    plotElement.on = vi.fn((eventName: string, handler: typeof plotlyClickHandler) => {
      if (eventName === "plotly_click") {
        plotlyClickHandler = handler;
      }

      return plotElement;
    });
  }
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

async function waitForRequestCount(fetchMock: ReturnType<typeof vi.fn>, count: number): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (fetchMock.mock.calls.length >= count) {
      return;
    }

    await act(async () => {
      await Promise.resolve();
    });
  }

  throw new Error(`Timed out waiting for ${count} fetch requests.`);
}

async function waitForPlotUpdates(plotMock: ReturnType<typeof vi.fn>, count: number): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (plotMock.mock.calls.length >= count) {
      return;
    }

    await act(async () => {
      await Promise.resolve();
    });
  }

  throw new Error(`Timed out waiting for ${count} plot updates.`);
}

function requestPaths(fetchMock: ReturnType<typeof vi.fn>): string[] {
  return fetchMock.mock.calls.map(([input]) => {
    const url = new URL(String(input), "http://localhost");
    return `${url.pathname}${url.search}`;
  });
}

function findInput(container: HTMLElement, labelText: string): HTMLInputElement {
  return findControlByLabel(container, labelText, "input:not([type='checkbox'])") as HTMLInputElement;
}

function findCheckbox(container: HTMLElement, labelText: string): HTMLInputElement {
  return findControlByLabel(container, labelText, "input[type='checkbox']") as HTMLInputElement;
}

function findControlByLabel(
  container: HTMLElement,
  labelText: string,
  selector: string,
): HTMLElement {
  const labels = Array.from(container.querySelectorAll("label"));
  const label = labels.find((candidate) => candidate.textContent?.includes(labelText));

  if (!label) {
    throw new Error(`Could not find label: ${labelText}`);
  }

  const nestedControl = label.querySelector(selector);
  if (nestedControl instanceof HTMLElement) {
    return nestedControl;
  }

  const htmlFor = label.getAttribute("for");
  if (!htmlFor) {
    throw new Error(`Label has no associated control: ${labelText}`);
  }

  const control = container.querySelector(`#${htmlFor}`);
  if (!(control instanceof HTMLElement)) {
    throw new Error(`Could not find control for label: ${labelText}`);
  }

  return control;
}

function findButton(container: HTMLElement, text: string): HTMLButtonElement {
  const buttons = Array.from(container.querySelectorAll("button"));
  const button = buttons.find((candidate) => candidate.textContent?.includes(text));

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`Could not find button: ${text}`);
  }

  return button;
}

function changeInputValue(input: HTMLInputElement, value: string): void {
  const valueSetter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  )?.set;

  if (!valueSetter) {
    throw new Error("HTMLInputElement value setter is unavailable.");
  }

  act(() => {
    valueSetter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

function clickElement(element: HTMLElement): void {
  act(() => {
    element.dispatchEvent(new MouseEvent("click", { bubbles: true }));
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
      connector_instance_id: null,
      min_cluster_size: 2,
      min_edge_weight: 0.25,
      app_hint: null,
      screen_category: null,
      observed_from: null,
      observed_to: null,
      has_knowledge: null,
      search_query: null,
    },
  };
}
