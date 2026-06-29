import type { AtlasRegion } from "../api/contracts";

export function atlasRegionDisplayCount(region: AtlasRegion): number {
  return Math.max(region.overlay.match_count, 0);
}

export function atlasRegionDisplayDomainMax(regions: AtlasRegion[]): number {
  return Math.max(1, ...regions.map((region) => atlasRegionDisplayCount(region)));
}

export function atlasRegionDisplayLabel(region: AtlasRegion): string {
  return `${atlasRegionDisplayCount(region)} items`;
}
