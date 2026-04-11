# Memoria: Semantic Atlas Cluster Visualization Design

## Status

- Status: ready for review
- Date: 2026-04-11
- Scope: screenshot cluster atlas, semantic zoom, atlas backend projection, and cluster workbench UX
- Constraint: keep the mental model cluster-first and avoid graph spaghetti

---

## 1. Purpose

The current screenshot semantic map already exposes:

- a cluster overview;
- cluster member listing;
- point drill-down to screenshot detail.

What it does not provide yet is a coherent exploration model for large numbers of clusters. The next iteration should not become a raw graph or a raw point cloud. It should become a **semantic atlas**:

- level 0: a stable map of topic regions;
- level 1: a focused view of adaptive subregions inside one region;
- level 2: evidence-oriented screenshot exploration within the selected subregion or filtered slice.

This design defines both the user experience and the backend projection shape needed to support that atlas.

---

## 2. Design Goals

This design is successful if all of the following are true:

1. The first screen communicates geography of similarity, not a node-link graph.
2. The interaction remains cluster-first; raw screenshot points do not dominate the initial view.
3. A persistent dock supports real work immediately after selection: summary, facets, representatives, bridges, filters, and evidence list.
4. Semantic zoom moves from region -> subregion -> screenshot evidence without changing the user's mental model.
5. Subregions, representatives, bridges, region shapes, and layout are computed by the backend or pipeline, not primarily in the browser.
6. Atlas layout remains stable across rebuilds as the corpus grows.
7. Search and filters are available already at level 0.
8. The frontend stack stays constrained: React + TypeScript shell, PixiJS v8 canvas, TanStack Virtual lists, d3 helper-only.

---

## 3. Explicit Non-Goals

This design does not include:

- a force-directed graph with all edges rendered;
- a raw scatterplot of every screenshot at the initial level;
- a pure hierarchy-first browser as the main landing view;
- a second interaction system built around d3 rendering;
- a final implementation on DataMapPlot or pure SVG as the primary renderer;
- live client-side recomputation of clustering logic as the main source of truth;
- a broad refactor of screenshot ingest, OCR, vision, or absorb pipelines.

`deck.gl` is allowed only as a fallback delivery path if the first working atlas cannot be shipped quickly enough with PixiJS.

---

## 4. Current Context

The repository currently has:

- a FastAPI screenshot product surface;
- a semantic map read path with cluster summaries, cluster items, and per-point detail;
- no dedicated frontend application shell for this atlas yet;
- a simple HTML map page that proves the read path but is not an atlas UX.

This means the new work should be treated as a focused atlas product layered on top of the existing screenshot and semantic map capabilities, not as a replacement for the whole screenshots vertical slice.

---

## 5. Product Direction

The atlas combines two models:

- **A as visual shell**: the user should primarily perceive a geography of similarity;
- **C as work model**: after selection, the user should immediately gain an operational dock for analysis and drill-down.

This creates a hybrid product:

- the left side is an atlas;
- the right side is a workbench.

The atlas should feel like a semantic archipelago, not like a database admin screen and not like a graph debugging tool.

---

## 6. Frontend Stack

The target stack is:

- React + TypeScript for the application shell and state flow;
- PixiJS v8 for the atlas rendering layer;
- TanStack Virtual for evidence and ranking lists in the dock;
- d3 helper-only for scales, geometry helpers, contour generation, and label placement.

Reasons:

- PixiJS gives explicit control over shapes, highlighting, camera motion, hit testing, and layered rendering for a custom atlas;
- TanStack Virtual handles large evidence lists without forcing the canvas layer to own list virtualization concerns;
- d3 remains useful as a math and geometry toolkit but should not become a second renderer or interaction system.

Fallback:

- deck.gl is acceptable if it materially reduces time-to-first-working-atlas, but it is not the preferred end state.

---

## 7. Core UX Model

### 7.1 Shared Rules

These interaction rules apply across all levels:

- `single click` selects;
- explicit actions in the dock or `Enter` perform drill-down;
- `double click` is only an optional desktop shortcut, not the primary path;
- the dock is always present;
- search and filters are available from the start;
- filters dim or narrow results without recomputing the global layout in the browser.

### 7.2 Level 0: Atlas Overview

The first screen shows top-level regions only.

The user sees:

- region positions and relative distances;
- region size by item count;
- sparse bridge hints between nearby or semantically adjacent regions;
- stable labels and lightweight hover summaries.

The user can:

- search globally;
- filter by app, time, people/entities, and topics;
- single-click a region to select it;
- inspect region summary and representative items in the dock;
- explicitly drill into the selected region.

The user should not see:

- a wall of raw screenshot points;
- dense edge spaghetti;
- a hierarchy tree replacing the map.

### 7.3 Level 1: Region Focus

When the user drills into a region, the atlas zooms to that region and reveals adaptive subregions.

The user sees:

- the selected top-level region in focus;
- adaptive subregions inside it;
- sparse local bridge hints between subregions;
- a few representative points for orientation, not a full evidence dump.

The dock shows:

