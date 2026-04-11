import type { AtlasFilters, AtlasRegion } from "../api/contracts";

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
