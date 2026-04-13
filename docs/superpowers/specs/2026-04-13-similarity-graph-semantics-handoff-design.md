# Similarity Graph Semantics And Handoff Design

Date: 2026-04-13
Status: Proposed
Owner: Codex
Supersedes in scope: `2026-04-12-cluster-similarity-graph-design.md` for this iteration

## Goal

Refine `/similarity` so it behaves as a truthful, readable region-to-region overview graph instead of a loosely labeled cluster chart.

This iteration fixes four concrete problems:

1. the graph must be named and described according to what it actually shows
2. labels must be readable and must not pretend to be unique identifiers
3. overview must show only the most important labels by default
4. clicking a node must lead to a sensible handoff into existing atlas drill-down

The result remains intentionally narrow:

- `/similarity` = overview + selection + summary + handoff
- `/atlas` = actual drill-down

## Current Context

Current repo state in the active worktree:

- worktree:
  `/home/xai/DEV/memoria/.worktrees/memoria-semantic-atlas-restart`
- similarity backend already exists:
  - `src/memoria/similarity/service.py`
  - `src/memoria/api/similarity.py`
- similarity frontend is expected in the active worktree under:
  - `frontend/similarity`
- the uploaded snapshot explicitly confirms backend routing and frontend bundle path assumptions
  but may not include the full `frontend/similarity` source tree
- atlas projection already persists:
  - `title`
  - `label_x`
  - `label_y`
  - `top_labels_json`
  - `top_apps_json`
  - region geometry and coordinates

Observed issues in current code:

- `src/memoria/atlas/projection.py` still derives region title as `top_labels[0]` or fallback
- region `label_x` and `label_y` are still set directly to `x` and `y`
- `src/memoria/similarity/service.py` still uses `is_labeled` and does not expose render-oriented label metadata
- similarity edges are loaded from `AtlasEdge.edge_type == "semantic_similarity"` but exposed through the misleading string `shared_topic_task_signature`
- frontend similarity still relies on weaker label semantics than it should

## Scope

### In Scope

- improve atlas region titles without schema changes
- compute persisted label anchors that do not sit on top of node centers
- extend similarity graph node semantics for rendering and disambiguation
- expose graph-level metadata describing what the graph is
- keep edges visible under item filters as snapshot edges for visible regions
- add lightweight `/similarity` selection summary and CTA handoff to `/atlas`
- keep labels progressive by priority instead of rendering all labels by default

### Out of Scope

- database migrations
- new persisted columns for display labels or title slugs
- a full details panel inside `/similarity`
- screenshot thumbnails or inline evidence explorer inside `/similarity`
- replacing `/atlas` drill-down
- topic/task graphs
- frontend heuristics that invent missing semantics independently of backend

## Chosen Approach

Chosen approach: Hybrid MVP.

Meaning:

- backend owns non-guessable graph semantics
- frontend renders the graph and interaction state, but does not invent graph meaning
- `/similarity` stays lightweight and hands off to `/atlas` for deeper inspection

Why this approach:

- a frontend-only patch would keep bad semantics in the API
- a fully backend-first cleanup would broaden scope too much for this iteration
- this split fixes the real user-visible problems without turning `/similarity` into a second explorer product

## Architecture And Responsibilities

### `src/memoria/atlas/projection.py`

Role:

- describe an atlas region well enough that downstream consumers can render and name it correctly

Owns:

- better `title`
- persisted `label_x`
- persisted `label_y`
- existing aggregate hints like `top_labels_json` and `top_apps_json`

Does not own:

- graph degree
- label visibility policy for `/similarity`
- graph kind metadata
- edge scope metadata

Rule:

`projection.py` describes the region itself, not the behavior of a specific graph view.

### `src/memoria/similarity/service.py`

Role:

- adapt atlas regions and atlas edges into a graph-ready region similarity response

Owns:

- loading visible nodes
- loading visible snapshot edges
- computing node degree
- building render labels
- computing label priority
- graph metadata such as `graph_kind` and `edge_scope`

Does not own:

- atlas region generation
- browser-side label placement heuristics
- full drill-down payloads

Rule:

`similarity/service.py` must return enough semantics that the frontend does not have to guess what a node means or how to label it.

### Frontend `/similarity`

Role:

- show the region similarity graph
- support selection and emphasis
- show a short summary for the selected region
- hand off to `/atlas`

Owns:

- graph rendering
- filter UI
- label mode UI
- selected state
- summary box
- CTA links

Does not own:

- title disambiguation logic
- degree calculation
- label priority calculation
- semantic interpretation of the graph

Rule:

