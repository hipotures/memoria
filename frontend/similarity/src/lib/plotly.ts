export type PlotlyLike = {
  newPlot: (
    element: HTMLElement,
    data: unknown[],
    layout: Record<string, unknown>,
    config: Record<string, unknown>,
  ) => Promise<unknown>;
  react: (
    element: HTMLElement,
    data: unknown[],
    layout: Record<string, unknown>,
    config: Record<string, unknown>,
  ) => Promise<unknown>;
};

declare global {
  interface Window {
    Plotly?: PlotlyLike;
    __PLOTLY_CDN_VERSION__?: string;
  }
}

export function resolvePlotly(): PlotlyLike {
  const plotly = window.Plotly;

  if (!plotly) {
    throw new Error("Plotly 3.5.0 CDN failed to load.");
  }

  return plotly;
}
