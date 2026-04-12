import type { SimilarityGraphResponse } from "./contracts";

type SimilarityClientOptions = {
  baseUrl?: string;
  minClusterSize?: number;
  minEdgeWeight?: number;
  currentPath?: string;
};

export function fetchSimilarityGraph(
  options: SimilarityClientOptions = {},
): Promise<SimilarityGraphResponse> {
  return similarityFetch(
    "/similarity/graph",
    {
      baseUrl: options.baseUrl,
      envOrigin: import.meta.env.VITE_SIMILARITY_API_ORIGIN,
      minClusterSize: options.minClusterSize,
      minEdgeWeight: options.minEdgeWeight,
      currentPath: options.currentPath,
    },
  );
}

async function similarityFetch(
  path: string,
  options: {
    baseUrl?: string;
    envOrigin?: string | null;
    minClusterSize?: number;
    minEdgeWeight?: number;
    currentPath?: string;
  },
): Promise<SimilarityGraphResponse> {
  const response = await fetch(buildSimilarityRequestUrl(path, options));

  if (!response.ok) {
    throw new Error(`Similarity request failed: ${response.status} ${response.statusText}`);
  }

  return (await response.json()) as SimilarityGraphResponse;
}

export function buildSimilarityRequestUrl(
  path: string,
  options: {
    baseUrl?: string;
    envOrigin?: string | null;
    minClusterSize?: number;
    minEdgeWeight?: number;
    currentPath?: string;
  } = {},
): string {
  const apiOrigin =
    normalizeSimilarityOrigin(options.baseUrl) ?? normalizeSimilarityOrigin(options.envOrigin);
  const requestPath =
    apiOrigin === null ? resolveSimilarityRequestPath(path, options.currentPath) : path;
  const url = new URL(requestPath, apiOrigin ?? "http://memoria.local");

  if (options.minClusterSize !== undefined) {
    url.searchParams.set("min_cluster_size", String(options.minClusterSize));
  }

  if (options.minEdgeWeight !== undefined) {
    url.searchParams.set("min_edge_weight", String(options.minEdgeWeight));
  }

  if (apiOrigin === null) {
    return `${url.pathname}${url.search}`;
  }

  return url.toString();
}

function resolveSimilarityRequestPath(path: string, currentPath?: string): string {
  const normalizedCurrentPath = normalizeCurrentPath(currentPath);
  const similaritySuffix = path.startsWith("/similarity/") ? path.slice("/similarity/".length) : null;

  if (
    normalizedCurrentPath !== null &&
    similaritySuffix !== null &&
    normalizedCurrentPath.endsWith("/similarity")
  ) {
    return `${normalizedCurrentPath}/${similaritySuffix}`;
  }

  return path;
}

function normalizeSimilarityOrigin(origin?: string | null): string | null {
  if (origin === undefined || origin === null) {
    return null;
  }

  const trimmed = origin.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function normalizeCurrentPath(currentPath?: string): string | null {
  const rawPath = currentPath ?? (typeof window === "undefined" ? null : window.location.pathname);

  if (rawPath === null) {
    return null;
  }

  const trimmed = rawPath.trim();
  if (trimmed.length === 0) {
    return null;
  }

  return trimmed.endsWith("/") ? trimmed.slice(0, -1) : trimmed;
}