- region summary;
- subregion list;
- top topics;
- app hints;
- top people when available or top entities as fallback;
- time range;
- representatives;
- local filters and sorting controls.

The user can:

- select subregions;
- compare subregions through dock summaries;
- explicitly open evidence for the active subregion;
- navigate via breadcrumbs instead of relying only on canvas clicks.

### 7.4 Level 2: Evidence Focus

The evidence level is where screenshot work happens.

The canvas shows:

- screenshot points for the active subregion or filtered slice;
- highlighted representatives;
- highlighted bridges;
- the selected screenshot point.

The dock shows:

- representatives;
- bridges;
- a virtualized evidence list;
- detail for the selected screenshot;
- a link to the full screenshot detail endpoint.

The default evidence ordering should prioritize understanding first:

1. representatives;
2. bridges;
3. the remainder, typically by `observed_at desc`.

---

## 8. Screen Components

### 8.1 `AtlasCanvas`

Responsibilities:

- render top-level regions, subregions, and screenshot points according to the active level;
- keep camera position and semantic zoom transitions stable;
- render region shapes, labels, and sparse bridge hints;
- expose selection and hover events.

It should not own clustering logic or evidence ranking logic.

### 8.2 `AtlasToolbar`

Responsibilities:

- global search;
- global filters;
- reset view;
- filtered-state controls;
- optional bridge visibility toggle.

This toolbar applies already at level 0 and persists through deeper levels.

### 8.3 `InsightDock`

Responsibilities:

- summary;
- facets;
- representatives;
- bridges;
- local filters;
- drill-down actions;
- evidence detail.

This is not a passive info sidebar. It is the main operational workspace once a region or subregion is selected.

### 8.4 `RegionNavigator`

Responsibilities:

- breadcrumbs;
- explicit drill-down actions;
- subregion list and quick navigation;
- contextual ranking and region switching within the active focus.

### 8.5 `EvidenceList`

Responsibilities:

- present screenshot evidence records at level 2;
- support grouping and sorting by representatives, bridges, recency, app, and topic;
- keep navigation fast and stable through virtualization.

The name intentionally reflects screenshot evidence rather than identity-graph entities.

---

## 9. Semantic Zoom Transitions

### 9.1 Level 0 -> Level 1

Primary flow:

- single-click selects a top-level region;
- the dock updates immediately;
- an explicit dock action or `Enter` drills down into the region.

Behavior:

- the region remains anchored during the transition;
- nearby regions fade but stay legible enough for context;
- the camera animates to the selected region;
- subregions appear progressively rather than replacing the scene abruptly.

### 9.2 Level 1 -> Level 2

Primary flow:

- single-click selects a subregion;
- the dock updates immediately;
- an explicit dock action or `Enter` opens evidence for that subregion.

Behavior:

- the active subregion remains spatially anchored;
- representatives appear before the broader evidence cloud;
- evidence points fade in after the subregion context is established.

### 9.3 Return Navigation

The atlas should preserve spatial memory:

- breadcrumbs allow explicit ascent to parent levels;
- camera memory should restore the prior viewport when stepping back;
- deep links should preserve active region, subregion, selected item, and filters.

---

## 10. Backend Projection Requirement

Atlas logic should be served from a backend read model or pipeline-generated projection, not primarily recomputed in the browser.

The backend is responsible for:

- top-level region layout;
- adaptive subregion layout;
- representatives;
- bridges;
- region shapes;
- stable region identities across rebuilds;
- reproducibility metadata for each atlas run.

The browser is responsible for:

- rendering;
- local interaction;
- camera transitions;
- highlighting and filtering already-projected data;
- virtualized evidence browsing.

---

## 11. Heuristics

### 11.1 Subregions

Subregions are a backend projection inside a selected region.

Rules:

- the target UX is usually `3-8` subregions, but this is not a hard algorithmic rule;
- very small or weakly separated groups should be merged into a stronger neighbor rather than surfaced as noise;
- the number of displayed subregions should adapt to region complexity and corpus shape.

Method:

- form candidate groups from semantic similarity in embedding space;
- choose a cut that balances cohesion and separation;
- label and order resulting groups using metadata such as topics, app hints, people/entities, and time range.

Subregions should remain semantically grounded first and metadata-readable second.

### 11.2 Representatives

Representatives are `exemplars / medoids + metadata quality`.

Rules:

- representative status starts from semantic typicality within the region or subregion;
- metadata quality can reorder strong candidates but should not replace semantic representativeness;
- near-duplicates should be suppressed so the representative set stays informative.

Ranking signals:

- medoid or exemplar score;
- availability and quality of `semantic_summary`;
- availability of `app_hint`;
- availability of `object_refs`;
- linked knowledge or evidence richness;
- diversity penalty against already selected representatives.

### 11.3 Bridges

Bridges are screenshots that sit near more than one semantic neighborhood.

Operational definition:

- every screenshot has a primary region or subregion assignment;
- a screenshot is a bridge when it also has a strong secondary affinity and the margin between primary and secondary affinity is small enough to matter.

Bridge categories:

