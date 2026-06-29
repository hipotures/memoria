import type { AtlasEdge, AtlasItem, AtlasOverviewPoint, AtlasRegion } from "../api/contracts";
import type { AtlasLevel } from "../state/atlasReducer";
import { atlasRegionDisplayCount, atlasRegionDisplayLabel, atlasRegionDisplayDomainMax } from "./displayCounts";
import { presentRegionCanvasTitle } from "./labelPresentation";
import { presentRegionVisualTreatment } from "./regionVisualTreatment";

export type DeckSceneInput = {
  level: AtlasLevel;
  width: number;
  height: number;
  regions: AtlasRegion[];
  overviewPoints?: AtlasOverviewPoint[];
  edges: AtlasEdge[];
  evidenceItems: AtlasItem[];
  filteringActive: boolean;
  selectedRegionKey: string | null;
  selectedSubregionKey: string | null;
  selectedItemId: number | null;
  focusRegion: AtlasRegion | null;
};

export type DeckScene = {
  focusBackdrop: DeckPolygonDatum | null;
  edges: DeckEdgeDatum[];
  regions: DeckPolygonDatum[];
  markers: DeckRegionMarkerDatum[];
  overviewPoints: DeckOverviewPointDatum[];
  labels: DeckLabelDatum[];
  items: DeckItemDatum[];
};

export type DeckPolygonDatum = {
  key: string;
  title: string;
  regionKey: string;
  polygons: number[][][];
  centroid: [number, number];
  fillColor: [number, number, number, number];
  lineColor: [number, number, number, number];
  lineWidth: number;
  selectable: boolean;
};

export type DeckLabelDatum = {
  key: string;
  regionKey: string;
  text: string;
  position: [number, number];
  color: [number, number, number, number];
  size: number;
  bold: boolean;
};

export type DeckEdgeDatum = {
  key: string;
  source: [number, number];
  target: [number, number];
  color: [number, number, number, number];
  width: number;
};

export type DeckItemDatum = {
  key: string;
  item: AtlasItem;
  position: [number, number];
  radius: number;
  fillColor: [number, number, number, number];
  lineColor: [number, number, number, number];
  lineWidth: number;
};

export type DeckRegionMarkerDatum = {
  key: string;
  regionKey: string;
  title: string;
  position: [number, number];
  radius: number;
  fillColor: [number, number, number, number];
  lineColor: [number, number, number, number];
  lineWidth: number;
  selectable: boolean;
};

export type DeckOverviewPointDatum = {
  key: string;
  sourceItemId: number;
  regionKey: string;
  position: [number, number];
  radius: number;
  fillColor: [number, number, number, number];
  lineColor: [number, number, number, number];
  lineWidth: number;
  appHint: string | null;
  matchesFilters: boolean;
  isRepresentative: boolean;
  isBridge: boolean;
};

type AtlasPoint = {
  x: number;
  y: number;
};

type Bounds = {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
};

const REGION_PALETTE = [
  { fill: [244, 99, 132], stroke: [148, 36, 70], label: [61, 19, 35] },
  { fill: [86, 209, 191], stroke: [21, 96, 89], label: [15, 61, 57] },
  { fill: [255, 195, 90], stroke: [148, 93, 29], label: [73, 46, 13] },
  { fill: [175, 143, 233], stroke: [90, 63, 142], label: [43, 30, 70] },
  { fill: [112, 175, 255], stroke: [42, 85, 148], label: [22, 41, 79] },
];

