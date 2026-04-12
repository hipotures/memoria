import type { SimilarityGraphResponse } from "./contracts";

type SimilarityClientOptions = {
  baseUrl?: string;
  minClusterSize?: number;
  minEdgeWeight?: number;
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
  } = {},
): string {
  const apiOrigin =
    normalizeSimilarityOrigin(options.baseUrl) ?? normalizeSimilarityOrigin(options.envOrigin);
  const url = new URL(path, apiOrigin ?? "http://memoria.local");

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

function normalizeSimilarityOrigin(origin?: string | null): string | null {
  if (origin === undefined || origin === null) {
    return null;
  }

  const trimmed = origin.trim();
  return trimmed.length > 0 ? trimmed : null;
}
