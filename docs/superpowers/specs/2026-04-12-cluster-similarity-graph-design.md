# Cluster Similarity Graph Design

Date: 2026-04-12
Status: Proposed
Owner: Codex

## Goal

Add a separate `/similarity` explorer that renders a Plotly-based cluster similarity network over Memoria screenshot data.

This view is intentionally separate from `/atlas`.

- `/atlas` remains the exploratory atlas/workbench built around region and evidence drill-down.
- `/similarity` becomes a cluster-first network overview with native Plotly navigation:
  zoom, pan, reset axes, hover, legend toggle, and image export.

The target look and interaction model are taken from the local prototype:

- `/home/xai/Downloads/memoria_cluster_similarity_network.html`
- `/home/xai/Downloads/memoria_visualization_recommendations.md`

The final implementation must use Plotly from:

- `https://cdn.plot.ly/plotly-3.5.0.min.js`

## Why This Exists

The current atlas overview solves a different problem than the cluster similarity network.

- The atlas is a spatial workbench intended to support region and evidence drill-down.
- The similarity network is better at showing large cluster families, semantic adjacency, and category balance.

The local prototype already demonstrates that a cluster-first network is a better top-level overview for this question than a screenshot-per-point map.

## Current Context

Current repo state relevant to this work:

- The work is happening in the isolated worktree:
  `/home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart`
- The repo already has atlas read-side services under `src/memoria/atlas/`.
- The repo already serves one separate frontend bundle under `/atlas` from `frontend/atlas`.
- The current atlas frontend is React-based and owns its own API client/types/tests.
- No `similarity` API router or `frontend/similarity` bundle exists yet.
- The local prototype HTML is a standalone Plotly document and currently embeds an older Plotly bundle in the file itself.

Important observation from the prototype and notes:

- the desired graph is cluster-first
- nodes represent screenshot clusters
- edges represent shared topic/task signatures or closely related semantic structure
- labels should be progressive, not global
- Plotly's built-in interactions are part of the desired UX, not incidental behavior

## Product Scope

### In Scope

- A new page at `/similarity`
- A new backend endpoint for graph data
- Plotly 3.5.0 loaded from CDN
- A visual treatment closely inspired by the local HTML prototype
- Native Plotly interactions:
  - zoom
  - pan
  - reset axes
  - autoscale
  - hover
  - legend toggle
  - responsive resize
- Cluster nodes
- Similarity edges
- Progressive labels
- Click-to-highlight behavior for a selected cluster
- Minimal graph controls for overview usability

### Out of Scope for MVP

- Replacing `/atlas`
- Reusing the Pixi/deck renderer for this view
- Screenshot gallery below the graph
- A full right-side dock like `/atlas`
- Separate ego-network pages
- Bidirectional URL sync between `/similarity` and `/atlas`
- New persistence tables just for similarity
- A second standalone clustering pipeline

## Chosen Approach

Chosen approach: hybrid Plotly shell.

Meaning:

- the final page is a new application page with its own shell
- Plotly remains the renderer
- the local prototype informs the visual design and trace structure
- the data comes from Memoria API, not from static arrays embedded in HTML

This keeps the desired Plotly behavior while avoiding a brittle one-off transplant of a static prototype.

## UX Model

`/similarity` is a graph-first overview page.

Primary questions it answers:

- what large screenshot cluster families exist
- which clusters sit near each other semantically
- which categories dominate the corpus
- which cluster is worth opening next

### Layout

MVP page structure:

- top: compact header with page title and one-line explanatory subtitle
- under header: a small controls row
- main area: one large Plotly network graph

The page should feel lighter than `/atlas`. It is an overview explorer, not a workbench.

### Interaction

Hover on node:

- cluster title
- item count
- dominant screen category
- top labels
- top apps

Click on node:

- marks the node as selected
- strengthens the selected node visually
- highlights its local neighborhood
- reveals the selected cluster label if labels are otherwise hidden

Legend:

- categories are grouped by dominant screen category
- clicking legend items uses Plotly's built-in show/hide behavior

Labels:

- no full global label dump
- labels shown by default only for the strongest clusters
- selected cluster label is always shown
- hover remains available for the rest

### Controls

Minimal MVP controls:

- `Min cluster size`
- `Min edge weight`
- `Show labels`

These controls operate at the view level only. They do not re-cluster data live in the browser.

## Data Model

The frontend should not reconstruct graph semantics from raw atlas tables. Backend returns a graph-ready view.

### SimilarityGraphRun

- `atlas_run_id`
- `atlas_key`
- `generated_at`
- `source_count`

This is enough for MVP page metadata and debugging.

### SimilarityGraphNode

- `region_key`
- `title`
- `x`
- `y`
- `size`
- `item_count`
- `dominant_screen_category`
- `top_labels`
- `top_apps`
- `top_entities`
- `is_labeled`
- `representative_source_item_ids`

Notes:

- node corresponds to a top-level cluster/region, not a screenshot
- `x` and `y` are graph coordinates already prepared by backend
- `size` is a presentation field so frontend does not have to guess radius scaling

### SimilarityGraphEdge

- `source_region_key`
- `target_region_key`
- `weight`
- `support`
- `reason`