export function buildDeckScene(input: DeckSceneInput): DeckScene {
  const bounds = sceneBounds(input);
  const transform = createTransform(bounds, input.width, input.height, 56);
  const overlayMax = Math.max(1, atlasRegionDisplayDomainMax(input.regions));
  const itemCountMax = Math.max(1, ...input.regions.map((region) => region.item_count));
  const hasActiveSubregionSelection =
    (input.level === "region" || input.level === "evidence") &&
    input.selectedSubregionKey !== null;
  const labelRanks = new Map(
    [...input.regions]
      .sort((left, right) =>
        atlasRegionDisplayCount(right) - atlasRegionDisplayCount(left) ||
        right.item_count - left.item_count,
      )
      .map((region, index) => [region.region_key, index]),
  );

  const focusBackdrop =
    input.focusRegion !== null
      ? buildFocusBackdrop(input.focusRegion, transform)
      : null;
  const labelSelection = selectLabelKeys(input, transform);

  const regions: DeckPolygonDatum[] = [];
  const markers: DeckRegionMarkerDatum[] = [];
  const overviewPoints = buildOverviewPointCloud(input.overviewPoints ?? [], transform);
  const labels: DeckLabelDatum[] = [];

  input.regions.forEach((region, index) => {
    const palette = REGION_PALETTE[hashKey(region.region_key) % REGION_PALETTE.length];
    const isSelected =
      input.level === "overview"
        ? input.selectedRegionKey === region.region_key
        : input.selectedSubregionKey === region.region_key;
    const matchCount = atlasRegionDisplayCount(region);
    const isDimmed = input.filteringActive && matchCount === 0 && !isSelected;
    const treatment = presentRegionVisualTreatment({
      level: input.level,
      isSelected,
      isDimmed,
      index,
      hasActiveSelection: hasActiveSubregionSelection,
    });
    const fillAlpha =
      input.level === "overview" && !isDimmed
        ? Math.max(matchCount / overlayMax * 0.84, treatment.fillAlpha)
        : treatment.fillAlpha;
    const renderPolygon = shouldRenderPolygon({
      level: input.level,
      isSelected,
      hasActiveSubregionSelection,
    });
    const markerRadius = presentMarkerRadius({
      level: input.level,
      itemCount: region.item_count,
      maxItemCount: itemCountMax,
      isSelected,
    });

    regions.push({
      key: region.region_key,
      title: region.title,
      regionKey: region.region_key,
      polygons: renderPolygon ? projectRegionPolygons(region, transform) : [],
      centroid: projectPoint({ x: region.x, y: region.y }, transform),
      fillColor: rgba(palette.fill, renderPolygon ? fillAlpha : 0),
      lineColor: rgba(palette.stroke, renderPolygon ? treatment.strokeAlpha : 0),
      lineWidth: renderPolygon ? treatment.strokeWidth : 0,
      selectable: true,
    });

    markers.push({
      key: `${region.region_key}:marker`,
      regionKey: region.region_key,
      title: region.title,
      position: projectPoint({ x: region.x, y: region.y }, transform),
      radius: markerRadius,
      fillColor: rgba(palette.fill, isDimmed ? 0.42 : isSelected ? 0.92 : 0.78),
      lineColor: rgba(palette.stroke, isSelected ? 1 : 0.72),
      lineWidth: isSelected ? 3.5 : 2,
      selectable: true,
    });

    if (
      labelSelection.has(region.region_key) &&
      shouldRenderLabel(input.level, labelRanks.get(region.region_key) ?? index, isSelected, treatment.showLabel)
    ) {
      const labelPos = projectPoint(
        { x: region.label_x || region.x, y: region.label_y || region.y },
        transform,
      );
      labels.push({
        key: `${region.region_key}:title`,
        regionKey: region.region_key,
        text: presentRegionCanvasTitle(region.title),
        position: [labelPos[0], labelPos[1] - 10],
        color: rgba(isSelected ? palette.stroke : palette.label, treatment.labelAlpha),
        size: treatment.labelFontSize,
        bold: true,
      });
      if (treatment.showCountLabel) {
        if (input.level === "overview") {
          return;
        }
        labels.push({
          key: `${region.region_key}:count`,
          regionKey: region.region_key,
          text: atlasRegionDisplayLabel(region),
          position: [labelPos[0], labelPos[1] + 16],
          color: rgba([52, 80, 93], treatment.countAlpha),
          size: 12,
          bold: false,
        });
      }
    }
  });

  return {
    focusBackdrop,
    edges: buildDeckEdges(input.regions, input.edges, transform, input.filteringActive, labelSelection, input),
    regions,
    markers,
    overviewPoints,
    labels,
    items: buildDeckItems(input.evidenceItems, transform, input.selectedItemId),
  };
}

function buildFocusBackdrop(
  region: AtlasRegion,
  transform: (x: number, y: number) => [number, number],
): DeckPolygonDatum | null {
  const palette = REGION_PALETTE[hashKey(region.region_key) % REGION_PALETTE.length];
  const polygons = projectRegionPolygons(region, transform);
  if (polygons.length === 0) {
    return null;
  }

  return {
    key: `${region.region_key}:focus`,
    title: region.title,
    regionKey: region.region_key,
    polygons,
    centroid: projectPoint({ x: region.x, y: region.y }, transform),
    fillColor: rgba(palette.fill, 0.08),
    lineColor: rgba(palette.stroke, 0.18),
    lineWidth: 2.5,
    selectable: false,
  };
}

