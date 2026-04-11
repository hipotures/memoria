import type {
  AtlasEvidenceQuery,
  AtlasEvidenceSliceResponse,
  AtlasFilters,
  AtlasOverviewResponse,
  AtlasRegionDetailResponse,
} from "./contracts";

type AtlasClientOptions = {
  baseUrl?: string;
};

type QueryValue = string | number | boolean | null | undefined;

export function fetchAtlasOverview(
  filters: AtlasFilters = {},
  options?: AtlasClientOptions,
): Promise<AtlasOverviewResponse> {
  return atlasFetch("/atlas/overview", atlasFilterParams(filters), options);
}

export function fetchAtlasRegionDetail(
  regionKey: string,
  filters: AtlasFilters = {},
  options?: AtlasClientOptions,
): Promise<AtlasRegionDetailResponse> {
  return atlasFetch(
    `/atlas/regions/${encodeURIComponent(regionKey)}`,
    atlasFilterParams(filters),
    options,
  );
}

export function fetchAtlasEvidenceSlice(
  query: AtlasEvidenceQuery,
  options?: AtlasClientOptions,
): Promise<AtlasEvidenceSliceResponse> {
  return atlasFetch(
    "/atlas/evidence",
    {
      region_key: query.regionKey,
      subregion_key: query.subregionKey,
      sort: query.sort ?? "observed_at_desc",
      limit: query.limit ?? 25,
      offset: query.offset ?? 0,
      ...atlasFilterParams(query),
    },
    options,
  );
}

async function atlasFetch<T>(
  path: string,
  params: Record<string, QueryValue>,
  options?: AtlasClientOptions,
): Promise<T> {
  const response = await fetch(buildAtlasUrl(path, params, options));

  if (!response.ok) {
    throw new Error(`Atlas request failed: ${response.status} ${response.statusText}`);
  }

  return (await response.json()) as T;
}

function atlasFilterParams(filters: AtlasFilters): Record<string, QueryValue> {
  return {
    connector_instance_id: filters.connector_instance_id,
    app_hint: filters.app_hint,
    screen_category: filters.screen_category,
    has_knowledge: filters.has_knowledge,
    observed_from: filters.observed_from,
    observed_to: filters.observed_to,
  };
}

function buildAtlasUrl(
  path: string,
  params: Record<string, QueryValue>,
  options?: AtlasClientOptions,
): string {
  const url = new URL(path, resolveBaseUrl(options?.baseUrl));

  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") {
      continue;
    }

    url.searchParams.set(key, String(value));
  }

  return url.toString();
}

function resolveBaseUrl(baseUrl?: string): string {
  if (baseUrl) {
    return baseUrl;
  }

  if (typeof window !== "undefined") {
    return window.location.origin;
  }

  return "http://localhost";
}
