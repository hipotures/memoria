import { useEffect, useMemo, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import { scaleLinear } from "d3-scale";

import type { AtlasEdge, AtlasItem, AtlasRegion } from "../api/contracts";
import { formatAtlasDateRange, humanizeAtlasValue } from "../lib/atlasPresentation";
import type { AtlasLevel } from "../state/atlasReducer";
import {
  atlasRegionDisplayCount,
  atlasRegionDisplayDomainMax,
  atlasRegionDisplayLabel,
} from "./displayCounts";
import { clearPixiContainer } from "./pixiCleanup";

type AtlasCanvasProps = {
  level: AtlasLevel;
  overviewRegions: AtlasRegion[];
  overviewEdges: AtlasEdge[];
  focusRegion: AtlasRegion | null;
  subregions: AtlasRegion[];
  evidenceItems: AtlasItem[];
  filteringActive: boolean;
  stageNotice: {
    title: string;
    detail: string;
  } | null;
  selectedRegionKey: string | null;
  selectedSubregionKey: string | null;
  selectedItemId: number | null;
  onSelectRegion: (regionKey: string) => void;
  onDrillRegion: (regionKey: string) => void;
  onSelectSubregion: (subregionKey: string) => void;
  onDrillSubregion: (subregionKey: string) => void;
  onSelectItem: (sourceItemId: number) => void;
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

type PixiModule = typeof import("pixi.js");
type PixiApplication = import("pixi.js").Application;
type PixiPointerEvent = import("pixi.js").FederatedPointerEvent;

type AtlasHoverCard = {
  eyebrow: string;
  title: string;
  lines: string[];
  x: number;
  y: number;
};

const REGION_PALETTE = [
  { fill: 0xd8d0b7, stroke: 0x7b6a53, label: 0x152534 },
  { fill: 0xc0d6cb, stroke: 0x3f5f63, label: 0x17363b },
  { fill: 0xe3c99f, stroke: 0x8d5f35, label: 0x3f2817 },
  { fill: 0xd6c5d7, stroke: 0x69506b, label: 0x2e2433 },
  { fill: 0xc7d3e6, stroke: 0x48607f, label: 0x12243c },
];

const LABEL_STYLE_OPTIONS = {
  fontFamily: '"Iowan Old Style", "Palatino Linotype", serif',
  fill: 0x142534,
  fontSize: 18,
  fontWeight: "600",
} as const;

const SECONDARY_LABEL_STYLE_OPTIONS = {
  fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif',
  fill: 0x34505d,
  fontSize: 12,
  fontWeight: "500",
} as const;

export function AtlasCanvas({
  level,
  overviewRegions,
  overviewEdges,
  focusRegion,
  subregions,
  evidenceItems,
  filteringActive,
  stageNotice,
  selectedRegionKey,
  selectedSubregionKey,
  selectedItemId,
  onSelectRegion,
  onDrillRegion,
  onSelectSubregion,
  onDrillSubregion,
  onSelectItem,
}: AtlasCanvasProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const appRef = useRef<PixiApplication | null>(null);
  const pixiRef = useRef<PixiModule | null>(null);
  const lastTapRef = useRef<{ key: string; at: number }>({ key: "", at: 0 });
  const [hoverCard, setHoverCard] = useState<AtlasHoverCard | null>(null);
  const pixiEnabled = canUsePixi();

  const scene = useMemo(
    () => ({
      level,
      regions: level === "overview" ? overviewRegions : subregions,
      edges: level === "overview" ? overviewEdges : buildSubregionEdges(subregions),
      evidenceItems,
      filteringActive,
      selectedRegionKey,
      selectedSubregionKey,
      selectedItemId,
      focusRegion,
    }),
    [
      evidenceItems,
      filteringActive,
      focusRegion,
      level,
      overviewEdges,
      overviewRegions,
      selectedItemId,
      selectedRegionKey,
      selectedSubregionKey,
      subregions,
    ],
  );

  useEffect(() => {
    if (!pixiEnabled || hostRef.current === null) {
      return undefined;
    }

    let cancelled = false;
    const host = hostRef.current;

    const setup = async () => {
      const pixi = await import("pixi.js");
      const app = new pixi.Application();
      await app.init({
        antialias: true,
        backgroundAlpha: 0,
        resizeTo: host,
      });

      if (cancelled) {
        app.destroy();
        return;
      }

      host.replaceChildren(app.canvas);
      pixiRef.current = pixi;
      appRef.current = app;
      const handleLeave = () => {
        setHoverCard(null);
      };
      app.canvas.addEventListener("pointerleave", handleLeave);
      drawScene(app, scene, {
        lastTapRef,
        onSelectRegion,
        onDrillRegion,
        onSelectSubregion,
        onDrillSubregion,
        onSelectItem,
        onHoverChange: setHoverCard,
      }, pixi);

      if (cancelled) {
        app.canvas.removeEventListener("pointerleave", handleLeave);
      }
    };

    void setup();

    return () => {
      cancelled = true;
      host.replaceChildren();
      setHoverCard(null);
      appRef.current?.destroy({ removeView: true }, { children: true });
      appRef.current = null;
      pixiRef.current = null;
    };
  }, [pixiEnabled]);

  useEffect(() => {
    if (!pixiEnabled || appRef.current === null || pixiRef.current === null) {
      return;
    }

    drawScene(appRef.current, scene, {
      lastTapRef,
      onSelectRegion,
      onDrillRegion,
      onSelectSubregion,
      onDrillSubregion,
      onSelectItem,
      onHoverChange: setHoverCard,
    }, pixiRef.current);
  }, [onDrillRegion, onDrillSubregion, onSelectItem, onSelectRegion, onSelectSubregion, pixiEnabled, scene]);

  return (
    <section className="atlas-stage">
      <div className="atlas-stage__frame">
        <div className="atlas-stage__compass" aria-hidden="true">
          <span>N</span>
        </div>
        <div ref={hostRef} className="atlas-stage__viewport">
          {!pixiEnabled ? (
            <div className="atlas-stage__fallback">
              <p>Canvas preview unavailable in this environment.</p>
            </div>
          ) : null}
        </div>
        {stageNotice !== null ? (
          <div className="atlas-stage__notice" role="status" aria-live="polite">
            <strong>{stageNotice.title}</strong>
            <p>{stageNotice.detail}</p>
          </div>
        ) : null}
        {hoverCard !== null ? (
          <div
            className="atlas-stage__hover-card"
            style={{ left: `${hoverCard.x}px`, top: `${hoverCard.y}px` }}
          >
            <span>{hoverCard.eyebrow}</span>
            <strong>{hoverCard.title}</strong>
            {hoverCard.lines.map((line) => (
              <p key={line}>{line}</p>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function drawScene(
  app: PixiApplication,
  scene: SceneModel,
  handlers: {
    lastTapRef: MutableRefObject<{ key: string; at: number }>;
    onSelectRegion: (regionKey: string) => void;
    onDrillRegion: (regionKey: string) => void;
    onSelectSubregion: (subregionKey: string) => void;
    onDrillSubregion: (subregionKey: string) => void;
    onSelectItem: (sourceItemId: number) => void;
    onHoverChange: (hoverCard: AtlasHoverCard | null) => void;
  },
  pixi: PixiModule,
) {
  const { Container, Graphics, Text, TextStyle } = pixi;
  const stage = app.stage;
  clearPixiContainer(stage);
  const secondaryLabelStyle = new TextStyle(SECONDARY_LABEL_STYLE_OPTIONS);

  const width = app.renderer.width || 800;
  const height = app.renderer.height || 560;
  const background = new Graphics();
  background.beginFill(0xf5efdf, 0.94);
  background.drawRoundedRect(0, 0, width, height, 28);
  background.endFill();
  stage.addChild(background);

  const contourLayer = new Graphics();
  contourLayer.lineStyle(1, 0xd5cab3, 0.42);
  for (let index = 0; index < 7; index += 1) {
    const y = 54 + index * 72;
    contourLayer.moveTo(28, y);
    contourLayer.bezierCurveTo(width * 0.28, y - 18, width * 0.68, y + 18, width - 28, y - 4);
  }
  stage.addChild(contourLayer);

  const bounds = sceneBounds(scene);
  const transform = createTransform(bounds, width, height, 56);
  const overlayScale = scaleLinear()
    .domain([0, atlasRegionDisplayDomainMax(scene.regions)])
    .range([0.32, 0.84]);
  const itemScale = scaleLinear()
    .domain([0, maxBridgeScore(scene.evidenceItems)])
    .range([4, 9]);

  const mapLayer = new Container();
  stage.addChild(mapLayer);

  for (const edge of scene.edges) {
    const sourceRegion = scene.regions.find((region) => region.region_key === edge.source_region_key);
    const targetRegion = scene.regions.find((region) => region.region_key === edge.target_region_key);
    if (sourceRegion === undefined || targetRegion === undefined) {
      continue;
    }

    const source = transform(sourceRegion.x, sourceRegion.y);
    const target = transform(targetRegion.x, targetRegion.y);
    const dimEdge =
      scene.filteringActive &&
      (atlasRegionDisplayCount(sourceRegion) === 0 || atlasRegionDisplayCount(targetRegion) === 0);
    const bridge = new Graphics();
    bridge.lineStyle(
      dimEdge ? 1 : 1 + edge.weight * 2,
      0x697a80,
      dimEdge ? 0.08 : 0.25 + edge.weight * 0.25,
    );
    bridge.moveTo(source.x, source.y);
    bridge.bezierCurveTo(
      source.x + (target.x - source.x) * 0.25,
      source.y - 26,
      source.x + (target.x - source.x) * 0.75,
      target.y + 26,
      target.x,
      target.y,
    );
    mapLayer.addChild(bridge);
  }

  scene.regions.forEach((region, index) => {
    const palette = REGION_PALETTE[hashKey(region.region_key) % REGION_PALETTE.length];
    const isSelected =
      scene.level === "overview"
        ? scene.selectedRegionKey === region.region_key
        : scene.selectedSubregionKey === region.region_key;
    const matchCount = atlasRegionDisplayCount(region);
    const isDimmed = scene.filteringActive && matchCount === 0 && !isSelected;
    const alpha = isDimmed ? 0.14 : Math.max(overlayScale(matchCount), isSelected ? 0.36 : 0.2);
    const graphics = new Graphics();
    graphics.eventMode = "static";
    graphics.cursor = "pointer";

    const rings = regionRings(region);
    if (rings.length > 0) {
      graphics.lineStyle(isSelected ? 4 : 2, palette.stroke, isSelected ? 0.88 : isDimmed ? 0.22 : 0.54);
      graphics.beginFill(palette.fill, alpha);
      for (const ring of rings) {
        const points = ring.flatMap((point) => {
          const projected = transform(point.x, point.y);
          return [projected.x, projected.y];
        });
        graphics.drawPolygon(points);
      }
      graphics.endFill();
    } else {
      const center = transform(region.x, region.y);
      graphics.lineStyle(isSelected ? 4 : 2, palette.stroke, isSelected ? 0.88 : 0.54);
      graphics.beginFill(palette.fill, alpha);
      graphics.drawRoundedRect(center.x - 90, center.y - 54, 180, 108, 24);
      graphics.endFill();
    }

    graphics.on("pointertap", () => {
      if (scene.level === "overview") {
        handleTap(region.region_key, handlers.lastTapRef, () => handlers.onSelectRegion(region.region_key), () =>
          handlers.onDrillRegion(region.region_key),
        );
        return;
      }

      handleTap(
        region.region_key,
        handlers.lastTapRef,
        () => handlers.onSelectSubregion(region.region_key),
        () => handlers.onDrillSubregion(region.region_key),
      );
    });
    graphics.on("pointermove", (event: PixiPointerEvent) =>
      handlers.onHoverChange(buildRegionHoverCard(region, scene.level, event, width, height)),
    );
    graphics.on("pointerout", () => handlers.onHoverChange(null));
    mapLayer.addChild(graphics);

    const labelPoint = transform(region.label_x || region.x, region.label_y || region.y);
    const title = new Text({
      text: region.title,
      style: new TextStyle({
        ...LABEL_STYLE_OPTIONS,
        fill: isSelected ? palette.stroke : palette.label,
        fontSize: isSelected ? 19 : 17,
      }),
    });
    title.anchor.set(0.5);
    title.position.set(labelPoint.x, labelPoint.y - 8);
    title.alpha = isDimmed ? 0.46 : 1;
    mapLayer.addChild(title);

    const countLabel = new Text({
      text: atlasRegionDisplayLabel(region),
      style: secondaryLabelStyle,
    });
    countLabel.anchor.set(0.5);
    countLabel.position.set(labelPoint.x, labelPoint.y + 15 + index * 0);
    countLabel.alpha = isDimmed ? 0.62 : 1;
    mapLayer.addChild(countLabel);
  });

  if (scene.level === "evidence") {
    scene.evidenceItems.forEach((item) => {
      const point = transform(item.x, item.y);
      const radius = itemScale(item.bridge_score || 0);
      const graphic = new Graphics();
      const isSelected = scene.selectedItemId === item.source_item_id;
      const fill = item.is_representative ? 0xa56b2e : item.is_bridge ? 0x265f67 : 0x4d6177;
      graphic.eventMode = "static";
      graphic.cursor = "pointer";
      graphic.lineStyle(isSelected ? 3 : 1.5, 0xf6f0e4, isSelected ? 1 : 0.82);
      graphic.beginFill(fill, item.is_bridge ? 0.9 : 0.82);
      graphic.drawCircle(point.x, point.y, isSelected ? radius + 2.5 : radius);
      graphic.endFill();
      graphic.on("pointertap", () => handlers.onSelectItem(item.source_item_id));
      graphic.on("pointermove", (event: PixiPointerEvent) =>
        handlers.onHoverChange(buildItemHoverCard(item, event, width, height)),
      );
      graphic.on("pointerout", () => handlers.onHoverChange(null));
      mapLayer.addChild(graphic);
    });
  }
}

type SceneModel = {
  level: AtlasLevel;
  regions: AtlasRegion[];
  edges: AtlasEdge[];
  evidenceItems: AtlasItem[];
  filteringActive: boolean;
  selectedRegionKey: string | null;
  selectedSubregionKey: string | null;
  selectedItemId: number | null;
  focusRegion: AtlasRegion | null;
};

function canUsePixi(): boolean {
  if (import.meta.env.MODE === "test" || typeof document === "undefined") {
    return false;
  }

  try {
    const canvas = document.createElement("canvas");
    return typeof canvas.getContext === "function";
  } catch {
    return false;
  }
}

function regionRings(region: AtlasRegion): AtlasPoint[][] {
  const rings = region.region_shape?.rings;
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

function sceneBounds(scene: SceneModel): Bounds {
  const points: AtlasPoint[] = [];

  if (scene.focusRegion !== null) {
    points.push(...regionRings(scene.focusRegion).flat());
  }

  scene.regions.forEach((region) => {
    points.push({ x: region.x, y: region.y });
    points.push({ x: region.label_x, y: region.label_y });
    points.push(...regionRings(region).flat());
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
  const domainWidth = Math.max(bounds.maxX - bounds.minX, 1);
  const domainHeight = Math.max(bounds.maxY - bounds.minY, 1);
  const scale = Math.min(usableWidth / domainWidth, usableHeight / domainHeight);
  const offsetX = (width - domainWidth * scale) / 2;
  const offsetY = (height - domainHeight * scale) / 2;

  return (x: number, y: number) => ({
    x: offsetX + (x - bounds.minX) * scale,
    y: height - (offsetY + (y - bounds.minY) * scale),
  });
}

function maxBridgeScore(items: AtlasItem[]): number {
  return Math.max(1, ...items.map((item) => item.bridge_score || 0));
}

function buildSubregionEdges(regions: AtlasRegion[]): AtlasEdge[] {
  const visibleKeys = new Set(regions.map((region) => region.region_key));
  const edges = new Map<string, AtlasEdge>();

  regions.forEach((region) => {
    region.bridge_neighbors.forEach((neighbor) => {
      if (!visibleKeys.has(neighbor.region_key)) {
        return;
      }

      const edgeKey = [region.region_key, neighbor.region_key].sort().join("::");
      if (!edges.has(edgeKey)) {
        edges.set(edgeKey, {
          source_region_key: region.region_key,
          target_region_key: neighbor.region_key,
          edge_type: neighbor.edge_type,
          weight: neighbor.weight,
        });
      }
    });
  });

  return Array.from(edges.values());
}

function buildRegionHoverCard(
  region: AtlasRegion,
  level: AtlasLevel,
  event: PixiPointerEvent,
  width: number,
  height: number,
): AtlasHoverCard {
  const rangeLabel = formatAtlasDateRange(region.time_start, region.time_end);
  const lines = [
    `${atlasRegionDisplayCount(region)} matching screenshots`,
    region.top_labels.length > 0 ? region.top_labels.slice(0, 2).join(" · ") : "No topical labels",
  ];

  if (rangeLabel !== null) {
    lines.push(rangeLabel);
  }

  return {
    eyebrow: level === "overview" ? "Region" : "Lane",
    title: region.title,
    lines,
    ...hoverPosition(event, width, height),
  };
}

function buildItemHoverCard(
  item: AtlasItem,
  event: PixiPointerEvent,
  width: number,
  height: number,
): AtlasHoverCard {
  const lines = [item.app_hint ?? "Unknown app"];
  if (item.observed_at !== null) {
    lines.push(formatAtlasDateRange(item.observed_at, item.observed_at) ?? "");
  }
  if (item.object_refs.length > 0) {
    lines.push(item.object_refs.slice(0, 2).map(humanizeAtlasValue).join(" · "));
  }

  return {
    eyebrow: item.is_representative ? "Representative" : item.is_bridge ? "Bridge" : "Evidence",
    title: item.semantic_summary ?? `Screenshot #${item.source_item_id}`,
    lines: lines.filter((line) => line.length > 0),
    ...hoverPosition(event, width, height),
  };
}

function hoverPosition(
  event: PixiPointerEvent,
  width: number,
  height: number,
) {
  const cardWidth = 250;
  const cardHeight = 148;
  return {
    x: Math.min(Math.max(event.global.x + 16, 18), Math.max(width - cardWidth - 18, 18)),
    y: Math.min(Math.max(event.global.y + 16, 18), Math.max(height - cardHeight - 18, 18)),
  };
}

function handleTap(
  key: string,
  lastTapRef: MutableRefObject<{ key: string; at: number }>,
  onSelect: () => void,
  onDrill: () => void,
) {
  const now = performance.now();
  if (lastTapRef.current.key === key && now - lastTapRef.current.at < 280) {
    lastTapRef.current = { key: "", at: 0 };
    onDrill();
    return;
  }

  lastTapRef.current = { key, at: now };
  onSelect();
}

function hashKey(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}