function buildDeckEdges(
  regions: AtlasRegion[],
  edges: AtlasEdge[],
  transform: (x: number, y: number) => [number, number],
  filteringActive: boolean,
  labelSelection: Set<string>,
  input: DeckSceneInput,
): DeckEdgeDatum[] {
  const byKey = new Map(regions.map((region) => [region.region_key, region]));
  const selectedKey = input.level === "overview" ? input.selectedRegionKey : input.selectedSubregionKey;
  if (input.level === "overview" && selectedKey === null) {
    return [];
  }
  const visibleEdges = edges
    .filter((edge) => {
      if (input.level === "overview") {
        return (
          selectedKey !== null &&
          (edge.source_region_key === selectedKey || edge.target_region_key === selectedKey)
        );
      }
      const bothLabeled = labelSelection.has(edge.source_region_key) && labelSelection.has(edge.target_region_key);
      const touchesSelected =
        selectedKey !== null &&
        (edge.source_region_key === selectedKey || edge.target_region_key === selectedKey);
      return bothLabeled || touchesSelected;
    })
    .sort((left, right) =>
      edgePriority(right) - edgePriority(left) || right.weight - left.weight,
    )
    .slice(0, input.level === "overview" ? 4 : 12);

  return visibleEdges.flatMap((edge) => {
    const sourceRegion = byKey.get(edge.source_region_key);
    const targetRegion = byKey.get(edge.target_region_key);
    if (sourceRegion === undefined || targetRegion === undefined) {
      return [];
    }
    const dimmed =
      filteringActive &&
      (atlasRegionDisplayCount(sourceRegion) === 0 || atlasRegionDisplayCount(targetRegion) === 0);
    const isOverview = input.level === "overview";
    const isBridge = edge.edge_type === "semantic_bridge";
    return [{
      key: `${edge.source_region_key}:${edge.target_region_key}`,
      source: projectPoint({ x: sourceRegion.x, y: sourceRegion.y }, transform),
      target: projectPoint({ x: targetRegion.x, y: targetRegion.y }, transform),
      color: rgba(
        [105, 122, 128],
        dimmed ? 0.08 : isOverview ? (isBridge ? 0.22 : 0.14) : 0.24 + edge.weight * 0.18,
      ),
      width: dimmed ? 1 : isOverview ? (isBridge ? 2.2 : 1.25) : 1 + edge.weight * 2,
    }];
  });
}

function buildDeckItems(
  items: AtlasItem[],
  transform: (x: number, y: number) => [number, number],
  selectedItemId: number | null,
): DeckItemDatum[] {
  const maxBridgeScore = Math.max(1, ...items.map((item) => item.bridge_score || 0));
  return items.map((item) => {
    const scoreRatio = (item.bridge_score || 0) / maxBridgeScore;
    const radius = 4 + scoreRatio * 5;
    const fill =
      item.is_representative ? [165, 107, 46] :
      item.is_bridge ? [38, 95, 103] :
      [77, 97, 119];
    return {
      key: String(item.source_item_id),
      item,
      position: projectPoint({ x: item.x, y: item.y }, transform),
      radius: selectedItemId === item.source_item_id ? radius + 2.5 : radius,
      fillColor: rgba(fill, item.is_bridge ? 0.9 : 0.82),
      lineColor: rgba([246, 240, 228], selectedItemId === item.source_item_id ? 1 : 0.82),
      lineWidth: selectedItemId === item.source_item_id ? 3 : 1.5,
    };
  });
}

