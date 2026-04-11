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
  const response = await fetch(
    buildAtlasRequestUrl(path, params, {
      baseUrl: options?.baseUrl,
      envOrigin: import.meta.env.VITE_ATLAS_API_ORIGIN,
    }),
  );

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

type AtlasRequestUrlOptions = {
  baseUrl?: string;
  envOrigin?: string | null;
};

export function buildAtlasRequestUrl(
  path: string,
  params: Record<string, QueryValue>,
  options: AtlasRequestUrlOptions = {},
): string {
  const query = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") {
      continue;
    }

    query.set(key, String(value));
  }

  const queryString = query.toString();
  const requestPath = queryString.length > 0 ? `${path}?${queryString}` : path;
  const apiOrigin = normalizeAtlasOrigin(options.baseUrl) ?? normalizeAtlasOrigin(options.envOrigin);

  if (apiOrigin === null) {
    return requestPath;
  }

  return new URL(requestPath, apiOrigin).toString();
}

function normalizeAtlasOrigin(origin?: string | null): string | null {
  if (origin === undefined || origin === null) {
    return null;
  }

  const trimmed = origin.trim();
  return trimmed.length > 0 ? trimmed : null;
}
