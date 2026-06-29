import { useEffect, useMemo, useRef, useState } from "react";

import { CollisionFilterExtension } from "@deck.gl/extensions";
import { OrthographicView } from "@deck.gl/core";
import { LineLayer, PolygonLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import DeckGL from "@deck.gl/react";

import type { AtlasEdge, AtlasItem, AtlasOverviewPoint, AtlasRegion } from "../api/contracts";
import { formatAtlasDateRange, humanizeAtlasValue } from "../lib/atlasPresentation";
import type { AtlasLevel } from "../state/atlasReducer";
import {
  buildDeckScene,
  type DeckItemDatum,
  type DeckLabelDatum,
  type DeckOverviewPointDatum,
  type DeckPolygonDatum,
  type DeckRegionMarkerDatum,
} from "./deckScene";

type AtlasCanvasProps = {
  level: AtlasLevel;
  overviewRegions: AtlasRegion[];
  overviewPoints: AtlasOverviewPoint[];
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

type AtlasHoverCard = {
  eyebrow: string;
  title: string;
  lines: string[];
  x: number;
  y: number;
};

type Viewport = {
  width: number;
  height: number;
};

type PolygonRecord = DeckPolygonDatum & {
  polygon: number[][];
};

const VIEW = new OrthographicView({ id: "atlas" });

export function AtlasCanvas({
  level,
  overviewRegions,
  overviewPoints,
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
  const [viewport, setViewport] = useState<Viewport>({ width: 960, height: 720 });
  const [hoverCard, setHoverCard] = useState<AtlasHoverCard | null>(null);
  const deckEnabled = canUseDeck();

  useEffect(() => {
    if (!deckEnabled || hostRef.current === null) {
      return undefined;
    }

    const host = hostRef.current;
    const updateViewport = () => {
      setViewport({
        width: host.clientWidth || 800,
        height: host.clientHeight || 560,
      });
    };

    updateViewport();

    const observer = new ResizeObserver(updateViewport);
    observer.observe(host);

    return () => observer.disconnect();
  }, [deckEnabled]);

  const scene = useMemo(
    () =>
      buildDeckScene({
        level,
        width: viewport.width,
        height: viewport.height,
        regions: level === "overview" ? overviewRegions : subregions,
        overviewPoints: level === "overview" ? overviewPoints : [],
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
      overviewPoints,
      overviewRegions,
      selectedItemId,
      selectedRegionKey,
      selectedSubregionKey,
      subregions,
      viewport.height,
      viewport.width,
    ],
  );

  const layers = useMemo(() => {
    if (scene === null) {
      return [];
    }

    const polygonData: PolygonRecord[] = scene.regions.flatMap((region) =>
      region.polygons.map((polygon, index) => ({
        ...region,
        key: `${region.key}:${index}`,
        polygon,
      })),
    );
    const backdropData: PolygonRecord[] =
      scene.focusBackdrop === null
        ? []
        : scene.focusBackdrop.polygons.map((polygon, index) => ({
            ...scene.focusBackdrop!,
            key: `${scene.focusBackdrop!.key}:${index}`,
            polygon,
          }));

    return [
      new PolygonLayer<PolygonRecord>({
        id: "atlas-focus-backdrop",
        data: backdropData,
        pickable: false,
        stroked: true,
        filled: true,
        getPolygon: (datum) => datum.polygon,
        getFillColor: (datum) => datum.fillColor,
        getLineColor: (datum) => datum.lineColor,
        getLineWidth: (datum) => datum.lineWidth,
        lineWidthUnits: "pixels",
      }),
      new LineLayer({
        id: "atlas-edges",
        data: scene.edges,
        pickable: false,
        getSourcePosition: (datum: { source: [number, number] }) => datum.source,
        getTargetPosition: (datum: { target: [number, number] }) => datum.target,
        getColor: (datum: { color: [number, number, number, number] }) => datum.color,
        getWidth: (datum: { width: number }) => datum.width,
        widthUnits: "pixels",
      }),
      new ScatterplotLayer<DeckOverviewPointDatum>({
        id: "atlas-overview-points",
        data: scene.overviewPoints,
        visible: level === "overview",
        pickable: true,
        stroked: true,
        filled: true,
        radiusUnits: "pixels",
        getPosition: (datum) => datum.position,
        getRadius: (datum) => datum.radius,
        getFillColor: (datum) => datum.fillColor,
        getLineColor: (datum) => datum.lineColor,
        getLineWidth: (datum) => datum.lineWidth,
        onHover: ({ object, x, y }) => {
          if (object === undefined) {
            setHoverCard(null);
            return;
          }
          const region = scene.regions.find((candidate) => candidate.regionKey === object.regionKey);
          if (region === undefined) {
            return;
          }
          setHoverCard(
            buildOverviewPointHoverCard(object, region, x, y, viewport.width, viewport.height),
          );
        },
        onClick: ({ object }) => {
          if (object === undefined) {
            return;
          }
          onSelectRegion(object.regionKey);
        },
      }),
      new ScatterplotLayer<DeckRegionMarkerDatum>({
        id: "atlas-region-markers",
        data: scene.markers,
        visible: level !== "overview",
        pickable: true,
        stroked: true,
        filled: true,
        radiusUnits: "pixels",
        getPosition: (datum) => datum.position,
        getRadius: (datum) => datum.radius,
        getFillColor: (datum) => datum.fillColor,
        getLineColor: (datum) => datum.lineColor,
        getLineWidth: (datum) => datum.lineWidth,
        onHover: ({ object, x, y }) => {
          if (object === undefined) {
            setHoverCard(null);
            return;
          }
          const region = scene.regions.find((candidate) => candidate.regionKey === object.regionKey);
          if (region === undefined) {
            return;
          }
          setHoverCard(buildRegionHoverCard(region, level, x, y, viewport.width, viewport.height));
        },
        onClick: ({ object }) => {
          if (object === undefined || !object.selectable) {
            return;
          }
          if (level === "overview") {
            onSelectRegion(object.regionKey);
            return;
          }
          onSelectSubregion(object.regionKey);
        },
      }),
      new PolygonLayer<PolygonRecord>({
        id: "atlas-regions",
        data: polygonData,
        pickable: true,
        stroked: true,
        filled: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 28],
        getPolygon: (datum) => datum.polygon,
        getFillColor: (datum) => datum.fillColor,
        getLineColor: (datum) => datum.lineColor,
        getLineWidth: (datum) => datum.lineWidth,
        lineWidthUnits: "pixels",
        onHover: ({ object, x, y }) => {
          if (object === undefined) {
            setHoverCard(null);
            return;
          }
          setHoverCard(buildRegionHoverCard(object, level, x, y, viewport.width, viewport.height));
        },
        onClick: ({ object }) => {
          if (object === undefined || !object.selectable) {
            return;
          }
          if (level === "overview") {
            onSelectRegion(object.regionKey);
            return;
          }
          onSelectSubregion(object.regionKey);
        },
      }),
      new TextLayer<DeckLabelDatum>({
        id: "atlas-labels",
        data: scene.labels,
        pickable: false,
        characterSet: "auto",
        getPosition: (datum) => datum.position,
        getText: (datum) => datum.text,
        getColor: (datum) => datum.color,
        getSize: (datum) => datum.size,
        getTextAnchor: "middle",
        getAlignmentBaseline: "center",
        getFontFamily: (datum) =>
          datum.bold ? '"Iowan Old Style", "Palatino Linotype", serif' : '"IBM Plex Sans", "Segoe UI", sans-serif',
        getFontWeight: (datum) => (datum.bold ? 700 : 500),
        background: false,
        extensions: [new CollisionFilterExtension()],
        collisionEnabled: true,
        getCollisionPriority: (datum) => (datum.bold ? 2 : 1),
      }),
      new ScatterplotLayer<DeckItemDatum>({
        id: "atlas-items",
        data: scene.items,
        visible: level === "evidence",
        pickable: true,
        stroked: true,
        filled: true,
        radiusUnits: "pixels",
        getPosition: (datum) => datum.position,
        getRadius: (datum) => datum.radius,
        getFillColor: (datum) => datum.fillColor,
        getLineColor: (datum) => datum.lineColor,
        getLineWidth: (datum) => datum.lineWidth,
        onHover: ({ object, x, y }) => {
          if (object === undefined) {
            setHoverCard(null);
            return;
          }
          setHoverCard(buildItemHoverCard(object.item, x, y, viewport.width, viewport.height));
        },
        onClick: ({ object }) => {
          if (object !== undefined) {
            onSelectItem(object.item.source_item_id);
          }
        },
      }),
    ];
  }, [
    level,
    onSelectItem,
    onSelectRegion,
    onSelectSubregion,
    scene,
    viewport.height,
    viewport.width,
  ]);

  return (
    <section className="atlas-stage">
      <div className="atlas-stage__frame">
        <div ref={hostRef} className="atlas-stage__viewport">
          {scene === null ? (
            <div className="atlas-stage__fallback">
              <p>Canvas preview unavailable in this environment.</p>
            </div>
          ) : !deckEnabled ? (
            <AtlasSvgScene
              level={level}
              scene={scene}
              viewport={viewport}
              onSelectRegion={onSelectRegion}
              onSelectSubregion={onSelectSubregion}
              onSelectItem={onSelectItem}
              onHoverChange={setHoverCard}
            />
          ) : (
            <DeckGL
              views={VIEW}
              controller={false}
              layers={layers}
              viewState={{
                target: [viewport.width / 2, viewport.height / 2, 0],
                zoom: 0,
              }}
              style={{ position: "absolute", inset: 0 }}
              onViewStateChange={() => undefined}
            />
          )}
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

function canUseDeck(): boolean {
  if (import.meta.env.MODE === "test" || typeof document === "undefined") {
    return false;
  }

  try {
    const canvas = document.createElement("canvas");
    return canvas.getContext("webgl2") !== null || canvas.getContext("webgl") !== null;
  } catch {
    return false;
  }
}

function AtlasSvgScene({
  level,
  scene,
  viewport,
  onSelectRegion,
  onSelectSubregion,
  onSelectItem,
  onHoverChange,
}: {
  level: AtlasLevel;
  scene: ReturnType<typeof buildDeckScene>;
  viewport: Viewport;
  onSelectRegion: (regionKey: string) => void;
  onSelectSubregion: (subregionKey: string) => void;
  onSelectItem: (sourceItemId: number) => void;
  onHoverChange: (hoverCard: AtlasHoverCard | null) => void;
}) {
  return (
    <svg className="atlas-stage__svg" viewBox={`0 0 ${viewport.width} ${viewport.height}`} role="img" aria-label="Semantic atlas">
      {scene.focusBackdrop !== null
        ? scene.focusBackdrop.polygons.map((polygon, index) => (
            <polygon
              key={`${scene.focusBackdrop!.key}:${index}`}
              points={polygonPoints(polygon)}
              fill={toCssColor(scene.focusBackdrop!.fillColor)}
              stroke={toCssColor(scene.focusBackdrop!.lineColor)}
              strokeWidth={scene.focusBackdrop!.lineWidth}
            />
          ))
        : null}

      {scene.edges.map((edge) => (
        <line
          key={edge.key}
          x1={edge.source[0]}
          y1={edge.source[1]}
          x2={edge.target[0]}
          y2={edge.target[1]}
          stroke={toCssColor(edge.color)}
          strokeWidth={edge.width}
        />
      ))}

      {level === "overview"
        ? scene.overviewPoints.map((point) => (
            <circle
              key={point.key}
              cx={point.position[0]}
              cy={point.position[1]}
              r={point.radius}
              fill={toCssColor(point.fillColor)}
              stroke={toCssColor(point.lineColor)}
              strokeWidth={point.lineWidth}
              data-kind="overview-point"
              data-region-key={point.regionKey}
              style={{ cursor: "pointer" }}
              onMouseMove={(event) => {
                const region = scene.regions.find((candidate) => candidate.regionKey === point.regionKey);
                if (region === undefined) {
                  return;
                }
                onHoverChange(
                  buildOverviewPointHoverCard(
                    point,
                    region,
                    event.nativeEvent.offsetX,
                    event.nativeEvent.offsetY,
                    viewport.width,
                    viewport.height,
                  ),
                );
              }}
              onMouseLeave={() => onHoverChange(null)}
              onClick={() => onSelectRegion(point.regionKey)}
            />
          ))
        : null}

      {level !== "overview" ? scene.markers.map((marker) => {
        const region = scene.regions.find((candidate) => candidate.regionKey === marker.regionKey);
        if (region === undefined) {
          return null;
        }
        return (
          <circle
            key={marker.key}
            cx={marker.position[0]}
            cy={marker.position[1]}
            r={marker.radius}
            fill={toCssColor(marker.fillColor)}
            stroke={toCssColor(marker.lineColor)}
            strokeWidth={marker.lineWidth}
            style={{ cursor: marker.selectable ? "pointer" : "default" }}
            onMouseMove={(event) =>
              onHoverChange(
                buildRegionHoverCard(
                  region,
                  level,
                  event.nativeEvent.offsetX,
                  event.nativeEvent.offsetY,
                  viewport.width,
                  viewport.height,
                ),
              )
            }
            onMouseLeave={() => onHoverChange(null)}
            onClick={() => {
              if (!marker.selectable) {
                return;
              }
              if (level === "overview") {
                onSelectRegion(marker.regionKey);
                return;
              }
              onSelectSubregion(marker.regionKey);
            }}
          />
        );
      }) : null}

      {scene.regions.flatMap((region) =>
        region.polygons.map((polygon, index) => (
          <polygon
            key={`${region.key}:${index}`}
            points={polygonPoints(polygon)}
            fill={toCssColor(region.fillColor)}
            stroke={toCssColor(region.lineColor)}
            strokeWidth={region.lineWidth}
            style={{ cursor: region.selectable ? "pointer" : "default" }}
            onMouseMove={(event) =>
              onHoverChange(
                buildRegionHoverCard(
                  region,
                  level,
                  event.nativeEvent.offsetX,
                  event.nativeEvent.offsetY,
                  viewport.width,
                  viewport.height,
                ),
              )
            }
            onMouseLeave={() => onHoverChange(null)}
            onClick={() => {
              if (!region.selectable) {
                return;
              }
              if (level === "overview") {
                onSelectRegion(region.regionKey);
                return;
              }
              onSelectSubregion(region.regionKey);
            }}
          />
        )),
      )}

      {scene.items.map((item) => (
        <circle
          key={item.key}
          cx={item.position[0]}
          cy={item.position[1]}
          r={item.radius}
          fill={toCssColor(item.fillColor)}
          stroke={toCssColor(item.lineColor)}
          strokeWidth={item.lineWidth}
          style={{ cursor: "pointer" }}
          onMouseMove={(event) =>
            onHoverChange(
              buildItemHoverCard(
                item.item,
                event.nativeEvent.offsetX,
                event.nativeEvent.offsetY,
                viewport.width,
                viewport.height,
              ),
            )
          }
          onMouseLeave={() => onHoverChange(null)}
          onClick={() => onSelectItem(item.item.source_item_id)}
        />
      ))}

      {scene.labels.map((label) => (
        <text
          key={label.key}
          x={label.position[0]}
          y={label.position[1]}
          fill={toCssColor(label.color)}
          fontFamily={label.bold ? '"Iowan Old Style", "Palatino Linotype", serif' : '"IBM Plex Sans", "Segoe UI", sans-serif'}
          fontSize={label.size}
          fontWeight={label.bold ? 700 : 500}
          textAnchor="middle"
          dominantBaseline="middle"
        >
          {label.text}
        </text>
      ))}
    </svg>
  );
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
  region: DeckPolygonDatum,
  level: AtlasLevel,
  x: number,
  y: number,
  width: number,
  height: number,
): AtlasHoverCard {
  return {
    eyebrow: level === "overview" ? "Region" : "Lane",
    title: region.title,
    lines: [],
    ...hoverPosition(x, y, width, height),
  };
}

function buildOverviewPointHoverCard(
  point: DeckOverviewPointDatum,
  region: DeckPolygonDatum,
  x: number,
  y: number,
  width: number,
  height: number,
): AtlasHoverCard {
  const lines = [region.title];
  if (point.appHint !== null) {
    lines.push(point.appHint);
  }
  lines.push("Click to focus region");
  return {
    eyebrow: point.matchesFilters
      ? point.isRepresentative
        ? "Representative screenshot"
        : point.isBridge
          ? "Bridge screenshot"
          : "Screenshot point"
      : "Filtered-out screenshot",
    title: point.isRepresentative
      ? "Representative point"
      : point.isBridge
        ? "Bridge point"
        : `Screenshot #${point.sourceItemId}`,
    lines,
    ...hoverPosition(x, y, width, height),
  };
}

function buildItemHoverCard(
  item: AtlasItem,
  x: number,
  y: number,
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
    ...hoverPosition(x, y, width, height),
  };
}

function hoverPosition(x: number, y: number, width: number, height: number) {
  const cardWidth = 250;
  const cardHeight = 148;
  return {
    x: Math.min(Math.max(x + 16, 18), Math.max(width - cardWidth - 18, 18)),
    y: Math.min(Math.max(y + 16, 18), Math.max(height - cardHeight - 18, 18)),
  };
}

function polygonPoints(polygon: number[][]): string {
  return polygon.map(([x, y]) => `${x},${y}`).join(" ");
}

function toCssColor([red, green, blue, alpha]: [number, number, number, number]) {
  return `rgba(${red}, ${green}, ${blue}, ${(alpha / 255).toFixed(3)})`;
}