frontend consumes backend semantics directly and should not try to repair them heuristically.

## Data Contracts

### Atlas Projection Contract

No schema changes in this iteration.

Persisted fields whose quality changes:

- `title`
- `label_x`
- `label_y`
- `top_labels_json`
- `top_apps_json`

### Region Title Requirements

`title` must be short, deterministic, and more informative than `top_labels[0]`.

Add helper responsibilities in `projection.py`:

- `_normalize_title_token(...)`
- `_is_generic_region_label(...)`
- `_build_region_title(...)`

Generic labels should include at least:

- `chrome`
- `x`
- `twitter`
- `tiktok`
- `youtube`
- `instagram`
- `settings`
- `terminal`
- `calendar`

Title-building rules:

1. prefer semantic labels over platform-only labels
2. if only a platform-like label exists, add semantic context
3. keep the output short and stable

Preferred outcomes:

- `chrome · dns management`
- `tiktok · live streaming`

Fallback order:

1. `"{top_app} · {semantic_label}"`
2. `"{label1}, {label2}"`
3. `"{label1}"`
4. `top_app`
5. `fallback_title`

### Label Anchor Requirements

Add `_compute_label_anchor(...)`.

Rules:

- `label_x` and `label_y` must not default to `x` and `y`
- anchor must be computed deterministically from region geometry and atlas context
- no perfect collision solver is required
- the label should be offset away from the node center, not drawn through it

Minimal acceptable behavior:

- compute anchor from region extent or centroid
- offset by region size
- bias direction relative to the overall atlas center

## Similarity Graph Contract

### `SimilarityGraphNode`

Required fields:

- `region_key: str`
- `title: str`
- `label: str`
- `canonical_title: str`
- `duplicate_title_count: int`
- `x: float`
- `y: float`
- `label_x: float`
- `label_y: float`
- `size: float`
- `item_count: int`
- `degree: int`
- `label_priority: float`
- `dominant_screen_category: str`
- `top_labels: list[str]`
- `top_apps: list[str]`
- `top_entities: list[str]`
- `representative_source_item_ids: list[int]`

Rules:

- `title` = atlas region title
- `label` = render label for the graph
- `label_x` and `label_y` come from `AtlasRegion`
- `representative_source_item_ids` must be capped at `8`
- representative IDs must be returned in deterministic atlas order

### `canonical_title`

`canonical_title` is used only for duplicate detection.

Normalization:

- trim
- lowercase
- collapse whitespace
- normalize `-`, `_`, and repeated spaces into a single space

`canonical_title` must not just mirror raw `title`.

### `duplicate_title_count`

Definition:

- number of nodes in the final response `nodes` array that share the same `canonical_title`

This count is response-scoped, not database-scoped.

### `label`

Rules:

- if `title` is unique within the final response, `label = title`
- if `title` is duplicated, backend must disambiguate it

Fallback order:

1. `"{title} · {top_app}"`
2. `"{title} · {item_count}"`
3. `"{title} · {region_key_suffix}"`

Final rule:

- if `duplicate_title_count > 1`, final `label` must be unique within the final response
- if earlier disambiguation steps still collide, `region_key_suffix` becomes mandatory

`region_key_suffix`:

- use the last `6` characters of `region_key`

### `degree`

Definition:

- number of final returned edges touching this node

`degree` is computed from the final `edges` response after filters are applied.

### `label_priority`

Definition:

- deterministic backend heuristic used by frontend default label mode

Formula:

- `label_priority = item_count + 3 * degree`

The frontend must not invent a different ranking formula.

### `SimilarityGraphEdge`

Required fields:

- `source_region_key: str`
- `target_region_key: str`
- `weight: float`
- `support: int`
- `edge_type: str`

Compatibility:

- `reason` may remain temporarily if existing callers still depend on it
- `edge_type` is the field that defines actual semantics

`support`:

- remains a compatibility field in this iteration
- because persisted atlas edge data does not currently store a separate support signal, `support` stays the placeholder value `1`
- no migration is introduced to backfill or persist a real support value in this scope

### `SimilarityGraphResponse`

Required top-level fields:

- `run`
- `nodes`
- `edges`
- `legend`
- `filters`
- `graph_kind: str`
- `edge_scope: str`
- optional `default_label_limit: int`

Required values for this iteration:

- `graph_kind = "region_similarity"`
- `edge_scope = "atlas_snapshot"`

`default_label_limit` behavior:

- backend may return it
- if omitted, frontend uses `20`

### Filters

`filters` must include:

- `min_cluster_size`
- `min_edge_weight`
- `connector_instance_id`
- `app_hint`
- `screen_category`
- `has_knowledge`
- `observed_from`
- `observed_to`
- `search_query`

