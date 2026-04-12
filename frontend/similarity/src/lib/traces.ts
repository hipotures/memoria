import type {
  SimilarityGraphEdge,
  SimilarityGraphNode,
  SimilarityGraphResponse,
} from "../api/contracts";

type FigureTrace = Record<string, unknown>;
type FigureLayout = Record<string, unknown>;
type FigureConfig = Record<string, unknown>;

export type SimilarityFigure = {
  data: FigureTrace[];
  layout: FigureLayout;
  config: FigureConfig;
};

export type SimilarityFigureOptions = {
  showLabels: boolean;
  selectedRegionKey: string | null;
};

export function buildSimilarityFigure(
  graph: SimilarityGraphResponse,
  options: SimilarityFigureOptions,
): SimilarityFigure {
  const nodesByRegionKey = new Map(graph.nodes.map((node) => [node.region_key, node]));

  const edgeTrace = {
    type: "scattergl",
    mode: "lines",
    hoverinfo: "skip",
    showlegend: false,
    line: {
      color: "rgba(180,220,220,0.20)",
      width: 0.6,
    },
    x: edgeCoordinates(graph.edges, nodesByRegionKey, "x"),
    y: edgeCoordinates(graph.edges, nodesByRegionKey, "y"),
  };

  const nodeTraces = graph.legend.map((entry) => {
    const categoryNodes = graph.nodes.filter(
      (node) => node.dominant_screen_category === entry.category,
    );

    return {
      type: "scattergl",
      mode: "markers",
      name: entry.category,
      x: categoryNodes.map((node) => node.x),
      y: categoryNodes.map((node) => node.y),
      text: categoryNodes.map((node) => node.title),
      customdata: categoryNodes.map((node) => [
        node.region_key,
        node.item_count,
        joinList(node.top_labels),
        joinList(node.top_apps),
        joinList(node.top_entities),
      ]),
      marker: {
        size: categoryNodes.map((node) => node.size),
        color: entry.color,
        opacity: 0.9,
        line: {
          color: "rgba(255,255,255,0.35)",
          width: 0.8,
        },
      },
      hovertemplate:
        "<b>%{text}</b><br>" +
        "cluster: %{customdata[0]}<br>" +
        "items: %{customdata[1]}<br>" +
        "top labels: %{customdata[2]}<br>" +
        "top apps: %{customdata[3]}<br>" +
        "top entities: %{customdata[4]}<extra></extra>",
    };
  });

  const labeledNodes = selectLabeledNodes(graph.nodes, options);
  const labelTrace = {
    type: "scattergl",
    mode: "text",
    showlegend: false,
    hoverinfo: "skip",
    text: labeledNodes.map((node) => node.title),
    x: labeledNodes.map((node) => node.x),
    y: labeledNodes.map((node) => node.y),
    textposition: "top center",
    textfont: {
      color: "rgba(235,240,245,0.85)",
      size: 11,
    },
  };

  return {
    data: [edgeTrace, ...nodeTraces, labelTrace],
    layout: {
      paper_bgcolor: "#001f2d",
      plot_bgcolor: "#001f2d",
      title: {
        text: "Memoria screenshots — cluster similarity network (shared topic/task signatures)",
        x: 0.02,
      },
      font: {
        color: "rgba(245,248,250,0.95)",
        size: 16,
      },
      xaxis: {
        showgrid: false,
        zeroline: false,
        showticklabels: false,
      },
      yaxis: {
        showgrid: false,
        zeroline: false,
        showticklabels: false,
      },
      legend: {
        x: 1.02,
        y: 1,
        bgcolor: "rgba(0,0,0,0)",
        font: { size: 12 },
        title: { text: "dominant screen category" },
      },
      margin: {
        l: 30,
        r: 180,
        t: 60,
        b: 30,
      },
      hoverlabel: {
        bgcolor: "rgba(15,20,25,0.95)",
        font: { size: 12 },
      },
    },
    config: {
      displaylogo: false,
      responsive: true,
      scrollZoom: true,
    },
  };
}

function edgeCoordinates(
  edges: SimilarityGraphEdge[],
  nodesByRegionKey: Map<string, SimilarityGraphNode>,
  axis: "x" | "y",
): Array<number | null> {
  const coordinates: Array<number | null> = [];

  for (const edge of edges) {
    const source = nodesByRegionKey.get(edge.source_region_key);
    const target = nodesByRegionKey.get(edge.target_region_key);

    if (!source || !target) {
      continue;
    }

    coordinates.push(source[axis], target[axis], null);
  }

  return coordinates;
}

function selectLabeledNodes(
  nodes: SimilarityGraphNode[],
  options: SimilarityFigureOptions,
): SimilarityGraphNode[] {
  if (!options.showLabels) {
    return [];
  }

  const labeledNodes = nodes.filter(
    (node) => node.is_labeled || node.region_key === options.selectedRegionKey,
  );

  return labeledNodes;
}

function joinList(values: string[]): string {
  if (values.length === 0) {
    return "none";
  }

  return values.join(", ");
}