function buildOverviewPointCloud(
  points: AtlasOverviewPoint[],
  transform: (x: number, y: number) => [number, number],
): DeckOverviewPointDatum[] {
  return [...points]
    .sort((left, right) => {
      const leftRank =
        (left.matches_filters ? 1 : 0) * 100 +
        (left.is_representative ? 1 : 0) * 10 +
        (left.is_bridge ? 1 : 0);
      const rightRank =
        (right.matches_filters ? 1 : 0) * 100 +
        (right.is_representative ? 1 : 0) * 10 +
        (right.is_bridge ? 1 : 0);
      return leftRank - rightRank || left.source_item_id - right.source_item_id;
    })
    .map((point) => {
    const palette = REGION_PALETTE[hashKey(point.region_key) % REGION_PALETTE.length];
    const radius = point.is_representative ? 5.75 : point.is_bridge ? 3.1 : 1.65;
    const alpha = point.matches_filters ? 0.58 : 0.14;
    const outlineAlpha = point.is_representative ? 0.85 : point.is_bridge ? 0.28 : 0;
    return {
      key: `overview-point:${point.source_item_id}`,
      sourceItemId: point.source_item_id,
      regionKey: point.region_key,
      position: projectPoint({ x: point.x, y: point.y }, transform),
      radius,
      fillColor: rgba(palette.fill, alpha),
      lineColor: rgba(palette.stroke, outlineAlpha),
      lineWidth: point.is_representative ? 1.4 : point.is_bridge ? 0.8 : 0,
      appHint: point.app_hint,
      matchesFilters: point.matches_filters,
      isRepresentative: point.is_representative,
      isBridge: point.is_bridge,
    };
  });
}

function projectRegionPolygons(
  region: AtlasRegion,
  transform: (x: number, y: number) => [number, number],
): number[][][] {
  const rings = regionRings(region);
  if (rings.length > 0) {
    return rings.map((ring) => ring.map((point) => projectPoint(point, transform)));
  }

  const center = projectPoint({ x: region.x, y: region.y }, transform);
  return [[
    [center[0] - 90, center[1] - 54],
    [center[0] + 90, center[1] - 54],
    [center[0] + 90, center[1] + 54],
    [center[0] - 90, center[1] + 54],
  ]];
}

function regionRings(region: AtlasRegion): AtlasPoint[][] {
  const rings = (region.region_shape as { rings?: unknown }).rings;
  if (!Array.isArray(rings)) {
    return [];
  }
  return rings
    .map((ring) => {
      if (!Array.isArray(ring)) {
        return [];
      }
      return ring
        .map((point) => {
          if (
            typeof point === "object" &&
            point !== null &&
            "x" in point &&
            "y" in point &&
            typeof point.x === "number" &&
            typeof point.y === "number"
          ) {
            return { x: point.x, y: point.y };
          }
          return null;
        })
        .filter((point): point is AtlasPoint => point !== null);
    })
    .filter((ring) => ring.length > 2);
}

function sceneBounds(scene: Omit<DeckSceneInput, "width" | "height">): Bounds {
  const points: AtlasPoint[] = [];
  const hasActiveSubregionSelection =
    (scene.level === "region" || scene.level === "evidence") &&
    scene.selectedSubregionKey !== null;

  if (scene.level === "overview" && (scene.overviewPoints?.length ?? 0) > 0) {
    scene.overviewPoints?.forEach((point) => {
      points.push({ x: point.x, y: point.y });
    });
  }

  if (scene.focusRegion !== null) {
    points.push(...regionRings(scene.focusRegion).flat());
  }

  scene.regions.forEach((region) => {
    const isSelected =
      scene.level === "overview"
        ? scene.selectedRegionKey === region.region_key
        : scene.selectedSubregionKey === region.region_key;
    points.push({ x: region.x, y: region.y });
    points.push({ x: region.label_x, y: region.label_y });
    if (
      shouldRenderPolygon({
        level: scene.level,
        isSelected,
        hasActiveSubregionSelection,
      })
    ) {
      points.push(...regionRings(region).flat());
    }
  });

  scene.evidenceItems.forEach((item) => {
    points.push({ x: item.x, y: item.y });
  });

  if (points.length === 0) {
    return { minX: -1, minY: -1, maxX: 1, maxY: 1 };
  }

  return {
    minX: Math.min(...points.map((point) => point.x)),
    minY: Math.min(...points.map((point) => point.y)),
    maxX: Math.max(...points.map((point) => point.x)),
    maxY: Math.max(...points.map((point) => point.y)),
  };
}

