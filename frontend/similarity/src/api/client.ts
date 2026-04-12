import type { SimilarityGraphResponse } from "./contracts";

type SimilarityClientOptions = {
  baseUrl?: string;
};

export function fetchSimilarityGraph(
  options?: SimilarityClientOptions,
): Promise<SimilarityGraphResponse> {
  return similarityFetch(
    "/similarity/graph",
    {
      baseUrl: options?.baseUrl,
      envOrigin: import.meta.env.VITE_SIMILARITY_API_ORIGIN,
    },
  );
}

async function similarityFetch(
  path: string,
  options: {
    baseUrl?: string;
    envOrigin?: string | null;
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
  } = {},
): string {
  const apiOrigin =
    normalizeSimilarityOrigin(options.baseUrl) ?? normalizeSimilarityOrigin(options.envOrigin);

  if (apiOrigin === null) {
    return path;
  }

  return new URL(path, apiOrigin).toString();
}

function normalizeSimilarityOrigin(origin?: string | null): string | null {
  if (origin === undefined || origin === null) {
    return null;
  }

  const trimmed = origin.trim();
  return trimmed.length > 0 ? trimmed : null;
}