- `internal_bridge`: between subregions within one region;
- `external_bridge`: between top-level regions.

Bridge records should expose:

- primary region key;
- secondary region key;
- bridge type;
- bridge score.

### 11.4 Region Shapes

The atlas should not assume naive convex hulls.

Use a more general concept:

- `region_shape`

This field may represent:

- a polygon;
- a multipolygon;
- a contour-like simplified outline.

The purpose of the shape is visual comprehension and hit area support, not geometric purity.

### 11.5 Layout Stability

Atlas layout must remain stable across rebuilds.

Rules:

- stable region keys are required;
- new rebuilds should first match new regions to prior regions;
- matched regions inherit prior anchors whenever the match quality is acceptable;
- only genuinely new or heavily changed regions should require significant repositioning;
- filters and search should not recompute region positions in the client.

Matching signals across rebuilds:

- member overlap;
- embedding centroid similarity;
- label similarity.

This stability is a product requirement, not just an implementation nice-to-have.

---

## 12. Atlas Data Model

### 12.1 `AtlasRun`

Represents one reproducible atlas build.

Fields:

- `atlas_key`
- `generated_at`
- `source_count`
- `layout_version`
- `embedding_model`
- `embedding_version`
- `clustering_method`
- `clustering_params`
- `random_seed`
- `source_snapshot_id` or `corpus_hash`

### 12.2 `AtlasRegion`

Represents either a top-level region or a subregion.

Fields:

- `region_key`
- `parent_region_key`
- `level`
- `title`
- `x`
- `y`
- `region_shape`
- `label_anchor`
- `item_count`
- `match_count`
- `top_labels`
- `top_apps`
- `top_people` optional
- `top_entities` fallback
- `time_start`
- `time_end`
- `representatives`
- `bridge_neighbors`
- `cohesion_score`

`level=0` represents a top-level region.
`level=1` represents a subregion.

### 12.3 `AtlasItem`

Represents a screenshot evidence point at level 2.

Fields:

- `source_item_id`
- `region_key`
- `subregion_key`
- `x`
- `y`
- `semantic_summary`
- `app_hint`
- `observed_at`
- `object_refs`
- `is_representative`
- `representative_rank`
- `is_bridge`
- `bridge_type`
- `secondary_region_key`
- `bridge_score`
- `screenshot_detail_url`

### 12.4 `AtlasEdge`

Represents sparse region-to-region adjacency.

Fields:

- `source_region_key`
- `target_region_key`
- `weight`
- `edge_type`

These edges are intentionally sparse. They are neighborhood hints, not a full graph.

---

## 13. API Shapes

The atlas should be exposed through read-only payloads that preserve the same layout while allowing filtering.

### 13.1 `AtlasOverview`

Purpose:

- level 0 atlas view.

Should contain:

- `AtlasRun` metadata;
- top-level `AtlasRegion` records;
- sparse `AtlasEdge` records;
- global filter/facet summaries;
- active filter echo.

### 13.2 `AtlasRegionDetail`

Purpose:

- level 1 region focus.

Should contain:

- `AtlasRun` metadata;
- active parent region;
- child subregions;
- local bridge neighbors;
- representative items;
- dock summary and facet summaries;
- active filter echo.

### 13.3 `AtlasEvidenceSlice`

Purpose:

- level 2 evidence exploration.

Should contain:

- `AtlasRun` metadata;
- active region and subregion keys;
- paginated `AtlasItem` records;
- sort metadata;
- grouping metadata for representatives and bridges;
- active filter echo.

The API should share the same screenshot-oriented filter vocabulary across all atlas levels.

---

## 14. Interaction And State Contract

The browser state model should stay small and explicit:

- current level;
- selected region;
- selected subregion;
- selected item;
- active filters;
- search query;
- current sort mode;
- camera state.

Important rules:

- selection and drill-down are separate actions;
- filter changes should not destroy spatial memory;
- canvas state and dock state should move together;
- deep links should reconstruct atlas state without recomputing clustering in the browser.

---

## 15. Testing And Verification Goals

The design is ready for implementation if it can be verified against the following outcomes:

1. The initial atlas communicates region geography without graph clutter.
2. Search and filters work at level 0 without causing layout drift.
3. Drill-down uses explicit actions rather than relying on double click.
4. Region focus reveals adaptive subregions with stable labels and representative evidence.
5. Evidence focus surfaces representatives and bridges ahead of the long tail.
6. Rebuild-to-rebuild layout remains recognizably stable when the corpus changes incrementally.
7. The frontend renderer consumes backend atlas projections rather than recomputing core atlas structure.

---

## 16. Implementation Boundaries

This spec intentionally describes a bounded first atlas product.

The first implementation should include:

- atlas overview;
- region focus;
- evidence focus;
- persistent dock;
- backend atlas projection;
- stable layout support;
- search and filtering at all levels.

The first implementation should not expand scope into:

- arbitrary graph exploration tooling;
- free-form visual analytics modes;
- client-side reclustering experiments;
- a generic visualization framework for every future memory surface.

The goal is a coherent screenshot semantic atlas, not a visualization platform.
