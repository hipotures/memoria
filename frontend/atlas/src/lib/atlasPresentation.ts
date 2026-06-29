import type { AtlasLevel } from "../state/atlasReducer";
import type { AtlasFilters, AtlasRegion } from "../api/contracts";

export type AtlasRegionListSort =
  | "match_count_desc"
  | "item_count_desc"
  | "title_asc"
  | "stable_order";

export type AtlasOverviewScope = "condensed" | "all";
export type AtlasRegionFocusScope = "featured" | "all";

export const DEFAULT_ATLAS_REGION_LIST_SORT: AtlasRegionListSort = "match_count_desc";
export const DEFAULT_ATLAS_OVERVIEW_SCOPE: AtlasOverviewScope = "condensed";
export const DEFAULT_ATLAS_REGION_FOCUS_SCOPE: AtlasRegionFocusScope = "featured";
const FEATURED_SUBREGION_LIMIT = 8;

export function humanizeAtlasValue(value: string): string {
  const withoutPrefix = value.includes(":") ? value.split(":").slice(1).join(":") : value;
  return withoutPrefix.replace(/[-_]+/g, " ").trim();
}

export function titleCaseAtlasValue(value: string): string {
  return humanizeAtlasValue(value).replace(/\b\w/g, (match) => match.toUpperCase());
}

export function resolveFocusPeople(region: AtlasRegion | null): string[] {
  if (region === null) {
    return [];
  }

  const fallbackValues =
    region.top_people.length > 0
      ? region.top_people
      : region.top_entities.length > 0
        ? region.top_entities
        : region.top_labels;

  return fallbackValues.map(humanizeAtlasValue);
}

export function formatAtlasDateRange(
  start: string | null | undefined,
  end: string | null | undefined,
): string | null {
  if (start === null || start === undefined) {
    if (end === null || end === undefined) {
      return null;
    }
    return `Until ${formatAtlasDate(end)}`;
  }

  if (end === null || end === undefined) {
    return `From ${formatAtlasDate(start)}`;
  }

  const startLabel = formatAtlasDate(start);
  const endLabel = formatAtlasDate(end);

  if (startLabel === endLabel) {
    return startLabel;
  }

  return `${startLabel} - ${endLabel}`;
}

export function inputDateFromIso(isoDate: string | null | undefined): string {
  if (isoDate === null || isoDate === undefined) {
    return "";
  }

  const date = new Date(isoDate);
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function toStartOfDayIso(dateValue: string): string {
  const [year, month, day] = dateValue.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day, 0, 0, 0, 0)).toISOString();
}

export function toEndOfDayIso(dateValue: string): string {
  const [year, month, day] = dateValue.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day, 23, 59, 59, 999)).toISOString();
}

export function applyOverlayFilter(
  regions: AtlasRegion[],
  filteringActive: boolean,
  selectedKey: string | null,
): AtlasRegion[] {
  if (!filteringActive) {
    return regions;
  }

  return regions.filter(
    (region) => region.overlay.match_count > 0 || region.region_key === selectedKey,
  );
}

export function regionSetHasMatches(regions: AtlasRegion[]): boolean {
  return regions.some((region) => region.overlay.match_count > 0);
}

export function applyOverviewScope(
  regions: AtlasRegion[],
  scope: AtlasOverviewScope,
  selectedKey: string | null,
): AtlasRegion[] {
  if (scope === "all") {
    return regions;
  }

  return regions.filter(
    (region) => region.overlay.match_count > 1 || region.region_key === selectedKey,
  );
}

export function applyRegionFocusScope(
  regions: AtlasRegion[],
  scope: AtlasRegionFocusScope,
  selectedKey: string | null,
): AtlasRegion[] {
  if (scope === "all" || regions.length <= FEATURED_SUBREGION_LIMIT) {
    return regions;
  }

  const ordered = sortAtlasRegions(regions, "match_count_desc");
  const multiMatch = ordered.filter((region) => region.overlay.match_count > 1);
  const featuredSource = multiMatch.length > 0 ? [...multiMatch] : [];
  if (featuredSource.length < FEATURED_SUBREGION_LIMIT) {
    for (const region of ordered) {
      if (featuredSource.some((candidate) => candidate.region_key === region.region_key)) {
        continue;
      }
      featuredSource.push(region);
      if (featuredSource.length === FEATURED_SUBREGION_LIMIT) {
        break;
      }
    }
  }
  const featuredKeys = new Set(
    (featuredSource.length > 0 ? featuredSource : ordered)
      .slice(0, FEATURED_SUBREGION_LIMIT)
      .map((region) => region.region_key),
  );

  if (selectedKey !== null) {
    featuredKeys.add(selectedKey);
  }

  return ordered.filter((region) => featuredKeys.has(region.region_key));
}

export function resolveCanvasSubregions(
  level: AtlasLevel,
  structuralSubregions: AtlasRegion[],
  visibleSubregions: AtlasRegion[],
): AtlasRegion[] {
  return level === "overview" ? structuralSubregions : visibleSubregions;
}

export function sortAtlasRegions(
  regions: AtlasRegion[],
  sort: AtlasRegionListSort,
): AtlasRegion[] {
  return [...regions].sort((left, right) => compareAtlasRegions(left, right, sort));
}

export function isFocusWindowActive(filters: AtlasFilters, region: AtlasRegion | null): boolean {
  if (region === null) {
    return false;
  }

  const expectedObservedFrom = region.time_start
    ? toStartOfDayIso(inputDateFromIso(region.time_start))
    : null;
  const expectedObservedTo = region.time_end
    ? toEndOfDayIso(inputDateFromIso(region.time_end))
    : null;

  return (
    (filters.observed_from ?? null) === expectedObservedFrom &&
    (filters.observed_to ?? null) === expectedObservedTo
  );
}

function formatAtlasDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "UTC",
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function compareAtlasRegions(
  left: AtlasRegion,
  right: AtlasRegion,
  sort: AtlasRegionListSort,
): number {
  if (sort === "item_count_desc") {
    return (
      right.item_count - left.item_count ||
      right.overlay.match_count - left.overlay.match_count ||
      left.title.localeCompare(right.title) ||
      left.region_key.localeCompare(right.region_key)
    );
  }

  if (sort === "title_asc") {
    return (
      left.title.localeCompare(right.title) ||
      right.overlay.match_count - left.overlay.match_count ||
      right.item_count - left.item_count ||
      left.region_key.localeCompare(right.region_key)
    );
  }

  if (sort === "stable_order") {
    return left.region_key.localeCompare(right.region_key);
  }

  return (
    right.overlay.match_count - left.overlay.match_count ||
    right.item_count - left.item_count ||
    left.title.localeCompare(right.title) ||
    left.region_key.localeCompare(right.region_key)
  );
}