For MVP, `reason` is a compact string such as:

- `shared_topic_task_signature`

This allows future expansion without changing the trace model.

### SimilarityGraphLegendEntry

- `category`
- `color`
- `count`

### SimilarityGraphResponse

- `run`
- `nodes`
- `edges`
- `legend`
- `filters`

## Backend Architecture

### New Service

Add a dedicated read-side module:

- `src/memoria/similarity/service.py`

Responsibility:

- load the latest published atlas run
- derive graph nodes from top-level atlas regions
- derive graph edges from atlas edges
- compute dominant category and trace-ready metadata
- apply request filters and lightweight thresholds
- return a graph-ready response object

This service is read-only and sits next to atlas read-side code, but remains logically separate.

### New API Router

Add:

- `src/memoria/api/similarity.py`

Primary endpoint:

- `GET /similarity/graph`

Optional MVP query params:

- `min_cluster_size`
- `min_edge_weight`
- existing atlas/screenshot filters where already safe to reuse

### Schemas

Add response schemas to:

- `src/memoria/api/schemas.py`

The response should be explicit and frontend-friendly. No frontend-side reconstruction of graph topology should be required.

## Backend Data Source Policy

MVP reuses existing atlas outputs as the source of truth.

- nodes come from top-level atlas regions
- edges come from atlas edges or a thin read-side transformation over them
- no new persistence tables are introduced for MVP

If current atlas edges are too noisy for the visual result, the similarity service may filter or rescale them at read time.

This is allowed:

- dropping weak edges
- normalizing weights
- capping node count for overview readability

This is not part of MVP:

- recomputing a second clustering system
- adding a new migration just to support `/similarity`

## Frontend Architecture

### New Bundle

Add a separate frontend application:

- `frontend/similarity`

This avoids mixing Plotly graph code into the atlas workbench bundle.

### Shell

The frontend shell should be very small:

- load Plotly 3.5.0 from CDN
- fetch `/similarity/graph`
- map response to Plotly traces and layout
- render lightweight controls above the graph

### Plotly Structure

MVP trace composition:

1. edge trace
   - `mode: "lines"`
   - light low-alpha lines
   - hidden from legend

2. one node trace per dominant screen category
   - gives native Plotly legend grouping
   - node size driven by `size`
   - node color driven by legend entry

3. label trace
   - sparse text only
   - includes default high-priority labels and selected cluster label

4. optional selection highlight trace
   - only when a node is selected

This mirrors the successful structure already present in the local prototype while keeping the implementation understandable.

### Visual Direction

The page should stay close to the prototype:

- dark blue background
- low-alpha edges
- colored nodes by dominant category
- larger nodes for larger clusters
- right-side legend
- restrained text density

It should not inherit the warm light theme currently used by `/atlas`.

## Interaction Details

### Selection

Selection is local to the page.

When a node is clicked:

- selected node gains stronger visual emphasis
- selected node label becomes visible
- only the selected node's strongest neighborhood remains emphasized
- the rest of the graph stays visible but quieter

Selection does not need to navigate away from `/similarity` in MVP.

### Hover

Hover is the primary inspection mechanism for non-labeled nodes.

Hover payload should be concise and useful. No raw IDs unless needed for debugging.

### Controls Behavior

- `Min cluster size` filters out nodes below threshold
- `Min edge weight` filters weak edges
- `Show labels` toggles the sparse label layer

These should trigger a new fetch when server-side filtering is involved, rather than large in-browser recomputation.

## Error Handling

If graph data fails to load:

- show a compact inline error state
- keep the page shell visible
- offer a retry action

If there is no published atlas run:

- show an empty state explaining that similarity data is unavailable until atlas data exists

The page should not silently render a blank graph.

## Testing Strategy

### Backend

- unit tests for graph transformation logic
- integration tests for `GET /similarity/graph`
- tests for threshold filtering:
  - `min_cluster_size`
  - `min_edge_weight`
- tests for stable schema shape and category legend output

### Frontend

- tests for loading and error states
- tests for correct fetch path and query params
- tests that Plotly trace construction groups nodes by category
- tests for label toggle and selection-driven highlight behavior

### Verification

Minimum verification before claiming completion:

- targeted backend tests for similarity service and API
- frontend tests for the new bundle
- production build for `frontend/similarity`
- live browser smoke on `/similarity`

## Risks And Tradeoffs

### Risk: current atlas edges may not be visually good enough

Mitigation:

- filter and rescale edges in similarity read-side
- cap weak/noisy connections

### Risk: too many labels make the graph unreadable

Mitigation:

- sparse labels only
- selected cluster label always shown
- hover for the rest

### Risk: overcoupling with `/atlas`

Mitigation:

- separate route
- separate frontend bundle
- separate read-side service

## Definition Of Done

The work is done when:

- `/similarity` exists as a separate page
- it uses Plotly 3.5.0 from CDN
- it visually tracks the local prototype closely
- it renders cluster nodes and similarity edges from Memoria API
- hover, click, zoom, pan, reset, legend toggle all work
- labels are progressive rather than global
- `/atlas` remains untouched functionally
- backend and frontend tests pass

