export type ISODateTimeString = string;

export type SimilarityGraphFilters = {
  connector_instance_id?: string | null;
  min_cluster_size?: number;
  min_edge_weight?: number;
  app_hint?: string | null;
  screen_category?: string | null;
  observed_from?: ISODateTimeString | null;
  observed_to?: ISODateTimeString | null;
  has_knowledge?: boolean | null;
  search_query?: string | null;
};

export type SimilarityGraphRun = {
  atlas_run_id: number;
  atlas_key: string;
  generated_at: ISODateTimeString;
  source_count: number;
};

export type SimilarityGraphNode = {
  region_key: string;
  title: string;
  x: number;
  y: number;
  size: number;
  item_count: number;
  dominant_screen_category: string;
  top_labels: string[];
  top_apps: string[];
  top_entities: string[];
  is_labeled: boolean;
  representative_source_item_ids: number[];
};

export type SimilarityGraphEdge = {
  source_region_key: string;
  target_region_key: string;
  weight: number;
  support: number;
  reason: string;
};

export type SimilarityGraphLegendEntry = {
  category: string;
  color: string;
  count: number;
};

export type SimilarityGraphResponse = {
  run: SimilarityGraphRun | null;
  nodes: SimilarityGraphNode[];
  edges: SimilarityGraphEdge[];
  legend: SimilarityGraphLegendEntry[];
  filters: SimilarityGraphFilters;
};