`label_mode` is frontend state and does not need to round-trip through backend.

### Ordering

Within each node payload:

- `top_labels`
- `top_apps`
- `top_entities`

must be:

- deterministic
- sorted descending by strength or frequency
- tie-broken by text value

This keeps summary boxes stable between reloads.

## Edge Semantics

Current behavior is misleading because edges are loaded from `semantic_similarity` atlas edges but described as `shared_topic_task_signature`.

This iteration fixes that.

Rules:

- similarity edges come from persisted atlas edges with `AtlasEdge.edge_type == "semantic_similarity"`
- response must surface that semantic truth through `edge_type`
- graph-level `edge_scope` must explain that these are snapshot atlas edges

### Edge Behavior Under Filters

Current empty-edge behavior under non-threshold item filters is too confusing.

New rule:

- keep snapshot edges between still-visible regions
- do not return an empty edge set solely because item-level filters are active

This keeps the graph usable and avoids “it broke after filtering” UX.

## Frontend Behavior

`/similarity` remains an overview graph, not a deep explorer.

### Label Modes

Supported label modes:

- `none` = no persistent labels
- `default` = only top `N` labels by `label_priority`
- `all` = all visible node labels
- `selected` = label only for selected node; if nothing is selected, show no persistent labels

No neighbor-specific label mode in this iteration.

### Default Label Behavior

- circles always render
- labels are a separate render layer
- text uses `node.label`
- text position uses `node.label_x` and `node.label_y`
- `default` mode shows only highest-priority labels

### Selection Behavior

Clicking a node must:

1. select that node
2. visually emphasize the selected node
3. emphasize adjacent nodes and edges
4. dim unrelated nodes and edges
5. show a lightweight summary box

### Summary Box

For selected node:

- `label`
- `title`
- `region_key`
- `item_count`
- `dominant_screen_category`
- `degree`
- `top_labels` limited to `3-5`
- `top_apps` limited to `2-3`

CTA:

- `Region details` -> `/atlas/regions/{region_key}`
- `Evidence` -> `/atlas/evidence?region_key={region_key}`

The summary box is lightweight by design. No inline screenshots or nested evidence explorer in this iteration.
The summary box is populated only from the `/similarity/graph` node payload.
`/atlas/regions/{region_key}` and `/atlas/evidence?region_key=...` are opened only through CTA, not eagerly fetched on node selection.

## Implementation Order

### Stage 1: Backend semantics

1. `src/memoria/atlas/projection.py`
2. `src/memoria/similarity/service.py`
3. `src/memoria/api/schemas.py`
4. `src/memoria/api/similarity.py`

Outcome:

- atlas regions get better titles and label anchors
- similarity API exposes stable graph semantics

### Stage 2: Frontend overview

1. update frontend contracts
2. add `labelMode`
3. render circles and separate labels using backend anchors
4. show only priority labels in default mode
5. add selection summary and CTA handoff

Outcome:

- overview becomes readable
- clicking a node yields a clear next step

### Rollout Rule

Stage 1 backend changes must remain additive-compatible until Stage 2 frontend is merged, or backend and frontend must ship atomically in one release.

Practical rule for this iteration:

- keep `reason` temporarily if existing consumers still read it
- add new response fields without removing the old ones during the transition

### Stage 3: Polish

- copy cleanup
- tooltip cleanup
- URL filter persistence only if it stays low-cost and does not expand scope
- highlight tuning

No scope growth beyond this.

## Acceptance Criteria

1. `/similarity` clearly describes a region similarity graph, not a topic/task graph.
2. Atlas region titles are more informative than `top_labels[0]`.
3. Text labels no longer sit on top of node centers.
4. `title` and `label` are distinct concepts in the similarity response.
5. Duplicate raw titles are disambiguated in rendered labels.
6. `degree` is computed from final returned edges.
7. `duplicate_title_count` is computed from final returned nodes after filters.
8. Default overview shows only top labels by backend `label_priority`.
9. `top_labels`, `top_apps`, and `top_entities` remain deterministic across reloads.
10. Clicking a node selects it, highlights its neighborhood, shows a short summary, and provides working links to `/atlas/regions/{region_key}` and `/atlas/evidence?region_key=...`.
11. No migration is introduced for this iteration.

## Definition Of Done

This iteration is done when:

- backend owns graph semantics that frontend previously had to infer
- frontend `/similarity` behaves as overview + selection + handoff
- graph labels are readable, progressive, and not misleading
- filters no longer make the graph appear broken
- the work ships without expanding into a full inline explorer
