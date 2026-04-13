import type {
  SimilarityGraphEdge,
  SimilarityGraphNode,
  SimilarityGraphResponse,
} from "../api/contracts";

type FigureTrace = Record<string, unknown>;
type FigureLayout = Record<string, unknown>;
type FigureConfig = Record<string, unknown>;
type LegacySimilarityGraphNode = SimilarityGraphNode & {
  is_labeled?: boolean;
  label?: string;
  label_x?: number;
  label_y?: number;
  label_priority?: number;
};

export type SimilarityFigure = {
  data: FigureTrace[];
  layout: FigureLayout;
  config: FigureConfig;
};

export type LabelMode = "none" | "default" | "all" | "selected";

export type SimilarityFigureOptions = {
  labelMode?: LabelMode;
  showLabels?: boolean;
  selectedRegionKey: string | null;
  visibleCategories: Set<string> | null;
};

export function buildSimilarityFigure(
  graph: SimilarityGraphResponse,
  options: SimilarityFigureOptions,
): SimilarityFigure {
  const allNodesByRegionKey = new Map(graph.nodes.map((node) => [node.region_key, node]));
  const visibleNodes = filterVisibleNodes(graph.nodes, options.visibleCategories);
  const nodesByRegionKey = new Map(visibleNodes.map((node) => [node.region_key, node]));
  const selectedNode =
    options.selectedRegionKey !== null
      ? nodesByRegionKey.get(options.selectedRegionKey) ?? null
      : null;
  const visibleEdges = filterVisibleEdges(
    graph.edges,
    allNodesByRegionKey,
    options.visibleCategories,
  );
  const selectedNeighborhood =
    selectedNode === null ? null : collectSelectedNeighborhood(visibleEdges, selectedNode.region_key);
  const selectedNeighborhoodEdges =
    selectedNode === null
      ? []
      : visibleEdges.filter((edge) => edgeTouchesSelection(edge, selectedNode.region_key));
  const defaultLabelLimit = graph.default_label_limit ?? 20;

  const edgeTrace = {
    type: "scattergl",
    mode: "lines",
    hoverinfo: "skip",
    showlegend: false,
    line: {
      color:
        selectedNode === null ? "rgba(180,220,220,0.18)" : "rgba(180,220,220,0.05)",
      width: 0.7,
    },
    x: edgeCoordinates(visibleEdges, allNodesByRegionKey, "x"),
    y: edgeCoordinates(visibleEdges, allNodesByRegionKey, "y"),
  };

  const nodeTraces = graph.legend.map((entry) => {
    const categoryNodes = graph.nodes.filter(
      (node) => node.dominant_screen_category === entry.category,
    );
    const categoryIsVisible =
      options.visibleCategories === null || options.visibleCategories.has(entry.category);
    const categoryColor = resolveCategoryColor(entry.category, entry.color);

    return {
      type: "scattergl",
      mode: "markers",
      name: entry.category,
      x: categoryNodes.map((node) => node.x),
      y: categoryNodes.map((node) => node.y),
      text: categoryNodes.map((node) => resolveNodeLabel(node)),
      customdata: categoryNodes.map((node) => [
        node.region_key,
        resolveNodeLabel(node),
        node.title,
        node.item_count,
        node.dominant_screen_category,
        joinList(node.top_labels),
        joinList(node.top_apps),
      ]),
      marker: {
        size: categoryNodes.map((node) => node.size),
        color: categoryColor,
        opacity: categoryNodes.map((node) =>
          resolveNodeOpacity(node, selectedNode, selectedNeighborhood),
        ),
        line: {
          color: "rgba(255,255,255,0.4)",
          width: 0.8,
        },
      },
      visible: categoryIsVisible ? true : "legendonly",
      hovertemplate:
        "<b>%{customdata[1]}</b><br>" +
        "title: %{customdata[2]}<br>" +
        "items: %{customdata[3]}<br>" +
        "screen category: %{customdata[4]}<br>" +
        "top labels: %{customdata[5]}<br>" +
        "top apps: %{customdata[6]}<extra></extra>",
    };
  });

  const selectedNeighborhoodEdgeTrace =
    selectedNeighborhoodEdges.length === 0
      ? null
      : {
          type: "scattergl",
          mode: "lines",
          name: "selected-neighborhood-edges",
          hoverinfo: "skip",
          showlegend: false,
          line: {
            color: "rgba(148,217,255,0.72)",
            width: 1.8,
          },
          x: edgeCoordinates(selectedNeighborhoodEdges, allNodesByRegionKey, "x"),
          y: edgeCoordinates(selectedNeighborhoodEdges, allNodesByRegionKey, "y"),
        };

  const highlightTrace =
    selectedNode === null
      ? null
      : {
          type: "scattergl",
          mode: "markers",
          name: "selected-highlight",
          showlegend: false,
          hoverinfo: "skip",
          x: [selectedNode.x],
          y: [selectedNode.y],
          customdata: [selectedNode.region_key],
          marker: {
            size: [selectedNode.size + 10],
            symbol: "circle-open",
            color: "rgba(255,255,255,0)",
            line: {
              color: "rgba(255,255,255,0.95)",
              width: 2.5,
            },
          },
        };

  const labeledNodes = selectLabeledNodes(
    visibleNodes,
    options,
    selectedNode,
    defaultLabelLimit,
  );
  const labelText = labeledNodes.map((node) => resolveNodeLabel(node));
  const labelX = labeledNodes.map((node) => resolveNodeLabelCoordinate(node, "x"));
  const labelY = labeledNodes.map((node) => resolveNodeLabelCoordinate(node, "y"));
  const labelCustomdata = labeledNodes.map((node) => node.region_key);
  const labelTrace = {
    type: "scattergl",
    mode: "text",
    name: "labels",
    showlegend: false,
    hoverinfo: "skip",
    text: labelText,
    x: labelX,
    y: labelY,
    customdata: labelCustomdata,
    textposition: "middle center",
    textfont: {
      color: labeledNodes.map((node) =>
        resolveLabelColor(node, selectedNode, selectedNeighborhood),
      ),
      size: 11,
    },
  };
  const traces =
    [
      edgeTrace,
      ...nodeTraces,
      ...(selectedNeighborhoodEdgeTrace === null ? [] : [selectedNeighborhoodEdgeTrace]),
      ...(highlightTrace === null ? [] : [highlightTrace]),
      labelTrace,
    ];

  return {
    data: traces,
    layout: {
      paper_bgcolor: "#001f2d",
      plot_bgcolor: "#001f2d",
      title: {
        text: "Memoria screenshots — region similarity graph (semantic similarity edges)",
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

function resolveLabelMode(options: SimilarityFigureOptions): LabelMode {
  if (options.labelMode !== undefined) {
    return options.labelMode;
  }

  if (options.showLabels === false) {
    return "none";
  }

  return "default";
}

function filterVisibleNodes(
  nodes: SimilarityGraphNode[],
  visibleCategories: Set<string> | null,
): SimilarityGraphNode[] {
  if (visibleCategories === null) {
    return nodes;
  }

  return nodes.filter((node) => visibleCategories.has(node.dominant_screen_category));
}

function filterVisibleEdges(
  edges: SimilarityGraphEdge[],
  nodesByRegionKey: Map<string, SimilarityGraphNode>,
  visibleCategories: Set<string> | null,
): SimilarityGraphEdge[] {
  return edges.filter((edge) => {
    const source = nodesByRegionKey.get(edge.source_region_key);
    const target = nodesByRegionKey.get(edge.target_region_key);

    if (!source || !target) {
      return false;
    }

    if (
      visibleCategories !== null &&
      (!visibleCategories.has(source.dominant_screen_category) ||
        !visibleCategories.has(target.dominant_screen_category))
    ) {
      return false;
    }
    return true;
  });
}

const CATEGORY_COLOR_OVERRIDES: Record<string, string> = {
  article: "#FF9F1C",
  banking: "#B388EB",
  calendar: "#7B8CFF",
  chat: "#6EC5FF",
  code: "#FF6B6B",
  document: "#3DDC97",
  generic: "#00BBF9",
  maps: "#2EC4B6",
  news: "#F15BB5",
  research: "#FF7F50",
  shopping: "#F9C74F",
  social: "#00F5D4",
  utility: "#A0AEC0",
  video: "#43AA8B",
  workflow: "#90BE6D",
};

const DISTINCT_CATEGORY_PALETTE = [
  "#6EC5FF",
  "#3DDC97",
  "#FF9F1C",
  "#FF6B6B",
  "#B388EB",
  "#00BBF9",
  "#F9C74F",
  "#F15BB5",
  "#43AA8B",
  "#7B8CFF",
  "#90BE6D",
  "#FF7F50",
  "#00F5D4",
  "#A0AEC0",
];

function resolveCategoryColor(category: string, fallbackColor: string): string {
  const override = CATEGORY_COLOR_OVERRIDES[category];
  if (override) {
    return override;
  }

  const paletteIndex = Math.abs(hashCategory(category)) % DISTINCT_CATEGORY_PALETTE.length;
  return DISTINCT_CATEGORY_PALETTE[paletteIndex] ?? fallbackColor;
}

function hashCategory(category: string): number {
  let hash = 0;

  for (const character of category) {
    hash = (hash * 31 + character.charCodeAt(0)) | 0;
  }

  return hash;
}

function collectSelectedNeighborhood(
  edges: SimilarityGraphEdge[],
  selectedRegionKey: string,
): Set<string> {
  const neighborhood = new Set<string>([selectedRegionKey]);

  for (const edge of edges) {
    if (edge.source_region_key === selectedRegionKey) {
      neighborhood.add(edge.target_region_key);
    }

    if (edge.target_region_key === selectedRegionKey) {
      neighborhood.add(edge.source_region_key);
    }
  }

  return neighborhood;
}

function edgeTouchesSelection(edge: SimilarityGraphEdge, selectedRegionKey: string): boolean {
  return (
    edge.source_region_key === selectedRegionKey || edge.target_region_key === selectedRegionKey
  );
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

function resolveNodeOpacity(
  node: SimilarityGraphNode,
  selectedNode: SimilarityGraphNode | null,
  selectedNeighborhood: Set<string> | null,
): number {
  if (selectedNode === null || selectedNeighborhood === null) {
    return 0.9;
  }

  if (node.region_key === selectedNode.region_key) {
    return 1;
  }

  if (selectedNeighborhood.has(node.region_key)) {
    return 0.94;
  }

  return 0.12;
}

function resolveLabelColor(
  node: SimilarityGraphNode,
  selectedNode: SimilarityGraphNode | null,
  selectedNeighborhood: Set<string> | null,
): string {
  const baseColor = resolveCategoryColor(node.dominant_screen_category, "#6EC5FF");
  const darkText = withAlpha("#07121A", 0.96);
  const darkMuted = withAlpha("#07121A", 0.34);
  const darkFaint = withAlpha("#07121A", 0.12);
  const lightText = withAlpha("#F5F8FA", 0.96);
  const lightMuted = withAlpha("#D2DCE6", 0.42);
  const lightFaint = withAlpha("#D2DCE6", 0.18);
  const prefersDarkText = colorLuminance(baseColor) >= 0.58;
  const labelSitsOnNode = isLabelAnchoredOnNode(node);

  if (selectedNode === null || selectedNeighborhood === null) {
    return labelSitsOnNode && prefersDarkText ? darkText : lightText;
  }

  if (node.region_key === selectedNode.region_key) {
    return labelSitsOnNode && prefersDarkText ? darkText : lightText;
  }

  if (selectedNeighborhood.has(node.region_key)) {
    return labelSitsOnNode && prefersDarkText ? darkMuted : lightMuted;
  }

  return labelSitsOnNode && prefersDarkText ? darkFaint : lightFaint;
}

function isLabelAnchoredOnNode(node: SimilarityGraphNode): boolean {
  const labelX = resolveNodeLabelCoordinate(node, "x");
  const labelY = resolveNodeLabelCoordinate(node, "y");
  return Math.abs(labelX - node.x) <= 0.015 && Math.abs(labelY - node.y) <= 0.015;
}

function colorLuminance(color: string): number {
  const hex = color.replace("#", "");
  if (hex.length !== 6) {
    return 0;
  }

  const red = Number.parseInt(hex.slice(0, 2), 16) / 255;
  const green = Number.parseInt(hex.slice(2, 4), 16) / 255;
  const blue = Number.parseInt(hex.slice(4, 6), 16) / 255;

  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function withAlpha(hexColor: string, alpha: number): string {
  const hex = hexColor.replace("#", "");
  if (hex.length !== 6) {
    return hexColor;
  }

  const red = Number.parseInt(hex.slice(0, 2), 16);
  const green = Number.parseInt(hex.slice(2, 4), 16);
  const blue = Number.parseInt(hex.slice(4, 6), 16);

  return `rgba(${red},${green},${blue},${alpha})`;
}

function selectLabeledNodes(
  nodes: SimilarityGraphNode[],
  options: SimilarityFigureOptions,
  selectedNode: SimilarityGraphNode | null,
  defaultLabelLimit: number,
): SimilarityGraphNode[] {
  if (usesLegacyShowLabelsCompatibility(options)) {
    return selectLegacyLabeledNodes(nodes, options.showLabels ?? true, selectedNode, defaultLabelLimit);
  }

  const labelMode = resolveLabelMode(options);

  if (labelMode === "none") {
    return [];
  }

  if (labelMode === "selected") {
    return selectedNode ? [selectedNode] : [];
  }

  if (labelMode === "all") {
    return nodes;
  }

  return selectDefaultLabeledNodes(nodes, defaultLabelLimit);
}

function joinList(values: string[]): string {
  if (values.length === 0) {
    return "none";
  }

  return values.join(", ");
}

function usesLegacyShowLabelsCompatibility(options: SimilarityFigureOptions): boolean {
  return options.labelMode === undefined && options.showLabels !== undefined;
}

function selectLegacyLabeledNodes(
  nodes: SimilarityGraphNode[],
  showLabels: boolean,
  selectedNode: SimilarityGraphNode | null,
  defaultLabelLimit: number,
): SimilarityGraphNode[] {
  if (!showLabels) {
    return selectedNode ? [selectedNode] : [];
  }

  const labeledNodes = selectDefaultLabeledNodes(nodes, defaultLabelLimit);
  return includeSelectedNode(labeledNodes, selectedNode);
}

function selectDefaultLabeledNodes(
  nodes: SimilarityGraphNode[],
  defaultLabelLimit: number,
): SimilarityGraphNode[] {
  const nodesWithRenderMetadata = nodes.filter(hasBackendLabelMetadata);
  if (nodesWithRenderMetadata.length > 0) {
    return [...nodesWithRenderMetadata]
      .sort(
        (left, right) =>
          resolveNodeLabelPriority(right) - resolveNodeLabelPriority(left) ||
          resolveNodeLabel(left).localeCompare(resolveNodeLabel(right)),
      )
      .slice(0, defaultLabelLimit);
  }

  return nodes.filter((node) => isLegacyLabeledNode(node));
}

function includeSelectedNode(
  nodes: SimilarityGraphNode[],
  selectedNode: SimilarityGraphNode | null,
): SimilarityGraphNode[] {
  if (selectedNode === null) {
    return nodes;
  }

  if (nodes.some((node) => node.region_key === selectedNode.region_key)) {
    return nodes;
  }

  return [...nodes, selectedNode];
}

function hasBackendLabelMetadata(node: SimilarityGraphNode): boolean {
  const legacyNode = node as LegacySimilarityGraphNode;

  return (
    typeof legacyNode.label === "string" &&
    typeof legacyNode.label_x === "number" &&
    typeof legacyNode.label_y === "number" &&
    typeof legacyNode.label_priority === "number"
  );
}

function isLegacyLabeledNode(node: SimilarityGraphNode): boolean {
  const legacyNode = node as LegacySimilarityGraphNode;
  return legacyNode.is_labeled === true;
}

function resolveNodeLabel(node: SimilarityGraphNode): string {
  const legacyNode = node as LegacySimilarityGraphNode;
  return typeof legacyNode.label === "string" ? legacyNode.label : node.title;
}

function resolveNodeLabelCoordinate(
  node: SimilarityGraphNode,
  axis: "x" | "y",
): number {
  const legacyNode = node as LegacySimilarityGraphNode;

  if (axis === "x") {
    return typeof legacyNode.label_x === "number" ? legacyNode.label_x : node.x;
  }

  return typeof legacyNode.label_y === "number" ? legacyNode.label_y : node.y;
}

function resolveNodeLabelPriority(node: SimilarityGraphNode): number {
  const legacyNode = node as LegacySimilarityGraphNode;
  return typeof legacyNode.label_priority === "number" ? legacyNode.label_priority : 0;
}
