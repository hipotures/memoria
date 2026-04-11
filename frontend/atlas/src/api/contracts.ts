export type ISODateTimeString = string;

export type AtlasFilters = {
  connector_instance_id?: string | null;
  app_hint?: string | null;
  screen_category?: string | null;
  has_knowledge?: boolean | null;
  observed_from?: ISODateTimeString | null;
  observed_to?: ISODateTimeString | null;
};

export type AtlasRun = {
  atlas_run_id: number;
  atlas_key: string;
  status: string;
  source_count: number;
  source_snapshot_id: string | null;
  corpus_hash: string | null;
  embedding_type: string;
  embedding_model: string;
  embedding_version: string;
  clustering_method: string;
  clustering_params: Record<string, unknown>;
  random_seed: number;
  layout_version: string;
  generated_at: ISODateTimeString;
  completed_at: ISODateTimeString | null;
  published_at: ISODateTimeString | null;
};

export type AtlasOverlay = {
  match_count: number;
};

export type AtlasRepresentativeRef = {
  rank: number;
  source_item_id: number;
};

export type AtlasBridgeNeighbor = {
  edge_type: string;
  region_key: string;
  weight: number;
};

export type AtlasRegion = {
  atlas_run_id: number;
  region_key: string;
  parent_region_key: string | null;
  level: number;
  title: string;
  x: number;
  y: number;
  label_x: number;
  label_y: number;
  region_shape: Record<string, unknown>;
  item_count: number;
  top_labels: string[];
  top_apps: string[];
  top_people: string[];
  top_entities: string[];
  time_start: ISODateTimeString | null;
  time_end: ISODateTimeString | null;
  representatives: AtlasRepresentativeRef[];
  bridge_neighbors: AtlasBridgeNeighbor[];
  cohesion_score: number;
  overlay: AtlasOverlay;
};

export type AtlasEdge = {
  source_region_key: string;
  target_region_key: string;
  weight: number;
  edge_type: string;
};

export type AtlasItem = {
  source_item_id: number;
  region_key: string;
  subregion_key: string | null;
  x: number;
  y: number;
  semantic_summary: string | null;
  app_hint: string | null;
  observed_at: ISODateTimeString | null;
  object_refs: string[];
  is_representative: boolean;
  representative_rank: number | null;
  is_bridge: boolean;
  bridge_type: string | null;
  secondary_region_key: string | null;
  bridge_score: number;
  screenshot_detail_url: string | null;
};

export type AtlasItemPage = {
  items: AtlasItem[];
  limit: number;
  offset: number;
  total: number;
};

export type AtlasEvidenceSectionTotals = {
  representatives: number;
  bridges: number;
  long_tail: number;
};

export type AtlasOverviewResponse = {
  atlas_run: AtlasRun | null;
  regions: AtlasRegion[];
  edges: AtlasEdge[];
  active_filters: AtlasFilters;
};

export type AtlasRegionDetailResponse = {
  atlas_run: AtlasRun;
  region: AtlasRegion;
  subregions: AtlasRegion[];
  representatives: AtlasItem[];
  active_filters: AtlasFilters;
};

export type AtlasEvidenceSliceResponse = {
  atlas_run: AtlasRun;
  region_key: string;
  subregion_key: string | null;
  sort: string;
  representatives: AtlasItem[];
  bridges: AtlasItem[];
  long_tail_page: AtlasItemPage;
  section_totals: AtlasEvidenceSectionTotals;
  active_filters: AtlasFilters;
};

export type AtlasEvidenceQuery = AtlasFilters & {
  regionKey: string;
  subregionKey?: string | null;
  sort?: string;
  limit?: number;
  offset?: number;
};