function createTransform(bounds: Bounds, width: number, height: number, padding: number) {
  const usableWidth = Math.max(width - padding * 2, 1);
  const usableHeight = Math.max(height - padding * 2, 1);
  const domainWidth = Math.max(bounds.maxX - bounds.minX, 1e-6);
  const domainHeight = Math.max(bounds.maxY - bounds.minY, 1e-6);
  const scale = Math.min(usableWidth / domainWidth, usableHeight / domainHeight);
  const offsetX = (width - domainWidth * scale) / 2;
  const offsetY = (height - domainHeight * scale) / 2;

  return (x: number, y: number): [number, number] => [
    offsetX + (x - bounds.minX) * scale,
    height - (offsetY + (y - bounds.minY) * scale),
  ];
}

function projectPoint(point: AtlasPoint, transform: (x: number, y: number) => [number, number]) {
  return transform(point.x, point.y);
}

function rgba(rgb: number[], alpha: number): [number, number, number, number] {
  return [rgb[0] ?? 0, rgb[1] ?? 0, rgb[2] ?? 0, Math.round(alpha * 255)];
}

function hashKey(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function shouldRenderPolygon({
  level,
  isSelected,
  hasActiveSubregionSelection,
}: {
  level: AtlasLevel;
  isSelected: boolean;
  hasActiveSubregionSelection: boolean;
}): boolean {
  if (level === "overview") {
    return isSelected;
  }
  if (!hasActiveSubregionSelection) {
    return false;
  }
  return isSelected;
}

function presentMarkerRadius({
  level,
  itemCount,
  maxItemCount,
  isSelected,
}: {
  level: AtlasLevel;
  itemCount: number;
  maxItemCount: number;
  isSelected: boolean;
}): number {
  const ratio = Math.sqrt(Math.max(itemCount, 1) / Math.max(maxItemCount, 1));
  const [base, spread] = level === "overview" ? [10, 34] : [8, 20];
  const radius = base + ratio * spread;
  return isSelected ? radius + 4 : radius;
}

function shouldRenderLabel(
  level: AtlasLevel,
  rank: number,
  isSelected: boolean,
  treatmentAllows: boolean,
): boolean {
  if (level === "overview") {
    return treatmentAllows && isSelected;
  }
  if (!treatmentAllows) {
    return false;
  }
  if (isSelected) {
    return true;
  }
  const limit = level === "overview" ? 14 : 10;
  return rank < limit;
}

function selectLabelKeys(
  input: DeckSceneInput,
  transform: (x: number, y: number) => [number, number],
): Set<string> {
  const ranked = [...input.regions].sort((left, right) =>
    atlasRegionDisplayCount(right) - atlasRegionDisplayCount(left) ||
    right.item_count - left.item_count,
  );
  const selectedKey = input.level === "overview" ? input.selectedRegionKey : input.selectedSubregionKey;
  const limit = input.level === "overview" ? 8 : 8;
  const minDistance = input.level === "overview" ? 88 : 72;
  const chosen = new Set<string>();
  const seenTitles = new Set<string>();
  const anchors: [number, number][] = [];

  if (selectedKey !== null) {
    const selectedRegion = ranked.find((region) => region.region_key === selectedKey);
    if (selectedRegion !== undefined) {
      chosen.add(selectedRegion.region_key);
      seenTitles.add(normalizeTitleKey(selectedRegion.title));
      anchors.push(projectPoint({ x: selectedRegion.label_x || selectedRegion.x, y: selectedRegion.label_y || selectedRegion.y }, transform));
    }
  }

  for (const region of ranked) {
    if (chosen.size >= limit) {
      break;
    }
    if (chosen.has(region.region_key)) {
      continue;
    }
    const titleKey = normalizeTitleKey(region.title);
    if (input.level === "overview" && seenTitles.has(titleKey)) {
      continue;
    }
    const point = projectPoint(
      { x: region.label_x || region.x, y: region.label_y || region.y },
      transform,
    );
    const collides = anchors.some((anchor) => distance(anchor, point) < minDistance);
    if (collides) {
      continue;
    }
    chosen.add(region.region_key);
    seenTitles.add(titleKey);
    anchors.push(point);
  }

  return chosen;
}

function edgePriority(edge: AtlasEdge): number {
  return (edge.edge_type === "semantic_bridge" ? 1000 : 0) + edge.weight;
}

function normalizeTitleKey(title: string): string {
  return presentRegionCanvasTitle(title).replace(/\s+/g, " ").trim().toLowerCase();
}

function distance(left: [number, number], right: [number, number]): number {
  return Math.hypot(left[0] - right[0], left[1] - right[1]);
}
